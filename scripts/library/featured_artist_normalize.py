#!/usr/bin/env python3
"""Normalize featured-artist metadata: title ``(feat. …)``, comma-separated ``artist``, and ``remixer``.

Reads a ``list-tracks`` JSON export (optional leading banner line), writes ``lexicon bulk-update``
JSON with ``id``, ``title``, ``artist``, and ``remixer`` **only for tracks where at least one of
those fields changed**, plus an optional review file (aligned to those changed rows when present).

Dry-run against Lexicon (no writes until you apply)::

  uv run python scripts/library/featured_artist_normalize.py \\
      --input exports/tracks.json \\
      --output scripts/library/output/featured_normalize_edits.json \\
      --review scripts/library/output/featured_normalize_review.json

  uv run lexicon bulk-update --file scripts/library/output/featured_normalize_edits.json --dry-run

Apply after reviewing the diff::

  uv run lexicon bulk-update --file scripts/library/output/featured_normalize_edits.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- Trailing platform IDs (numeric 6+, or 11-char YouTube-like) -----------------
_RE_TRAIL_NUMERIC = re.compile(r"-(\d{6,})$")
_RE_TRAIL_YT11 = re.compile(r"-([A-Za-z0-9_-]{11})$")

# --- Junk remixer (domain / URL) -------------------------------------------------
_RE_DOMAINISH = re.compile(
    r"(?i)(?:https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|io|co|fm|tv|dj)\b)"
)

# --- Split artist on feat / ft / featuring ---------------------------------------
_RE_FEAT_SPLIT = re.compile(
    r"(?i)\s+(?:feat\.?|featuring|ft\.?)\s+(?=.)(.+)$",
)
# Avoid matching ``feat`` inside words like *Feather* (``\bfeat`` is wrong there).
_RE_FEAT_BARE_TITLE = re.compile(
    r"(?i)(?:^|\s)((?:feat\.|ft\.)\s*(?=\S)|(?:feat|ft)\s+)",
)

# Mid-title: " … featuring Name" before "(" or end (non-greedy name)
_RE_MID_FEATURING = re.compile(
    r"(?i)^(.+?)\s+featuring\s+(.+?)(?=\s*\(|$)\s*$",
)

# Parenthetical (with X) -> feat
_RE_PAREN_WITH = re.compile(r"(?i)\(\s*with\s+([^)]+)\)")
_RE_PAREN_FEAT = re.compile(r"(?i)\(\s*feat\.?\s+([^)]+)\)")
_RE_PAREN_FT = re.compile(r"(?i)\(\s*ft\.?\s+([^)]+)\)")
_RE_PAREN_FEATURING = re.compile(r"(?i)\(\s*featuring\s+([^)]+)\)")

# Remix-ish parenthetical content (keep as version suffix). Avoid bare "mix" (e.g. Extended Mix).
_RE_REMIXISH = re.compile(
    r"(?i)\b(remix|re-?mix|edit|vip|bootleg|flip|rework|version|dub|instrumental)\b"
)

# Collaboration split for mains (when no feat keyword in artist)
_RE_SPLIT_X = re.compile(r"(?i)\s+x\s+")
_RE_SPLIT_SLASH = re.compile(r"\s*/\s*")
_RE_SPLIT_COMMA = re.compile(r"\s*,\s*")
_RE_SPLIT_AND = re.compile(r"(?i)\s+and\s+")
_RE_SPLIT_AMP = re.compile(r"\s+&\s+")


def _strip_trailing_platform_ids(title: str) -> tuple[str, str | None]:
    """Strip ``-digits6+`` or ``-11char`` YouTube-like id from end of title."""
    t = title.rstrip()
    removed: str | None = None
    while True:
        m = _RE_TRAIL_NUMERIC.search(t)
        if m:
            removed = m.group(0)
            t = t[: m.start()].rstrip()
            continue
        m2 = _RE_TRAIL_YT11.search(t)
        if m2:
            removed = m2.group(0)
            t = t[: m2.start()].rstrip()
            continue
        break
    return t, removed


def remixer_is_junk(s: str) -> bool:
    if not (s or "").strip():
        return False
    return bool(_RE_DOMAINISH.search(s.strip()))


def split_remixer_tokens(s: str) -> list[str]:
    if not (s or "").strip():
        return []
    parts: list[str] = []
    for chunk in re.split(r",", s):
        for piece in _RE_SPLIT_AMP.split(chunk):
            p = piece.strip()
            if p:
                parts.append(p)
    return parts


def canonical_remixer_string(tokens: list[str]) -> str:
    """Comma-separated, de-duplicated, stable order."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        key = t.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(t.strip())
    return ", ".join(out)


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def names_equal(a: str, b: str) -> bool:
    return _norm_name(a).casefold() == _norm_name(b).casefold()


