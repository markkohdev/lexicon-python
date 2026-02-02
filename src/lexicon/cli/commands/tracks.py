"""CLI commands for track management."""

import json
import re
from typing import Annotated, Literal

import typer

from lexicon.client import Lexicon
from lexicon.resources.tracks_types import TrackField
from lexicon.cli.formatting import format_value, format_table, format_pairs
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
        field_pattern = re.compile(r'\{(\w+)\}')
        format_fields = field_pattern.findall(format_string)
        display_fields = format_fields if format_fields else default_fields
    
    # Always ensure id is included for fetching
    fetch_fields: list[TrackField] = display_fields  # type: ignore
    if "id" not in fetch_fields:
        fetch_fields.insert(0, "id")  # type: ignore
    
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
                    typer.echo(f"  Error formatting track {track.get('id')}: Missing field {e}")
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
