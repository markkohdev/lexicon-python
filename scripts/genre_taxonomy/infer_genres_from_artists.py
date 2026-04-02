#!/usr/bin/env python3
"""Infer missing track genres from peer tracks that share artists (and title credits).

Reads ``export.json`` from ``genre_cleanup.py`` (expects ``title``, ``artist``, ``genre``, optional
``remixer`` / ``producer``). Writes ``lexicon bulk-update`` JSON and a review file for ambiguous rows.

Example::

  uv run python scripts/genre_taxonomy/infer_genres_from_artists.py run \\
      --export scripts/genre_taxonomy/output/export.json

  uv run python scripts/genre_taxonomy/infer_genres_from_artists.py review \\
      --review scripts/genre_taxonomy/output/infer_genres_review.json

Tune thresholds with ``--profile`` on ``run``, or use ``run-advanced`` for every knob.
"""

from __future__ import annotations

import importlib.util
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import typer
from InquirerPy import inquirer
from InquirerPy.base.control import Choice

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_TAXONOMY = REPO_ROOT / ".notes" / "genres.txt"
DEFAULT_ALIASES = SCRIPT_DIR / "genre_aliases.json"
DEFAULT_RESOLVED = DEFAULT_OUTPUT_DIR / "infer_genres_resolved.json"
_REL_SCRIPT = "scripts/genre_taxonomy/infer_genres_from_artists.py"

TitleParsingMode = Literal["off", "conservative", "aggressive"]
InferProfile = Literal["default", "strict", "permissive"]

_ROLE_ORDER = {"primary": 0, "featured": 1, "remixer": 2, "producer": 3, "from_title": 4}

_REVIEW_REASON_BLURB: dict[str, str] = {
    "tie": "Two or more genres scored near each other—the model refused to pick one.",
    "no_signal": "No contributor had enough tagged history, or everyone looked multi-genre.",
    "title_only_votes": "Only names from track titles voted; needs a field-artist vote unless you override.",
}

_TITLE_BLOCKLIST = frozenset(
    x.lower()
    for x in (
        "remix",
        "mix",
        "original",
        "extended",
        "radio",
        "version",
        "instrumental",
        "acapella",
        "a cappella",
        "live",
        "vocal",
        "clean",
        "dirty",
        "explicit",
        "club",
        "megamix",
        "reprise",
        "edit",
        "dub",
        "vip",
        "bootleg",
        "flip",
        "rework",
    )
)

_FEAT_SPLIT = re.compile(r"(?i)\s+(?:feat\.?|featuring|ft\.|w/)\s+(?:the\s+)?")
_COHEAD = re.compile(r"(?i)\s+(?:&|/|vs\.?)\s+|\s+x\s+")
_BRACKET_CHUNK = re.compile(r"\([^)]+\)|\[[^\]]+\]|\{[^}]+\}")


def strip_json_prefix(raw: str) -> str:
    i = raw.find("[")
    if i < 0:
        raise ValueError("No JSON array found in input")
    j = raw.rfind("]")
    if j < i:
        raise ValueError("Unclosed JSON array")
    return raw[i : j + 1]


def normalize_artist_name(s: str, *, strip_the: bool = False) -> str:
    if not s or not str(s).strip():
        return ""
    t = unicodedata.normalize("NFKC", str(s).strip())
    t = re.sub(r"\s+", " ", t)
    t = t.strip()
    if strip_the and t.lower().startswith("the "):
        t = t[4:].strip()
    return t.casefold()


def _better_role(a: str, b: str) -> str:
    return a if _ROLE_ORDER[a] <= _ROLE_ORDER[b] else b


def _split_coheadliners(segment: str) -> list[str]:
    segment = segment.strip()
    if not segment:
        return []
    parts = _COHEAD.split(segment)
    return [p.strip() for p in parts if p.strip()]


def parse_artist_field(artist: str, *, strip_the: bool = False) -> list[tuple[str, str]]:
    artist = (artist or "").strip()
    if not artist:
        return []
    parts = _FEAT_SPLIT.split(artist, maxsplit=1)
    head = parts[0].strip()
    tail = parts[1].strip() if len(parts) > 1 else None
    out: list[tuple[str, str]] = []
    for tok in _split_coheadliners(head) if head else []:
        n = normalize_artist_name(tok, strip_the=strip_the)
        if n:
            out.append((n, "primary"))
    if tail:
        for tok in _split_coheadliners(tail):
            n = normalize_artist_name(tok, strip_the=strip_the)
            if n:
                out.append((n, "featured"))
    return out


