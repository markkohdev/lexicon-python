"""CLI commands for track management."""

import json
import re
import sys
from typing import Annotated, Literal

import typer

from lexicon.client import Lexicon
from lexicon.resources.tracks_types import TrackField
from lexicon.cli.formatting import (
    format_value,
    format_table,
    format_pairs,
    display_diff,
)
from lexicon.cli.prompts import prompt_for_fields


def list_tracks(
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            help="Hostname or IP for the Lexicon API",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            help="API port number",
        ),
    ] = None,
    fields: Annotated[
        list[str] | None,
        typer.Option(
            "-f",
            "--field",
            help="Field(s) to display (can be used multiple times, defaults to: title, artist, albumTitle)",
        ),
    ] = None,
    format_string: Annotated[
        str | None,
        typer.Option(
            "--format",
            help='Format string for output (e.g., "{title} - {artist} [{bpm} BPM]"). Overrides --field option.',
        ),
    ] = None,
    output_format: Annotated[
        Literal["compact", "table", "pairs", "json"],
        typer.Option(
            "--output-format",
            help="Output format: compact (default), table, pairs (key-value), or json",
        ),
    ] = "compact",
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output tracks as JSON objects. Overrides --output-format. Ignores --format option.",
        ),
    ] = False,
) -> None:
    """List all tracks in the library."""
    typer.echo("Listing all tracks in the library...")

    client = Lexicon(host=host, port=port)

    # Determine which fields to fetch
    default_fields = ["title", "artist", "albumTitle"]
    suggested_fields = ["bpm", "key", "genre", "year"]

    # Override output format if --json is used
    if json_output:
        output_format = "json"

    if output_format == "json" or not format_string:
        # For JSON output or when no format string, use --field options or defaults
        if fields:
            display_fields = fields
        else:
            # Prompt user interactively for fields
            display_fields = prompt_for_fields(default_fields, suggested_fields)
            if display_fields is None:
                typer.echo("Field selection cancelled.")
                raise typer.Exit(1)
    else:
        # Extract field names from format string
        field_pattern = re.compile(r"\{(\w+)\}")
        format_fields = field_pattern.findall(format_string)
        display_fields = format_fields if format_fields else default_fields

    # Always ensure id is included for fetching and display
    if "id" not in display_fields:
        display_fields.insert(0, "id")  # type: ignore
    fetch_fields: list[TrackField] = display_fields.copy()  # type: ignore

    # Fetch tracks with the fields to display
    tracks = client.tracks.list(fields=fetch_fields)

    if not tracks:
        typer.echo("No tracks found.")
        return

    # Display tracks based on output format
    if output_format == "json":
        # Create a list with only the requested fields
        output_tracks = []
        for track in tracks:
            filtered_track = {field: track.get(field) for field in display_fields}
            output_tracks.append(filtered_track)
        typer.echo(json.dumps(output_tracks, indent=2))
    elif output_format == "table":
        typer.echo(f"\nFound {len(tracks)} track(s):\n")
        table_output = format_table(tracks, display_fields)
        typer.echo(table_output)
    elif output_format == "pairs":
        typer.echo(f"\nFound {len(tracks)} track(s):\n")
        pairs_output = format_pairs(tracks, display_fields)
        typer.echo(pairs_output)
    else:  # compact
        if format_string:
            typer.echo(f"\nFound {len(tracks)} track(s):\n")
            for track in tracks:
                # Prepare values for formatting
                format_values = {}
                for field in display_fields:
                    value = track.get(field, "N/A")
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value) if value else "N/A"
                    format_values[field] = value

                # Format and display
                try:
                    output = format_string.format(**format_values)
                    typer.echo(f"  {output}")
                except KeyError as e:
                    typer.echo(
                        f"  Error formatting track {track.get('id')}: Missing field {e}"
                    )
        else:
            typer.echo(f"\nFound {len(tracks)} track(s):\n")
            # Always include ID first
            for track in tracks:
                track_id = track.get("id", "N/A")
                prefix = f"[{track_id}] "
                parts = []

                # Add requested fields
                for field in display_fields:
                    if field == "id":
                        continue
                    value = format_value(track.get(field, ""))
                    parts.append(value)

                typer.echo(f"  {prefix}{' - '.join(parts)}")


