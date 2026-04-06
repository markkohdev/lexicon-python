#!/usr/bin/env python3
"""Fill missing native genres using MusicBrainz + Wikipedia, mapped to ``.notes/genres.txt``.

Fetches tracks with empty genre via the Lexicon API (same filter as
``lexicon search-tracks --filter genre=NONE``), builds evidence per primary artist,
scores taxonomy paths, and writes:

* ``missing_genres_bulk_update.json`` — ``lexicon bulk-update`` rows (id + genre).
* ``missing_genres_review.json`` — per-track provenance, confidence, alternates.

Respect MusicBrainz rate limits (default 1.1s between MB calls). Re-runs use
``.mb_genre_cache.json`` under the output directory.

Example::

  uv run python scripts/library/infer_missing_genres_web.py \\
    --output-dir scripts/library/output

  uv run lexicon bulk-update --file scripts/library/output/missing_genres_bulk_update.json --dry-run
"""

from __future__ import annotations

import importlib.util
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
import typer

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAXONOMY = REPO_ROOT / ".notes" / "genres.txt"
DEFAULT_OUT = REPO_ROOT / "scripts/library" / "output"

_MB_UA = "lexicon-python-infer-genres/1.0 (https://github.com/photonicvelocity/lexicon-python)"
_WIKI_HEADERS = {"User-Agent": _MB_UA}
_MB_LAST = 0.0

# Strong substring / phrase hints before hitting the network
_TITLE_ARTIST_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("dubstep",), "Breakbeat > Dubstep"),
    (("drumstep",), "Breakbeat > Dubstep > Drumstep"),
    (("riddim",), "Breakbeat > Dubstep > Riddim"),
    (("drum and bass", "drum & bass", "dnb", "jungle"), "Breakbeat > Drum & Bass"),
    (("liquid dnb", "liquid drum"), "Breakbeat > Drum & Bass > Liquid"),
    (("techno",), "Techno"),
    (("hard techno",), "Techno > Hard Techno"),
    (("melodic techno",), "Techno > Melodic Techno"),
    (("deep techno",), "Techno > Deep"),
    (("house", "nudisco", "nu disco"), "House"),
    (("deep house",), "House > Deep House"),
    (("tech house",), "House > Tech House"),
    (("progressive house",), "House > Progressive House"),
    (("future house",), "House > Mainstage > Future House"),
    (("bass house",), "House > Bass House"),
    (("tropical house",), "House > Tropical House"),
    (("garage", "2-step", "2step", "uk garage"), "House > Garage > UK Garage"),
    (("trance",), "Trance"),
    (("psy", "psytrance", "psychedelic trance"), "Trance > Psy-Trance"),
    (("uplifting trance",), "Trance > Uplifting Trance"),
    (("future bass",), "Bass > Future Bass"),
    (("trap",), "Breakbeat > Trap"),
    (("hip hop", "hip-hop", "rap ", "grime", "eskibeat"), "Breakbeat > Hip-Hop"),
    (("funk", "disco"), "Funk > Disco > Nu Disco"),
    (("downtempo", "chillout", "chill out"), "Electronica > Downtempo"),
    (("ambient",), "Electronica > Ambient / Experimental"),
    (("trip hop", "trip-hop"), "Electronica > Trip Hop"),
    (("electro swing",), "Electro > Electro Swing"),
    (("complextro",), "Electro > Complextro"),
    (("moombahton", "global bass"), "Bass > Global Bass"),
    (("hardstyle",), "Hard dance > Hardstyle"),
    (("reggaeton",), "Global / World > Latin > Reggaeton"),
    (("afro house",), "House > Afro House"),
    (("melodic house",), "House > Melodic House"),
    (("organic house",), "House > Organic House"),
]

_SYNONYM_FRAGMENTS: dict[str, str] = {
    "grime": "Breakbeat > Hip-Hop",
    "edm": "House",
    "electronica": "Electronica",
    "electronic dance music": "House",
    "uk bass": "Bass",
    "breakbeat": "Breakbeat",
    "breakbeats": "Breakbeat",
    "glitch hop": "Breakbeat > Glitch Hop",
    "melodic dubstep": "Breakbeat > Dubstep > Melodic Dubstep",
    "jackin house": "House > Funky House",
    "soulful house": "House > Soulful House",
    "slap house": "House > Slap House",
    "indie dance": "Electro > Indie Dance",
    "nu jazz": "Jazz > Nu Jazz",
    "r&b": "R&B",
    "rhythm and blues": "R&B",
    "dancehall": "Reggae / Dancehall > Dancehall",
    "reggae": "Reggae / Dancehall > Reggae",
}