def parse_side_credit_field(value: str, role: str, *, strip_the: bool = False) -> list[tuple[str, str]]:
    value = (value or "").strip()
    if not value:
        return []
    pieces = re.split(r"(?i)\s*,\s*|\s+&\s+|\s+/\s+", value)
    out: list[tuple[str, str]] = []
    for piece in pieces:
        for tok in _split_coheadliners(piece.strip()):
            n = normalize_artist_name(tok, strip_the=strip_the)
            if n:
                out.append((n, role))
    return out


def _remix_name_prefix(inner: str) -> str | None:
    """Return text before the final remix-style token (greedy name, keyword at end)."""
    inner = inner.strip()
    if not inner:
        return None
    m = re.search(
        r"(?is)^(.+)\s+(?:remix|rework|vip|bootleg|flip|dub|edit|mix)\s*$",
        inner,
    )
    if not m:
        return None
    return m.group(1).strip()


def _title_bracket_remix_names(title: str) -> list[str]:
    out: list[str] = []
    for m in _BRACKET_CHUNK.finditer(title):
        inner = m.group(0)[1:-1].strip()
        prefix = _remix_name_prefix(inner)
        if not prefix:
            continue
        out.extend(_split_coheadliners(prefix))
    return out


def _title_hyphen_remix_tail(title: str) -> list[str]:
    if " - " not in title:
        return []
    tail = title.rsplit(" - ", 1)[1].strip()
    prefix = _remix_name_prefix(tail)
    if not prefix:
        return []
    return _split_coheadliners(prefix)


def _title_feat_names(title: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"(?i)\b(?:feat\.?|featuring|ft\.|w/)\s+(?:the\s+)?", title):
        rest = title[m.end() :]
        segment = re.split(r"[\(\[\{]", rest, 1)[0]
        segment = re.split(r"(?i)\s+(?:feat\.?|featuring|ft\.|w/)", segment, 1)[0]
        segment = segment.strip()
        for tok in _split_coheadliners(segment):
            if tok:
                out.append(tok)
    return out


def _accept_title_token(n: str, *, min_len: int, strip_the: bool) -> str | None:
    nn = normalize_artist_name(n, strip_the=strip_the)
    if not nn or len(nn) < min_len:
        return None
    for word in nn.split():
        if word in _TITLE_BLOCKLIST:
            return None
    if nn in _TITLE_BLOCKLIST:
        return None
    return nn


def parse_title_contributor_names(
    title: str,
    mode: TitleParsingMode,
    *,
    strip_the: bool,
    title_min_len: int,
) -> list[str]:
    if mode == "off" or not (title or "").strip():
        return []
    raw: list[str] = []
    if mode in ("conservative", "aggressive"):
        raw.extend(_title_bracket_remix_names(title))
        raw.extend(_title_hyphen_remix_tail(title))
    if mode == "aggressive":
        raw.extend(_title_feat_names(title))
    seen: set[str] = set()
    out: list[str] = []
    for r in raw:
        nn = _accept_title_token(r, min_len=title_min_len, strip_the=strip_the)
        if nn and nn not in seen:
            seen.add(nn)
            out.append(nn)
    return out


def merge_track_contributors(
    *,
    artist: str,
    remixer: str,
    producer: str,
    title: str,
    title_mode: TitleParsingMode,
    strip_the: bool,
    title_min_len: int,
) -> dict[str, str]:
    """Return contributor normalized name -> best role for one track."""
    merged: dict[str, str] = {}
    for n, r in parse_artist_field(artist, strip_the=strip_the):
        merged[n] = _better_role(merged.get(n, r), r)
    for n, r in parse_side_credit_field(remixer, "remixer", strip_the=strip_the):
        merged[n] = _better_role(merged.get(n, r), r)
    for n, r in parse_side_credit_field(producer, "producer", strip_the=strip_the):
        merged[n] = _better_role(merged.get(n, r), r)
    field_keys = set(merged.keys())
    for n in parse_title_contributor_names(
        title, title_mode, strip_the=strip_the, title_min_len=title_min_len
    ):
        if n not in field_keys:
            merged[n] = _better_role(merged.get(n, "from_title"), "from_title")
    return merged


