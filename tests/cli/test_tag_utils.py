"""Tests for cli/tag_utils.py -- TagResolver and parse_tag_value."""

import unittest
from unittest.mock import MagicMock

from lexicon.cli.tag_utils import TagResolver, parse_tag_value


SAMPLE_TAGS = [
    {"id": 1, "label": "House", "categoryId": 10, "position": 0},
    {"id": 2, "label": "Techno", "categoryId": 10, "position": 1},
    {"id": 3, "label": "Chill", "categoryId": 20, "position": 0},
]

SAMPLE_CATEGORIES = [
    {"id": 10, "label": "Genre", "position": 0, "color": "#FF0000", "tags": [1, 2]},
    {"id": 20, "label": "Mood", "position": 1, "color": "#00FF00", "tags": [3]},
]


def _make_client(tags=None, categories=None):
    client = MagicMock()
    client.tags.list.return_value = tags if tags is not None else SAMPLE_TAGS
    client.tags.categories.list.return_value = (
        categories if categories is not None else SAMPLE_CATEGORIES
    )
    return client


class TestTagResolverIdsToLabels(unittest.TestCase):
    def test_basic_resolution(self):
        resolver = TagResolver(_make_client())
        assert resolver.ids_to_labels([1, 3]) == ["Genre:House", "Mood:Chill"]

    def test_unknown_id_fallback(self):
        resolver = TagResolver(_make_client())
        assert resolver.ids_to_labels([1, 999]) == ["Genre:House", "?:999"]

    def test_empty_list(self):
        resolver = TagResolver(_make_client())
        assert resolver.ids_to_labels([]) == []

    def test_all_ids(self):
        resolver = TagResolver(_make_client())
        result = resolver.ids_to_labels([1, 2, 3])
        assert result == ["Genre:House", "Genre:Techno", "Mood:Chill"]


class TestTagResolverLabelsToIds(unittest.TestCase):
    def test_basic_resolution(self):
        resolver = TagResolver(_make_client())
        ids, unresolved = resolver.labels_to_ids(["Genre:House", "Mood:Chill"])
        assert ids == [1, 3]
        assert unresolved == []

    def test_case_insensitive(self):
        resolver = TagResolver(_make_client())
        ids, unresolved = resolver.labels_to_ids(["genre:house", "MOOD:CHILL"])
        assert ids == [1, 3]
        assert unresolved == []

    def test_unresolved(self):
        resolver = TagResolver(_make_client())
        ids, unresolved = resolver.labels_to_ids(["Genre:House", "Vibe:Dark"])
        assert ids == [1]
        assert unresolved == ["Vibe:Dark"]

    def test_all_unresolved(self):
        resolver = TagResolver(_make_client())
        ids, unresolved = resolver.labels_to_ids(["Foo:Bar"])
        assert ids == []
        assert unresolved == ["Foo:Bar"]


class TestTagResolverGetTagId(unittest.TestCase):
    def test_found(self):
        resolver = TagResolver(_make_client())
        assert resolver.get_tag_id("Genre:House") == 1

    def test_not_found(self):
        resolver = TagResolver(_make_client())
        assert resolver.get_tag_id("Nope:Nada") is None

    def test_case_insensitive(self):
        resolver = TagResolver(_make_client())
        assert resolver.get_tag_id("genre:techno") == 2


class TestTagResolverGetCategoryId(unittest.TestCase):
    def test_found(self):
        resolver = TagResolver(_make_client())
        assert resolver.get_category_id("Genre") == 10

    def test_not_found(self):
        resolver = TagResolver(_make_client())
        assert resolver.get_category_id("Nonexistent") is None

    def test_case_insensitive(self):
        resolver = TagResolver(_make_client())
        assert resolver.get_category_id("mood") == 20


class TestTagResolverGetAllTags(unittest.TestCase):
    def test_grouped(self):
        resolver = TagResolver(_make_client())
        result = resolver.get_all_tags()
        assert list(result.keys()) == ["Genre", "Mood"]
        assert result["Genre"] == ["House", "Techno"]
        assert result["Mood"] == ["Chill"]

    def test_empty(self):
        resolver = TagResolver(_make_client(tags=[], categories=[]))
        result = resolver.get_all_tags()
        assert result == {}


