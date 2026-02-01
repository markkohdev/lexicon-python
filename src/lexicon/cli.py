"""CLI interface for Lexicon."""

import re
from typing import Annotated

import typer

from lexicon.client import Lexicon
from lexicon.resources.tracks_types import TrackField

app = typer.Typer(
    name="lexicon",
    help="Manage your Lexicon DJ library from the command line",
)


@app.command("list-tracks")
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
) -> None:
    """List all tracks in the library."""
    typer.echo("Listing all tracks in the library...")
    
    client = Lexicon(host=host, port=port)
    
    # Determine which fields to fetch
    if format_string:
        # Extract field names from format string
        field_pattern = re.compile(r'\{(\w+)\}')
        format_fields = field_pattern.findall(format_string)
        display_fields = format_fields if format_fields else ["title", "artist", "albumTitle"]
    else:
        display_fields = fields if fields else ["title", "artist", "albumTitle"]
    
    # Always ensure id is included for fetching
    fetch_fields: list[TrackField] = [f for f in display_fields if f != "id"]  # type: ignore
    if "id" not in fetch_fields:
        fetch_fields.insert(0, "id")  # type: ignore
    
    tracks = client.tracks.list(fields=fetch_fields)
    
    if not tracks:
        typer.echo("No tracks found.")
        return
    
    # Display tracks
    typer.echo(f"\nFound {len(tracks)} track(s):\n")
    for track in tracks:
        if format_string:
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
            # Always include ID first
            track_id = track.get("id", "N/A")
            prefix = f"[{track_id}] "
            parts = []
            
            # Add requested fields
            for field in display_fields:
                if field == "id":
                    continue
                value = track.get(field, "N/A")
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value) if value else "N/A"
                parts.append(str(value))
            
            typer.echo(f"  {prefix}{' - '.join(parts)}")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