def build_artist_genre_counts(
    tracks: list[dict[str, Any]],
    *,
    title_mode: TitleParsingMode,
    strip_the: bool,
    title_min_len: int,
) -> dict[str, Counter[str]]:
    """genre_counter per artist (one increment per tagged track that lists the artist)."""
    genre_by_artist: dict[str, Counter[str]] = defaultdict(Counter)
    for t in tracks:
        g = (t.get("genre") or "").strip()
        if not g:
            continue
        contribs = merge_track_contributors(
            artist=str(t.get("artist") or ""),
            remixer=str(t.get("remixer") or ""),
            producer=str(t.get("producer") or ""),
            title=str(t.get("title") or ""),
            title_mode=title_mode,
            strip_the=strip_the,
            title_min_len=title_min_len,
        )
        for n in contribs.keys():
            genre_by_artist[n][g] += 1
    return genre_by_artist


def artist_vote_genre(
    genre_counter: Counter[str],
    *,
    min_tagged_tracks: int,
    min_concentration: float,
) -> tuple[str | None, str]:
    total = sum(genre_counter.values())
    if total < min_tagged_tracks:
        return None, "insufficient_tracks"
    top_g, top_c = genre_counter.most_common(1)[0]
    if top_c / total < min_concentration:
        return None, "polygenre"
    return top_g, "ok"


@dataclass
class VoteDetail:
    artist: str
    role: str
    genre: str
    weight: float


@dataclass
class InferenceResult:
    genre: str | None
    reason: str
    scores: dict[str, float] = field(default_factory=dict)
    votes: list[VoteDetail] = field(default_factory=list)
    only_title_votes: bool = False


@dataclass(frozen=True)
class InferTuning:
    strip_the: bool = False
    title_min_len: int = 2
    min_tagged_tracks: int = 3
    min_concentration: float = 0.55
    margin: float = 0.1
    w_primary: float = 1.0
    w_featured: float = 0.5
    w_remixer: float = 0.25
    w_producer: float = 0.25
    w_title: float = 0.25
    require_non_title_vote: bool = False


def infer_tuning_for_profile(profile: InferProfile) -> InferTuning:
    base = InferTuning()
    if profile == "strict":
        return replace(
            base,
            require_non_title_vote=True,
            min_concentration=0.65,
            margin=0.05,
            min_tagged_tracks=4,
        )
    if profile == "permissive":
        return replace(
            base,
            min_tagged_tracks=2,
            min_concentration=0.45,
            margin=0.15,
        )
    return base


def infer_track_genre(
    contribs: dict[str, str],
    genre_by_artist: dict[str, Counter[str]],
    *,
    weights: dict[str, float],
    min_tagged_tracks: int,
    min_concentration: float,
    margin: float,
    require_non_title_vote: bool,
) -> InferenceResult:
    scores: dict[str, float] = defaultdict(float)
    votes: list[VoteDetail] = []
    for name, role in contribs.items():
        g, why = artist_vote_genre(
            genre_by_artist.get(name, Counter()),
            min_tagged_tracks=min_tagged_tracks,
            min_concentration=min_concentration,
        )
        if g is None:
            continue
        w = weights.get(role, 0.0)
        if w <= 0:
            continue
        scores[g] += w
        votes.append(VoteDetail(artist=name, role=role, genre=g, weight=w))
    only_title = bool(votes) and all(v.role == "from_title" for v in votes)
    if not scores:
        return InferenceResult(None, "no_signal", {}, [], only_title)
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    best_g, best_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0.0
    if second_s > 0 and (best_s - second_s) <= margin * max(best_s, 1e-9):
        return InferenceResult(None, "tie", dict(scores), votes, only_title)
    if require_non_title_vote and only_title:
        return InferenceResult(None, "title_only_votes", dict(scores), votes, only_title)
    return InferenceResult(best_g, "ok", dict(scores), votes, only_title)


