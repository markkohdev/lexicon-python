"""Tests for interactive prompt utilities."""

import sys
import types
import unittest
from unittest.mock import patch

from lexicon.cli.prompts import prompt_for_fields


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
    """Tests for the prompt_for_fields function."""
    
    def tearDown(self):
        """Clean up fake InquirerPy module."""
        sys.modules.pop("InquirerPy", None)
    
    def test_prompt_returns_defaults_on_quick_select(self):
        """Test that selecting the quick defaults option returns default fields."""
        defaults = ["title", "artist", "albumTitle"]
        _install_fake_inquirer({"fields": ["__defaults__"]})
        
        result = prompt_for_fields(defaults)
        
        assert result == defaults
    
    def test_prompt_returns_selected_fields(self):
        """Test that custom field selection is returned."""
        defaults = ["title", "artist"]
        selected_fields = ["title", "bpm", "key"]
        _install_fake_inquirer({"fields": selected_fields})
        
        result = prompt_for_fields(defaults)
        
        assert result == selected_fields
    
    def test_prompt_filters_out_defaults_option_value(self):
        """Test that __defaults__ value is filtered out from custom selections."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"fields": ["__defaults__", "title", "bpm"]})
        
        result = prompt_for_fields(defaults)
        
        # Should return defaults since __defaults__ was in selection
        assert result == defaults
    
    def test_prompt_returns_none_on_invalid_result(self):
        """Test that None is returned when result is not a dict."""
        defaults = ["title", "artist"]
        _install_fake_inquirer(None)
        
        result = prompt_for_fields(defaults)
        
        assert result is None
    
    def test_prompt_returns_none_missing_fields_key(self):
        """Test that None is returned when 'fields' key is missing."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"other_key": ["title"]})
        
        result = prompt_for_fields(defaults)
        
        assert result is None
    
    def test_prompt_returns_defaults_on_empty_selection(self):
        """Test that defaults are returned when user selects no custom fields."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"fields": []})
        
        result = prompt_for_fields(defaults)
        
        assert result == defaults
    
    def test_prompt_with_suggested_fields(self):
        """Test that suggested fields are accepted as part of selection."""
        defaults = ["title", "artist"]
        suggested = ["bpm", "key"]
        _install_fake_inquirer({"fields": ["title", "artist", "bpm"]})
        
        result = prompt_for_fields(defaults, suggested)
        
        assert result == ["title", "artist", "bpm"]
    
    def test_prompt_suggested_fields_not_pre_selected(self):
        """Test that suggested fields are not automatically selected."""
        defaults = ["title"]
        suggested = ["bpm", "key"]
        _install_fake_inquirer({"fields": ["title", "bpm"]})
        
        result = prompt_for_fields(defaults, suggested)
        
        assert result == ["title", "bpm"]
    
    def test_prompt_without_suggested_fields(self):
        """Test that suggested_fields defaults to empty list."""
        defaults = ["title", "artist"]
        _install_fake_inquirer({"fields": ["title", "artist", "genre"]})
        
        result = prompt_for_fields(defaults)
        
        assert result == ["title", "artist", "genre"]
    
    @patch("lexicon.cli.prompts.typer.echo")
    def test_prompt_handles_missing_inquirerpy(self, mock_echo):
        """Test fallback when InquirerPy is not installed."""
        def mock_import(*args, **kwargs):
            if args[0] == "InquirerPy":
                raise ImportError("No module named 'InquirerPy'")
            return __import__(*args, **kwargs)
        
        defaults = ["title", "artist"]
        
        with patch("builtins.__import__", side_effect=mock_import):
            result = prompt_for_fields(defaults)
        
        assert result == defaults
        assert mock_echo.call_count >= 2
    
    def test_prompt_choice_order_defaults_first(self):
        """Test that default fields appear before other fields in choices."""
        defaults = ["title", "artist"]
        suggested = ["bpm"]
        
        captured_choices = []
        
        def mock_prompt(questions):
            captured_choices.extend(questions[0]["choices"])
            return {"fields": defaults}
        
        module = types.ModuleType("InquirerPy")
        module.prompt = mock_prompt
        sys.modules["InquirerPy"] = module
        
        prompt_for_fields(defaults, suggested)
        
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
        
        prompt_for_fields(defaults)
        
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
        
        prompt_for_fields(defaults, suggested)
        
        # Find suggested fields and verify they're not enabled
        bpm_choice = next(c for c in captured_choices if c["value"] == "bpm")
        assert bpm_choice["enabled"] is False
        
        key_choice = next(c for c in captured_choices if c["value"] == "key")
        assert key_choice["enabled"] is False