def _load_genre_cleanup() -> Any:
    path = REPO_ROOT / "scripts" / "genre_taxonomy" / "genre_cleanup.py"
    spec = importlib.util.spec_from_file_location("genre_cleanup_lib", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _feat_head(artist: str) -> str:
    if not artist:
        return ""
    parts = re.split(r"(?i)\s+(?:feat\.?|featuring|ft\.|w/)\s+", artist.strip(), maxsplit=1)
    head = (parts[0] or "").strip()
    head = re.split(r"(?i)\s*,\s*", head, maxsplit=1)[0].strip()
    return head


def _mb_throttle(gap: float) -> None:
    global _MB_LAST
    now = time.monotonic()
    wait = gap - (now - _MB_LAST)
    if wait > 0:
        time.sleep(wait)
    _MB_LAST = time.monotonic()


def _mb_get(path_qs: str, session: requests.Session, gap: float) -> dict[str, Any] | None:
    _mb_throttle(gap)
    url = f"https://musicbrainz.org/ws/2/{path_qs}"
    r = session.get(
        url,
        headers={
            "User-Agent": _MB_UA,
            "Accept": "application/json",
        },
        timeout=30,
    )
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except json.JSONDecodeError:
        return None


def _mb_artist_evidence(
    artist: str,
    session: requests.Session,
    gap: float,
    cache: dict[str, Any],
    dirty: list[bool],
) -> str:
    key = artist.casefold().strip()
    if not key:
        return ""
    hit = cache.get(key)
    if isinstance(hit, str):
        return hit

    q = urllib.parse.quote(f'artist:"{artist}"', safe="")
    data = _mb_get(f"artist?query={q}&fmt=json&limit=3", session, gap)
    if not isinstance(data, dict):
        cache[key] = ""
        dirty[0] = True
        return ""
    artists = data.get("artists")
    if not isinstance(artists, list) or not artists:
        fallback_q = urllib.parse.quote(artist, safe="")
        data = _mb_get(f"artist?query={fallback_q}&fmt=json&limit=3", session, gap)
        artists = data.get("artists") if isinstance(data, dict) else None
    if not isinstance(artists, list) or not artists:
        cache[key] = ""
        dirty[0] = True
        return ""
    mbid = artists[0].get("id")
    if not isinstance(mbid, str):
        cache[key] = ""
        dirty[0] = True
        return ""

    detail = _mb_get(f"artist/{mbid}?inc=tags+genres&fmt=json", session, gap)
    bits: list[str] = []
    if isinstance(detail, dict):
        for tag in detail.get("genres") or []:
            if isinstance(tag, dict) and tag.get("name"):
                bits.append(str(tag["name"]))
        for tag in detail.get("tags") or []:
            if isinstance(tag, dict) and tag.get("name"):
                bits.append(str(tag["name"]))
    evidence = " ".join(bits).lower()
    cache[key] = evidence
    dirty[0] = True
    return evidence


def _wiki_evidence(
    artist: str,
    session: requests.Session,
    cache: dict[str, Any],
    dirty: list[bool],
) -> str:
    if not artist.strip():
        return ""
    key = artist.casefold().strip()
    if isinstance(cache.get(key), str):
        return str(cache[key])
    term = f"{artist} electronic music"
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": term,
        "srlimit": "1",
        "origin": "*",
    }
    r = session.get(
        "https://en.wikipedia.org/w/api.php",
        params=params,
        headers=_WIKI_HEADERS,
        timeout=25,
    )
    if r.status_code != 200:
        cache[key] = ""
        dirty[0] = True
        return ""
    data = r.json()
    titles: list[str] = []
    try:
        for it in data["query"]["search"][:1]:
            if it.get("title"):
                titles.append(str(it["title"]))
    except (KeyError, TypeError):
        cache[key] = ""
        dirty[0] = True
        return ""
    if not titles:
        cache[key] = ""
        dirty[0] = True
        return ""
    p2 = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "titles": titles[0],
        "origin": "*",
    }
    r2 = session.get(
        "https://en.wikipedia.org/w/api.php",
        params=p2,
        headers=_WIKI_HEADERS,
        timeout=25,
    )
    if r2.status_code != 200:
        cache[key] = ""
        dirty[0] = True
        return ""
    d2 = r2.json()
    try:
        pages = d2["query"]["pages"]
        page = next(iter(pages.values()))
        ext = page.get("extract") or ""
        out = str(ext).lower()[:2500]
        cache[key] = out
        dirty[0] = True
        return out
    except (KeyError, StopIteration, TypeError):
        cache[key] = ""
        dirty[0] = True
        return ""


