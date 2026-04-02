"""Tests for scripts/genre_taxonomy/infer_genres_from_artists.py helpers and inference."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts" / "genre_taxonomy"
sys.path.insert(0, str(SCRIPT_DIR))

from infer_genres_from_artists import (  # noqa: E402
    artist_vote_genre,
    merge_track_contributors,
    normalize_artist_name,
    parse_artist_field,
    parse_title_contributor_names,
    run_inference,
)


def test_normalize_artist_name_strip_the() -> None:
    assert normalize_artist_name("  The   Smiths  ", strip_the=False) == "the smiths"
    assert normalize_artist_name("The Smiths", strip_the=True) == "smiths"
    assert normalize_artist_name("The Smiths", strip_the=False) == "the smiths"


def test_parse_artist_field_feat_and_coheadliners() -> None:
    pairs = dict(parse_artist_field("Daft Punk feat. Pharrell"))
    assert pairs[normalize_artist_name("Daft Punk")] == "primary"
    assert pairs[normalize_artist_name("Pharrell")] == "featured"

    pairs2 = dict(parse_artist_field("A & B feat. C"))
    assert normalize_artist_name("A") in pairs2 and pairs2[normalize_artist_name("A")] == "primary"
    assert normalize_artist_name("B") in pairs2
    assert pairs2[normalize_artist_name("C")] == "featured"


def test_parse_title_bracket_remix_conservative() -> None:
    names = parse_title_contributor_names(
        "Dance (MK Dub)",
        "conservative",
        strip_the=False,
        title_min_len=2,
    )
    assert normalize_artist_name("MK") in names or "mk" in names
    assert names == ["mk"]


def test_parse_title_hyphen_remix_tail() -> None:
    names = parse_title_contributor_names(
        "Original Jam - Artist Two Remix",
        "conservative",
        strip_the=False,
        title_min_len=2,
    )
    assert normalize_artist_name("Artist Two") == "artist two"
    assert "artist two" in names


def test_parse_title_feat_aggressive_only() -> None:
    assert (
        parse_title_contributor_names(
            "Bang feat. Guest Vocalist",
            "conservative",
            strip_the=False,
            title_min_len=2,
        )
        == []
    )
    ag = parse_title_contributor_names(
        "Bang feat. Guest Vocalist",
        "aggressive",
        strip_the=False,
        title_min_len=2,
    )
    assert "guest vocalist" in ag


def test_merge_title_skips_names_already_in_fields() -> None:
    mk = normalize_artist_name("MK")
    m = merge_track_contributors(
        artist="MK",
        remixer="",
        producer="",
        title="Song (MK Remix)",
        title_mode="conservative",
        strip_the=False,
        title_min_len=2,
    )
    assert m[mk] == "primary"
    assert list(m.keys()) == [mk]


def test_artist_vote_genre_polygenre() -> None:
    from collections import Counter

    c = Counter({"House": 1, "Techno": 1})
    g, reason = artist_vote_genre(c, min_tagged_tracks=3, min_concentration=0.55)
    assert g is None and reason == "insufficient_tracks"

    c2 = Counter({"House": 2, "Techno": 2})
    g2, reason2 = artist_vote_genre(c2, min_tagged_tracks=2, min_concentration=0.55)
    assert g2 is None and reason2 == "polygenre"


def test_infer_tie_and_run_inference_smoke() -> None:
    tracks: list[dict] = []
    for i in range(3):
        tracks.append({"id": i + 1, "artist": "OnlyHouse", "title": "", "genre": "House"})
    for i in range(3):
        tracks.append({"id": i + 4, "artist": "OnlyTechno", "title": "", "genre": "Techno"})
    tracks.append({"id": 7, "artist": "OnlyHouse & OnlyTechno", "title": "", "genre": ""})
    bulk, review, stats = run_inference(
        tracks,
        title_mode="off",
        strip_the=False,
        title_min_len=2,
        min_tagged_tracks=3,
        min_concentration=0.55,
        margin=0.1,
        w_primary=1.0,
        w_featured=0.5,
        w_remixer=0.25,
        w_producer=0.25,
        w_title=0.25,
        require_non_title_vote=False,
    )
    assert not any(r["id"] == 7 for r in bulk)
    assert any(r["id"] == 7 and r["reason"] == "tie" for r in review)
    assert stats["reasons"]["tie"] >= 1

    tracks2 = [
        {"id": 1, "artist": "Solo", "title": "", "genre": "House"},
        {"id": 2, "artist": "Solo", "title": "", "genre": "House"},
        {"id": 3, "artist": "Solo", "title": "", "genre": "House"},
        {"id": 4, "artist": "Solo", "title": "", "genre": ""},
    ]
    bulk2, _, _ = run_inference(
        tracks2,
        title_mode="off",
        strip_the=False,
        title_min_len=2,
        min_tagged_tracks=3,
        min_concentration=0.55,
        margin=0.1,
        w_primary=1.0,
        w_featured=0.5,
        w_remixer=0.25,
        w_producer=0.25,
        w_title=0.25,
        require_non_title_vote=False,
    )
    assert bulk2 == [{"id": 4, "genre": "House"}]


def test_require_non_title_vote() -> None:
    tracks: list[dict] = []
    for i in range(3):
        tracks.append(
            {
                "id": i + 1,
                "artist": "Host",
                "title": "Jam (XRmx Remix)",
                "genre": "House",
                "remixer": "",
                "producer": "",
            }
        )
    tracks.append(
        {
            "id": 4,
            "artist": "",
            "remixer": "",
            "producer": "",
            "title": "Other (XRmx Remix)",
            "genre": "",
        }
    )
    xrmx = normalize_artist_name("XRmx")
    bulk, review, _ = run_inference(
        tracks,
        title_mode="conservative",
        strip_the=False,
        title_min_len=2,
        min_tagged_tracks=3,
        min_concentration=0.55,
        margin=0.1,
        w_primary=1.0,
        w_featured=0.5,
        w_remixer=0.25,
        w_producer=0.25,
        w_title=1.0,
        require_non_title_vote=True,
    )
    assert not bulk
    row = next(r for r in review if r["id"] == 4)
    assert row["reason"] == "title_only_votes"
    assert xrmx in row["contributors"]
    assert row["contributors"][xrmx] == "from_title"