def name_in_list(n: str, lst: list[str]) -> bool:
    return any(names_equal(n, x) for x in lst)


def split_mains_blob(blob: str) -> list[str]:
    """Split collaboration mains; keep ``A & The B`` as one when RHS starts with *The*."""
    b = _norm_name(blob)
    if not b:
        return []

    if _RE_SPLIT_COMMA.search(b):
        return [_norm_name(x) for x in _RE_SPLIT_COMMA.split(b) if x.strip()]

    if _RE_SPLIT_X.search(b):
        return [_norm_name(x) for x in _RE_SPLIT_X.split(b) if x.strip()]

    if _RE_SPLIT_SLASH.search(b):
        return [_norm_name(x) for x in _RE_SPLIT_SLASH.split(b) if x.strip()]

    if _RE_SPLIT_AND.search(b):
        return [_norm_name(x) for x in _RE_SPLIT_AND.split(b) if x.strip()]

    if _RE_SPLIT_AMP.search(b):
        left, right = _RE_SPLIT_AMP.split(b, 1)
        if re.match(r"(?i)^the\b", right.strip()):
            return [b]
        return [_norm_name(left), _norm_name(right)]

    return [b]


def split_featured_blob(blob: str) -> list[str]:
    """Split featured guests on & and 'and'."""
    b = _norm_name(blob)
    if not b:
        return []
    parts = re.split(r"(?i)\s+&\s+|\s+and\s+", b)
    return [_norm_name(p) for p in parts if p.strip()]


def extract_trailing_paren_chain(title: str) -> tuple[str, list[str]]:
    """Pop ``(inner)`` groups from the right; return (core, inners left-to-right)."""
    remaining = title.rstrip()
    inners_rev: list[str] = []
    while True:
        m = re.search(r"\s*\(([^()]*)\)\s*$", remaining)
        if not m:
            break
        inners_rev.append(m.group(1).strip())
        remaining = remaining[: m.start()].rstrip()
    return remaining.strip(), list(reversed(inners_rev))


def classify_paren_inner(inner: str) -> str:
    """Return 'feat', 'remix', or 'other'."""
    il = inner.strip()
    if re.match(r"(?i)^(?:feat\.?|ft\.?|featuring)\s*", il):
        return "feat"
    if re.match(r"(?i)^with\s+", il):
        return "feat"
    if _RE_REMIXISH.search(il):
        return "remix"
    return "other"


def parse_feat_inner(inner: str) -> list[str]:
    """Guest names from ``(feat X)``, ``(ft X)``, ``(with X)``, etc."""
    il = inner.strip()
    m = re.match(r"(?i)^(?:feat\.?|ft\.?|featuring)\s*(.+)$", il)
    if m:
        body = m.group(1).strip()
        return split_featured_blob(body)
    m2 = re.match(r"(?i)^with\s+(.+)$", il)
    if m2:
        return split_featured_blob(m2.group(1).strip())
    return []


def extract_bare_feat_from_core(core: str) -> tuple[str, list[str]]:
    """Find last `` feat. `` / `` ft. `` segment in core; return (core_without, guests)."""
    matches = list(_RE_FEAT_BARE_TITLE.finditer(core))
    if not matches:
        return core, []
    m = matches[-1]
    before = core[: m.start()].rstrip()
    after = core[m.end() :].strip()
    # Stop featured span at next parenthesis start (shouldn't be in core)
    if "(" in after:
        after = after.split("(", 1)[0].strip()
    guests = split_featured_blob(after) if after else []
    return before, guests


