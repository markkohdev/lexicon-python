"""CLI commands for custom tag management."""

from __future__ import annotations

import json
from typing import Annotated, Literal

import typer

from lexicon.client import Lexicon
from lexicon.cli.tag_utils import TagResolver


def list_tags(
    output_format: Annotated[
        Literal["grouped", "flat", "json"],
        typer.Option(
            "--output-format",
            help="Output format: grouped (default), flat (Category:Label per line), or json",
        ),
    ] = "grouped",
    host: Annotated[
        str | None,
        typer.Option("--host", help="Hostname or IP for the Lexicon API"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", help="API port number"),
    ] = None,
) -> None:
    """List all custom tags, grouped by category."""
    client = Lexicon(host=host, port=port)
    resolver = TagResolver(client)

    if output_format == "json":
        tags_raw = client.tags.list() or []
        categories_raw = client.tags.categories.list() or []
        typer.echo(
            json.dumps({"categories": categories_raw, "tags": tags_raw}, indent=2)
        )
        return

    grouped = resolver.get_all_tags()

    if not grouped or all(len(v) == 0 for v in grouped.values()):
        typer.echo("No custom tags found.")
        return

    if output_format == "flat":
        for cat_label, tag_labels in grouped.items():
            for tag_label in tag_labels:
                typer.echo(f"{cat_label}:{tag_label}")
        return

    # grouped (default)
    first = True
    for cat_label, tag_labels in grouped.items():
        if not first:
            typer.echo()
        first = False
        typer.echo(
            f"{cat_label} ({len(tag_labels)} tag{'s' if len(tag_labels) != 1 else ''}):"
        )
        for tag_label in tag_labels:
            typer.echo(f"  {tag_label}")


def create_tag(
    tag: Annotated[
        str,
        typer.Option("--tag", help="Tag in 'Category:Label' format"),
    ],
    color: Annotated[
        str | None,
        typer.Option("--color", help="Color for a new category (hex, e.g. '#FF0000')"),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
    host: Annotated[
        str | None,
        typer.Option("--host", help="Hostname or IP for the Lexicon API"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", help="API port number"),
    ] = None,
) -> None:
    """Create a new custom tag (auto-creates the category if needed)."""
    if ":" not in tag:
        typer.echo("Error: --tag must be in 'Category:Label' format.", err=True)
        raise typer.Exit(1)

    cat_part, tag_part = tag.split(":", 1)
    cat_part = cat_part.strip()
    tag_part = tag_part.strip()

    if not cat_part or not tag_part:
        typer.echo("Error: --tag must be in 'Category:Label' format.", err=True)
        raise typer.Exit(1)

    client = Lexicon(host=host, port=port)
    resolver = TagResolver(client)

    existing = resolver.get_tag_id(tag)
    if existing is not None:
        typer.echo(f"Tag '{cat_part}:{tag_part}' already exists (id={existing}).")
        return

    cat_id = resolver.get_category_id(cat_part)
    if cat_id is None:
        if not yes:
            confirmed = typer.confirm(
                f"Category '{cat_part}' does not exist. Create it?"
            )
            if not confirmed:
                typer.echo("Aborted.")
                raise typer.Exit(1)
        new_cat = client.tags.categories.add(cat_part, color=color)
        if new_cat is None or "id" not in new_cat:
            typer.echo(f"Error: failed to create category '{cat_part}'.", err=True)
            raise typer.Exit(1)
        cat_id = new_cat["id"]
        typer.echo(f"Created category '{cat_part}' (id={cat_id}).")

    new_tag = client.tags.add(cat_id, tag_part)
    if new_tag is None or "id" not in new_tag:
        typer.echo(f"Error: failed to create tag '{cat_part}:{tag_part}'.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Created tag '{cat_part}:{tag_part}' (id={new_tag['id']}).")


def update_tag(
    tag: Annotated[
        str,
        typer.Option("--tag", help="Existing tag as 'Category:Label'"),
    ],
    label: Annotated[
        str | None,
        typer.Option("--label", help="New label for the tag"),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option(
            "--category",
            help="Move tag to this category (by label; created if missing with --yes)",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
    host: Annotated[
        str | None,
        typer.Option("--host", help="Hostname or IP for the Lexicon API"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", help="API port number"),
    ] = None,
) -> None:
    """Update an existing custom tag's label or category."""
    if ":" not in tag:
        typer.echo("Error: --tag must be in 'Category:Label' format.", err=True)
        raise typer.Exit(1)

    if label is None and category is None:
        typer.echo("Error: provide --label and/or --category.", err=True)
        raise typer.Exit(1)

    client = Lexicon(host=host, port=port)
    resolver = TagResolver(client)

    tag_id = resolver.get_tag_id(tag)
    if tag_id is None:
        typer.echo(f"Error: tag '{tag}' not found.", err=True)
        raise typer.Exit(1)

    kwargs: dict[str, object] = {}

    if label is not None:
        kwargs["label"] = label

    if category is not None:
        cat_id = resolver.get_category_id(category)
        if cat_id is None:
            if not yes:
                confirmed = typer.confirm(
                    f"Category '{category}' does not exist. Create it?"
                )
                if not confirmed:
                    typer.echo("Aborted.")
                    raise typer.Exit(1)
            new_cat = client.tags.categories.add(category)
            if new_cat is None or "id" not in new_cat:
                typer.echo(f"Error: failed to create category '{category}'.", err=True)
                raise typer.Exit(1)
            cat_id = new_cat["id"]
            typer.echo(f"Created category '{category}' (id={cat_id}).")
        kwargs["category_id"] = cat_id

    result = client.tags.update(tag_id, **kwargs)  # type: ignore[arg-type]
    if result is None:
        typer.echo(f"Error: failed to update tag '{tag}'.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Updated tag '{tag}' (id={tag_id}).")


def delete_tag(
    tag: Annotated[
        str,
        typer.Option("--tag", help="Tag to delete as 'Category:Label'"),
    ],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
    host: Annotated[
        str | None,
        typer.Option("--host", help="Hostname or IP for the Lexicon API"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", help="API port number"),
    ] = None,
) -> None:
    """Delete a custom tag by 'Category:Label'."""
    if ":" not in tag:
        typer.echo("Error: --tag must be in 'Category:Label' format.", err=True)
        raise typer.Exit(1)

    client = Lexicon(host=host, port=port)
    resolver = TagResolver(client)

    tag_id = resolver.get_tag_id(tag)
    if tag_id is None:
        typer.echo(f"Error: tag '{tag}' not found.", err=True)
        raise typer.Exit(1)

    if not yes:
        confirmed = typer.confirm(f"Delete tag '{tag}' (id={tag_id})?")
        if not confirmed:
            typer.echo("Aborted.")
            raise typer.Exit(1)

    ok = client.tags.delete(tag_id)
    if not ok:
        typer.echo(f"Error: failed to delete tag '{tag}'.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Deleted tag '{tag}' (id={tag_id}).")
