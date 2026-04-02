#!/usr/bin/env python3
"""Lexicon genre cleanup: export + backups, map library genres to a taxonomy, bulk-write native genre.

Phases
------
1. ``export`` — Run ``lexicon list-tracks --json``, write ``export.json`` plus timestamped backups
   ``genre_backup_bulk_update_YYYYMMDDTHHMMSS.json`` and ``tags_backup_bulk_update_YYYYMMDDTHHMMSS.json``
   from the same fetch.

2. ``map-genres`` — Read export + ``.notes/genres.txt`` + ``genre_aliases.json``; write inventory,
   ``taxonomy_paths.json``, ``needs_review.md`` (+ optional ``needs_review.json``). Does **not**
   write backups.

3. ``write-genres`` — Emit bulk-update JSON (``id`` + ``genre``) only for **definitive** mappings.
   Ambiguous or unknown source genres are omitted (tracks unchanged). Skips tracks whose genre
   already matches a canonical taxonomy path.

4. ``review-genres`` — Interactive TUI (InquirerPy) to resolve review queue items and update
   ``genre_aliases.json`` without hand-editing JSON.

Taxonomy: indentation tree in ``.notes/genres.txt`` (2 spaces per level). Aliases: ``exact``
(normalized full string → canonical `` > `` path) and ``aliases`` (token → replacement segment
or path).

Usage:
  uv run python scripts/genre_taxonomy/genre_cleanup.py export --out-dir scripts/genre_taxonomy/output
  uv run python scripts/genre_taxonomy/genre_cleanup.py map-genres --export scripts/genre_taxonomy/output/export.json
  uv run python scripts/genre_taxonomy/genre_cleanup.py write-genres --export scripts/genre_taxonomy/output/export.json
  uv run python scripts/genre_taxonomy/genre_cleanup.py dry-run --batch scripts/genre_taxonomy/output/bulk_update_genres.json
  uv run python scripts/genre_taxonomy/genre_cleanup.py review-genres --export scripts/genre_taxonomy/output/export.json
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import typer
from InquirerPy import inquirer
from InquirerPy.base.control import Choice

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TAXONOMY = SCRIPT_DIR.parent.parent / ".notes" / "genres.txt"
DEFAULT_ALIASES = SCRIPT_DIR / "genre_aliases.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
REPO_ROOT = SCRIPT_DIR.parent.parent
INDENT_SPACES_PER_LEVEL = 2

app = typer.Typer(help="Lexicon genre taxonomy cleanup helper")

# ---------------------------------------------------------------------------
# JSON export slice
# ---------------------------------------------------------------------------


def _strip_json_prefix(raw: str) -> str:
    i = raw.find("[")
    if i < 0:
        raise ValueError("No JSON array found in input")
    j = raw.rfind("]")
    if j < i:
        raise ValueError("Unclosed JSON array")
    return raw[i : j + 1]


def _fetch_tracks_json(repo_root: Path) -> list[dict[str, Any]]:
    cmd = [
        "uv",
        "run",
        "lexicon",
        "list-tracks",
        "--json",
        "-f",
        "title",
        "-f",
        "artist",
        "-f",
        "albumTitle",
        "-f",
        "remixer",
        "-f",
        "producer",
        "-f",
        "genre",
        "-f",
        "tags",
    ]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    raw = proc.stdout
    if proc.returncode != 0:
        raise RuntimeError(f"lexicon list-tracks failed ({proc.returncode}): {proc.stderr or raw[:500]}")
    return json.loads(_strip_json_prefix(raw))


def run_export(
    repo_root: Path,
    out_dir: Path,
    *,
    backup_home: bool,
) -> None:
    """Write export.json, genre backup, tags backup under ``out_dir``."""
    data = _fetch_tracks_json(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    export_path = out_dir / "export.json"
    export_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {len(data)} tracks to {export_path}")

    genre_rows: list[dict[str, Any]] = []
    tag_rows: list[dict[str, Any]] = []
    for t in data:
        tid = t["id"]
        g = (t.get("genre") or "").strip()
        if g:
            genre_rows.append({"id": tid, "genre": g})
        tags = t.get("tags") or []
        if isinstance(tags, list) and tags:
            str_tags = [x for x in tags if isinstance(x, str)]
            if str_tags:
                tag_rows.append({"id": tid, "tags": str_tags})

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    gb = out_dir / f"genre_backup_bulk_update_{stamp}.json"
    tb = out_dir / f"tags_backup_bulk_update_{stamp}.json"
    gb.write_text(json.dumps(genre_rows, indent=2), encoding="utf-8")
    tb.write_text(json.dumps(tag_rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(genre_rows)} genre backup rows to {gb}")
    print(f"Wrote {len(tag_rows)} tags backup rows to {tb}")

    if backup_home:
        home_dir = Path.home() / f"lexicon-genre-backup-{date.today().isoformat()}"
        home_dir.mkdir(parents=True, exist_ok=True)
        (home_dir / gb.name).write_text(gb.read_text(encoding="utf-8"), encoding="utf-8")
        (home_dir / tb.name).write_text(tb.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Wrote home backup copies under {home_dir}")


# ---------------------------------------------------------------------------
# Taxonomy: genres.txt → paths
# ---------------------------------------------------------------------------

TaxonomyPath = tuple[str, ...]


def parse_genres_txt(text: str) -> list[TaxonomyPath]:
    """Parse indented tree; emit every visited prefix path (intermediate + leaf)."""
    paths: list[TaxonomyPath] = []
    seen: set[TaxonomyPath] = set()
    stack: list[str] = []

    def record() -> None:
        tup = tuple(stack)
        if tup not in seen:
            seen.add(tup)
            paths.append(tup)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        depth = indent // INDENT_SPACES_PER_LEVEL
        name = line.strip()
        while len(stack) > depth:
            stack.pop()
        if len(stack) != depth:
            raise ValueError(f"Invalid indent in genres.txt at line {line!r}: depth {depth}, stack depth {len(stack)}")
        stack.append(name)
        record()
    return paths


def path_to_field(p: TaxonomyPath, sep: str = " > ") -> str:
    return sep.join(p)


def _norm_token(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_genre_field(s: str) -> str:
    """Normalize native genre string for equality (canonical skip)."""
    s = (s or "").strip()
    s = re.sub(r"\s*>\s*", " > ", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _path_key(p: TaxonomyPath) -> str:
    return "/".join(_norm_token(x) for x in p)


def canonical_native_strings(paths: list[TaxonomyPath]) -> set[str]:
    return {_norm_genre_field(path_to_field(p)) for p in paths}


def _build_indices(paths: list[TaxonomyPath]) -> dict[str, list[TaxonomyPath]]:
    by_token: dict[str, list[TaxonomyPath]] = defaultdict(list)

    def add(tok: str, p: TaxonomyPath) -> None:
        key = _norm_token(tok)
        if p not in by_token[key]:
            by_token[key].append(p)

    for p in paths:
        for seg in p:
            add(seg, p)
    return by_token


def _top_level_map(paths: list[TaxonomyPath]) -> dict[str, str]:
    """Normalized root name -> canonical spelling."""
    out: dict[str, str] = {}
    for p in paths:
        if len(p) >= 1:
            root = p[0]
            n = _norm_token(root)
            out.setdefault(n, root)
    return out


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------


def _norm_full_genre_key(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s*[/|;]+\s*", " / ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def load_aliases(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (token_aliases, exact_norm_key -> canonical path string)."""
    if not path.is_file():
        return {}, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_a = data.get("aliases") or {}
    aliases = {_norm_token(str(k)): str(v) for k, v in raw_a.items()}
    exact: dict[str, str] = {}
    raw_e = data.get("exact") or data.get("exact_genres") or {}
    for k, v in raw_e.items():
        if isinstance(v, str):
            exact[_norm_full_genre_key(str(k))] = v.strip()
        elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            exact[_norm_full_genre_key(str(k))] = _labels_list_to_path(v)
    return aliases, exact