def extract_mid_title_featuring(core: str) -> tuple[str, list[str], bool]:
    """``Africa (My No. 1) featuring The Horns`` -> core without 'featuring' tail, guests."""
    m = _RE_MID_FEATURING.match(core.strip())
    if not m:
        return core, [], False
    left, right = m.group(1).strip(), m.group(2).strip()
    guests = split_featured_blob(right) if right else []
    return left, guests, True


def merge_unique_ordered(existing: list[str], add: list[str]) -> list[str]:
    out = list(existing)
    for a in add:
        a = _norm_name(a)
        if not a:
            continue
        if not name_in_list(a, out):
            out.append(a)
    return out


@dataclass
class NormalizeResult:
    title: str
    artist: str
    remixer: str
    review: list[str] = field(default_factory=list)


def _apply_597_rule(artist: str, title_guests: list[str]) -> tuple[list[str], list[str]] | None:
    """If title names one featured guest and artist is ``A & B``, infer mains + featured."""
    if len(title_guests) != 1:
        return None
    tg = title_guests[0]
    m = re.match(r"^(.+?)\s*&\s*(.+)$", artist.strip())
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    if names_equal(tg, a):
        return [b], [a]
    if names_equal(tg, b):
        return [a], [b]
    return None


def _comma_parts_subtract_featured(
    artist_raw: str, title_featured_hint: list[str]
) -> tuple[list[str], list[str]] | None:
    """If artist is comma-separated and title lists featured names, split mains vs featured."""
    if not title_featured_hint or "," not in artist_raw:
        return None
    parts = [_norm_name(x) for x in _RE_SPLIT_COMMA.split(artist_raw) if x.strip()]
    if len(parts) < 2:
        return None
    featured_hit: list[str] = []
    mains: list[str] = []
    for p in parts:
        if any(names_equal(p, h) for h in title_featured_hint):
            featured_hit.append(p)
        else:
            mains.append(p)
    if not featured_hit:
        return None
    return mains, featured_hit


def _reorder_mains_matching_remixer(mains: list[str], remix_tokens: list[str]) -> list[str]:
    """Put segments that match a remixer token after other mains (original-first, remixer-last)."""
    if not mains or not remix_tokens:
        return mains
    kept: list[str] = []
    moved: list[str] = []
    for m in mains:
        if any(names_equal(m, r) for r in remix_tokens):
            moved.append(m)
        else:
            kept.append(m)
    return kept + moved


def _parse_artist_field(
    artist_raw: str,
    title_featured_hint: list[str],
    _review: list[str],
) -> tuple[list[str], list[str]]:
    """Return (mains, featured_from_artist_field)."""
    ar = artist_raw.strip()
    if not ar:
        return [], []

    mfeat = _RE_FEAT_SPLIT.search(ar)
    if mfeat:
        left = ar[: mfeat.start()].strip()
        right = mfeat.group(1).strip()
        mains = split_mains_blob(left) if left else []
        featured = split_featured_blob(right)
        return mains, featured

    rule = _apply_597_rule(ar, title_featured_hint)
    if rule:
        return rule

    # (with X) hint: remove featured name from "Main and Featured" style
    if len(title_featured_hint) == 1:
        fh = title_featured_hint[0]
        if _RE_SPLIT_AND.search(ar):
            parts = [_norm_name(x) for x in _RE_SPLIT_AND.split(ar)]
            if len(parts) == 2:
                if names_equal(parts[1], fh):
                    return [parts[0]], [parts[1]]
                if names_equal(parts[0], fh):
                    return [parts[1]], [parts[0]]

    sub = _comma_parts_subtract_featured(ar, title_featured_hint)
    if sub:
        return sub

    return split_mains_blob(ar), []


def _remix_tokens_from_paren_inners(inners: list[str]) -> list[str]:
    """Heuristic: remixer names from ``(Name Remix)`` — use full inner for display."""
    out: list[str] = []
    for inner in inners:
        if classify_paren_inner(inner) == "remix":
            out.append(inner.strip())
    return out


