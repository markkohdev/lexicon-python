#!/usr/bin/env python3
"""Genre taxonomy cleanup: flatten .notes/genres.json, map library export, write bulk-update batches.

High-level flow
---------------
1. ``export`` — Run ``lexicon list-tracks --json`` and save a trimmed JSON array of tracks
   (native ``genre`` string + ``tags`` per track).

2. ``ensure-categories`` — Ensure Lexicon has tag categories ``Genre``, ``Sub-genre``,
   ``Sub-sub-genre`` (needed before hierarchy tags can exist).

3. ``analyze`` — Read export + hierarchical taxonomy + aliases; classify each track's
   native ``genre`` field as a confident or uncertain taxonomy path; write inventory,
   backups, and per–top-level-genre bulk-update batch JSON files for *tags*.

4. ``write-genre-native`` — Same mapping logic, but output bulk-update rows that set
   the *native* ``genre`` field to ``Genre > Sub > Sub-sub`` (not tag IDs).

5. ``dry-run`` — Convenience wrapper around ``lexicon bulk-update --dry-run`` on a batch.

Data sources
------------
- Taxonomy: nested JSON tree (top-level genre → children → …) under ``DEFAULT_TAXONOMY``.
- Aliases: ``genre_aliases.json`` maps messy tokens / full strings to canonical paths.

See repo plan: Lexicon genre cleanup (hierarchical tags).

Usage:
  uv run python scripts/genre_taxonomy/genre_cleanup.py export -o output/export.json
  uv run python scripts/genre_taxonomy/genre_cleanup.py analyze --export output/export.json
  uv run python scripts/genre_taxonomy/genre_cleanup.py write-genre-native --export output/export.json
  uv run python scripts/genre_taxonomy/genre_cleanup.py ensure-categories
  uv run python scripts/genre_taxonomy/genre_cleanup.py dry-run --batch output/batches/all_confident.json
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import typer

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TAXONOMY = SCRIPT_DIR.parent.parent / ".notes" / "genres.json"
DEFAULT_ALIASES = SCRIPT_DIR / "genre_aliases.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
# Lexicon hierarchy tags use these prefixes (case-insensitive check in is_genre_hierarchy_label).
GENRE_TAG_PREFIXES = ("genre:", "sub-genre:", "sub-sub-genre:")

# Repo root so subprocesses can ``uv run lexicon`` with the right cwd.
REPO_ROOT = SCRIPT_DIR.parent.parent

app = typer.Typer(help="Lexicon genre taxonomy cleanup helper")

# ---------------------------------------------------------------------------
# Export helper
# ---------------------------------------------------------------------------


def _strip_json_prefix(raw: str) -> str:
    i = raw.find("[")
    if i < 0:
        raise ValueError("No JSON array found in input")
    j = raw.rfind("]")
    if j < i:
        raise ValueError("Unclosed JSON array")
    # Some CLIs print banners or warnings before the JSON; we only need the array slice.
    return raw[i : j + 1]


def run_lexicon_export(repo_root: Path, out_path: Path) -> None:
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
        raise RuntimeError(
            f"lexicon list-tracks failed ({proc.returncode}): {proc.stderr or raw[:500]}"
        )
    data = json.loads(_strip_json_prefix(raw))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {len(data)} tracks to {out_path}")


# ---------------------------------------------------------------------------
# Taxonomy model: tree → flat paths and lookup indices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenrePath:
    """One path through the taxonomy tree (genre may repeat across many paths).

    ``labels()`` are Lexicon hierarchy tag strings (``Genre:…``, ``Sub-genre:…``).
    ``to_lexicon_genre_field()`` is the native ``genre`` column format (`` > ``).
    """

    genre: str
    subgenre: str | None
    subsub: str | None

    def labels(self) -> list[str]:
        out = [f"Genre:{self.genre}"]
        if self.subgenre:
            out.append(f"Sub-genre:{self.subgenre}")
        if self.subsub:
            out.append(f"Sub-sub-genre:{self.subsub}")
        return out

    def slug(self) -> str:
        parts = [self.genre]
        if self.subgenre:
            parts.append(self.subgenre)
        if self.subsub:
            parts.append(self.subsub)
        return " / ".join(parts)

    def to_lexicon_genre_field(self, sep: str = " > ") -> str:
        """Native genre string for Lexicon (avoid ``/`` — some taxonomy names contain it)."""
        parts = [self.genre]
        if self.subgenre:
            parts.append(self.subgenre)
        if self.subsub:
            parts.append(self.subsub)
        return sep.join(parts)


def _collect_paths(tree: list[dict[str, Any]]) -> list[GenrePath]:
    """Flatten the nested taxonomy JSON into every valid ``GenrePath``.

    Tree shape: each node is ``{"name": str, "children": [...]}``. We emit:
    - paths ending at a **leaf** sub-genre (two levels under top); and
    - **intermediate** paths where a tier is a valid stop (e.g. genre + sub only),
      including when deeper children exist—so both "House → Tech House" and
      "House tech house → Organic" style branches produce usable paths for matching.
    """
    paths: list[GenrePath] = []

    def walk_sub(genre: str, node: dict[str, Any]) -> None:
        """First level under top-level genre: this node's ``name`` is a sub-genre."""
        name = node["name"]
        kids = node.get("children") or []
        if not kids:
            paths.append(GenrePath(genre, name, None))
            return
        # Sub-genre has children: still record Genre + this sub-genre (no leaf sub-sub).
        paths.append(GenrePath(genre, name, None))
        for ch in kids:
            walk_subsub(genre, name, ch)

    def walk_subsub(genre: str, sub: str, node: dict[str, Any]) -> None:
        """Second level: ``name`` is either a leaf sub-sub-genre or a branch name."""
        name = node["name"]
        kids = node.get("children") or []
        if not kids:
            paths.append(GenrePath(genre, sub, name))
            return
        paths.append(GenrePath(genre, sub, name))
        # Deeper nesting: treat each child's name as additional sub-sub slugs (one hop).
        for ch in kids:
            ss = ch["name"]
            paths.append(GenrePath(genre, sub, ss))

    for top in tree:
        g = top["name"]
        for ch in top.get("children") or []:
            walk_sub(g, ch)
    return paths