def run_inference(
    tracks: list[dict[str, Any]],
    *,
    title_mode: TitleParsingMode,
    strip_the: bool,
    title_min_len: int,
    min_tagged_tracks: int,
    min_concentration: float,
    margin: float,
    w_primary: float,
    w_featured: float,
    w_remixer: float,
    w_producer: float,
    w_title: float,
    require_non_title_vote: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    weights = {
        "primary": w_primary,
        "featured": w_featured,
        "remixer": w_remixer,
        "producer": w_producer,
        "from_title": w_title,
    }
    genre_by_artist = build_artist_genre_counts(
        tracks,
        title_mode=title_mode,
        strip_the=strip_the,
        title_min_len=title_min_len,
    )
    bulk: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for t in tracks:
        g0 = (t.get("genre") or "").strip()
        if g0:
            continue
        contribs = merge_track_contributors(
            artist=str(t.get("artist") or ""),
            remixer=str(t.get("remixer") or ""),
            producer=str(t.get("producer") or ""),
            title=str(t.get("title") or ""),
            title_mode=title_mode,
            strip_the=strip_the,
            title_min_len=title_min_len,
        )
        res = infer_track_genre(
            contribs,
            genre_by_artist,
            weights=weights,
            min_tagged_tracks=min_tagged_tracks,
            min_concentration=min_concentration,
            margin=margin,
            require_non_title_vote=require_non_title_vote,
        )
        row: dict[str, Any] = {
            "id": t.get("id"),
            "title": t.get("title"),
            "artist": t.get("artist"),
            "remixer": t.get("remixer"),
            "producer": t.get("producer"),
            "contributors": contribs,
            "reason": res.reason,
            "scores": res.scores,
            "votes": [
                {"artist": v.artist, "role": v.role, "genre": v.genre, "weight": v.weight}
                for v in res.votes
            ],
            "only_title_votes": res.only_title_votes,
        }
        if res.genre is not None:
            bulk.append({"id": t["id"], "genre": res.genre})
            reasons["inferred"] += 1
        else:
            review.append(row)
            reasons[res.reason] += 1
    stats = {
        "bulk_count": len(bulk),
        "review_count": len(review),
        "reasons": dict(reasons),
        "artist_profiles": len(genre_by_artist),
    }
    return bulk, review, stats


def run_inference_with_tuning(
    tracks: list[dict[str, Any]],
    *,
    title_mode: TitleParsingMode,
    tuning: InferTuning,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return run_inference(
        tracks,
        title_mode=title_mode,
        strip_the=tuning.strip_the,
        title_min_len=tuning.title_min_len,
        min_tagged_tracks=tuning.min_tagged_tracks,
        min_concentration=tuning.min_concentration,
        margin=tuning.margin,
        w_primary=tuning.w_primary,
        w_featured=tuning.w_featured,
        w_remixer=tuning.w_remixer,
        w_producer=tuning.w_producer,
        w_title=tuning.w_title,
        require_non_title_vote=tuning.require_non_title_vote,
    )


def _read_id_genre_rows(path: Path) -> dict[int, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    if not isinstance(data, list):
        return out
    for row in data:
        if isinstance(row, dict) and "id" in row and "genre" in row:
            out[int(row["id"])] = str(row["genre"])
    return out


def _write_id_genre_rows(path: Path, mapping: dict[int, str]) -> None:
    rows = [{"id": tid, "genre": mapping[tid]} for tid in sorted(mapping.keys())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _load_genre_cleanup_module() -> Any:
    path = SCRIPT_DIR / "genre_cleanup.py"
    spec = importlib.util.spec_from_file_location("_genre_cleanup_peer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load genre helpers from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def review_infer_interactive(
    *,
    export_path: Path,
    review_path: Path,
    taxonomy_path: Path,
    aliases_path: Path,
    resolved_path: Path,
    bulk_path: Path | None,
) -> None:
    """TUI to assign genres for infer_genres_review.json rows (same vibe as genre_cleanup review-genres)."""
    gc = _load_genre_cleanup_module()
    tracks = json.loads(export_path.read_text(encoding="utf-8"))
    by_id: dict[Any, dict[str, Any]] = {t["id"]: t for t in tracks}
    queue_all: list[dict[str, Any]] = json.loads(review_path.read_text(encoding="utf-8"))
    if not isinstance(queue_all, list):
        raise ValueError(f"{review_path} must be a JSON array")

    tree_text = taxonomy_path.read_text(encoding="utf-8")
    paths = gc.parse_genres_txt(tree_text)
    taxonomy_strings = sorted({gc.path_to_field(p) for p in paths})
    by_token = gc._build_indices(paths)
    token_aliases, _exact = gc.load_aliases(aliases_path)

    resolved_map = _read_id_genre_rows(resolved_path)
    bulk_map: dict[int, str] = _read_id_genre_rows(bulk_path) if bulk_path else {}

    skipped_session: set[int] = set()

    typer.secho(
        "Interactive infer review — choices save immediately to the resolved file "
        f"({resolved_path.name}). Ctrl+C to stop.\n",
        fg=typer.colors.CYAN,
    )

    while True:
        pending = [
            row
            for row in queue_all
            if int(row["id"]) not in resolved_map and int(row["id"]) not in skipped_session
        ]
        if not pending:
            typer.secho("Nothing left to review (all rows resolved or skipped this session).", fg=typer.colors.GREEN)
            break

        item = pending[0]
        tid = int(item["id"])
        reason = str(item.get("reason") or "")
        blurb = _REVIEW_REASON_BLURB.get(reason, reason or "(unknown)")
        tr = by_id.get(tid, {})
        typer.echo("")
        typer.echo("=" * 72)
        typer.secho(f"Track id {tid}", bold=True)
        typer.echo(f"Title:   {(item.get('title') or tr.get('title') or '').strip()}")
        typer.echo(f"Artist:  {(item.get('artist') or tr.get('artist') or '').strip()}")
        rm = (item.get("remixer") or tr.get("remixer") or "").strip()
        if rm:
            typer.echo(f"Remixer: {rm}")
        typer.echo(f"Reason:  {reason} — {blurb}")

        contribs = item.get("contributors") or {}
        if isinstance(contribs, dict) and contribs:
            typer.echo("Contributors:")
            for name, role in sorted(contribs.items(), key=lambda x: (x[1], x[0])):
                typer.echo(f"  • [{role}] {name}")

        votes = item.get("votes") or []
        if isinstance(votes, list) and votes:
            typer.echo("Votes (library genre per contributor):")
            for v in votes[:12]:
                if isinstance(v, dict):
                    typer.echo(
                        f"  • {v.get('artist')} [{v.get('role')}] → {v.get('genre')} (w={v.get('weight')})"
                    )
            if len(votes) > 12:
                typer.echo(f"  … ({len(votes) - 12} more)")

        scores = item.get("scores") or {}
        if isinstance(scores, dict) and scores:
            typer.echo("Score totals (inference, not applied):")
            for g, sc in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:8]:
                typer.echo(f"  • {sc:.3f}  {g}")

        sorted_score_genres = [g for g, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))] if isinstance(scores, dict) else []

        top_guess = sorted_score_genres[0] if sorted_score_genres else ""
        hints = gc.candidate_paths_for_raw(top_guess, paths, by_token, token_aliases) if top_guess else []

        action = inquirer.select(
            message="What do you want to do?",
            choices=[
                Choice(
                    value="pick",
                    name="Pick canonical genre (fuzzy search taxonomy)",
                ),
                Choice(
                    value="scores",
                    name="Pick one of the score totals above (library genre strings)",
                ),
                Choice(
                    value="type",
                    name="Type canonical path (must match genres.txt, like genre_cleanup)",
                ),
                Choice(value="skip", name="Skip this track for this session"),
                Choice(value="quit", name="Quit reviewer"),
            ],
        ).execute()

        if action == "quit":
            typer.echo("Bye.")
            break
        if action == "skip":
            skipped_session.add(tid)
            continue

        if action == "scores":
            if not sorted_score_genres:
                typer.secho("No score breakdown for this row.", fg=typer.colors.YELLOW)
                continue
            chosen = inquirer.select(
                message="Which genre?",
                choices=[Choice(value=g, name=g) for g in sorted_score_genres],
            ).execute()
            resolved_map[tid] = chosen
            _write_id_genre_rows(resolved_path, resolved_map)
            if bulk_path is not None:
                bulk_map[tid] = chosen
                _write_id_genre_rows(bulk_path, bulk_map)
                typer.secho(f"Saved id {tid} → {chosen!r} (resolved + bulk)", fg=typer.colors.GREEN)
            else:
                typer.secho(f"Saved id {tid} → {chosen!r} (resolved only)", fg=typer.colors.GREEN)
            continue

        if action == "pick":
            initial = hints[0] if len(hints) == 1 else (hints[0] if hints else "")
            chosen = inquirer.fuzzy(
                message="Canonical path:",
                choices=taxonomy_strings,
                default=initial or "",
            ).execute()
            canon = gc.resolve_canonical_path_string(chosen, paths)
            if not canon:
                typer.secho("Could not resolve choice — try again.", fg=typer.colors.RED)
                continue
            resolved_map[tid] = canon
            _write_id_genre_rows(resolved_path, resolved_map)
            if bulk_path is not None:
                bulk_map[tid] = canon
                _write_id_genre_rows(bulk_path, bulk_map)
                typer.secho(f"Saved id {tid} → {canon!r} (resolved + bulk)", fg=typer.colors.GREEN)
            else:
                typer.secho(f"Saved id {tid} → {canon!r} (resolved only)", fg=typer.colors.GREEN)

        elif action == "type":
            typed = inquirer.text(
                message="Canonical path (use ' > ' between segments):",
                validate=lambda t: bool((t or "").strip())
                and gc.resolve_canonical_path_string(t, paths) is not None,
                invalid_message="Must match a path from genres.txt (spacing can differ slightly).",
            ).execute()
            canon = gc.resolve_canonical_path_string(typed, paths)
            if not canon:
                typer.secho("Invalid path.", fg=typer.colors.RED)
                continue
            resolved_map[tid] = canon
            _write_id_genre_rows(resolved_path, resolved_map)
            if bulk_path is not None:
                bulk_map[tid] = canon
                _write_id_genre_rows(bulk_path, bulk_map)
                typer.secho(f"Saved id {tid} → {canon!r} (resolved + bulk)", fg=typer.colors.GREEN)
            else:
                typer.secho(f"Saved id {tid} → {canon!r} (resolved only)", fg=typer.colors.GREEN)


app = typer.Typer(help="Infer missing genres from artist/title overlap with tagged tracks")


@app.command("about", help="Show typical commands.")
def cmd_about() -> None:
    typer.echo(
        "  run       — build bulk + review JSON from export (see run --help)\n"
        "  review    — interactive TUI for review rows (like genre_cleanup review-genres)\n"
        "  run-advanced — same as run with every tuning flag exposed\n"
    )


@app.command("run")
def cmd_run(
    export_path: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "export.json",
        "--export",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    out_bulk: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "bulk_update_infer_genres.json",
        "--out-bulk",
        help="High-confidence rows for lexicon bulk-update",
    ),
    out_review: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "infer_genres_review.json",
        "--out-review",
        help="Uncertain rows to open in ``review``",
    ),
    stats_out: Path | None = typer.Option(
        None,
        "--stats-out",
        help="Optional JSON summary (counts and reason breakdown)",
    ),
    profile: InferProfile = typer.Option(
        "default",
        "--profile",
        help="default=balanced | strict=fewer auto-fills, higher bar | permissive=more rows, more risk",
    ),
    title_parsing: TitleParsingMode = typer.Option(
        "conservative",
        "--title-parsing",
        help="Parse remix/featuring cues from titles: off | conservative | aggressive",
    ),
) -> None:
    """Build bulk-update JSON + review queue from export (sensible defaults; use --profile to adjust)."""
    tuning = infer_tuning_for_profile(profile)
    _cmd_run_impl(export_path, out_bulk, out_review, stats_out, title_parsing, tuning)