def update_track(
    track_id: Annotated[
        int,
        typer.Option(
            "--id",
            help="Track ID to update",
        ),
    ],
    set_fields: Annotated[
        list[str] | None,
        typer.Option(
            "--set",
            help='Field edits as FIELD=VALUE (repeatable, e.g. --set title="New Title")',
        ),
    ] = None,
    edits_json: Annotated[
        str | None,
        typer.Option(
            "--edits",
            help='Raw JSON string of edits (e.g. \'{"title": "New Title"}\'). Mutually exclusive with --set.',
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview changes without applying them",
        ),
    ] = False,
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            help="Hostname or IP for the Lexicon API",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            help="API port number",
        ),
    ] = None,
    output_format: Annotated[
        Literal["pairs", "json", "compact"],
        typer.Option(
            "--output-format",
            help="Output format for the updated track: pairs (default), json, or compact",
        ),
    ] = "pairs",
) -> None:
    """Update a single track's fields."""
    has_set = set_fields is not None and len(set_fields) > 0
    has_edits = edits_json is not None

    if has_set and has_edits:
        typer.echo("Error: --set and --edits are mutually exclusive.", err=True)
        raise typer.Exit(1)
    if not has_set and not has_edits:
        typer.echo("Error: provide either --set or --edits.", err=True)
        raise typer.Exit(1)

    edits: dict[str, str] = {}
    if has_set:
        assert set_fields is not None
        for pair in set_fields:
            if "=" not in pair:
                typer.echo(
                    f"Error: invalid --set value (missing '='): {pair}", err=True
                )
                raise typer.Exit(1)
            # Split on first '=' only — values may contain '=' (e.g. --set comment="a=b")
            key, value = pair.split("=", 1)
            edits[key.strip()] = value.strip()
    else:
        assert edits_json is not None
        try:
            parsed = json.loads(edits_json)
        except json.JSONDecodeError as exc:
            typer.echo(f"Error: invalid JSON in --edits: {exc}", err=True)
            raise typer.Exit(1)
        if not isinstance(parsed, dict):
            typer.echo("Error: --edits must be a JSON object.", err=True)
            raise typer.Exit(1)
        # Keys become strings; values stay as parsed (int, str, etc.) —
        # the SDK's _normalize_edits handles type coercion per field.
        edits = {str(k): v for k, v in parsed.items()}

    if not edits:
        typer.echo("Error: no edits provided.", err=True)
        raise typer.Exit(1)

    client = Lexicon(host=host, port=port)

    if dry_run:
        current_track = client.tracks.get(track_id)
        if current_track is None:
            typer.echo(f"Error: track {track_id} not found.", err=True)
            raise typer.Exit(1)
        typer.echo(display_diff(track_id, current_track, edits))
        typer.echo(
            f"\nSummary: 1 track, {len(edits)} field change(s) (dry run — no changes applied)"
        )
        return

    result = client.tracks.update(track_id, edits)

    if result is None:
        typer.echo(f"Error: failed to update track {track_id}.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Track {track_id} updated successfully.\n")

    # Only show the edited fields (plus id) rather than the full track response
    if output_format == "json":
        filtered = {field: result.get(field) for field in edits}
        filtered["id"] = result.get("id")
        typer.echo(json.dumps(filtered, indent=2))
    elif output_format == "pairs":
        display_fields = ["id"] + [f for f in edits if f != "id"]
        typer.echo(format_pairs([result], display_fields))
    else:  # compact
        track_id_val = result.get("id", "N/A")
        parts = [format_value(result.get(f, "")) for f in edits if f != "id"]
        typer.echo(f"  [{track_id_val}] {' - '.join(parts)}")


def _parse_edits_file(file_path: str) -> list[dict]:
    """Read and parse a JSON array or JSONL edits file.

    Returns a list of dicts, each with at least an ``id`` key.
    Raises ``typer.Exit(1)`` on parse or validation errors.
    """
    if file_path == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(file_path) as f:
                raw = f.read()
        except FileNotFoundError:
            typer.echo(f"Error: file not found: {file_path}", err=True)
            raise typer.Exit(1)
        except OSError as exc:
            typer.echo(f"Error reading file: {exc}", err=True)
            raise typer.Exit(1)

    raw = raw.strip()
    if not raw:
        typer.echo("Error: edits file is empty.", err=True)
        raise typer.Exit(1)

    # Try JSON array first, then JSONL
    entries: list[dict] = []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            typer.echo(f"Error: invalid JSON in edits file: {exc}", err=True)
            raise typer.Exit(1)
        if not isinstance(parsed, list):
            typer.echo(
                "Error: edits file must contain a JSON array or JSONL.", err=True
            )
            raise typer.Exit(1)
        entries = parsed
    else:
        for line_num, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                typer.echo(f"Error: invalid JSON on line {line_num}: {exc}", err=True)
                raise typer.Exit(1)
            entries.append(obj)

    if not entries:
        typer.echo("Error: edits file contains no entries.", err=True)
        raise typer.Exit(1)

    # Validate each entry
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            typer.echo(f"Error: entry {i + 1} is not a JSON object.", err=True)
            raise typer.Exit(1)
        if "id" not in entry:
            typer.echo(
                f"Error: entry {i + 1} is missing required 'id' field.", err=True
            )
            raise typer.Exit(1)
        if not isinstance(entry["id"], int):
            typer.echo(
                f"Error: entry {i + 1} has non-integer 'id': {entry['id']!r}", err=True
            )
            raise typer.Exit(1)
        edit_fields = {k: v for k, v in entry.items() if k != "id"}
        if not edit_fields:
            typer.echo(
                f"Error: entry {i + 1} (id={entry['id']}) has no edit fields.", err=True
            )
            raise typer.Exit(1)

    return entries


