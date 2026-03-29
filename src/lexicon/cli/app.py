"""Main CLI application setup."""

from typing import Annotated

import typer

from lexicon.cli.commands import (
    list_tracks,
    list_fields,
    search_tracks,
    update_track,
    bulk_update,
    list_tags,
    create_tag,
    update_tag,
    delete_tag,
)
from lexicon.cli.logging_setup import configure_verbose_logging


app = typer.Typer(
    name="lexicon",
    help="Manage your Lexicon DJ library from the command line",
)


@app.callback()
def _main_options(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Print debug logs to stderr (e.g. raw API responses when updates fail to parse)",
        ),
    ] = False,
) -> None:
    if verbose:
        configure_verbose_logging()


# Register commands
app.command("list-tracks")(list_tracks)
app.command("search-tracks")(search_tracks)
app.command("list-fields")(list_fields)
app.command("update-track")(update_track)
app.command("bulk-update")(bulk_update)
app.command("list-tags")(list_tags)
app.command("create-tag")(create_tag)
app.command("update-tag")(update_tag)
app.command("delete-tag")(delete_tag)


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