@app.command("run-advanced")
def cmd_run_advanced(
    export_path: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "export.json",
        "--export",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    out_bulk: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "bulk_update_infer_genres.json",
        "--out-bulk",
    ),
    out_review: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "infer_genres_review.json",
        "--out-review",
    ),
    stats_out: Path | None = typer.Option(None, "--stats-out"),
    title_parsing: TitleParsingMode = typer.Option("conservative", "--title-parsing"),
    strip_the: bool = typer.Option(False, "--strip-the"),
    title_min_len: int = typer.Option(2, "--title-min-len"),
    min_tagged_tracks: int = typer.Option(3, "--min-tagged-tracks"),
    min_concentration: float = typer.Option(0.55, "--min-concentration"),
    margin: float = typer.Option(0.1, "--margin"),
    w_primary: float = typer.Option(1.0, "--w-primary"),
    w_featured: float = typer.Option(0.5, "--w-featured"),
    w_remixer: float = typer.Option(0.25, "--w-remixer"),
    w_producer: float = typer.Option(0.25, "--w-producer"),
    w_title: float = typer.Option(0.25, "--w-title"),
    require_non_title_vote: bool = typer.Option(False, "--require-non-title-vote"),
) -> None:
    """Same as ``run`` but exposes every weight and threshold (for power users)."""
    tuning = InferTuning(
        strip_the=strip_the,
        title_min_len=title_min_len,
        min_tagged_tracks=min_tagged_tracks,
        min_concentration=min_concentration,
        margin=margin,
        w_primary=w_primary,
        w_featured=w_featured,
        w_remixer=w_remixer,
        w_producer=w_producer,
        w_title=w_title,
        require_non_title_vote=require_non_title_vote,
    )
    _cmd_run_impl(export_path, out_bulk, out_review, stats_out, title_parsing, tuning)


