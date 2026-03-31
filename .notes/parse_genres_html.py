#!/usr/bin/env python3
"""Parse .notes/genres_table.html into genre / sub-genre JSON (stdout)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Install beautifulsoup4: uv run --with beautifulsoup4 python .notes/parse_genres_html.py", file=sys.stderr)
    raise


def _classify_td(td) -> tuple[str, str]:
    """Return ('genre'|'sub'|'empty', text)."""
    raw = td.get_text(separator=" ", strip=True)
    if raw in ("", "\xa0") or raw.isspace():
        return ("empty", "")
    # Column titles use <h2><strong>…</strong></h2> — not a genre row.
    if td.find("h2"):
        return ("empty", "")
    strong = td.find("strong")
    if strong:
        return ("genre", strong.get_text(strip=True))
    em = td.find("em")
    if em:
        return ("sub", em.get_text(strip=True))
    # e.g. h2 header row
    if td.find("h2"):
        return ("empty", "")
    return ("empty", raw)


def _expand_row(tr, rowspan_carry: list[int], row_slots: list) -> None:
    """Fill row_slots[0:5] with (kind, text) or None; update rowspan_carry."""
    tds = tr.find_all("td", recursive=False)
    col = 0
    ti = 0

    while col < 5:
        if rowspan_carry[col] > 0:
            rowspan_carry[col] -= 1
            col += 1
            continue
        if ti >= len(tds):
            col += 1
            continue

        td = tds[ti]
        ti += 1
        cs = int(td.get("colspan", 1))
        rs = int(td.get("rowspan", 1))
        kind, text = _classify_td(td)

        for c in range(col, min(col + cs, 5)):
            row_slots[c] = (kind, text)
            if rs > 1:
                rowspan_carry[c] = rs - 1
        col += cs


def parse_genres(html_path: Path) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        raise SystemExit("no tbody")
    trs = tbody.find_all("tr", recursive=False)
    rowspan_carry = [0] * 5

    left: list[dict] = []
    right: list[dict] = []
    cur_left: dict | None = None
    cur_right: dict | None = None

    for tr in trs:
        row_slots: list = [None] * 5
        _expand_row(tr, rowspan_carry, row_slots)

        # Left: genre in merged col 0–1
        g0 = row_slots[0]
        g1 = row_slots[1]
        if g0 and g0[0] == "genre":
            cur_left = {"genre": g0[1], "sub-genres": []}
            left.append(cur_left)
        elif g1 and g1[0] == "genre" and (g0 is None or g0[0] == "empty"):
            cur_left = {"genre": g1[1], "sub-genres": []}
            left.append(cur_left)
        elif g1 and g1[0] == "sub" and cur_left is not None:
            cur_left["sub-genres"].append(g1[1])

        # Right: genre in merged col 3–4
        g3 = row_slots[3]
        g4 = row_slots[4]
        if g3 and g3[0] == "genre":
            cur_right = {"genre": g3[1], "sub-genres": []}
            right.append(cur_right)
        elif g4 and g4[0] == "genre" and (g3 is None or g3[0] == "empty"):
            cur_right = {"genre": g4[1], "sub-genres": []}
            right.append(cur_right)
        elif g4 and g4[0] == "sub" and cur_right is not None:
            cur_right["sub-genres"].append(g4[1])

    return left, right


def main() -> None:
    root = Path(__file__).resolve().parent
    html_path = root / "genres_table.html"
    left, right = parse_genres(html_path)
    combined = left + right
    out_path = root / "genres.json"
    out_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(combined)} genres ({len(left)} left + {len(right)} right) -> {out_path}")


if __name__ == "__main__":
    main()
