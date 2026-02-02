import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

# Ensure src/ is on sys.path so we can import the package without installation
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lexicon.cli import app, _prompt_for_fields  # noqa: E402


class TestCLI(unittest.TestCase):
    """Tests for the CLI interface."""

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

    @patch("lexicon.cli._prompt_for_fields")
    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_default(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks with default options."""
        # Setup prompt mock to return default fields
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(app, ["list-tracks"])

        # Verify
        assert result.exit_code == 0
        assert "Listing all tracks in the library..." in result.stdout
        assert "Found 2 track(s):" in result.stdout
        assert "[1] Test Track - Test Artist - Test Album" in result.stdout
        assert "[2] Another Song - Different Artist - Different Album" in result.stdout

        # Verify API call
        mock_lexicon_class.assert_called_once_with(host=None, port=None)
        mock_client.tracks.list.assert_called_once()

    @patch("lexicon.cli._prompt_for_fields")
    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_empty(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks when no tracks are found."""
        # Setup prompt mock to return default fields
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = []
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(app, ["list-tracks"])

        # Verify
        assert result.exit_code == 0
        assert "No tracks found." in result.stdout

    @patch("lexicon.cli._prompt_for_fields")
    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_with_host_and_port(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks with custom host and port."""
        # Setup prompt mock to return default fields
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(app, ["list-tracks", "--host", "192.168.1.100", "--port", "8080"])

        # Verify
        assert result.exit_code == 0
        mock_lexicon_class.assert_called_once_with(host="192.168.1.100", port=8080)

    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_with_custom_fields(self, mock_lexicon_class):
        """Test list-tracks with custom field options."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(app, ["list-tracks", "-f", "title", "-f", "bpm", "-f", "key"])

        # Verify
        assert result.exit_code == 0
        assert "[1] Test Track - 128 - C Major" in result.stdout
        assert "[2] Another Song - 140 - D Minor" in result.stdout

        # Verify that id, title, bpm, key were requested
        call_args = mock_client.tracks.list.call_args
        fields = call_args.kwargs["fields"]
        assert "id" in fields
        assert "title" in fields
        assert "bpm" in fields
        assert "key" in fields

    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_with_format_string(self, mock_lexicon_class):
        """Test list-tracks with format string."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(
            app, ["list-tracks", "--format", "{title} by {artist} [{bpm} BPM]"]
        )

        # Verify
        assert result.exit_code == 0
        assert "Test Track by Test Artist [128 BPM]" in result.stdout
        assert "Another Song by Different Artist [140 BPM]" in result.stdout

        # Verify that the right fields were requested
        call_args = mock_client.tracks.list.call_args
        fields = call_args.kwargs["fields"]
        assert "id" in fields
        assert "title" in fields
        assert "artist" in fields
        assert "bpm" in fields

    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_format_with_missing_field(self, mock_lexicon_class):
        """Test list-tracks with format string when a field is missing."""
        # Setup mock with incomplete data
        incomplete_tracks = [
            {
                "id": 1,
                "title": "Test Track",
                "artist": "Test Artist",
                # bpm is missing
            },
        ]
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = incomplete_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(
            app, ["list-tracks", "--format", "{title} - {artist} [{bpm} BPM]"]
        )

        # Verify that N/A is used for missing field
        assert result.exit_code == 0
        assert "Test Track - Test Artist [N/A BPM]" in result.stdout

    @patch("lexicon.cli._prompt_for_fields")
    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_with_array_field(self, mock_lexicon_class, mock_prompt):
        """Test list-tracks with array fields (like artists)."""
        # Setup prompt mock to return default fields
        mock_prompt.return_value = ["title", "artist", "albumTitle"]
        
        # Setup mock with array data
        tracks_with_arrays = [
            {
                "id": 1,
                "title": "Collab Track",
                "artist": ["Artist One", "Artist Two"],
                "albumTitle": "Test Album",
            },
        ]
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = tracks_with_arrays
        mock_lexicon_class.return_value = mock_client

        # Run command
        result = self.runner.invoke(app, ["list-tracks"])

        # Verify that array is joined with commas
        assert result.exit_code == 0
        assert "[1] Collab Track - Artist One, Artist Two - Test Album" in result.stdout

    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_format_overrides_fields(self, mock_lexicon_class):
        """Test that --format option overrides --field options."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command with both --field and --format
        result = self.runner.invoke(
            app,
            [
                "list-tracks",
                "-f", "title",
                "-f", "albumTitle",
                "--format", "{title} - {bpm}",
            ],
        )

        # Verify that format string is used (not fields)
        assert result.exit_code == 0
        assert "Test Track - 128" in result.stdout
        assert "Another Song - 140" in result.stdout
        assert "Test Album" not in result.stdout  # albumTitle should not appear

        # Verify that only format fields were requested
        call_args = mock_client.tracks.list.call_args
        fields = call_args.kwargs["fields"]
        assert "title" in fields
        assert "bpm" in fields
        # albumTitle should not be in fields since format doesn't use it

    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_id_always_included(self, mock_lexicon_class):
        """Test that id is always included in API request."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command with fields that don't include id
        result = self.runner.invoke(app, ["list-tracks", "-f", "title", "-f", "bpm"])

        # Verify
        assert result.exit_code == 0

        # Verify that id was requested even though not explicitly specified
        call_args = mock_client.tracks.list.call_args
        fields = call_args.kwargs["fields"]
        assert "id" in fields

    @patch("lexicon.cli.Lexicon")
    def test_list_tracks_complex_format_string(self, mock_lexicon_class):
        """Test list-tracks with complex format string."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.tracks.list.return_value = self.sample_tracks
        mock_lexicon_class.return_value = mock_client

        # Run command with complex format
        result = self.runner.invoke(
            app,
            ["list-tracks", "--format", "[{id}] {title} | {artist} | {year} | {key}"],
        )

        # Verify
        assert result.exit_code == 0
        assert "[1] Test Track | Test Artist | 2023 | C Major" in result.stdout
        assert "[2] Another Song | Different Artist | 2024 | D Minor" in result.stdout


class TestListFieldsCommand(unittest.TestCase):
    """Tests for the list-fields CLI command."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("lexicon.cli.TRACK_FIELDS")
    def test_list_fields_track_default(self, mock_track_fields):
        """Test list-fields with default track entity."""
        mock_track_fields = (
            "id", "type", "title", "artist", "albumTitle", "label",
            "remixer", "mix", "composer", "producer", "bpm", "duration"
        )
        with patch("lexicon.cli.TRACK_FIELDS", mock_track_fields):
            result = self.runner.invoke(app, ["list-fields"])

        assert result.exit_code == 0
        assert "Available fields for tracks (12):" in result.output
        assert "id" in result.output
        assert "title" in result.output
        assert "artist" in result.output

    @patch("lexicon.cli.TRACK_FIELDS")
    def test_list_fields_track_explicit(self, mock_track_fields):
        """Test list-fields with explicit track entity."""
        mock_track_fields = ("id", "title", "artist", "bpm")
        with patch("lexicon.cli.TRACK_FIELDS", mock_track_fields):
            result = self.runner.invoke(app, ["list-fields", "track"])

        assert result.exit_code == 0
        assert "Available fields for tracks (4):" in result.output
        for field in mock_track_fields:
            assert field in result.output

    @patch("lexicon.cli.SORT_FIELDS")
    @patch("lexicon.cli.TRACK_FIELDS")
    def test_list_fields_track_sortable(self, mock_track_fields, mock_sort_fields):
        """Test list-fields with sortable flag for tracks."""
        mock_sort_fields = ("id", "title", "artist", "bpm", "duration")
        with patch("lexicon.cli.SORT_FIELDS", mock_sort_fields):
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
        assert "type" in result.output
        assert "folderType" in result.output
        assert "parentId" in result.output
        assert "position" in result.output
        assert "trackIds" in result.output
        assert "smartlist" in result.output

    def test_list_fields_playlist_sortable(self):
        """Test list-fields with sortable flag for playlists (should show no sorting)."""
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
        assert "categoryId" in result.output
        assert "position" in result.output

    def test_list_fields_tag_sortable(self):
        """Test list-fields with sortable flag for tags (should show no sorting)."""
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
        assert "Available fields for tracks" in result_mixed.output

    def test_list_fields_invalid_entity(self):
        """Test list-fields with invalid entity type."""
        result = self.runner.invoke(app, ["list-fields", "invalid_entity"])

        assert result.exit_code == 1
        assert "Error: Unknown entity type 'invalid_entity'" in result.output
        assert "Valid types: track, playlist, tag" in result.output

    def test_list_fields_invalid_entity_variations(self):
        """Test list-fields with various invalid entity types."""
        invalid_entities = ["album", "artist", "cue", "song", ""]
        
        for entity in invalid_entities:
            result = self.runner.invoke(app, ["list-fields", entity])
            assert result.exit_code == 1
            assert "Error: Unknown entity type" in result.output

    @patch("lexicon.cli.SORT_FIELDS")
    def test_list_fields_sortable_count_correct(self, mock_sort_fields):
        """Test that sortable field count matches the number of sortable fields."""
        # SORT_FIELDS excludes cuepoints, tempomarkers, tags from TRACK_FIELDS
        mock_sort_fields = (
            "id", "type", "title", "artist", "albumTitle", "label"
        )
        with patch("lexicon.cli.SORT_FIELDS", mock_sort_fields):
            result = self.runner.invoke(app, ["list-fields", "track", "--sortable"])

        assert result.exit_code == 0
        assert "Sortable fields for tracks (6):" in result.output

    def test_list_fields_each_field_on_separate_line(self):
        """Test that each field is printed on its own line."""
        result = self.runner.invoke(app, ["list-fields", "tag"])

        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        # Filter out header and empty lines, count the actual field lines
        field_lines = [line for line in lines if line.strip() and not "fields for" in line and not "Available" in line]
        # Should have 4 tag fields
        assert len(field_lines) == 4


def _install_fake_inquirer(selection_result):
    """Install a fake InquirerPy module for testing.
    
    Parameters
    ----------
    selection_result
        The result dict to return from the prompt call.
    """
    module = types.ModuleType("InquirerPy")
    
    def prompt(_questions):
        return selection_result
    
    module.prompt = prompt
    sys.modules["InquirerPy"] = module
    return module


class TestPromptForFields(unittest.TestCase):
    """Tests for the _prompt_for_fields function."""
    
    def tearDown(self):
        """Clean up fake InquirerPy module."""
        sys.modules.pop("InquirerPy", None)
    
    def test_prompt_returns_defaults_on_quick_select(self):
        """Test that selecting the quick defaults option returns default fields."""
        defaults = ["title", "artist", "albumTitle"]
        _install_fake_inquirer({"fields": ["__defaults__"]})
        
        result = _prompt_for_fields(defaults)
        
        assert result == defaults
    
    def test_prompt_returns_selected_fields(self):
        """Test that custom field selection is returned."""
        defaults = ["title", "artist"]
        selected_fields = ["title", "bpm", "key"]
        _install_fake_inquirer({"fields": selected_fields})
        
        result = _prompt_for_fields(defaults)
        
        assert result == selected_fields
    
    def test_prompt_filters_out_defaults_option_value(self):
        """Test that __defaults__ value is filtered out from custom selections."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"fields": ["__defaults__", "title", "bpm"]})
        
        result = _prompt_for_fields(defaults)
        
        # Should return defaults since __defaults__ was in selection
        assert result == defaults
    
    def test_prompt_returns_none_on_invalid_result(self):
        """Test that None is returned when result is not a dict."""
        defaults = ["title", "artist"]
        _install_fake_inquirer(None)
        
        result = _prompt_for_fields(defaults)
        
        assert result is None
    
    def test_prompt_returns_none_missing_fields_key(self):
        """Test that None is returned when 'fields' key is missing."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"other_key": ["title"]})
        
        result = _prompt_for_fields(defaults)
        
        assert result is None
    
    def test_prompt_returns_defaults_on_empty_selection(self):
        """Test that defaults are returned when user selects no custom fields."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"fields": []})
        
        result = _prompt_for_fields(defaults)
        
        assert result == defaults
    
    def test_prompt_with_suggested_fields(self):
        """Test that suggested fields are accepted as part of selection."""
        defaults = ["title", "artist"]
        suggested = ["bpm", "key"]
        _install_fake_inquirer({"fields": ["title", "artist", "bpm"]})
        
        result = _prompt_for_fields(defaults, suggested)
        
        assert result == ["title", "artist", "bpm"]
    
    def test_prompt_suggested_fields_not_pre_selected(self):
        """Test that suggested fields are not automatically selected."""
        defaults = ["title"]
        suggested = ["bpm", "key"]
        # Selecting just the defaults and one suggested field
        _install_fake_inquirer({"fields": ["title", "bpm"]})
        
        result = _prompt_for_fields(defaults, suggested)
        
        assert result == ["title", "bpm"]
    
    def test_prompt_without_suggested_fields(self):
        """Test that suggested_fields defaults to empty list."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"fields": ["title", "artist", "genre"]})
        
        result = _prompt_for_fields(defaults)
        
        assert result == ["title", "artist", "genre"]
    
    @patch("lexicon.cli.typer.echo")
    def test_prompt_handles_missing_inquirerpy(self, mock_echo):
        """Test fallback when InquirerPy is not installed."""
        # Mock the import to raise ImportError
        def mock_import(*args, **kwargs):
            if args[0] == "InquirerPy":
                raise ImportError("No module named 'InquirerPy'")
            return __import__(*args, **kwargs)
        
        defaults = ["title", "artist"]
        
        with patch("builtins.__import__", side_effect=mock_import):
            result = _prompt_for_fields(defaults)
        
        # Should return defaults
        assert result == defaults
        # Should have echoed error messages
        assert mock_echo.call_count >= 2
    
    def test_prompt_choice_order_defaults_first(self):
        """Test that default fields appear before other fields in choices."""
        defaults = ["title", "artist"]
        suggested = ["bpm"]
        
        # We need to capture the choices passed to prompt
        captured_choices = []
        
        def mock_prompt(questions):
            captured_choices.extend(questions[0]["choices"])
            return {"fields": defaults}
        
        module = types.ModuleType("InquirerPy")
        module.prompt = mock_prompt
        sys.modules["InquirerPy"] = module
        
        _prompt_for_fields(defaults, suggested)
        
        # First choice should be the "Use defaults" option
        assert captured_choices[0]["value"] == "__defaults__"
        
        # Next choices should be the default fields
        assert captured_choices[1]["value"] == "title"
        assert captured_choices[2]["value"] == "artist"
        
        # After defaults, suggested fields should appear
        assert captured_choices[3]["value"] == "bpm"
    
    def test_prompt_defaults_are_pre_selected(self):
        """Test that default fields have enabled=True in choices."""
        defaults = ["title", "artist"]
        
        captured_choices = []
        
        def mock_prompt(questions):
            captured_choices.extend(questions[0]["choices"])
            return {"fields": defaults}
        
        module = types.ModuleType("InquirerPy")
        module.prompt = mock_prompt
        sys.modules["InquirerPy"] = module
        
        _prompt_for_fields(defaults)
        
        # Find the title choice
        title_choice = next(c for c in captured_choices if c["value"] == "title")
        assert title_choice["enabled"] is True
        
        # Find another field (not in defaults) and verify it's not enabled
        other_choice = next(c for c in captured_choices if c["value"] not in defaults and c["value"] != "__defaults__")
        assert other_choice["enabled"] is False
    
    def test_prompt_suggested_fields_not_pre_selected_in_choices(self):
        """Test that suggested fields have enabled=False in choices."""
        defaults = ["title"]
        suggested = ["bpm", "key"]
        
        captured_choices = []
        
        def mock_prompt(questions):
            captured_choices.extend(questions[0]["choices"])
            return {"fields": defaults}
        
        module = types.ModuleType("InquirerPy")
        module.prompt = mock_prompt
        sys.modules["InquirerPy"] = module
        
        _prompt_for_fields(defaults, suggested)
        
        # Find suggested fields and verify they're not enabled
        bpm_choice = next(c for c in captured_choices if c["value"] == "bpm")
        assert bpm_choice["enabled"] is False
        
        key_choice = next(c for c in captured_choices if c["value"] == "key")
        assert key_choice["enabled"] is False