def _cmd_run_impl(
    export_path: Path,
    out_bulk: Path,
    out_review: Path,
    stats_out: Path | None,
    title_parsing: TitleParsingMode,
    tuning: InferTuning,
) -> None:
    data = json.loads(export_path.read_text(encoding="utf-8"))
    bulk, review, stats = run_inference_with_tuning(data, title_mode=title_parsing, tuning=tuning)
    out_bulk.parent.mkdir(parents=True, exist_ok=True)
    out_bulk.write_text(json.dumps(bulk, indent=2), encoding="utf-8")
    out_review.parent.mkdir(parents=True, exist_ok=True)
    out_review.write_text(json.dumps(review, indent=2), encoding="utf-8")
    print(f"Wrote {len(bulk)} bulk rows to {out_bulk}")
    print(f"Wrote {len(review)} review rows to {out_review}")
    print(f"Stats: {stats}")
    print(
        "\nNext:\n"
        f"  High-confidence updates: uv run lexicon bulk-update --dry-run --file {out_bulk}\n"
        f"  Uncertain rows (TUI):     uv run python {_REL_SCRIPT} review "
        f"--export {export_path} --review {out_review}\n"
    )
    if stats_out is not None:
        stats_out.parent.mkdir(parents=True, exist_ok=True)
        stats_out.write_text(json.dumps(stats, indent=2), encoding="utf-8")