def bulk_update(
    file: Annotated[
        str,
        typer.Option(
            "--file",
            help="Path to JSON/JSONL edits file, or '-' for stdin",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview changes without applying them",
        ),
    ] = False,
    continue_on_error: Annotated[
        bool,
        typer.Option(
            "--continue-on-error",
            help="Continue processing if an individual update fails",
        ),
    ] = False,
    output_format: Annotated[
        Literal["summary", "json", "table"],
        typer.Option(
            "--output-format",
            help="Output format: summary (default), json (full results), or table (diff view)",
        ),
    ] = "summary",
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            help="Hostname or IP for the Lexicon API",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            help="API port number",
        ),
    ] = None,
) -> None:
    """Apply batch edits to multiple tracks from a JSON/JSONL file."""
    entries = _parse_edits_file(file)

    client = Lexicon(host=host, port=port)

    # Collect all unique edit field names (excluding id) for fetching
    all_edit_fields: set[str] = set()
    for entry in entries:
        all_edit_fields.update(k for k in entry if k != "id")

    track_ids = [entry["id"] for entry in entries]
    total_field_changes = sum(len(e) - 1 for e in entries)  # -1 for id

    if dry_run or output_format == "table":
        # Fetch current values for diff display (get_many returns full track dicts)
        current_tracks = client.tracks.get_many(track_ids) or []
        current_by_id: dict[int, dict] = {}
        for track in current_tracks:
            if isinstance(track, dict) and "id" in track:
                current_by_id[track["id"]] = track

    if dry_run:
        # Display diff for each entry and exit
        diff_parts = []
        for entry in entries:
            tid = entry["id"]
            proposed = {k: v for k, v in entry.items() if k != "id"}
            current = current_by_id.get(tid, {})
            if not current:
                diff_parts.append(f"Track {tid}: (not found — will be skipped)")
            else:
                diff_parts.append(display_diff(tid, current, proposed))

        typer.echo("\n\n".join(diff_parts))
        typer.echo(
            f"\nSummary: {len(entries)} track(s), {total_field_changes} field change(s) "
            f"(dry run — no changes applied)"
        )
        return

    # Apply mode
    successes = 0
    failures = 0
    results: list[dict] = []

    for entry in entries:
        tid = entry["id"]
        edits = {k: v for k, v in entry.items() if k != "id"}
        try:
            result = client.tracks.update(tid, edits)
        except Exception as exc:
            failures += 1
            results.append({"id": tid, "status": "error", "error": str(exc)})
            if not continue_on_error:
                typer.echo(f"Error updating track {tid}: {exc}", err=True)
                break
            typer.echo(f"Warning: failed to update track {tid}: {exc}", err=True)
            continue

        if result is None:
            failures += 1
            results.append(
                {"id": tid, "status": "error", "error": "update returned None"}
            )
            if not continue_on_error:
                typer.echo(f"Error: failed to update track {tid}.", err=True)
                break
            typer.echo(f"Warning: failed to update track {tid}.", err=True)
        else:
            successes += 1
            results.append({"id": tid, "status": "ok", "result": result})

    # Output
    if output_format == "json":
        typer.echo(json.dumps(results, indent=2))
    elif output_format == "table":
        diff_parts = []
        for entry, res in zip(entries, results):
            tid = entry["id"]
            proposed = {k: v for k, v in entry.items() if k != "id"}
            current = current_by_id.get(tid, {})
            if res["status"] == "ok":
                diff_parts.append(display_diff(tid, current, proposed) + "  ✓")
            else:
                diff_parts.append(
                    f"Track {tid}: FAILED — {res.get('error', 'unknown')}"
                )
        typer.echo("\n\n".join(diff_parts))

    total = successes + failures
    if failures == 0:
        typer.echo(f"Updated {successes}/{total} track(s) successfully.")
    else:
        typer.echo(f"Updated {successes}/{total} track(s) ({failures} failed).")
