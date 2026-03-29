"""CLI commands for listing available fields."""

from typing import Annotated

import typer

from lexicon.resources.tracks_types import TRACK_FIELDS, SORT_FIELDS


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
        typer.echo(
            f"Error: Unknown entity type '{entity}'. Valid types: track, playlist, tag",
            err=True,
        )
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
            "id",
            "name",
            "dateAdded",
            "type",
            "folderType",
            "parentId",
            "position",
            "trackIds",
            "smartlist",
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
