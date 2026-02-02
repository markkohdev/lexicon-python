"""CLI interface for Lexicon."""

import json
import re
from typing import Annotated

import typer

from lexicon.client import Lexicon
from lexicon.resources.tracks_types import TrackField, TRACK_FIELDS, SORT_FIELDS


def _prompt_for_fields(
    default_fields: list[str],
    suggested_fields: list[str] | None = None,
) -> list[str] | None:
    """Prompt user to select fields interactively.
    
    Parameters
    ----------
    default_fields
        Fields to pre-select in the prompt. Appear first in the list.
    suggested_fields
        Optional fields to highlight after defaults (not pre-selected).
    
    Returns
    -------
    list[str] | None
        Selected fields, or None if user cancels.
    """
    try:
        from InquirerPy import prompt
    except ImportError:  # pragma: no cover
        typer.echo(
            "InquirerPy is required for interactive field selection. "
            "Install it with: pip install InquirerPy",
            err=True,
        )
        typer.echo(f"Using default fields: {', '.join(default_fields)}")
        return default_fields
    
    suggested_fields = suggested_fields or []
    
    # Build ordered list: defaults, suggested, then remaining
    all_fields = [f for f in TRACK_FIELDS if f != "id"]
    defaults_set = set(default_fields)
    suggested_set = set(suggested_fields) - defaults_set
    remaining_set = set(all_fields) - defaults_set - suggested_set
    
    # Build choices in order
    choices = []
    
    # Add quick "use defaults" option at the top
    choices.append(
        {
            "name": f"✓ Use defaults ({', '.join(default_fields)})",
            "value": "__defaults__",
            "enabled": False,
        }
    )
    
    # Add defaults (pre-selected)
    for field in default_fields:
        if field in all_fields:
            choices.append(
                {
                    "name": field,
                    "value": field,
                    "enabled": True,
                }
            )
    
    # Add suggested fields (not pre-selected)
    for field in suggested_fields:
        if field in suggested_set:
            choices.append(
                {
                    "name": field,
                    "value": field,
                    "enabled": False,
                }
            )
    
    # Add remaining fields (not pre-selected)
    for field in all_fields:
        if field in remaining_set:
            choices.append(
                {
                    "name": field,
                    "value": field,
                    "enabled": False,
                }
            )
    
    result = prompt(
        [
            {
                "type": "checkbox",
                "name": "fields",
                "message": "Select fields to display (space to toggle, enter to confirm):",
                "choices": choices,
                "validate": lambda x: len(x) > 0 or "Select at least one field",
            }
        ]
    )
    
    if not isinstance(result, dict) or "fields" not in result:
        return None
    
    selected = result["fields"]
    
    # Handle the quick defaults option
    if "__defaults__" in selected:
        return default_fields
    
    # Filter out the defaults option if user selected other fields
    selected = [f for f in selected if f != "__defaults__"]
    
    return selected if selected else default_fields

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
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output tracks as JSON objects. Ignores --format option when enabled.",
        ),
    ] = False,
) -> None:
    """List all tracks in the library."""
    typer.echo("Listing all tracks in the library...")
    
    client = Lexicon(host=host, port=port)
    
    # Determine which fields to fetch
    default_fields = ["title", "artist", "albumTitle"]
    suggested_fields = ["bpm", "key", "genre", "year"]
    
    if json_output or not format_string:
        # For JSON output or when no format string, use --field options or defaults
        if fields:
            display_fields = fields
        else:
            # Prompt user interactively for fields
            display_fields = _prompt_for_fields(default_fields, suggested_fields)
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
    
    # Display tracks
    if json_output:
        # Create a list with only the requested fields
        output_tracks = []
        for track in tracks:
            filtered_track = {field: track.get(field) for field in display_fields}
            output_tracks.append(filtered_track)
        typer.echo(json.dumps(output_tracks, indent=2))
    else:
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


@app.command("list-fields")
def list_fields(
    entity: Annotated[
        str,
        typer.Argument(
            help="Entity type (track, playlist, tag). Defaults to track if not specified.",
        ),
    ] = "track",
    sortable: Annotated[
        bool,
        typer.Option(
            "--sortable",
            help="Show only fields that can be used for sorting",
        ),
    ] = False,
) -> None:
    """List available fields for a given entity type."""
    entity = entity.lower()
    
    if entity not in ["track", "playlist", "tag"]:
        typer.echo(f"Error: Unknown entity type '{entity}'. Valid types: track, playlist, tag", err=True)
        raise typer.Exit(1)
    
    if entity == "track":
        if sortable:
            fields = SORT_FIELDS
            typer.echo(f"Sortable fields for tracks ({len(fields)}):\n")
        else:
            fields = TRACK_FIELDS
            typer.echo(f"Available fields for tracks ({len(fields)}):\n")
        
        for field in fields:
            typer.echo(f"  {field}")
    
    elif entity == "playlist":
        # Playlist fields from PlaylistResponse TypedDict
        playlist_fields = (
            "id", "name", "dateAdded", "type", "folderType", 
            "parentId", "position", "trackIds", "smartlist"
        )
        if sortable:
            # Playlists don't have documented sortable fields, so return empty
            typer.echo("Playlists do not currently support sorting via the API.\n")
        else:
            typer.echo(f"Available fields for playlists ({len(playlist_fields)}):\n")
            for field in playlist_fields:
                typer.echo(f"  {field}")
    
    elif entity == "tag":
        # Tag fields from TagResponse TypedDict
        tag_fields = ("id", "label", "categoryId", "position")
        if sortable:
            # Tags don't have documented sortable fields, so return empty
            typer.echo("Tags do not currently support sorting via the API.\n")
        else:
            typer.echo(f"Available fields for tags ({len(tag_fields)}):\n")
            for field in tag_fields:
                typer.echo(f"  {field}")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
