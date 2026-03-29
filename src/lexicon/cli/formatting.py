"""Output formatting utilities for CLI commands."""

from typing import Any, Mapping


def format_value(value: Any) -> str:
    """Convert a value to a string for display.

    Parameters
    ----------
    value
        The value to format (any type).

    Returns
    -------
    str
        Formatted string representation of the value.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def format_table(
    tracks: list[dict],
    fields: list[str],
    max_col_width: int = 30,
) -> str:
    """Format tracks as a simple ASCII table with column width limit.

    Parameters
    ----------
    tracks
        List of track dictionaries to display.
    fields
        Field names to include in the table.
    max_col_width
        Maximum width for any column (default: 30).

    Returns
    -------
    str
        Formatted table as a string.
    """
    if not tracks:
        return ""

    # Calculate column widths with a max limit
    col_widths = {}
    for field in fields:
        max_val_width = max(
            (len(format_value(track.get(field, ""))) for track in tracks),
            default=0,
        )
        col_widths[field] = min(max(len(field), max_val_width), max_col_width)

    def truncate(value: str, width: int) -> str:
        """Truncate value to width, adding ... if needed."""
        if len(value) > width:
            return value[: width - 3] + "..." if width > 3 else value[:width]
        return value

    # Build header
    header = " | ".join(field.ljust(col_widths[field]) for field in fields)
    separator = "-+-".join("-" * col_widths[field] for field in fields)

    # Build rows
    lines = [header, separator]
    for track in tracks:
        row = " | ".join(
            truncate(format_value(track.get(field, "")), col_widths[field]).ljust(
                col_widths[field]
            )
            for field in fields
        )
        lines.append(row)

    return "\n".join(lines)


def format_pairs(
    tracks: list[dict],
    fields: list[str],
) -> str:
    """Format tracks as key-value pairs (one track per block).

    Parameters
    ----------
    tracks
        List of track dictionaries to display.
    fields
        Field names to include in the output.

    Returns
    -------
    str
        Formatted key-value pairs as a string.
    """
    lines = []
    for idx, track in enumerate(tracks, 1):
        if idx > 1:
            lines.append("")  # Blank line between tracks
        track_id = track.get("id", "?")
        lines.append(f"Track {idx} (ID: {track_id})")
        lines.append("-" * 40)
        for field in fields:
            if field != "id":
                value = format_value(track.get(field, ""))
                lines.append(f"  {field:20} {value}")

    return "\n".join(lines)


def display_diff(
    track_id: int,
    current: dict[str, object],
    proposed: Mapping[str, object],
) -> str:
    """Format a before/after comparison for edited fields.

    Parameters
    ----------
    track_id
        Track identifier.
    current
        Current track data dict.
    proposed
        Dict of field names to new values.

    Returns
    -------
    str
        Formatted diff string.
    """
    lines = [f"Track {track_id}:"]
    for field, new_value in proposed.items():
        old_value = current.get(field, "")
        lines.append(
            f"  {field}:  {format_value(old_value)!r}  →  {format_value(new_value)!r}"
        )
    return "\n".join(lines)