@app.command("review")
def cmd_review(
    export_path: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "export.json",
        "--export",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Same export.json used for ``run``",
    ),
    review_path: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "infer_genres_review.json",
        "--review",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    taxonomy: Path = typer.Option(DEFAULT_TAXONOMY, "--taxonomy", exists=True),
    aliases: Path = typer.Option(DEFAULT_ALIASES, "--aliases", help="genre_aliases.json for matcher hints"),
    resolved_out: Path = typer.Option(
        DEFAULT_RESOLVED,
        "--resolved-out",
        help="Write resolved {id, genre} rows here as you work",
    ),
    bulk: Path = typer.Option(
        DEFAULT_OUTPUT_DIR / "bulk_update_infer_genres.json",
        "--bulk",
        help="Bulk-update JSON to merge picks into (when merge-bulk is on)",
    ),
    merge_bulk: bool = typer.Option(
        True,
        "--merge-bulk/--no-merge-bulk",
        help="If enabled, each pick also updates --bulk so one file is ready for lexicon bulk-update",
    ),
) -> None:
    """Interactive review for infer_genres_review.json (InquirerPy, like genre_cleanup ``review-genres``)."""
    bulk_path = bulk if merge_bulk else None
    review_infer_interactive(
        export_path=export_path,
        review_path=review_path,
        taxonomy_path=taxonomy,
        aliases_path=aliases,
        resolved_path=resolved_out,
        bulk_path=bulk_path,
    )
    if not merge_bulk:
        print(
            f"\nResolutions saved under {resolved_out}. Merge into your bulk file manually, "
            "or re-run review with --merge-bulk."
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
