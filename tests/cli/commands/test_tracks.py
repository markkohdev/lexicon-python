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


class TestSearchTracks(unittest.TestCase):
    """Tests for the search-tracks CLI command."""

    def setUp(self):
        self.runner = CliRunner()
        self.sample_tracks = SAMPLE_TRACKS

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_filter_and_default_sort(self, mock_lexicon_class):
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "search-tracks",
                "--filter",
                "artist=Test Artist",
                "-f",
                "title",
                "-f",
                "artist",
            ],
        )

        assert result.exit_code == 0
        assert "Searching tracks..." in result.stdout
        assert "[1] Test Track - Test Artist" in result.stdout
        call_kw = mock_client.tracks.search.call_args.kwargs
        assert call_kw["filter"] == {"artist": "Test Artist"}
        assert call_kw["sort"] == [("title", "asc")]
        assert call_kw["source"] == "non-archived"
        assert "id" in call_kw["fields"]

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_sort_parsing(self, mock_lexicon_class):
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app,
            [
                "search-tracks",
                "--filter",
                "bpm=128",
                "--sort",
                "title:desc",
                "--sort",
                "artist",
                "-f",
                "title",
            ],
        )

        assert result.exit_code == 0
        assert mock_client.tracks.search.call_args.kwargs["sort"] == [
            ("title", "desc"),
            ("artist", "asc"),
        ]

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_source_option(self, mock_lexicon_class):
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = []
        mock_lexicon_class.return_value = mock_client

        self.runner.invoke(
            app,
            ["search-tracks", "--source", "archived", "-f", "title"],
        )

        assert mock_client.tracks.search.call_args.kwargs["source"] == "archived"

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_table_and_pairs_json_output(self, mock_lexicon_class):
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        r_table = self.runner.invoke(
            app,
            ["search-tracks", "-f", "title", "-f", "bpm", "--output-format", "table"],
        )
        assert r_table.exit_code == 0
        assert "-+-" in r_table.stdout

        r_pairs = self.runner.invoke(
            app,
            ["search-tracks", "-f", "title", "--output-format", "pairs"],
        )
        assert r_pairs.exit_code == 0
        assert "Track 1" in r_pairs.stdout

        r_json = self.runner.invoke(
            app, ["search-tracks", "-f", "title", "-f", "artist", "--json"]
        )
        assert r_json.exit_code == 0
        lines = r_json.stdout.split("\n")
        json_str = "\n".join(lines[1:])
        data = json.loads(json_str)
        assert len(data) == 2
        assert data[0]["title"] == "Test Track"

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_empty_results(self, mock_lexicon_class):
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = []
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(app, ["search-tracks", "-f", "title"])
        assert result.exit_code == 0
        assert "No tracks found." in result.stdout

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_none_returns_error(self, mock_lexicon_class):
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = None
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(app, ["search-tracks", "-f", "title"])
        assert result.exit_code == 1
        assert "Error: search failed." in result.stderr

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_1000_results_warning(self, mock_lexicon_class):
        many = [{"id": i, "title": f"T{i}", "artist": "A"} for i in range(1000)]
        mock_client = MagicMock()
        mock_client.tracks.search.return_value = many
        mock_lexicon_class.return_value = mock_client

        result = self.runner.invoke(
            app, ["search-tracks", "-f", "title", "-f", "artist"]
        )
        assert result.exit_code == 0
        assert "1000" in result.stderr
        assert "limit" in result.stderr.lower()

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_search_invalid_filter_missing_equals(self, mock_lexicon_class):
        result = self.runner.invoke(
            app, ["search-tracks", "--filter", "notakeyvalue", "-f", "title"]
        )
        assert result.exit_code == 1
        assert "missing '='" in result.stderr
        mock_lexicon_class.assert_not_called()


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