def _labels_list_to_path(labels: list[str]) -> str:
    """Legacy Genre: / Sub-genre: tags → Lexicon native path."""
    parts: list[str] = []
    for raw in labels:
        low = raw.lower()
        if low.startswith("genre:"):
            parts.append(raw.split(":", 1)[1])
        elif low.startswith("sub-genre:"):
            parts.append(raw.split(":", 1)[1])
        elif low.startswith("sub-sub-genre:"):
            parts.append(raw.split(":", 1)[1])
    return path_to_field(tuple(parts))


def save_genre_aliases(
    path: Path,
    *,
    merge_exact: dict[str, str] | None = None,
    merge_aliases: dict[str, str] | None = None,
) -> None:
    """Merge into ``exact`` / ``aliases`` and write JSON (stable sort, drops legacy keys)."""
    data: dict[str, Any] = {"exact": {}, "aliases": {}}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        ex = dict(raw.get("exact") or {})
        if not ex and raw.get("exact_genres"):
            raise ValueError(f"{path} uses legacy exact_genres; migrate ``exact`` to string paths first.")
        if any(not isinstance(v, str) for v in ex.values()):
            raise ValueError(f"{path}: all ``exact`` values must be strings (canonical paths).")
        data["exact"] = {str(k): str(v) for k, v in ex.items()}
        al = raw.get("aliases") or {}
        data["aliases"] = {str(k): str(v) for k, v in al.items()}
    if merge_exact:
        for k, v in merge_exact.items():
            data["exact"][str(k).strip()] = str(v).strip()
    if merge_aliases:
        for k, v in merge_aliases.items():
            data["aliases"][str(k).strip()] = str(v).strip()
    data.pop("exact_genres", None)
    exact_clean = {k: v for k, v in data["exact"].items() if isinstance(v, str)}
    alias_clean = {k: v for k, v in data["aliases"].items() if isinstance(v, str)}
    out = {
        "exact": dict(sorted(exact_clean.items(), key=lambda x: x[0].lower())),
        "aliases": dict(sorted(alias_clean.items(), key=lambda x: x[0].lower())),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def _raw_genre_segment_tokens(g: str) -> list[str]:
    """Split raw genre into tokens for matching (Lexicon uses `` > ``, tags often use ``/`` or ``|``)."""
    s = (g or "").strip()
    if not s:
        return []
    compound = re.sub(r"\s*>\s*", "/", s)
    normalized = re.sub(r"\s*[/|;]+\s*", "/", compound)
    return [p.strip() for p in normalized.split("/") if p.strip()]


def resolve_canonical_path_string(typed: str, paths: list[TaxonomyPath]) -> str | None:
    """Return canonical `` > `` path if ``typed`` matches a taxonomy path (spacing-normalized)."""
    t = typed.strip()
    if not t:
        return None
    n = _norm_genre_field(t)
    for p in paths:
        if _norm_genre_field(path_to_field(p)) == n:
            return path_to_field(p)
    return None


def candidate_paths_for_raw(
    raw: str,
    paths: list[TaxonomyPath],
    by_token: dict[str, list[TaxonomyPath]],
    token_aliases: dict[str, str],
) -> list[str]:
    """Paths the matcher might have been torn between (for quick-pick); may be empty."""
    g = (raw or "").strip()
    if not g:
        return []

    canon = resolve_canonical_path_string(g, paths)
    if canon:
        return [canon]

    def apply_alias_token(token: str) -> str:
        n = _norm_token(token)
        return token_aliases.get(n, token.strip())

    parts = [apply_alias_token(p) for p in _raw_genre_segment_tokens(g)]
    parts_norm = [_norm_token(p) for p in parts]

    if len(parts) >= 2:
        candidates = list(paths)
        for i, pn in enumerate(parts_norm):
            candidates = [p for p in candidates if len(p) > i and _norm_token(p[i]) == pn]
        if len(candidates) > 1:
            return sorted({path_to_field(p) for p in candidates})

    if len(parts) == 1:
        tok = _norm_token(parts[0])
        cand = by_token.get(tok, [])
        if len(cand) > 1:
            return sorted({path_to_field(p) for p in cand})
    return []


# ---------------------------------------------------------------------------
# Matching: raw genre → (canonical path | None, confidence, reason)
# ---------------------------------------------------------------------------


def match_genre_field(
    genre_field: str,
    paths: list[TaxonomyPath],
    by_token: dict[str, list[TaxonomyPath]],
    token_aliases: dict[str, str],
    exact: dict[str, str],
    top_level: dict[str, str],
) -> tuple[str | None, str, str]:
    """
    Returns ``(canonical_path, confidence, reason)``. ``canonical_path`` is ``None`` when
    not definitively mapped (ambiguous / unknown / empty).
    """
    g = (genre_field or "").strip()
    if not g:
        return None, "skip", "empty genre"

    def apply_alias_token(token: str) -> str:
        n = _norm_token(token)
        return token_aliases.get(n, token.strip())

    exact_key = _norm_full_genre_key(g)
    if exact_key in exact:
        return exact[exact_key], "high", "exact alias"

    canon = resolve_canonical_path_string(g, paths)
    if canon:
        return canon, "high", "canonical path"

    parts = [apply_alias_token(p) for p in _raw_genre_segment_tokens(g)]
    parts_norm = [_norm_token(p) for p in parts]

    key = "/".join(parts_norm)
    for p in paths:
        if _path_key(p) == key:
            return path_to_field(p), "high", "exact path"

    if len(parts) == 1:
        tok = _norm_token(parts[0])
        if tok in top_level:
            return top_level[tok], "high", "top-level genre only"
        cand = by_token.get(tok, [])
        if len(cand) == 1:
            return path_to_field(cand[0]), "high", "unique token"
        if not cand:
            return None, "none", "unknown token"
        leaf_matches = [c for c in cand if _norm_token(c[-1]) == tok]
        if len(leaf_matches) == 1:
            return path_to_field(leaf_matches[0]), "high", "unique leaf match"
        sub_tier = [c for c in cand if len(c) == 2 and _norm_token(c[1]) == tok]
        if len(sub_tier) == 1:
            return path_to_field(sub_tier[0]), "high", "unique two-segment tier"
        return None, "ambiguous", f"{len(cand)} paths for token"

    candidates = list(paths)
    for i, pn in enumerate(parts_norm):
        nxt = [p for p in candidates if len(p) > i and _norm_token(p[i]) == pn]
        candidates = nxt
    if len(candidates) == 1:
        return path_to_field(candidates[0]), "high", "multi-segment path"
    if len(candidates) > 1:
        return None, "ambiguous", "multi-segment multiple"

    return None, "none", "unmatched compound"


# ---------------------------------------------------------------------------
# map-genres
# ---------------------------------------------------------------------------


def _tracks_for_genre(tracks: list[dict[str, Any]], raw: str) -> list[dict[str, Any]]:
    return [t for t in tracks if (t.get("genre") or "").strip() == raw]


def _top_artists(trs: list[dict[str, Any]], n: int = 8) -> list[str]:
    c: Counter[str] = Counter()
    for t in trs:
        a = (t.get("artist") or "").strip()
        if a:
            c[a] += 1
    return [a for a, _ in c.most_common(n)]


def _build_review_queue(
    tracks: list[dict[str, Any]],
    paths: list[TaxonomyPath],
    token_aliases: dict[str, str],
    exact: dict[str, str],
    top_level: dict[str, str],
) -> tuple[Counter[str], list[dict[str, Any]]]:
    """Unique raw genres needing human review (not high-confidence mapped)."""
    by_token = _build_indices(paths)
    genre_counts: Counter[str] = Counter()
    for t in tracks:
        g = (t.get("genre") or "").strip()
        if g:
            genre_counts[g] += 1
    review_items: list[dict[str, Any]] = []
    for raw, count in genre_counts.most_common():
        canon, conf, reason = match_genre_field(raw, paths, by_token, token_aliases, exact, top_level)
        if canon is not None and conf == "high":
            continue
        trs = _tracks_for_genre(tracks, raw)
        artists = _top_artists(trs)
        samples = _sample_tracks(trs)
        norm_key = _norm_full_genre_key(raw)
        action = (
            "Decide the canonical path, then add one `exact` entry in "
            "`scripts/genre_taxonomy/genre_aliases.json` (or an `aliases` token if appropriate)."
        )
        review_items.append(
            {
                "raw_genre": raw,
                "track_count": count,
                "reason": reason,
                "confidence": conf,
                "action": action,
                "top_artists": artists,
                "sample_tracks": samples,
                "exact_entry_template": {norm_key: "CANONICAL_PATH"},
                "normalized_exact_key": norm_key,
            }
        )
    return genre_counts, review_items


def _sample_tracks(trs: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for t in trs:
        tid = t.get("id")
        if tid in seen:
            continue
        seen.add(tid)
        out.append(
            {
                "id": tid,
                "title": t.get("title"),
                "artist": t.get("artist"),
            }
        )
        if len(out) >= n:
            break
    return out


def map_genres(
    export_path: Path,
    taxonomy_path: Path,
    aliases_path: Path,
    out_dir: Path,
    *,
    write_review_json: bool,
) -> None:
    tracks = json.loads(export_path.read_text(encoding="utf-8"))
    tree_text = taxonomy_path.read_text(encoding="utf-8")
    paths = parse_genres_txt(tree_text)
    token_aliases, exact = load_aliases(aliases_path)
    top_level = _top_level_map(paths)
    genre_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    missing_signal: list[dict[str, Any]] = []

    for t in tracks:
        g = (t.get("genre") or "").strip()
        if g:
            genre_counts[g] += 1
        tags = t.get("tags") or []
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    tag_counts[tag] += 1
        if not g:
            missing_signal.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "artist": t.get("artist"),
                }
            )

    inventory = {
        "track_count": len(tracks),
        "unique_genres": len(genre_counts),
        "genre_counts": dict(genre_counts.most_common()),
        "unique_track_tags": len(tag_counts),
        "tag_counts": dict(tag_counts.most_common(200)),
        "tracks_empty_genre": len(missing_signal),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "genre_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (out_dir / "tracks_missing_genre.json").write_text(json.dumps(missing_signal, indent=2), encoding="utf-8")

    flat = [{"path": path_to_field(p), "segments": list(p)} for p in paths]
    (out_dir / "taxonomy_paths.json").write_text(json.dumps(flat, indent=2), encoding="utf-8")
    print(f"Wrote {len(paths)} taxonomy paths to {out_dir / 'taxonomy_paths.json'}")

    _, review_items = _build_review_queue(tracks, paths, token_aliases, exact, top_level)

    lines: list[str] = [
        "# Genre mapping — needs review",
        "",
        "Sections are ordered by **track count** (highest first).",
        "**Unresolved items here are not modified** by `write-genres` until you add an `exact` or `aliases` entry in `genre_aliases.json` and re-run `map-genres`.",
        "",
        "## How to resolve",
        "",
        "1. Pick a canonical path from `.notes/genres.txt`.",
        "2. Add it under `exact` in `scripts/genre_taxonomy/genre_aliases.json` (normalized key is noted per section).",
        "3. Re-run `map-genres`, then `write-genres`.",
        "",
    ]

    for item in review_items:
        raw = item["raw_genre"]
        count = item["track_count"]
        reason = item["reason"]
        conf = item["confidence"]
        action = item["action"]
        artists = item["top_artists"]
        samples = item["sample_tracks"]
        norm_key = item["normalized_exact_key"]
        entry_template = item["exact_entry_template"]

        esc = raw.replace("`", "\\`")
        lines.append(f"### `{esc}`")
        lines.append("")
        lines.append(f"- **Impact:** {count} tracks — **Reason:** {reason} (`{conf}`)")
        lines.append("- **Context:**")
        lines.append("  - Artists: " + (", ".join(artists) if artists else "(none)"))
        for s in samples:
            artist = s.get("artist") or ""
            title = s.get("title") or ""
            lines.append(f"  - {artist} — {title}")
        lines.append(f"- **Action:** {action}")
        lines.append(
            f"- **Copy-paste:** merge under `exact` using normalized key `{norm_key}`... (see JSON block below)."
        )
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(entry_template, indent=2))
        lines.append("```")
        lines.append("")

    md_path = out_dir / "needs_review.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {md_path} ({len(review_items)} section(s))")

    if write_review_json:
        jpath = out_dir / "needs_review.json"
        jpath.write_text(json.dumps(review_items, indent=2), encoding="utf-8")
        print(f"Wrote {jpath}")


