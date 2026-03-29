"""Commands module initialization."""

# Import command functions for easier access
from lexicon.cli.commands.fields import list_fields
from lexicon.cli.commands.tracks import (
    list_tracks,
    search_tracks,
    update_track,
    bulk_update,
)
from lexicon.cli.commands.tags import (
    list_tags,
    create_tag,
    update_tag,
    delete_tag,
)

__all__ = [
    "list_fields",
    "list_tracks",
    "search_tracks",
    "update_track",
    "bulk_update",
    "list_tags",
    "create_tag",
    "update_tag",
    "delete_tag",
]
