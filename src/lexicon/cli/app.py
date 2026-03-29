"""Main CLI application setup."""

import typer

from lexicon.cli.commands import list_tracks, list_fields, update_track


app = typer.Typer(
    name="lexicon",
    help="Manage your Lexicon DJ library from the command line",
)


# Register commands
app.command("list-tracks")(list_tracks)
app.command("list-fields")(list_fields)
app.command("update-track")(update_track)


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