# ---------------------------------------------------------------------------
# Interactive review (InquirerPy)
# ---------------------------------------------------------------------------


def review_genres_interactive(
    export_path: Path,
    taxonomy_path: Path,
    aliases_path: Path,
) -> None:
    tracks = json.loads(export_path.read_text(encoding="utf-8"))
    paths = parse_genres_txt(taxonomy_path.read_text(encoding="utf-8"))
    taxonomy_strings = sorted({path_to_field(p) for p in paths})
    top_level = _top_level_map(paths)
    by_token = _build_indices(paths)
    skipped_session: set[str] = set()

    typer.secho(
        "Interactive genre review — edits save to genre_aliases.json immediately. " "Ctrl+C to stop.\n",
        fg=typer.colors.CYAN,
    )
    while True:
        try:
            token_aliases, exact = load_aliases(aliases_path)
            _, queue = _build_review_queue(tracks, paths, token_aliases, exact, top_level)
            queue = [x for x in queue if x["raw_genre"] not in skipped_session]
            if not queue:
                typer.secho("Nothing left to review.", fg=typer.colors.GREEN)
                break

            item = queue[0]
            raw = item["raw_genre"]
            typer.echo("")
            typer.echo("=" * 72)
            typer.secho(f"Raw genre: {raw!r}", bold=True)
            typer.echo(f"Tracks: {item['track_count']}  |  {item['reason']} ({item['confidence']})")
            if item["top_artists"]:
                typer.echo("Artists: " + ", ".join(item["top_artists"][:8]))
            for s in item["sample_tracks"][:5]:
                typer.echo(f"  • {s.get('artist') or ''} — {s.get('title') or ''}")

            hints = candidate_paths_for_raw(raw, paths, by_token, token_aliases)
            if hints:
                typer.echo(f"Matcher candidates: {', '.join(hints[:6])}")

            action = inquirer.select(
                message="What do you want to do?",
                choices=[
                    Choice(
                        value="pick",
                        name="Pick canonical path (fuzzy search full taxonomy)",
                    ),
                    Choice(
                        value="type",
                        name="Type canonical path (must match genres.txt)",
                    ),
                    Choice(
                        value="delete",
                        name="Clear genre for all tracks with this raw value (set empty)",
                    ),
                    Choice(
                        value="list_all",
                        name=(f"List all {item['track_count']} tracks, then choose an action"),
                    ),
                    Choice(
                        value="alias",
                        name="Add token alias (rewrite one segment, e.g. hip hop → Hip-Hop)",
                    ),
                    Choice(value="skip", name="Skip this genre for this session"),
                    Choice(value="quit", name="Quit reviewer"),
                ],
            ).execute()

            if action == "quit":
                typer.echo("Bye.")
                break
            if action == "skip":
                skipped_session.add(raw)
                continue

            if action == "list_all":
                all_trs = _tracks_for_genre(tracks, raw)
                typer.echo("")
                for t in all_trs:
                    artist = (t.get("artist") or "").strip()
                    title = (t.get("title") or "").strip()
                    tid = t.get("id")
                    line = f"  • {artist} — {title}"
                    if tid is not None:
                        line += f"  [id {tid}]"
                    typer.echo(line)
                typer.echo(f"\n({len(all_trs)} track(s) with raw genre {raw!r})")
                continue

            if action == "pick":
                initial = hints[0] if len(hints) == 1 else ""
                chosen = inquirer.fuzzy(
                    message="Canonical path:",
                    choices=taxonomy_strings,
                    default=initial,
                ).execute()
                canon = resolve_canonical_path_string(chosen, paths)
                if not canon:
                    typer.secho("Could not resolve choice — try again.", fg=typer.colors.RED)
                    continue
                save_genre_aliases(aliases_path, merge_exact={raw: canon})
                typer.secho(f"Saved exact[{raw!r}] → {canon!r}", fg=typer.colors.GREEN)

            elif action == "type":
                typed = inquirer.text(
                    message="Canonical path (use ' > ' between segments):",
                    validate=lambda t: bool((t or "").strip()) and resolve_canonical_path_string(t, paths) is not None,
                    invalid_message="Must match a path from genres.txt (spacing can differ slightly).",
                ).execute()
                canon = resolve_canonical_path_string(typed, paths)
                if not canon:
                    typer.secho("Invalid path.", fg=typer.colors.RED)
                    continue
                save_genre_aliases(aliases_path, merge_exact={raw: canon})
                typer.secho(f"Saved exact[{raw!r}] → {canon!r}", fg=typer.colors.GREEN)

            elif action == "delete":
                confirm = inquirer.confirm(
                    message=(f"Set genre to empty string for ALL tracks whose raw genre is {raw!r}?"),
                    default=False,
                ).execute()
                if not confirm:
                    continue
                # Store as an exact alias to empty string; matcher treats it as high-confidence
                # and write-genres will emit edits setting genre to "".
                save_genre_aliases(aliases_path, merge_exact={raw: ""})
                typer.secho(
                    f"Will clear genre for tracks with raw genre {raw!r} " "(exact mapping to empty string).",
                    fg=typer.colors.YELLOW,
                )

            elif action == "alias":
                tok = (
                    inquirer.text(
                        message="Token to rewrite (lowercase messy segment, e.g. hip hop):",
                        validate=lambda t: bool((t or "").strip()),
                    )
                    .execute()
                    .strip()
                )
                repl = (
                    inquirer.text(
                        message="Replace with (segment or full path from taxonomy):",
                        validate=lambda t: bool((t or "").strip()),
                    )
                    .execute()
                    .strip()
                )
                if "/" in repl or "|" in repl:
                    typer.secho(
                        "Use full path keys under ``exact`` for compound strings; "
                        "aliases are single-segment rewrites.",
                        fg=typer.colors.YELLOW,
                    )
                save_genre_aliases(aliases_path, merge_aliases={tok: repl})
                typer.secho(
                    f"Saved aliases[{tok!r}] → {repl!r}",
                    fg=typer.colors.GREEN,
                )

        except KeyboardInterrupt:
            typer.echo("\nStopped.")
            break