class TestBulkUpdate(unittest.TestCase):
    """Tests for the bulk-update CLI command."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    # --- File parsing: JSON array ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_json_array_file(self, mock_lexicon_class):
        """Test parsing a JSON array edits file."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = [
            {"id": 843, "title": "New Title", "genre": "Bass House"},
            {"id": 844, "artist": "ZHU ft. 24kGoldn"},
        ]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "New Title", "genre": "Bass House"},
                {"id": 844, "artist": "ZHU ft. 24kGoldn"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "edits.json"])

        assert result.exit_code == 0
        assert "Updated 2/2" in result.output
        assert mock_client.tracks.update.call_count == 2

    # --- File parsing: JSONL ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_jsonl_file(self, mock_lexicon_class):
        """Test parsing a JSONL edits file."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = [
            {"id": 843, "title": "New Title"},
            {"id": 844, "artist": "ZHU"},
        ]
        mock_lexicon_class.return_value = mock_client

        lines = [
            '{"id": 843, "title": "New Title"}',
            '{"id": 844, "artist": "ZHU"}',
        ]

        with self.runner.isolated_filesystem():
            with open("edits.jsonl", "w") as f:
                f.write("\n".join(lines))

            result = self.runner.invoke(app, ["bulk-update", "--file", "edits.jsonl"])

        assert result.exit_code == 0
        assert "Updated 2/2" in result.output
        assert mock_client.tracks.update.call_count == 2

    # --- File parsing: stdin ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_stdin_input(self, mock_lexicon_class):
        """Test reading edits from stdin via --file -."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = {"id": 843, "title": "New"}
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps([{"id": 843, "title": "New"}])

        result = self.runner.invoke(app, ["bulk-update", "--file", "-"], input=edits)

        assert result.exit_code == 0
        assert "Updated 1/1" in result.output

    # --- Validation errors ---

    def test_empty_file(self):
        """Test error on empty edits file."""
        with self.runner.isolated_filesystem():
            with open("empty.json", "w") as f:
                f.write("")

            result = self.runner.invoke(app, ["bulk-update", "--file", "empty.json"])

        assert result.exit_code == 1
        assert "empty" in result.output

    def test_file_not_found(self):
        """Test error when edits file doesn't exist."""
        result = self.runner.invoke(app, ["bulk-update", "--file", "nonexistent.json"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_invalid_json(self):
        """Test error on invalid JSON."""
        with self.runner.isolated_filesystem():
            with open("bad.json", "w") as f:
                f.write("{bad json}")

            result = self.runner.invoke(app, ["bulk-update", "--file", "bad.json"])

        assert result.exit_code == 1
        assert "invalid JSON" in result.output

    def test_missing_id_field(self):
        """Test error when an entry is missing the id field."""
        edits = json.dumps([{"title": "No ID here"}])

        with self.runner.isolated_filesystem():
            with open("noid.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "noid.json"])

        assert result.exit_code == 1
        assert "missing required 'id'" in result.output

    def test_non_integer_id(self):
        """Test error when id is not an integer."""
        edits = json.dumps([{"id": "abc", "title": "Bad"}])

        with self.runner.isolated_filesystem():
            with open("badid.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "badid.json"])

        assert result.exit_code == 1
        assert "non-integer" in result.output

    def test_entry_with_no_edit_fields(self):
        """Test error when entry has id but no edit fields."""
        edits = json.dumps([{"id": 843}])

        with self.runner.isolated_filesystem():
            with open("noedit.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "noedit.json"])

        assert result.exit_code == 1
        assert "no edit fields" in result.output

    def test_entry_not_object(self):
        """Test error when an entry is not a JSON object."""
        edits = json.dumps(["not an object"])

        with self.runner.isolated_filesystem():
            with open("notobj.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "notobj.json"])

        assert result.exit_code == 1
        assert "not a JSON object" in result.output

    def test_empty_json_array(self):
        """Test error on empty JSON array."""
        with self.runner.isolated_filesystem():
            with open("empty_arr.json", "w") as f:
                f.write("[]")

            result = self.runner.invoke(
                app, ["bulk-update", "--file", "empty_arr.json"]
            )

        assert result.exit_code == 1
        assert "no entries" in result.output

    def test_jsonl_invalid_line(self):
        """Test error on invalid JSON within a JSONL file."""
        lines = '{"id": 843, "title": "Good"}\n{bad line}'

        with self.runner.isolated_filesystem():
            with open("bad.jsonl", "w") as f:
                f.write(lines)

            result = self.runner.invoke(app, ["bulk-update", "--file", "bad.jsonl"])

        assert result.exit_code == 1
        assert "line 2" in result.output

    # --- Dry-run ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_dry_run_shows_diff_no_update(self, mock_lexicon_class):
        """Test --dry-run shows diff and makes no update calls."""
        mock_client = MagicMock()
        mock_client.tracks.get_many.return_value = [
            {"id": 843, "title": "Old Title", "genre": ""},
            {"id": 844, "artist": "Zhu ft 24kgoldn"},
        ]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "New Title", "genre": "Bass House"},
                {"id": 844, "artist": "ZHU ft. 24kGoldn"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app, ["bulk-update", "--file", "edits.json", "--dry-run"]
            )

        assert result.exit_code == 0
        assert "Track 843:" in result.output
        assert "Old Title" in result.output
        assert "New Title" in result.output
        assert "Bass House" in result.output
        assert "Track 844:" in result.output
        assert "ZHU ft. 24kGoldn" in result.output
        assert "dry run" in result.output
        assert "3 field change(s)" in result.output
        mock_client.tracks.update.assert_not_called()

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_dry_run_track_not_found(self, mock_lexicon_class):
        """Test --dry-run when a track is not found."""
        mock_client = MagicMock()
        mock_client.tracks.get_many.return_value = [None]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps([{"id": 999, "title": "New"}])

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app, ["bulk-update", "--file", "edits.json", "--dry-run"]
            )

        assert result.exit_code == 0
        assert "not found" in result.output
        mock_client.tracks.update.assert_not_called()

    # --- Apply mode ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_apply_all_succeed(self, mock_lexicon_class):
        """Test successful bulk update of all tracks."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = [
            {"id": 843, "title": "A"},
            {"id": 844, "title": "B"},
            {"id": 845, "title": "C"},
        ]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "A"},
                {"id": 844, "title": "B"},
                {"id": 845, "title": "C"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "edits.json"])

        assert result.exit_code == 0
        assert "Updated 3/3 track(s) successfully" in result.output

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_apply_stops_on_first_error(self, mock_lexicon_class):
        """Test that apply mode stops on first failure by default."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = [
            {"id": 843, "title": "A"},
            None,  # second fails
            {"id": 845, "title": "C"},  # should not be reached
        ]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "A"},
                {"id": 844, "title": "B"},
                {"id": 845, "title": "C"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "edits.json"])

        assert result.exit_code == 0
        assert "1/2" in result.output
        assert "1 failed" in result.output
        assert mock_client.tracks.update.call_count == 2

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_continue_on_error(self, mock_lexicon_class):
        """Test --continue-on-error continues after failures."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = [
            {"id": 843, "title": "A"},
            None,  # second fails
            {"id": 845, "title": "C"},
        ]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "A"},
                {"id": 844, "title": "B"},
                {"id": 845, "title": "C"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app,
                ["bulk-update", "--file", "edits.json", "--continue-on-error"],
            )

        assert result.exit_code == 0
        assert "2/3" in result.output
        assert "1 failed" in result.output
        assert mock_client.tracks.update.call_count == 3

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_continue_on_error_with_exception(self, mock_lexicon_class):
        """Test --continue-on-error handles exceptions from update."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = [
            Exception("network error"),
            {"id": 844, "title": "B"},
        ]
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "A"},
                {"id": 844, "title": "B"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app,
                ["bulk-update", "--file", "edits.json", "--continue-on-error"],
            )

        assert result.exit_code == 0
        assert "1/2" in result.output
        assert "1 failed" in result.output
        assert "network error" in result.output

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_exception_stops_without_continue_on_error(self, mock_lexicon_class):
        """Test that exceptions stop processing without --continue-on-error."""
        mock_client = MagicMock()
        mock_client.tracks.update.side_effect = Exception("network error")
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps(
            [
                {"id": 843, "title": "A"},
                {"id": 844, "title": "B"},
            ]
        )

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(app, ["bulk-update", "--file", "edits.json"])

        assert result.exit_code == 0
        assert "0/1" in result.output or "1 failed" in result.output
        assert mock_client.tracks.update.call_count == 1

    # --- Output formats ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_json_output_format(self, mock_lexicon_class):
        """Test --output-format json."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = {"id": 843, "title": "New"}
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps([{"id": 843, "title": "New"}])

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app,
                ["bulk-update", "--file", "edits.json", "--output-format", "json"],
            )

        assert result.exit_code == 0
        output = json.loads(result.output.rsplit("Updated", 1)[0].strip())
        assert isinstance(output, list)
        assert output[0]["status"] == "ok"
        assert output[0]["id"] == 843

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_table_output_format(self, mock_lexicon_class):
        """Test --output-format table shows diff view."""
        mock_client = MagicMock()
        mock_client.tracks.get_many.return_value = [
            {"id": 843, "title": "Old Title"},
        ]
        mock_client.tracks.update.return_value = {"id": 843, "title": "New Title"}
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps([{"id": 843, "title": "New Title"}])

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app,
                ["bulk-update", "--file", "edits.json", "--output-format", "table"],
            )

        assert result.exit_code == 0
        assert "Track 843:" in result.output
        assert "Old Title" in result.output
        assert "New Title" in result.output

    # --- Connection options ---

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_host_and_port(self, mock_lexicon_class):
        """Test --host and --port forwarded to client."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = {"id": 843, "title": "New"}
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps([{"id": 843, "title": "New"}])

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app,
                [
                    "bulk-update",
                    "--file",
                    "edits.json",
                    "--host",
                    "192.168.1.100",
                    "--port",
                    "9999",
                ],
            )

        assert result.exit_code == 0
        mock_lexicon_class.assert_called_once_with(host="192.168.1.100", port=9999)

    @patch("lexicon.cli.commands.tracks.Lexicon")
    def test_bulk_update_with_verbose_flag(self, mock_lexicon_class):
        """Global --verbose should not break bulk-update."""
        mock_client = MagicMock()
        mock_client.tracks.update.return_value = {"id": 843, "title": "New"}
        mock_lexicon_class.return_value = mock_client

        edits = json.dumps([{"id": 843, "title": "New"}])

        with self.runner.isolated_filesystem():
            with open("edits.json", "w") as f:
                f.write(edits)

            result = self.runner.invoke(
                app, ["--verbose", "bulk-update", "--file", "edits.json"]
            )

        assert result.exit_code == 0
        assert mock_client.tracks.update.call_count == 1