def _remix_redundant_with_field(short: str, full_inner: str, field_tokens: list[str]) -> bool:
    for t in field_tokens:
        if names_equal(short, t) or names_equal(full_inner, t):
            return True
        ts, sf = t.casefold(), short.casefold()
        if sf == ts or sf.startswith(ts + " ") or full_inner.casefold().startswith(ts + " "):
            return True
    return False


def remix_names_for_mains_reorder(
    remixer_field_tokens: list[str], remix_inners: list[str]
) -> list[str]:
    """Tokens used to detect ``main==remixer`` comma billing (e.g. Tinlicker vs alt-J)."""
    names: list[str] = []
    for t in remixer_field_tokens:
        if t.strip():
            names.append(t.strip())
    for inner in remix_inners:
        if classify_paren_inner(inner) != "remix":
            continue
        m = re.match(
            r"(?i)^(.+?)\s+(?:remix|re-?mix|mix|vip|edit|version|bootleg|flip|rework)\s*$",
            inner.strip(),
        )
        if m:
            names.append(m.group(1).strip())
        else:
            names.append(inner.strip())
    return canonical_remixer_string(names).split(", ") if names else []


def rebuild_title(
    core_base: str,
    featured: list[str],
    remix_inners: list[str],
    other_inners: list[str],
) -> str:
    parts: list[str] = [_norm_name(core_base)] if core_base.strip() else []
    if featured:
        if len(featured) == 1:
            parts.append(f"(feat. {_norm_name(featured[0])})")
        else:
            feat_body = " & ".join(_norm_name(f) for f in featured)
            parts.append(f"(feat. {feat_body})")
    for r in remix_inners:
        parts.append(f"({_norm_name(r)})")
    for o in other_inners:
        parts.append(f"({_norm_name(o)})")
    return " ".join(parts).strip()


