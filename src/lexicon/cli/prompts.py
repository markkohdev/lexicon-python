"""Interactive prompt utilities for CLI commands."""

import typer

from lexicon.resources.tracks_types import TRACK_FIELDS


def prompt_for_fields(
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