# ---------------------------------------------------------------------------
# write-genres
# ---------------------------------------------------------------------------


def write_genres(
    export_path: Path,
    taxonomy_path: Path,
    aliases_path: Path,
    out_path: Path,
    *,
    dry_run: bool,
    repo_root: Path,
) -> None:
    tracks = json.loads(export_path.read_text(encoding="utf-8"))
    tree_text = taxonomy_path.read_text(encoding="utf-8")
    paths = parse_genres_txt(tree_text)
    token_aliases, exact = load_aliases(aliases_path)
    by_token = _build_indices(paths)
    top_level = _top_level_map(paths)
    canon_set = canonical_native_strings(paths)

    raw_to_result: dict[str, tuple[str | None, str, str]] = {}
    for t in tracks:
        g = (t.get("genre") or "").strip()
        if not g:
            continue
        if g not in raw_to_result:
            raw_to_result[g] = match_genre_field(g, paths, by_token, token_aliases, exact, top_level)

    edits: list[dict[str, str | int]] = []
    skipped_empty = 0
    skipped_already_canonical = 0
    skipped_not_definitive = 0
    reasons: Counter[str] = Counter()

    for t in tracks:
        tid = t["id"]
        g = (t.get("genre") or "").strip()
        if not g:
            skipped_empty += 1
            continue
        if _norm_genre_field(g) in canon_set:
            skipped_already_canonical += 1
            continue
        canon, conf, reason = raw_to_result[g]
        if canon is None or conf != "high":
            skipped_not_definitive += 1
            reasons[reason] += 1
            continue
        if _norm_genre_field(canon) == _norm_genre_field(g):
            skipped_already_canonical += 1
            continue
        edits.append({"id": tid, "genre": canon})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(edits, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(edits)} genre edits to {out_path} | "
        f"skipped empty={skipped_empty}, already_canonical={skipped_already_canonical}, "
        f"not_definitive={skipped_not_definitive}"
    )
    if reasons:
        print("  not_definitive by reason: " + ", ".join(f"{k}={v}" for k, v in reasons.most_common()))

    if dry_run:
        proc = subprocess.run(
            [
                "uv",
                "run",
                "lexicon",
                "bulk-update",
                "--file",
                str(out_path),
                "--dry-run",
                "--output-format",
                "summary",
            ],
            cwd=repo_root,
        )
        raise SystemExit(proc.returncode)