def normalize_track(
    title: str,
    artist: str,
    remixer: str,
) -> NormalizeResult:
    review: list[str] = []
    t_raw = title or ""
    a_raw = artist or ""
    r_raw = (remixer or "").strip()

    t, id_removed = _strip_trailing_platform_ids(t_raw)
    if id_removed:
        review.append(f"stripped_title_id:{id_removed}")

    if remixer_is_junk(r_raw):
        r_raw = ""
        review.append("cleared_junk_remixer")

    remixer_tokens = split_remixer_tokens(r_raw)

    core, paren_inners = extract_trailing_paren_chain(t)

    feat_inners: list[str] = []
    remix_inners: list[str] = []
    other_inners: list[str] = []
    for inner in paren_inners:
        cls = classify_paren_inner(inner)
        if cls == "feat":
            feat_inners.append(inner)
        elif cls == "remix":
            remix_inners.append(inner)
        else:
            other_inners.append(inner)

    featured_from_title: list[str] = []
    for inner in feat_inners:
        featured_from_title.extend(parse_feat_inner(inner))

    # Bare (with X) still inside core? e.g. not only trailing chain
    for m in _RE_PAREN_WITH.finditer(core):
        featured_from_title.extend(split_featured_blob(m.group(1)))
    core = _RE_PAREN_WITH.sub("", core).strip()
    for m in _RE_PAREN_FEAT.finditer(core):
        featured_from_title.extend(split_featured_blob(m.group(1)))
    core = _RE_PAREN_FEAT.sub("", core).strip()
    for m in _RE_PAREN_FT.finditer(core):
        featured_from_title.extend(split_featured_blob(m.group(1)))
    core = _RE_PAREN_FT.sub("", core).strip()
    for m in _RE_PAREN_FEATURING.finditer(core):
        featured_from_title.extend(split_featured_blob(m.group(1)))
    core = _RE_PAREN_FEATURING.sub("", core).strip()

    core, mid_guests, had_mid = extract_mid_title_featuring(core)
    if had_mid:
        featured_from_title = merge_unique_ordered(featured_from_title, mid_guests)

    core, bare_guests = extract_bare_feat_from_core(core)
    featured_from_title = merge_unique_ordered(featured_from_title, bare_guests)

    featured_from_title = [_norm_name(x) for x in featured_from_title if x.strip()]
    had_title_feat_source = bool(featured_from_title)

    mains, featured_from_artist = _parse_artist_field(a_raw, featured_from_title, review)

    remix_from_title = _remix_tokens_from_paren_inners(remix_inners)

    all_remix_tokens = list(remixer_tokens)
    for rt in remix_from_title:
        full_inner = rt.strip()
        short = full_inner
        mrm = re.match(
            r"(?i)^(.+?)\s+(?:remix|re-?mix|mix|vip|edit|version|bootleg|flip|rework)\s*$",
            full_inner,
        )
        if mrm:
            short = mrm.group(1).strip()
        if _remix_redundant_with_field(short, full_inner, all_remix_tokens):
            continue
        if not name_in_list(short, all_remix_tokens) and not name_in_list(full_inner, all_remix_tokens):
            all_remix_tokens.append(short if mrm else full_inner)

    canonical_rem = canonical_remixer_string(all_remix_tokens)

    reorder_hints = remix_names_for_mains_reorder(remixer_tokens, remix_inners)
    mains = _reorder_mains_matching_remixer(mains, reorder_hints)

    featured = merge_unique_ordered(featured_from_artist, featured_from_title)

    # Artist tail: append remixer tokens that are not already a main artist name
    mains_nf = [_norm_name(m) for m in mains if m.strip()]
    featured_nf = [_norm_name(f) for f in featured if f.strip()]

    artist_segments: list[str] = list(mains_nf)
    artist_segments.extend(featured_nf)

    for tok in split_remixer_tokens(canonical_rem) if canonical_rem else []:
        if not tok:
            continue
        if name_in_list(tok, mains_nf):
            continue
        if name_in_list(tok, artist_segments):
            continue
        artist_segments.append(_norm_name(tok))

    new_artist = ", ".join(artist_segments)

    # Do not inject ``(feat. …)`` into the title when guests only come from the artist
    # field and the title already has version/remix parentheses (golden: 844).
    title_feat_block = featured_nf
    if (
        not had_title_feat_source
        and featured_from_artist
        and (remix_inners or other_inners)
    ):
        title_feat_block = []

    new_title = rebuild_title(core, title_feat_block, remix_inners, other_inners)

    return NormalizeResult(
        title=new_title,
        artist=new_artist,
        remixer=canonical_rem if canonical_rem else "",
        review=review,
    )


def load_tracks_json(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    idx = raw.find("[")
    if idx == -1:
        raise ValueError(f"No JSON array found in {path}")
    data = json.loads(raw[idx:])
    if not isinstance(data, list):
        raise ValueError("Root JSON must be an array")
    return data


def run_cli() -> None:
    p = argparse.ArgumentParser(description="Normalize feat./artist/remixer for Lexicon bulk-update.")
    p.add_argument("--input", "-i", type=Path, required=True, help="Export JSON from list-tracks")
    p.add_argument("--output", "-o", type=Path, required=True, help="bulk-update JSON output path")
    p.add_argument(
        "--review",
        type=Path,
        default=None,
        help="Optional JSON lines of id + review reasons",
    )
    p.add_argument("--limit", type=int, default=None, help="Process only first N tracks")
    args = p.parse_args()

    tracks = load_tracks_json(args.input)
    if args.limit is not None:
        tracks = tracks[: args.limit]

    edits: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for tr in tracks:
        tid = tr.get("id")
        if tid is None:
            continue
        title = str(tr.get("title") or "")
        artist = str(tr.get("artist") or "")
        remixer = str(tr.get("remixer") or "").strip()

        res = normalize_track(title, artist, remixer)
        changed = (
            res.title != title
            or res.artist != artist
            or res.remixer != remixer
        )
        if not changed:
            continue

        edits.append(
            {
                "id": tid,
                "title": res.title,
                "artist": res.artist,
                "remixer": res.remixer,
            }
        )
        if res.review:
            review_rows.append({"id": tid, "reasons": res.review})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(edits, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.review is not None:
        args.review.parent.mkdir(parents=True, exist_ok=True)
        args.review.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in review_rows) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    run_cli()
