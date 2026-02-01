"""Tests for list-tracks command."""

import json
import unittest
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from lexicon.cli import app


class TestListTracks(unittest.TestCase):
    """Tests for the list-tracks CLI command."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.sample_tracks = [
            {
                "id": 1,
                "title": "Test Track",
                "artist": "Test Artist",
                "albumTitle": "Test Album",
                "bpm": 128,
                "key": "C Major",
                "year": 2023,
            },
            {
                "id": 2,
                "title": "Another Song",
                "artist": "Different Artist",
                "albumTitle": "Different Album",
                "bpm": 140,
                "key": "D Minor",
                "year": 2024,
            },
        ]

    @patch("lexicon.cli.commands.tracks.prompt_for_fields")
    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_default(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks with default options."""
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(app, ["list-tracks"])

        assert result.exit_code == 0
        assert "Found 2 track(s):" in result.stdout
        assert "[1] Test Track - Test Artist - Test Album" in result.stdout
        assert "[2] Another Song - Different Artist - Different Album" in result.stdout
        mock_lexicon_class.assert_called_once_with(host=None, port=None)

    @patch("lexicon.cli.commands.tracks.prompt_for_fields")
    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_empty(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks when no tracks are found."""
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = []
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(app, ["list-tracks"])

        assert result.exit_code == 0
        assert "No tracks found." in result.stdout

    @patch("lexicon.cli.commands.tracks.prompt_for_fields")
    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_with_host_and_port(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks with custom host and port."""
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["list-tracks", "--host", "192.168.1.100", "--port", "8080"]
        )

        assert result.exit_code == 0
        mock_lexicon_class.assert_called_once_with(host="192.168.1.100", port=8080)

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_with_custom_fields(self, mock_lexicon_class):
        """Test list-tracks with custom field options."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["list-tracks", "-f", "title", "-f", "bpm", "-f", "key"]
        )

        assert result.exit_code == 0
        assert "[1] Test Track - 128 - C Major" in result.stdout
        assert "[2] Another Song - 140 - D Minor" in result.stdout

        # Verify correct fields were requested
        call_args = mock_client.tracks.list.call_args
        fields = call_args.kwargs["fields"]
        assert set(fields) >= {"id", "title", "bpm", "key"}

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_with_format_string(self, mock_lexicon_class):
        """Test list-tracks with format string."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["list-tracks", "--format", "{title} by {artist} [{bpm} BPM]"]
        )

        assert result.exit_code == 0
        assert "Test Track by Test Artist [128 BPM]" in result.stdout
        assert "Another Song by Different Artist [140 BPM]" in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_format_with_missing_field(self, mock_lexicon_class):
        """Test list-tracks with format string when field is missing."""
        incomplete_tracks = [{"id": 1, "title": "Test Track", "artist": "Test Artist"}]
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = incomplete_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["list-tracks", "--format", "{title} - {artist} [{bpm} BPM]"]
        )

        assert result.exit_code == 0
        assert "Test Track - Test Artist [N/A BPM]" in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_format_overrides_fields(self, mock_lexicon_class):
        """Test that --format option overrides --field options."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "list-tracks",
                "-f",
                "title",
                "-f",
                "albumTitle",
                "--format",
                "{title} - {bpm}",
            ],
        )

        assert result.exit_code == 0
        assert "Test Track - 128" in result.stdout
        assert "Test Album" not in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_id_always_included(self, mock_lexicon_class):
        """Test that id is always included in API request."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        self.runner.invoke(app, ["list-tracks", "-f", "title", "-f", "bpm"])

        call_args = mock_client.tracks.list.call_args
        fields = call_args.kwargs["fields"]
        assert "id" in fields

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_compact_format(self, mock_lexicon_class):
        """Test list-tracks with compact output format."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "list-tracks",
                "-f",
                "title",
                "-f",
                "artist",
                "--output-format",
                "compact",
            ],
        )

        assert result.exit_code == 0
        assert "[1] Test Track - Test Artist" in result.stdout
        assert "[2] Another Song - Different Artist" in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_table_format(self, mock_lexicon_class):
        """Test list-tracks with table output format."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["list-tracks", "-f", "title", "-f", "bpm", "--output-format", "table"]
        )

        assert result.exit_code == 0
        assert "title" in result.stdout
        assert "Test Track" in result.stdout
        assert "128" in result.stdout
        assert "-+-" in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_pairs_format(self, mock_lexicon_class):
        """Test list-tracks with pairs output format."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            ["list-tracks", "-f", "title", "-f", "artist", "--output-format", "pairs"],
        )

        assert result.exit_code == 0
        assert "Track 1" in result.stdout
        assert "Track 2" in result.stdout
        assert "Test Track" in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_list_tracks_json_flag(self, mock_lexicon_class):
        """Test that --json flag works correctly."""
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["list-tracks", "-f", "title", "-f", "artist", "--json"]
        )

        assert result.exit_code == 0
        # Parse JSON from output
        output_lines = result.stdout.split("\n")
        json_str = "\n".join(output_lines[1:])  # Skip "Listing..." line
        output = json.loads(json_str)
        assert isinstance(output, list)
        assert len(output) == 2
        assert output[0]["title"] == "Test Track"