def _norm_evidence_blob(*parts: str) -> str:
    t = " ".join(p for p in parts if p).lower()
    t = re.sub(r"\s+", " ", t)
    for a, b in _SYNONYM_FRAGMENTS.items():
        if a in t:
            t = f"{t} {b.lower()}"
    return t


def _token_in_haystack(tok: str, hay: str) -> bool:
    tok_l = tok.lower().strip()
    if len(tok_l) <= 2:
        return False
    if len(tok_l) <= 3:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(tok_l)}(?![a-z0-9])", hay))
    return tok_l in hay


def _score_path(path: tuple[str, ...], hay: str) -> float:
    score = 0.0
    joined = " ".join(path).lower()
    if joined in hay:
        score += 8.0
    for seg in path:
        s = seg.strip()
        if not s:
            continue
        if "&" in s:
            for part in re.split(r"\s*&\s*", s):
                if part and _token_in_haystack(part, hay):
                    score += 3.0
        elif _token_in_haystack(s, hay):
            score += 3.0
    return score


def _hint_from_title_artist(title: str, artist: str) -> str | None:
    blob = _norm_evidence_blob(title, artist)
    best: tuple[float, str] | None = None
    for phrases, genre_field in _TITLE_ARTIST_HINTS:
        for ph in phrases:
            if ph in blob:
                pri = float(len(ph))
                if best is None or pri > best[0]:
                    best = (pri, genre_field)
                break
    return best[1] if best else None


def _best_paths(
    paths: list[tuple[str, ...]], hay: str, topn: int = 5
) -> list[tuple[float, tuple[str, ...]]]:
    scored = [(_score_path(p, hay), p) for p in paths]
    scored.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
    return scored[:topn]


def _field_for_canonical(gc: Any, paths: list[tuple[str, ...]], canon: str) -> tuple[str, ...] | None:
    canon_l = canon.strip().lower()
    for p in paths:
        if gc.path_to_field(p).lower() == canon_l:
            return p
    return None


def _pick_with_margin(
    top: list[tuple[float, tuple[str, ...]]],
    gc: Any,
    paths: list[tuple[str, ...]],
    *,
    hint_field: str | None,
) -> tuple[str | None, float, list[str]]:
    if not top or top[0][0] <= 0:
        if hint_field:
            return hint_field, 2.0, []
        return None, 0.0, []

    best_s, best_p = top[0]
    second = top[1][0] if len(top) > 1 else 0.0
    margin = best_s - second
    field = gc.path_to_field(best_p)

    alternates = [gc.path_to_field(p) for s, p in top[1:4] if s > 0]

    if hint_field:
        hinted = _field_for_canonical(gc, paths, hint_field)
        if hinted:
            hinted_field = gc.path_to_field(hinted)
            if best_s < 4.0 or margin < 1.5:
                return hinted_field, max(best_s, 2.5), alternates
            if hint_field.lower() in field.lower() or field.lower() in hint_field.lower():
                return field, best_s + 1.0, alternates

    if best_s < 2.0 and hint_field:
        return hint_field, 2.0, alternates

    return field, best_s, alternates


def _flush_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _confidence(score: float, margin: float, has_network: bool) -> str:
    if score >= 6.0 and margin >= 2.0:
        return "high"
    if score >= 4.0 and margin >= 1.0:
        return "medium"
    if has_network and score >= 2.5:
        return "medium"
    if score > 0:
        return "low"
    return "none"


app = typer.Typer(help="Infer missing Lexicon genres via MusicBrainz + Wikipedia")