def dry_run_genre_batch(repo_root: Path, batch_path: Path) -> int:
    cmd = [
        "uv",
        "run",
        "lexicon",
        "bulk-update",
        "--file",
        str(batch_path),
        "--dry-run",
        "--output-format",
        "summary",
    ]
    proc = subprocess.run(cmd, cwd=repo_root)
    return proc.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command("export")
def cmd_export(
    out_dir: Path = typer.Option(
        OUTPUT_DIR,
        "--out-dir",
        help="Directory for export.json and backup JSON files",
    ),
    backup_home: bool = typer.Option(
        False,
        "--backup-home",
        help="Also copy backup JSON files under ~/lexicon-genre-backup-YYYY-MM-DD/",
    ),
) -> None:
    """Export library + genre/tags bulk-update backups."""
    run_export(REPO_ROOT, out_dir, backup_home=backup_home)


@app.command("map-genres")
def cmd_map_genres(
    export_path: Path = typer.Option(
        ...,
        "--export",
        help="Path to export.json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    taxonomy: Path = typer.Option(DEFAULT_TAXONOMY, "--taxonomy"),
    aliases: Path = typer.Option(DEFAULT_ALIASES, "--aliases"),
    out_dir: Path = typer.Option(OUTPUT_DIR, "--out-dir"),
    review_json: bool = typer.Option(
        False,
        "--review-json",
        help="Also write needs_review.json",
    ),
) -> None:
    """Inventory + taxonomy paths + needs_review.md from export."""
    map_genres(export_path, taxonomy, aliases, out_dir, write_review_json=review_json)


@app.command("review-genres")
def cmd_review_genres(
    export_path: Path = typer.Option(
        ...,
        "--export",
        help="Path to export.json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    taxonomy: Path = typer.Option(DEFAULT_TAXONOMY, "--taxonomy"),
    aliases: Path = typer.Option(DEFAULT_ALIASES, "--aliases"),
) -> None:
    """Interactive TUI to resolve genres and update genre_aliases.json (InquirerPy)."""
    review_genres_interactive(export_path, taxonomy, aliases)


@app.command("write-genres")
def cmd_write_genres(
    export_path: Path = typer.Option(
        ...,
        "--export",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    taxonomy: Path = typer.Option(DEFAULT_TAXONOMY, "--taxonomy"),
    aliases: Path = typer.Option(DEFAULT_ALIASES, "--aliases"),
    output: Path = typer.Option(
        OUTPUT_DIR / "bulk_update_genres.json",
        "-o",
        "--output",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="After writing file, run lexicon bulk-update --dry-run",
    ),
) -> None:
    """Write bulk-update JSON: native genre only for definitive mappings."""
    write_genres(
        export_path,
        taxonomy,
        aliases,
        output,
        dry_run=dry_run,
        repo_root=REPO_ROOT,
    )


@app.command("dry-run")
def cmd_dry_run(
    batch: Path = typer.Option(
        ...,
        "--batch",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """Run lexicon bulk-update --dry-run on a genre bulk file."""
    raise SystemExit(dry_run_genre_batch(REPO_ROOT, batch))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