class TestTagResolverResolveOrCreate(unittest.TestCase):
    def test_all_existing(self):
        resolver = TagResolver(_make_client())
        result = resolver.resolve_or_create(
            ["Genre:House", "Mood:Chill"], auto_create=True
        )
        assert result == [1, 3]

    def test_missing_tag_auto_create(self):
        client = _make_client()
        client.tags.add.return_value = {"id": 50, "label": "Ambient", "categoryId": 10}
        resolver = TagResolver(client)
        result = resolver.resolve_or_create(["Genre:Ambient"], auto_create=True)
        assert result == [50]
        client.tags.add.assert_called_once_with(10, "Ambient")

    def test_missing_category_and_tag_auto_create(self):
        client = _make_client()
        client.tags.categories.add.return_value = {"id": 30, "label": "Vibe"}
        client.tags.add.return_value = {"id": 51, "label": "Dark", "categoryId": 30}
        resolver = TagResolver(client)
        result = resolver.resolve_or_create(["Vibe:Dark"], auto_create=True)
        assert result == [51]
        client.tags.categories.add.assert_called_once_with("Vibe")
        client.tags.add.assert_called_once_with(30, "Dark")

    def test_missing_tag_no_auto_no_confirm_raises(self):
        resolver = TagResolver(_make_client())
        with self.assertRaises(ValueError, msg="does not exist"):
            resolver.resolve_or_create(["Genre:Ambient"], auto_create=False)

    def test_missing_tag_confirm_accepted(self):
        client = _make_client()
        client.tags.add.return_value = {"id": 60, "label": "Deep", "categoryId": 10}
        resolver = TagResolver(client)
        result = resolver.resolve_or_create(
            ["Genre:Deep"],
            auto_create=False,
            confirm_fn=lambda msg: True,
        )
        assert result == [60]

    def test_missing_tag_confirm_declined(self):
        resolver = TagResolver(_make_client())
        with self.assertRaises(ValueError, msg="declined"):
            resolver.resolve_or_create(
                ["Genre:NewTag"],
                auto_create=False,
                confirm_fn=lambda msg: False,
            )

    def test_invalid_format_no_colon(self):
        resolver = TagResolver(_make_client())
        with self.assertRaises(ValueError, msg="Category:Label"):
            resolver.resolve_or_create(["JustALabel"], auto_create=True)

    def test_invalid_format_empty_parts(self):
        resolver = TagResolver(_make_client())
        with self.assertRaises(ValueError):
            resolver.resolve_or_create([":Label"], auto_create=True)
        with self.assertRaises(ValueError):
            resolver.resolve_or_create(["Category:"], auto_create=True)

    def test_category_create_failure(self):
        client = _make_client()
        client.tags.categories.add.return_value = None
        resolver = TagResolver(client)
        with self.assertRaises(ValueError, msg="Failed to create category"):
            resolver.resolve_or_create(["NewCat:Tag"], auto_create=True)

    def test_tag_create_failure(self):
        client = _make_client()
        client.tags.add.return_value = None
        resolver = TagResolver(client)
        with self.assertRaises(ValueError, msg="Failed to create tag"):
            resolver.resolve_or_create(["Genre:FailTag"], auto_create=True)


class TestTagResolverReload(unittest.TestCase):
    def test_reload_fetches_again(self):
        client = _make_client()
        resolver = TagResolver(client)
        resolver.ids_to_labels([1])
        assert client.tags.list.call_count == 1
        resolver.reload()
        assert client.tags.list.call_count == 2


class TestTagResolverLazyLoad(unittest.TestCase):
    def test_no_fetch_until_needed(self):
        client = _make_client()
        _ = TagResolver(client)
        client.tags.list.assert_not_called()

    def test_single_fetch_on_multiple_calls(self):
        client = _make_client()
        resolver = TagResolver(client)
        resolver.ids_to_labels([1])
        resolver.labels_to_ids(["Genre:House"])
        resolver.get_tag_id("Mood:Chill")
        assert client.tags.list.call_count == 1


class TestParseTagValue(unittest.TestCase):
    def test_comma_separated_string(self):
        result = parse_tag_value("Genre:House, Mood:Chill")
        assert result == ["Genre:House", "Mood:Chill"]

    def test_single_string(self):
        result = parse_tag_value("Genre:House")
        assert result == ["Genre:House"]

    def test_string_without_colons_returns_none(self):
        assert parse_tag_value("just a string") is None

    def test_list_of_strings(self):
        result = parse_tag_value(["Genre:House", "Mood:Chill"])
        assert result == ["Genre:House", "Mood:Chill"]

    def test_list_of_ints(self):
        result = parse_tag_value([1, 2, 3])
        assert result == [1, 2, 3]

    def test_empty_list(self):
        assert parse_tag_value([]) is None

    def test_none(self):
        assert parse_tag_value(None) is None

    def test_int_value(self):
        assert parse_tag_value(42) is None

    def test_mixed_list_returns_none(self):
        assert parse_tag_value([1, "two"]) is None
