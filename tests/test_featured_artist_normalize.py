"""Golden tests for ``scripts/library/featured_artist_normalize.py``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "library"
sys.path.insert(0, str(_LIB))

import featured_artist_normalize as fan  # noqa: E402


def _strip(title: str) -> tuple[str, str | None]:
    return fan._strip_trailing_platform_ids(title)


@pytest.mark.parametrize(
    ("title", "expected_stripped", "had_id"),
    [
        ("Bad Bitch (feat. Chynaa)-695096506", "Bad Bitch (feat. Chynaa)", True),
        ("gold lights-1852", "gold lights-1852", False),
        ("Lick It (Noizu Remix)-m4YlpP8ePk0", "Lick It (Noizu Remix)", True),
    ],
)
def test_strip_trailing_ids(title: str, expected_stripped: str, had_id: bool) -> None:
    stripped, removed = _strip(title)
    assert stripped == expected_stripped
    assert (removed is not None) == had_id


def test_remixer_junk_domain() -> None:
    assert fan.remixer_is_junk("TraxCrate.com") is True
    assert fan.remixer_is_junk("FaltyDL") is False


def _g(
    title: str,
    artist: str,
    remixer: str,
    *,
    exp_title: str,
    exp_artist: str,
    exp_remixer: str,
) -> None:
    r = fan.normalize_track(title, artist, remixer)
    assert r.title == exp_title, f"title got {r.title!r}"
    assert r.artist == exp_artist, f"artist got {r.artist!r}"
    assert r.remixer == exp_remixer, f"remixer got {r.remixer!r}"


def test_golden_core_table() -> None:
    _g(
        "Little Pleasures",
        "TOKiMONSTA feat. Gavin Turek",
        "",
        exp_title="Little Pleasures (feat. Gavin Turek)",
        exp_artist="TOKiMONSTA, Gavin Turek",
        exp_remixer="",
    )
    _g(
        "Better Now (feat. MARO)",
        "ODESZA",
        "",
        exp_title="Better Now (feat. MARO)",
        exp_artist="ODESZA, MARO",
        exp_remixer="",
    )
    _g(
        "Eyesdown",
        "Bonobo feat. Andreya Triana & DELS",
        "",
        exp_title="Eyesdown (feat. Andreya Triana & DELS)",
        exp_artist="Bonobo, Andreya Triana, DELS",
        exp_remixer="",
    )
    _g(
        "Can We Still Be Friends? (with Laurence Guy)",
        "Barry Can't Swim and Laurence Guy",
        "",
        exp_title="Can We Still Be Friends? (feat. Laurence Guy)",
        exp_artist="Barry Can't Swim, Laurence Guy",
        exp_remixer="",
    )
    _g(
        "Sun Models (feat. Madelyn Grant) (ODESZA VIP Remix)",
        "ODESZA",
        "ODESZA",
        exp_title="Sun Models (feat. Madelyn Grant) (ODESZA VIP Remix)",
        exp_artist="ODESZA, Madelyn Grant",
        exp_remixer="ODESZA",
    )
    _g(
        "All In Forms (FaltyDL Remix)",
        "Bonobo",
        "FaltyDL",
        exp_title="All In Forms (FaltyDL Remix)",
        exp_artist="Bonobo, FaltyDL",
        exp_remixer="FaltyDL",
    )
    _g(
        "Breezeblocks (Tinlicker Remix)",
        "Tinlicker, alt-J",
        "Tinlicker",
        exp_title="Breezeblocks (Tinlicker Remix)",
        exp_artist="alt-J, Tinlicker",
        exp_remixer="Tinlicker",
    )
    _g(
        "Hide U (Tinlicker Remix)",
        "Sian Evans, Tinlicker",
        "Tinlicker",
        exp_title="Hide U (Tinlicker Remix)",
        exp_artist="Sian Evans, Tinlicker",
        exp_remixer="Tinlicker",
    )
    _g(
        "Fireworks (feat. Moss Kena & The Knocks)",
        "Purple Disco Machine, Moss Kena, The Knocks",
        "",
        exp_title="Fireworks (feat. Moss Kena & The Knocks)",
        exp_artist="Purple Disco Machine, Moss Kena, The Knocks",
        exp_remixer="",
    )
    _g(
        "Afterglow",
        "Bob Moses x Kasablanca",
        "",
        exp_title="Afterglow",
        exp_artist="Bob Moses, Kasablanca",
        exp_remixer="",
    )
    _g(
        "I NEED U",
        "SIDEPIECE feat. ZOI",
        "",
        exp_title="I NEED U (feat. ZOI)",
        exp_artist="SIDEPIECE, ZOI",
        exp_remixer="",
    )
    _g(
        "Call My Name feat. Rae Morris (Extended Mix)",
        "Rae Morris & Franky Wah",
        "",
        exp_title="Call My Name (feat. Rae Morris) (Extended Mix)",
        exp_artist="Franky Wah, Rae Morris",
        exp_remixer="",
    )


def test_golden_additional_table() -> None:
    _g(
        "God Is The Space Between Us",
        "Barry Can't Swim featuring Taite Imogen",
        "",
        exp_title="God Is The Space Between Us (feat. Taite Imogen)",
        exp_artist="Barry Can't Swim, Taite Imogen",
        exp_remixer="",
    )
    _g(
        "Transits",
        "Bonobo Featuring Szjerdene",
        "",
        exp_title="Transits (feat. Szjerdene)",
        exp_artist="Bonobo, Szjerdene",
        exp_remixer="",
    )
    _g(
        "Help Herself (Feat. Diamond Pistols)",
        "bbno$",
        "",
        exp_title="Help Herself (feat. Diamond Pistols)",
        exp_artist="bbno$, Diamond Pistols",
        exp_remixer="",
    )
    _g(
        "Bad Bitch (ft Chynaa)-695096506",
        "Chris Lorenzo",
        "",
        exp_title="Bad Bitch (feat. Chynaa)",
        exp_artist="Chris Lorenzo, Chynaa",
        exp_remixer="",
    )
    _g(
        "Africa (My No. 1) featuring The Ibibio Horns (Captain Planet Remix)",
        "General Ehi Duncan, The Africa Army Express, The Ibibio Horns",
        "Captain Planet",
        exp_title="Africa (My No. 1) (feat. The Ibibio Horns) (Captain Planet Remix)",
        exp_artist="General Ehi Duncan, The Africa Army Express, The Ibibio Horns, Captain Planet",
        exp_remixer="Captain Planet",
    )
    _g(
        "Gone (Feat.Sugaray)",
        "Smokey Joe & The Kid",
        "",
        exp_title="Gone (feat. Sugaray)",
        exp_artist="Smokey Joe & The Kid, Sugaray",
        exp_remixer="",
    )
    _g(
        "Tail Feather (Feat. Youthstar & Erica Guaca)",
        "Smokey Joe & The Kid",
        "",
        exp_title="Tail Feather (feat. Youthstar & Erica Guaca)",
        exp_artist="Smokey Joe & The Kid, Youthstar, Erica Guaca",
        exp_remixer="",
    )
    _g(
        "one more day",
        "San Holo featuring Mija and Mr. Carmack",
        "",
        exp_title="one more day (feat. Mija & Mr. Carmack)",
        exp_artist="San Holo, Mija, Mr. Carmack",
        exp_remixer="",
    )
    _g(
        "Closure",
        "Massane Ft Benjamin Roustaing",
        "",
        exp_title="Closure (feat. Benjamin Roustaing)",
        exp_artist="Massane, Benjamin Roustaing",
        exp_remixer="",
    )
    _g(
        "I Admit It (Selcta Remix) (Clean Extended)",
        "Zhu ft 24kgoldn",
        "Selcta",
        exp_title="I Admit It (Selcta Remix) (Clean Extended)",
        exp_artist="Zhu, 24kgoldn, Selcta",
        exp_remixer="Selcta",
    )
    _g(
        "Release Me (feat Rationale) (Extended Mix)",
        "Billon",
        "TraxCrate.com",
        exp_title="Release Me (feat. Rationale) (Extended Mix)",
        exp_artist="Billon, Rationale",
        exp_remixer="",
    )
    _g(
        "Dreaming (Gibson Parker Remix) (ft. Cammie Robinson)",
        "Rootkit",
        "Gibson Parker",
        exp_title="Dreaming (feat. Cammie Robinson) (Gibson Parker Remix)",
        exp_artist="Rootkit, Cammie Robinson, Gibson Parker",
        exp_remixer="Gibson Parker",
    )
    _g(
        "Spread Love Paddington Feat Dvno",
        "Boston Bun Feat Dvno",
        "",
        exp_title="Spread Love Paddington (feat. Dvno)",
        exp_artist="Boston Bun, Dvno",
        exp_remixer="",
    )