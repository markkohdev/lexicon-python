"""Tests for list-fields command."""

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from lexicon.cli import app


class TestListFieldsCommand(unittest.TestCase):
    """Tests for the list-fields CLI command."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("lexicon.cli.commands.fields.TRACK_FIELDS")
    def test_list_fields_track_default(self, mock_track_fields):
        """Test list-fields with default track entity."""
        mock_track_fields = (
            "id", "type", "title", "artist", "albumTitle", "label",
            "remixer", "mix", "composer", "producer", "bpm", "duration"
        )
        with patch("lexicon.cli.commands.fields.TRACK_FIELDS", mock_track_fields):
            result = self.runner.invoke(app, ["list-fields"])

        assert result.exit_code == 0
        assert "Available fields for tracks (12):" in result.output
        assert "id" in result.output
        assert "title" in result.output
        assert "artist" in result.output

    @patch("lexicon.cli.commands.fields.TRACK_FIELDS")
    def test_list_fields_track_explicit(self, mock_track_fields):
        """Test list-fields with explicit track entity."""
        mock_track_fields = ("id", "title", "artist", "bpm")
        with patch("lexicon.cli.commands.fields.TRACK_FIELDS", mock_track_fields):
            result = self.runner.invoke(app, ["list-fields", "track"])

        assert result.exit_code == 0
        assert "Available fields for tracks (4):" in result.output
        for field in mock_track_fields:
            assert field in result.output

    @patch("lexicon.cli.commands.fields.SORT_FIELDS")
    @patch("lexicon.cli.commands.fields.TRACK_FIELDS")
    def test_list_fields_track_sortable(self, mock_track_fields, mock_sort_fields):
        """Test list-fields with sortable flag for tracks."""
        mock_sort_fields = ("id", "title", "artist", "bpm", "duration")
        with patch("lexicon.cli.commands.fields.SORT_FIELDS", mock_sort_fields):
            result = self.runner.invoke(app, ["list-fields", "track", "--sortable"])

        assert result.exit_code == 0
        assert "Sortable fields for tracks (5):" in result.output
        for field in mock_sort_fields:
            assert field in result.output

    def test_list_fields_playlist(self):
        """Test list-fields with playlist entity."""
        result = self.runner.invoke(app, ["list-fields", "playlist"])

        assert result.exit_code == 0
        assert "Available fields for playlists (9):" in result.output
        assert "id" in result.output
        assert "name" in result.output
        assert "dateAdded" in result.output

    def test_list_fields_playlist_sortable(self):
        """Test list-fields with sortable flag for playlists."""
        result = self.runner.invoke(app, ["list-fields", "playlist", "--sortable"])

        assert result.exit_code == 0
        assert "Playlists do not currently support sorting via the API." in result.output

    def test_list_fields_tag(self):
        """Test list-fields with tag entity."""
        result = self.runner.invoke(app, ["list-fields", "tag"])

        assert result.exit_code == 0
        assert "Available fields for tags (4):" in result.output
        assert "id" in result.output
        assert "label" in result.output

    def test_list_fields_tag_sortable(self):
        """Test list-fields with sortable flag for tags."""
        result = self.runner.invoke(app, ["list-fields", "tag", "--sortable"])

        assert result.exit_code == 0
        assert "Tags do not currently support sorting via the API." in result.output

    def test_list_fields_case_insensitive(self):
        """Test that entity type is case-insensitive."""
        result_upper = self.runner.invoke(app, ["list-fields", "TRACK"])
        result_mixed = self.runner.invoke(app, ["list-fields", "TrAcK"])

        assert result_upper.exit_code == 0
        assert result_mixed.exit_code == 0
        assert "Available fields for tracks" in result_upper.output

    def test_list_fields_invalid_entity(self):
        """Test list-fields with invalid entity type."""
        result = self.runner.invoke(app, ["list-fields", "invalid_entity"])

        assert result.exit_code == 1
        assert "Error: Unknown entity type 'invalid_entity'" in result.output

    def test_list_fields_invalid_entity_variations(self):
        """Test list-fields with various invalid entity types."""
        invalid_entities = ["album", "artist", "cue", "song"]
        
        for entity in invalid_entities:
            result = self.runner.invoke(app, ["list-fields", entity])
            assert result.exit_code == 1
            assert "Error: Unknown entity type" in result.output

    @patch("lexicon.cli.commands.fields.SORT_FIELDS")
    def test_list_fields_sortable_count_correct(self, mock_sort_fields):
        """Test that sortable field count matches the number of sortable fields."""
        mock_sort_fields = (
            "id", "type", "title", "artist", "albumTitle", "label"
        )
        with patch("lexicon.cli.commands.fields.SORT_FIELDS", mock_sort_fields):
            result = self.runner.invoke(app, ["list-fields", "track", "--sortable"])

        assert result.exit_code == 0
        assert "Sortable fields for tracks (6):" in result.output
