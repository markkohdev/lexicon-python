"""Tests for formatting utilities."""

import unittest

from lexicon.cli.formatting import format_value, format_table, format_pairs


class TestFormatValue(unittest.TestCase):
    """Tests for the format_value helper function."""

    def test_format_none(self):
        """Test formatting None values."""
        assert format_value(None) == ""

    def test_format_string(self):
        """Test formatting string values."""
        assert format_value("test") == "test"

    def test_format_integer(self):
        """Test formatting integer values."""
        assert format_value(42) == "42"

    def test_format_float_whole_number(self):
        """Test formatting float values that are whole numbers."""
        assert format_value(42.0) == "42"

    def test_format_float_decimal(self):
        """Test formatting float values with decimals."""
        assert format_value(42.5) == "42.5"

    def test_format_boolean_true(self):
        """Test formatting boolean True."""
        assert format_value(True) == "Yes"

    def test_format_boolean_false(self):
        """Test formatting boolean False."""
        assert format_value(False) == "No"

    def test_format_empty_list(self):
        """Test formatting empty list."""
        assert format_value([]) == ""

    def test_format_list_with_values(self):
        """Test formatting list with values."""
        assert format_value(["a", "b", "c"]) == "a, b, c"

    def test_format_list_with_mixed_types(self):
        """Test formatting list with mixed types."""
        assert format_value(["a", 1, "b"]) == "a, 1, b"


class TestFormatTable(unittest.TestCase):
    """Tests for the format_table helper function."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_tracks = [
            {
                "id": 1,
                "title": "Test Track",
                "artist": "Test Artist",
                "bpm": 128.5,
            },
            {
                "id": 2,
                "title": "Another Song",
                "artist": "Different Artist",
                "bpm": 140,
            },
        ]

    def test_format_table_empty(self):
        """Test formatting empty track list."""
        result = format_table([], ["title", "artist"])
        assert result == ""

    def test_format_table_basic(self):
        """Test basic table formatting."""
        result = format_table(self.sample_tracks, ["id", "title", "bpm"])

        # Check for headers
        lines = result.split("\n")
        assert "id" in lines[0]
        assert "title" in lines[0]
        assert "bpm" in lines[0]

        # Check for separator
        assert "-+-" in lines[1]

        # Check for data rows
        assert "1" in result
        assert "Test Track" in result
        assert "128.5" in result

    def test_format_table_column_width_limit(self):
        """Test that long values are truncated."""
        long_track = [
            {
                "id": 1,
                "title": "This is a very long track title that should be truncated for display purposes",
                "artist": "Artist",
            }
        ]
        result = format_table(long_track, ["id", "title", "artist"], max_col_width=20)

        # Check that the title is truncated
        assert "..." in result  # Should contain truncation indicator
        # The title should be truncated to 20 chars max
        assert "This is a very lo" in result

    def test_format_table_with_missing_fields(self):
        """Test table formatting with missing fields in data."""
        incomplete_track = [
            {
                "id": 1,
                "title": "Test Track",
                # artist is missing
            }
        ]
        result = format_table(incomplete_track, ["id", "title", "artist"])

        assert "Test Track" in result
        # Missing field should show empty


class TestFormatPairs(unittest.TestCase):
    """Tests for the format_pairs helper function."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_tracks = [
            {
                "id": 1,
                "title": "Test Track",
                "artist": "Test Artist",
                "bpm": 128,
            },
            {
                "id": 2,
                "title": "Another Song",
                "artist": "Different Artist",
                "bpm": 140,
            },
        ]

    def test_format_pairs_empty(self):
        """Test formatting empty track list."""
        result = format_pairs([], ["title", "artist"])
        assert result == ""

    def test_format_pairs_single_track(self):
        """Test formatting single track in pairs format."""
        result = format_pairs(self.sample_tracks[:1], ["title", "artist", "bpm"])

        # Check structure
        assert "Track 1" in result
        assert "ID: 1" in result
        assert "title" in result
        assert "Test Track" in result
        assert "artist" in result
        assert "Test Artist" in result
        assert "bpm" in result
        assert "128" in result

    def test_format_pairs_multiple_tracks(self):
        """Test formatting multiple tracks in pairs format."""
        result = format_pairs(self.sample_tracks, ["title", "artist"])

        # Check both tracks are present
        assert "Track 1" in result
        assert "Track 2" in result
        assert "Test Track" in result
        assert "Another Song" in result

        # Check that tracks are separated
        assert result.count("Track 1") == 1
        assert result.count("Track 2") == 1

    def test_format_pairs_skips_id_field(self):
        """Test that id field is not duplicated in pairs format."""
        result = format_pairs(self.sample_tracks[:1], ["id", "title", "artist"])

        # id should appear only in header, not in field list
        assert "ID: 1" in result
        lines = result.split("\n")
        # Find lines that contain "id" field (should be none after the header)
        field_lines = [line for line in lines if line.strip().startswith("id")]
        assert len(field_lines) == 0

    def test_format_pairs_handles_missing_fields(self):
        """Test pairs formatting with missing fields."""
        incomplete_tracks = [
            {
                "id": 1,
                "title": "Test Track",
                # artist is missing
            }
        ]
        result = format_pairs(incomplete_tracks, ["title", "artist"])

        assert "Test Track" in result
        # Missing field should appear with empty value
