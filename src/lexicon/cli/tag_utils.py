"""Tag resolution utilities for the CLI.

Provides bidirectional mapping between tag IDs and ``Category:Label`` strings,
with optional auto-creation of missing tags/categories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from lexicon.client import Lexicon


class TagResolver:
    """Lazy-loaded bidirectional tag ID <-> ``Category:Label`` resolver.

    The tag catalog is fetched from the API on first access and cached for the
    lifetime of the resolver instance.
    """

    def __init__(self, client: Lexicon) -> None:
        self._client = client
        self._id_to_label: dict[int, str] | None = None
        self._label_to_id: dict[str, int] | None = None
        self._category_id_to_label: dict[int, str] | None = None
        self._category_label_to_id: dict[str, int] | None = None

    def _load(self) -> None:
        """Fetch tags + categories and build lookup maps."""
        tags = self._client.tags.list() or []
        categories = self._client.tags.categories.list() or []

        self._category_id_to_label = {c["id"]: c["label"] for c in categories if "id" in c and "label" in c}
        self._category_label_to_id = {label.lower(): cid for cid, label in self._category_id_to_label.items()}

        self._id_to_label = {}
        self._label_to_id = {}
        for tag in tags:
            tag_id = tag.get("id")
            tag_label = tag.get("label")
            cat_id = tag.get("categoryId")
            if tag_id is None or tag_label is None or cat_id is None:
                continue
            cat_label = self._category_id_to_label.get(cat_id, "?")
            full = f"{cat_label}:{tag_label}"
            self._id_to_label[tag_id] = full
            self._label_to_id[full.lower()] = tag_id

    def _ensure_loaded(self) -> None:
        if self._id_to_label is None:
            self._load()

    def reload(self) -> None:
        """Force a fresh fetch of the tag catalog."""
        self._id_to_label = None
        self._load()

    def ids_to_labels(self, tag_ids: list[int]) -> list[str]:
        """Map tag IDs to ``Category:Label`` strings.

        Unknown IDs are rendered as ``?:<id>``.
        """
        self._ensure_loaded()
        assert self._id_to_label is not None
        return [self._id_to_label.get(tid, f"?:{tid}") for tid in tag_ids]

    def labels_to_ids(self, labels: list[str]) -> tuple[list[int], list[str]]:
        """Map ``Category:Label`` strings to tag IDs.

        Returns
        -------
        tuple[list[int], list[str]]
            (resolved IDs, unresolved label strings)
        """
        self._ensure_loaded()
        assert self._label_to_id is not None
        resolved: list[int] = []
        unresolved: list[str] = []
        for label in labels:
            tid = self._label_to_id.get(label.lower())
            if tid is not None:
                resolved.append(tid)
            else:
                unresolved.append(label)
        return resolved, unresolved

    def get_tag_id(self, label: str) -> int | None:
        """Look up a single ``Category:Label`` and return its ID, or ``None``."""
        self._ensure_loaded()
        assert self._label_to_id is not None
        return self._label_to_id.get(label.lower())

    def get_category_id(self, category_label: str) -> int | None:
        """Return the category ID for *category_label*, or ``None``."""
        self._ensure_loaded()
        assert self._category_label_to_id is not None
        return self._category_label_to_id.get(category_label.lower())

    def get_all_tags(self) -> dict[str, list[str]]:
        """Return all tags grouped by category label.

        Returns ``{category_label: [tag_label, ...]}``, preserving API order.
        """
        self._ensure_loaded()
        assert self._id_to_label is not None
        assert self._category_id_to_label is not None

        tags = self._client.tags.list() or []
        categories = self._client.tags.categories.list() or []

        cat_order = [c["label"] for c in categories if "label" in c]
        grouped: dict[str, list[str]] = {label: [] for label in cat_order}

        for tag in tags:
            cat_id = tag.get("categoryId")
            tag_label = tag.get("label")
            if cat_id is None or tag_label is None:
                continue
            cat_label = self._category_id_to_label.get(cat_id)
            if cat_label is not None:
                grouped.setdefault(cat_label, []).append(tag_label)

        return grouped

    def resolve_or_create(
        self,
        labels: list[str],
        *,
        auto_create: bool = False,
        confirm_fn: Optional[Callable[[str], bool]] = None,
    ) -> list[int]:
        """Resolve ``Category:Label`` strings to IDs, creating missing ones.

        Parameters
        ----------
        labels
            Tag strings in ``Category:Label`` format.
        auto_create
            If ``True``, create missing tags/categories without prompting.
        confirm_fn
            Called with a description string when ``auto_create`` is ``False``.
            Must return ``True`` to proceed with creation.  If ``None`` and
            ``auto_create`` is ``False``, missing tags raise ``ValueError``.

        Returns
        -------
        list[int]
            Resolved tag IDs (one per input label).

        Raises
        ------
        ValueError
            If a label is not in ``Category:Label`` format, or creation is
            declined / not possible.
        """
        self._ensure_loaded()
        assert self._label_to_id is not None
        assert self._category_label_to_id is not None
        assert self._category_id_to_label is not None

        result: list[int] = []

        for label in labels:
            if ":" not in label:
                raise ValueError(
                    f"Tag must be in 'Category:Label' format: {label!r}"
                )

            cat_part, tag_part = label.split(":", 1)
            cat_part = cat_part.strip()
            tag_part = tag_part.strip()
            if not cat_part or not tag_part:
                raise ValueError(
                    f"Tag must be in 'Category:Label' format: {label!r}"
                )

            existing_id = self._label_to_id.get(f"{cat_part}:{tag_part}".lower())
            if existing_id is not None:
                result.append(existing_id)
                continue

            # Need to create -- check permission
            if not auto_create:
                if confirm_fn is None:
                    raise ValueError(
                        f"Tag {label!r} does not exist (use --create-tags to auto-create)"
                    )
                if not confirm_fn(f"Create tag '{cat_part}:{tag_part}'?"):
                    raise ValueError(f"Tag creation declined for {label!r}")

            # Ensure category exists
            cat_id = self._category_label_to_id.get(cat_part.lower())
            if cat_id is None:
                if not auto_create and confirm_fn is not None:
                    if not confirm_fn(f"Create new category '{cat_part}'?"):
                        raise ValueError(
                            f"Category creation declined for {cat_part!r}"
                        )
                new_cat = self._client.tags.categories.add(cat_part)
                if new_cat is None or "id" not in new_cat:
                    raise ValueError(f"Failed to create category {cat_part!r}")
                cat_id = new_cat["id"]
                self._category_id_to_label[cat_id] = cat_part
                self._category_label_to_id[cat_part.lower()] = cat_id

            # Create the tag
            new_tag = self._client.tags.add(cat_id, tag_part)
            if new_tag is None or "id" not in new_tag:
                raise ValueError(f"Failed to create tag {label!r}")
            tag_id = new_tag["id"]
            full = f"{cat_part}:{tag_part}"
            self._id_to_label[tag_id] = full
            self._label_to_id[full.lower()] = tag_id
            result.append(tag_id)

        return result


def parse_tag_value(value: object) -> list[str] | list[int] | None:
    """Detect whether a tag edit value contains string labels or integer IDs.

    Returns
    -------
    list[str]
        If the value is a comma-separated string of ``Category:Label`` entries
        or a JSON list of strings.
    list[int]
        If the value is already a list of integers.
    None
        If the value format is unrecognised.
    """
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if parts and all(":" in p for p in parts):
            return parts
        return None

    if isinstance(value, list):
        if value and all(isinstance(v, str) for v in value):
            return value  # type: ignore[return-value]
        if value and all(isinstance(v, int) for v in value):
            return value  # type: ignore[return-value]

    return None
