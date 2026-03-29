"""Tests for list-tracks and update-track commands."""

import json
import unittest
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from lexicon.cli import app


SAMPLE_TRACKS = [
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


class TestListTracks(unittest.TestCase):
    """Tests for the list-tracks CLI command."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.sample_tracks = SAMPLE_TRACKS

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


class TestUpdateTrack(unittest.TestCase):
    """Tests for the update-track CLI command."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.updated_track = {
            "id": 843,
            "title": "Rinse & The Night",
            "artist": "Test Artist",
            "genre": "Bass House",
            "bpm": 126,
        }

    # --- --set parsing ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_set_single_field(self, mock_lexicon_class):
        """Test --set with a single field."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--set", "title=Rinse & The Night"]
        )

        assert result.exit_code == 0
        mock_client.tracks.update.assert_called_once_with(
            843, {"title": "Rinse & The Night"}
        )

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_set_multiple_fields(self, mock_lexicon_class):
        """Test --set with multiple fields."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--set",
                "title=Rinse & The Night",
                "--set",
                "genre=Bass House",
            ],
        )

        assert result.exit_code == 0
        call_edits = mock_client.tracks.update.call_args[0][1]
        assert call_edits == {"title": "Rinse & The Night", "genre": "Bass House"}

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_set_value_containing_equals(self, mock_lexicon_class):
        """Test --set with a value that contains '='."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--set", "comment=a=b=c"]
        )

        assert result.exit_code == 0
        call_edits = mock_client.tracks.update.call_args[0][1]
        assert call_edits == {"comment": "a=b=c"}

    def test_set_missing_equals(self):
        """Test --set with a value that has no '=' sign."""
        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--set", "title"]
        )

        assert result.exit_code == 1
        assert "missing '='" in result.output

    # --- --edits JSON parsing ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_edits_json(self, mock_lexicon_class):
        """Test --edits with valid JSON."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--edits",
                '{"title": "Rinse & The Night", "genre": "Bass House"}',
            ],
        )

        assert result.exit_code == 0
        call_edits = mock_client.tracks.update.call_args[0][1]
        assert call_edits == {"title": "Rinse & The Night", "genre": "Bass House"}

    def test_edits_invalid_json(self):
        """Test --edits with invalid JSON."""
        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--edits", "{bad json}"]
        )

        assert result.exit_code == 1
        assert "invalid JSON" in result.output

    def test_edits_non_object_json(self):
        """Test --edits with JSON that is not an object."""
        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--edits", '["a", "b"]']
        )

        assert result.exit_code == 1
        assert "must be a JSON object" in result.output

    # --- Mutual exclusion ---

    def test_set_and_edits_mutually_exclusive(self):
        """Test that --set and --edits cannot be used together."""
        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--set",
                "title=New",
                "--edits",
                '{"genre": "House"}',
            ],
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_neither_set_nor_edits(self):
        """Test that at least one of --set or --edits is required."""
        result = self.runner.invoke(app, ["update-track", "--id", "843"])

        assert result.exit_code == 1
        assert "provide either --set or --edits" in result.output

    def test_edits_empty_json_object(self):
        """Test --edits with an empty JSON object."""
        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--edits", "{}"]
        )

        assert result.exit_code == 1
        assert "no edits provided" in result.output

    # --- Dry-run ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_dry_run_shows_diff(self, mock_lexicon_class):
        """Test --dry-run shows before/after without calling update."""
        mock_client = MagicMock()
        mock_client.tracks.get.return_value = {
            "id": 843,
            "title": "Old Title",
            "genre": "",
        }
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--set",
                "title=New Title",
                "--set",
                "genre=Bass House",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Track 843:" in result.output
        assert "Old Title" in result.output
        assert "New Title" in result.output
        assert "Bass House" in result.output
        assert "dry run" in result.output
        assert "2 field change(s)" in result.output
        mock_client.tracks.update.assert_not_called()

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_dry_run_track_not_found(self, mock_lexicon_class):
        """Test --dry-run when track doesn't exist."""
        mock_client = MagicMock()
        mock_client.tracks.get.return_value = None
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            ["update-track", "--id", "999", "--set", "title=New", "--dry-run"],
        )

        assert result.exit_code == 1
        assert "not found" in result.output

    # --- Successful update ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_successful_update_pairs_output(self, mock_lexicon_class):
        """Test successful update with default pairs output."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--set", "title=Rinse & The Night"]
        )

        assert result.exit_code == 0
        assert "updated successfully" in result.output
        assert "Rinse & The Night" in result.output

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_successful_update_json_output(self, mock_lexicon_class):
        """Test successful update with JSON output."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--set",
                "title=Rinse & The Night",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code == 0
        lines = result.output.split("\n")
        json_str = "\n".join(lines[1:])  # Skip "updated successfully" line
        output = json.loads(json_str)
        assert output["id"] == 843
        assert output["title"] == "Rinse & The Night"

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_successful_update_compact_output(self, mock_lexicon_class):
        """Test successful update with compact output."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--set",
                "title=Rinse & The Night",
                "--output-format",
                "compact",
            ],
        )

        assert result.exit_code == 0
        assert "[843]" in result.output
        assert "Rinse & The Night" in result.output

    # --- Failed update ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_update_returns_none(self, mock_lexicon_class):
        """Test that None return from update exits with error."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = None
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["update-track", "--id", "843", "--set", "title=New"]
        )

        assert result.exit_code == 1
        assert "failed to update" in result.output

    # --- Connection options ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_host_and_port_passed_to_client(self, mock_lexicon_class):
        """Test that --host and --port are forwarded to the SDK client."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = self.updated_track
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "update-track",
                "--id",
                "843",
                "--set",
                "title=New",
                "--host",
                "192.168.1.100",
                "--port",
                "9999",
            ],
        )

        assert result.exit_code == 0
        mock_lexicon_class.assert_called_once_with(host="192.168.1.100", port=9999)