@app.command()
def main(
    taxonomy: Path = typer.Option(DEFAULT_TAXONOMY, "--taxonomy", help="Path to genres.txt tree"),
    output_dir: Path = typer.Option(DEFAULT_OUT, "--output-dir", "-o"),
    host: str | None = typer.Option(None, "--host", envvar="LEXICON_HOST"),
    port: int | None = typer.Option(None, "--port", envvar="LEXICON_PORT"),
    mb_gap: float = typer.Option(1.1, "--mb-gap", help="Seconds between MusicBrainz requests"),
    include_low_in_bulk: bool = typer.Option(
        False,
        "--include-low-in-bulk",
        help="Emit bulk-update rows for low/none confidence too (for manual cleanup)",
    ),
    skip_network: bool = typer.Option(False, "--skip-network", help="Title/hint heuristics only"),
    wiki_mb_max_chars: int = typer.Option(
        48,
        "--wiki-mb-max-chars",
        help="Fetch Wikipedia only when MusicBrainz tag string is shorter than this",
    ),
    flush_every: int = typer.Option(
        12,
        "--flush-every",
        help="Persist MB/Wikipedia caches to disk after this many new artist lookups",
    ),
) -> None:
    from lexicon import Lexicon

    gc = _load_genre_cleanup()
    tree_text = taxonomy.read_text(encoding="utf-8")
    paths = gc.parse_genres_txt(tree_text)

    lex = Lexicon(host=host, port=port)
    tracks = lex.tracks.search(
        filter={"genre": "NONE"},
        sort=[("title", "asc")],
        fields=[
            "id",
            "title",
            "artist",
            "albumTitle",
            "genre",
            "label",
            "remixer",
            "bpm",
        ],
        source="non-archived",
    )
    if tracks is None:
        raise SystemExit("Lexicon search failed (is the app running?)")
    out_dir = output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_path = out_dir / ".mb_genre_cache.json"
    wiki_cache_path = out_dir / ".wiki_genre_cache.json"
    cache: dict[str, Any] = {}
    wiki_cache: dict[str, Any] = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    if wiki_cache_path.is_file():
        try:
            wiki_cache = json.loads(wiki_cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            wiki_cache = {}

    session = requests.Session()
    dirty = [False]
    wiki_dirty = [False]

    heads_ordered = sorted(
        {_feat_head(str(t.get("artist") or "")) for t in tracks if _feat_head(str(t.get("artist") or ""))}
    )
    if not skip_network:
        for i, head in enumerate(heads_ordered, start=1):
            mb_e = _mb_artist_evidence(head, session, mb_gap, cache, dirty)
            if len(mb_e) < wiki_mb_max_chars:
                _wiki_evidence(head, session, wiki_cache, wiki_dirty)
            if flush_every > 0 and i % flush_every == 0:
                _flush_json(cache_path, cache)
                _flush_json(wiki_cache_path, wiki_cache)

    bulk: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    summary = {"tracks": len(tracks), "high": 0, "medium": 0, "low": 0, "none": 0}

    for t in tracks:
        tid = t.get("id")
        title = str(t.get("title") or "")
        artist = str(t.get("artist") or "")
        head = _feat_head(artist)
        hint = _hint_from_title_artist(title, artist)

        mb_e = ""
        wiki_e = ""
        if head:
            k = head.casefold().strip()
            mb_e = str(cache.get(k, "") if isinstance(cache.get(k), str) else "")
            wiki_e = str(wiki_cache.get(k, "") if isinstance(wiki_cache.get(k), str) else "")

        hay = _norm_evidence_blob(title, artist, mb_e, wiki_e)
        top_paths = _best_paths(paths, hay, topn=6)
        best_s0 = top_paths[0][0] if top_paths else 0.0
        field, adj_score, alts = _pick_with_margin(
            top_paths, gc, paths, hint_field=hint
        )
        margin = (
            (top_paths[0][0] - top_paths[1][0])
            if len(top_paths) > 1
            else (best_s0 if best_s0 > 0 else 0.0)
        )

        if field is None and hint:
            field = hint
            adj_score = 2.0
            margin = 2.0

        has_net = bool(mb_e or wiki_e)
        conf = _confidence(adj_score, margin, has_net)

        if conf == "high":
            summary["high"] += 1
        elif conf == "medium":
            summary["medium"] += 1
        elif conf == "low":
            summary["low"] += 1
        else:
            summary["none"] += 1

        review_items.append(
            {
                "id": tid,
                "title": title,
                "artist": artist,
                "primary_artist_guess": head,
                "proposed_genre": field,
                "confidence": conf,
                "score": round(adj_score, 2),
                "margin": round(margin, 2),
                "sources": {
                    "title_artist_hint": hint,
                    "musicbrainz_tags": mb_e[:300] if mb_e else "",
                    "wikipedia_excerpt": wiki_e[:300] if wiki_e else "",
                },
                "alternates": alts,
            }
        )

        include_bulk = field and (
            conf in ("high", "medium") or (include_low_in_bulk and conf in ("low",))
        )
        if include_bulk:
            bulk.append({"id": tid, "genre": field})

    if dirty[0]:
        _flush_json(cache_path, cache)
    if wiki_dirty[0]:
        _flush_json(wiki_cache_path, wiki_cache)

    bulk_path = out_dir / "missing_genres_bulk_update.json"
    review_path = out_dir / "missing_genres_review.json"
    bulk_path.write_text(json.dumps(bulk, indent=2), encoding="utf-8")
    review_path.write_text(
        json.dumps(
            {
                "generated_notes": "Proposed genres from infer_missing_genres_web.py; verify before apply.",
                "summary": summary,
                "items": review_items,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {len(bulk)} bulk rows to {bulk_path}")
    print(f"Wrote review for {len(review_items)} tracks to {review_path}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    app()