def _norm_token(s: str) -> str:
    """Normalize a single segment for matching (lower case, collapse whitespace)."""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _load_aliases(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    if not path.is_file():
        return {}, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    # Token-level rewrites applied inside slash-split paths (see match_genre_field).
    raw = data.get("aliases") or {}
    aliases = {_norm_token(k): v for k, v in raw.items()}
    # Full native genre string → precomputed hierarchy tag list (bypass fuzzy match).
    exact: dict[str, list[str]] = {}
    for k, v in (data.get("exact_genres") or {}).items():
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            exact[_norm_full_genre_key(k)] = v
    return aliases, exact


def _norm_full_genre_key(s: str) -> str:
    """Key for exact_genres: same idea as path matching (slashes normalized to `` / ``)."""
    s = s.strip().lower()
    s = re.sub(r"\s*[/|;]+\s*", " / ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _build_indices(paths: list[GenrePath]) -> dict[str, list[GenrePath]]:
    """Map normalized token -> paths where token appears as genre, subgenre, or subsub."""
    by_token: dict[str, list[GenrePath]] = defaultdict(list)

    def add(tok: str, p: GenrePath) -> None:
        key = _norm_token(tok)
        if p not in by_token[key]:
            by_token[key].append(p)

    for p in paths:
        add(p.genre, p)
        if p.subgenre:
            add(p.subgenre, p)
        if p.subsub:
            add(p.subsub, p)
    return by_token


def _path_key(p: GenrePath) -> str:
    """Stable normalized key for comparing a taxonomy path to slash-split input."""
    return "/".join(
        _norm_token(x) for x in (p.genre, p.subgenre or "", p.subsub or "") if x
    )


def _top_level_map(tree: list[dict[str, Any]]) -> dict[str, str]:
    """Map normalized top-level name to canonical spelling (preserves original casing)."""
    return {_norm_token(t["name"]): t["name"] for t in tree}


# ---------------------------------------------------------------------------
# Native ``genre`` string → taxonomy (labels + confidence)
# ---------------------------------------------------------------------------


def match_genre_field(
    genre_field: str,
    paths: list[GenrePath],
    by_token: dict[str, list[GenrePath]],
    aliases: dict[str, str],
    exact_genres: dict[str, list[str]],
    top_level: dict[str, str],
) -> tuple[list[str] | None, str, str]:
    """Map a track's native ``genre`` string to hierarchy tag labels.

    Returns ``(hierarchy_labels, confidence, reason)``. ``hierarchy_labels`` is
    ``None`` when we cannot map. Order of attempts:

    1. ``exact_genres`` table (full string).
    2. Split on ``/``, ``|``, ``;``; apply token ``aliases``; join segments and
       compare to every ``GenrePath`` via ``_path_key``.
    3. Single segment: top-level genre only, or unique token among paths, or
       disambiguate by preferring sub-sub / sub-tier-only matches.
    4. Multi-segment: filter candidate paths segment-by-segment; exactly one
       candidate → high confidence; zero / many → none / ambiguous.
    """
    g = (genre_field or "").strip()
    if not g:
        return None, "skip", "empty genre"

    def apply_alias(token: str) -> str:
        n = _norm_token(token)
        return aliases.get(n, token.strip())

    exact_key = _norm_full_genre_key(g)
    if exact_key in exact_genres:
        return list(exact_genres[exact_key]), "high", "exact_genres alias"

    # Full-string path: "House / Tech House" or "House/Tech House"
    normalized_slash = re.sub(r"\s*[/|;]+\s*", "/", g)
    parts = [apply_alias(p) for p in normalized_slash.split("/") if p.strip()]
    parts_norm = [_norm_token(p) for p in parts]

    # Exact path match
    key = "/".join(parts_norm)
    for p in paths:
        if _path_key(p) == key:
            return p.labels(), "high", "exact path"

    # Single segment after alias
    if len(parts) == 1:
        tok = _norm_token(parts[0])
        if tok in top_level:
            return [f"Genre:{top_level[tok]}"], "high", "top-level genre only"
        cand = by_token.get(tok, [])
        if len(cand) == 1:
            return cand[0].labels(), "high", "unique token"
        if not cand:
            return None, "none", "unknown token"
        # Same token appears in multiple paths—pick a unique interpretation when possible:
        # prefer the path where this token is the sub-sub label, else the path where it is
        # a sub-genre "tier" (subgenre set, subsub empty), before giving up as ambiguous.
        best = [c for c in cand if c.subsub and _norm_token(c.subsub) == tok]
        if len(best) == 1:
            return best[0].labels(), "high", "unique sub-sub match"
        sub_tier = [
            c
            for c in cand
            if c.subgenre and _norm_token(c.subgenre) == tok and c.subsub is None
        ]
        if len(sub_tier) == 1:
            return sub_tier[0].labels(), "high", "unique sub-genre tier"
        return None, "ambiguous", f"{len(cand)} paths for token"

    # Multi-segment: walk genre / sub / sub-sub in order
    if len(parts_norm) >= 2:
        candidates = list(paths)
        for i, pn in enumerate(parts_norm):
            if i == 0:
                candidates = [p for p in candidates if _norm_token(p.genre) == pn]
            elif i == 1:
                candidates = [
                    p
                    for p in candidates
                    if p.subgenre and _norm_token(p.subgenre) == pn
                ]
            elif i == 2:
                candidates = [
                    p for p in candidates if p.subsub and _norm_token(p.subsub) == pn
                ]
        if len(candidates) == 1:
            return candidates[0].labels(), "high", "multi-segment path"
        if len(candidates) > 1:
            return None, "ambiguous", "multi-segment multiple"

    return None, "none", "unmatched compound"


# ---------------------------------------------------------------------------
# Tags vs. native genre field helpers
# ---------------------------------------------------------------------------


def is_genre_hierarchy_label(label: str) -> bool:
    lower = label.lower()
    return lower.startswith(GENRE_TAG_PREFIXES)


def strip_genre_tags(tag_labels: list[str]) -> list[str]:
    """Remove old hierarchy tags so we can replace with canonical taxonomy tags."""
    return [t for t in tag_labels if not is_genre_hierarchy_label(t)]


def labels_to_lexicon_genre_field(hierarchy_labels: list[str], sep: str = " > ") -> str:
    """Build ``Genre > Sub-genre > Sub-sub-genre`` from ``Category:Label`` hierarchy tags."""
    genre = sub = subsub = None
    for raw in hierarchy_labels:
        low = raw.lower()
        if low.startswith("genre:"):
            genre = raw.split(":", 1)[1]
        elif low.startswith("sub-genre:"):
            sub = raw.split(":", 1)[1]
        elif low.startswith("sub-sub-genre:"):
            subsub = raw.split(":", 1)[1]
    parts = [x for x in (genre, sub, subsub) if x]
    return sep.join(parts)


# ---------------------------------------------------------------------------
# Commands (core logic)
# ---------------------------------------------------------------------------


def write_genre_native(
    export_path: Path,
    taxonomy_path: Path,
    aliases_path: Path,
    out_path: Path,
    confidence: str,
    *,
    dry_run: bool,
    repo_root: Path,
) -> None:
    """Write bulk-update JSON setting native ``genre`` to ``A > B > C`` for mapped tracks.

    Unlike ``analyze``, this does not merge tags—only emits ``{"id", "genre"}`` rows.
    ``confidence`` filters which match_genre_field results are included (only ``high``
    by default; ``medium`` is accepted if ``--confidence all``).
    """
    tracks = json.loads(export_path.read_text(encoding="utf-8"))
    tree = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    aliases, exact_genres = _load_aliases(aliases_path)
    paths = _collect_paths(tree)
    by_token = _build_indices(paths)
    top_level = _top_level_map(tree)

    # write-genre-native currently only gets "high" from the matcher; hook preserves
    # parity with analyze if medium confidence is introduced later.
    allowed_conf = {"high"} if confidence == "high" else {"high", "medium"}

    edits: list[dict[str, str | int]] = []
    skipped_empty = 0
    skipped_unmapped = 0
    skipped_confidence = 0

    for t in tracks:
        tid = t["id"]
        g = (t.get("genre") or "").strip()
        if not g:
            skipped_empty += 1
            continue
        hierarchy_labels, conf, _reason = match_genre_field(
            g, paths, by_token, aliases, exact_genres, top_level
        )
        if hierarchy_labels is None or conf in ("skip", "none", "ambiguous"):
            skipped_unmapped += 1
            continue
        if conf not in allowed_conf:
            skipped_confidence += 1
            continue
        # Lexicon native genre: use `` > `` so ``/`` inside a genre name stays unambiguous.
        native = labels_to_lexicon_genre_field(hierarchy_labels)
        edits.append({"id": tid, "genre": native})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(edits, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(edits)} genre field edits to {out_path} "
        f"(confidence={confidence!r}; skipped empty={skipped_empty}, "
        f"unmapped={skipped_unmapped}, confidence_filter={skipped_confidence})"
    )

    # Optional: validate the file against the real CLI without applying changes.
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


def analyze(
    export_path: Path,
    taxonomy_path: Path,
    aliases_path: Path,
    out_dir: Path,
    backup_home: bool,
) -> None:
    """Produce reports and bulk-update *tag* batches from an export.

    Outputs (under ``out_dir``):

    - ``genre_inventory.json`` — counts of raw genres/tags, tracks missing both genre and hierarchy tags.
    - ``tracks_missing_genre.json`` — id/title/artist for those weak-signal tracks.
    - ``taxonomy_paths.json`` — every flattened path as tag labels + human slug.
    - ``genre_backup_bulk_update.json`` — current native genres (restore before bulk tag apply).
    - ``uncertain_genres.json`` — tracks the matcher could not place confidently.
    - ``batches/*.json`` + ``batches/all_confident.json`` — ``bulk-update`` payloads with ``id`` + ``tags``.
    """
    tracks = json.loads(export_path.read_text(encoding="utf-8"))
    tree = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    aliases, exact_genres = _load_aliases(aliases_path)
    paths = _collect_paths(tree)
    by_token = _build_indices(paths)
    top_level = _top_level_map(tree)

    # --- Pass 1: inventory and "no genre signal" list ---
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
        has_h = False
        if isinstance(tags, list):
            has_h = any(is_genre_hierarchy_label(x) for x in tags if isinstance(x, str))
        if not g and not has_h:
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
        "tracks_empty_genre_no_hierarchy_tags": len(missing_signal),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "genre_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )
    (out_dir / "tracks_missing_genre.json").write_text(
        json.dumps(missing_signal, indent=2), encoding="utf-8"
    )

    # Reference file: all canonical tag triples (useful for spot-checking the tree walk).
    flat = [{"tags": p.labels(), "path": p.slug()} for p in paths]
    (out_dir / "taxonomy_paths.json").write_text(
        json.dumps(flat, indent=2), encoding="utf-8"
    )
    print(
        f"Wrote taxonomy with {len(paths)} leaf paths to {out_dir / 'taxonomy_paths.json'}"
    )

    # Backup native genres (bulk-update shape)
    backup = [{"id": t["id"], "genre": (t.get("genre") or "").strip()} for t in tracks]
    backup = [b for b in backup if b["genre"]]
    backup_path = out_dir / "genre_backup_bulk_update.json"
    backup_path.write_text(json.dumps(backup, indent=2), encoding="utf-8")
    print(f"Wrote {len(backup)} genre backup rows to {backup_path}")

    # Optional second copy in home directory (safer if ``out_dir`` is disposable).
    if backup_home:
        home_backup = (
            Path.home() / f"lexicon-genre-backup-{date.today().isoformat()}.json"
        )
        home_backup.write_text(json.dumps(backup, indent=2), encoding="utf-8")
        print(f"Wrote home backup {home_backup}")

    # --- Pass 2: map each track; split into tag bulk-update rows vs. manual review ---
    confident: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []

    for t in tracks:
        tid = t["id"]
        g = (t.get("genre") or "").strip()
        tag_labels = [x for x in (t.get("tags") or []) if isinstance(x, str)]
        hierarchy_labels, conf, reason = match_genre_field(
            g, paths, by_token, aliases, exact_genres, top_level
        )

        if not g:
            continue  # analyze focuses on string cleanup; empty genre handled in inventory only

        if hierarchy_labels is None:
            uncertain.append(
                {
                    "id": tid,
                    "title": t.get("title"),
                    "artist": t.get("artist"),
                    "albumTitle": t.get("albumTitle"),
                    "genre": g,
                    "tags": tag_labels,
                    "confidence": conf,
                    "reason": reason,
                }
            )
            continue

        if conf not in ("high", "medium"):
            uncertain.append(
                {
                    "id": tid,
                    "title": t.get("title"),
                    "artist": t.get("artist"),
                    "albumTitle": t.get("albumTitle"),
                    "genre": g,
                    "tags": tag_labels,
                    "confidence": conf,
                    "reason": reason,
                }
            )
            continue

        # Drop stale genre:* tags, add canonical hierarchy labels, dedupe.
        kept = strip_genre_tags(tag_labels)
        final_tags = sorted(set(kept + hierarchy_labels))
        confident.append(
            {
                "id": tid,
                "tags": final_tags,
                "_source_genre": g,
                "_confidence": conf,
            }
        )

    (out_dir / "uncertain_genres.json").write_text(
        json.dumps(uncertain, indent=2), encoding="utf-8"
    )
    print(f"Confident: {len(confident)}, uncertain: {len(uncertain)}")

    batches_dir = out_dir / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    # Smaller files for human review: one JSON per top-level ``Genre:…`` bucket.
    by_top: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in confident:
        tags = row["tags"]
        top = next((t for t in tags if t.startswith("Genre:")), "Genre:?")
        by_top[top].append(row)

    all_batch: list[dict[str, Any]] = []
    for top, rows in sorted(by_top.items(), key=lambda x: x[0]):
        # bulk-update expects minimal rows; debug fields stay only in per-source analysis JSON.
        clean_rows = [{"id": r["id"], "tags": r["tags"]} for r in rows]
        all_batch.extend(clean_rows)
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", top).strip("_") or "batch"
        (batches_dir / f"{safe}.json").write_text(
            json.dumps(clean_rows, indent=2), encoding="utf-8"
        )

    (batches_dir / "all_confident.json").write_text(
        json.dumps(all_batch, indent=2), encoding="utf-8"
    )
    print(f"Wrote batches under {batches_dir} ({len(all_batch)} edits)")


def ensure_categories(host: str | None, port: int | None) -> None:
    """Connect to Lexicon and create hierarchy tag categories if missing.

    Deferred imports keep the CLI importable without ``src`` on PYTHONPATH until
    this command runs.
    """
    repo_root = SCRIPT_DIR.parent.parent
    sys.path.insert(0, str(repo_root / "src"))
    from lexicon.client import Lexicon
    from lexicon.cli.tag_utils import TagResolver

    client = Lexicon(host=host, port=port)
    resolver = TagResolver(client)
    for cat in ("Genre", "Sub-genre", "Sub-sub-genre"):
        cid = resolver.get_category_id(cat)
        if cid is not None:
            print(f"Category {cat!r} already exists (id={cid})")
            continue
        created = client.tags.categories.add(cat)
        if created and "id" in created:
            print(f"Created category {cat!r} (id={created['id']})")
        else:
            print(f"Failed to create category {cat!r}", file=sys.stderr)
            raise SystemExit(1)


def dry_run_batch(repo_root: Path, batch_path: Path) -> int:
    """Return exit code from ``lexicon bulk-update --dry-run`` (tags file)."""
    cmd = [
        "uv",
        "run",
        "lexicon",
        "bulk-update",
        "--file",
        str(batch_path),
        "--dry-run",
        "--create-tags",
        "--output-format",
        "summary",
    ]
    proc = subprocess.run(cmd, cwd=repo_root)
    return proc.returncode


class Confidence(str, Enum):
    """Filter for write-genre-native: how strict to be about matcher confidence."""

    high = "high"
    all = "all"


# ---------------------------------------------------------------------------
# Typer CLI entrypoints (thin wrappers)
# ---------------------------------------------------------------------------


@app.command("export")
def cmd_export(
    output: Path = typer.Option(
        OUTPUT_DIR / "export.json",
        "-o",
        "--output",
        help="Output path",
    ),
) -> None:
    """Run list-tracks and save JSON."""
    run_lexicon_export(REPO_ROOT, output)


@app.command("analyze")
def cmd_analyze(
    export_path: Path = typer.Option(
        ...,
        "--export",
        help="Path to library export JSON",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    taxonomy: Path = typer.Option(DEFAULT_TAXONOMY, "--taxonomy"),
    aliases: Path = typer.Option(DEFAULT_ALIASES, "--aliases"),
    out_dir: Path = typer.Option(OUTPUT_DIR, "--out-dir"),
    backup_home: bool = typer.Option(
        False,
        "--backup-home",
        help=f"Also write ~/lexicon-genre-backup-{date.today().isoformat()}.json",
    ),
) -> None:
    """Build inventory, backup, batches from export."""
    analyze(export_path, taxonomy, aliases, out_dir, backup_home)


@app.command("ensure-categories")
def cmd_ensure_categories(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Create Genre tag categories via API."""
    ensure_categories(host, port)


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
    """Run lexicon bulk-update --dry-run on a batch file."""
    raise SystemExit(dry_run_batch(REPO_ROOT, batch))


@app.command("write-genre-native")
def cmd_write_genre_native(
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
        OUTPUT_DIR / "bulk_update_genre_native_field.json",
        "-o",
        "--output",
        help="bulk-update JSON output path",
    ),
    confidence: Confidence = typer.Option(
        Confidence.high,
        "--confidence",
        help="'high' = only high confidence (default); 'all' = high and medium",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="After writing file, run lexicon bulk-update --dry-run",
    ),
) -> None:
    """Write bulk-update JSON: native genre as Genre > Sub-genre > Sub-sub-genre."""
    write_genre_native(
        export_path,
        taxonomy,
        aliases,
        output,
        confidence.value,
        dry_run=dry_run,
        repo_root=REPO_ROOT,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
