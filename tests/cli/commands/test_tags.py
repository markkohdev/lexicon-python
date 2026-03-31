"""Tests for list-tags, create-tag, update-tag, delete-tag CLI commands."""

import json
import unittest
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from lexicon.cli import app


SAMPLE_TAGS = [
    {"id": 1, "label": "House", "categoryId": 10, "position": 0},
    {"id": 2, "label": "Techno", "categoryId": 10, "position": 1},
    {"id": 3, "label": "Chill", "categoryId": 20, "position": 0},
]

SAMPLE_CATEGORIES = [
    {"id": 10, "label": "Genre", "position": 0, "color": "#FF0000", "tags": [1, 2]},
    {"id": 20, "label": "Mood", "position": 1, "color": "#00FF00", "tags": [3]},
]


def _mock_client():
    client = MagicMock()
    client.tags.list.return_value = SAMPLE_TAGS
    client.tags.categories.list.return_value = SAMPLE_CATEGORIES
    return client


class TestListTags(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_grouped_output(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(app, ["list-tags"])
        assert result.exit_code == 0
        assert "Genre (2 tags):" in result.stdout
        assert "  House" in result.stdout
        assert "  Techno" in result.stdout
        assert "Mood (1 tag):" in result.stdout
        assert "  Chill" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_flat_output(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(app, ["list-tags", "--output-format", "flat"])
        assert result.exit_code == 0
        assert "Genre:House" in result.stdout
        assert "Genre:Techno" in result.stdout
        assert "Mood:Chill" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_json_output(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(app, ["list-tags", "--output-format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert "categories" in parsed
        assert "tags" in parsed
        assert len(parsed["tags"]) == 3

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_empty_tags(self, mock_lexicon_class):
        client = MagicMock()
        client.tags.list.return_value = []
        client.tags.categories.list.return_value = []
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(app, ["list-tags"])
        assert result.exit_code == 0
        assert "No custom tags found." in result.stdout


class TestCreateTag(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_create_existing_tag(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(app, ["create-tag", "--tag", "Genre:House"])
        assert result.exit_code == 0
        assert "already exists" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_create_new_tag_existing_category(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.add.return_value = {"id": 50, "label": "Ambient", "categoryId": 10}
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(app, ["create-tag", "--tag", "Genre:Ambient"])
        assert result.exit_code == 0
        assert "Created tag 'Genre:Ambient'" in result.stdout
        client.tags.add.assert_called_once_with(10, "Ambient")

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_create_new_tag_new_category_yes(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.categories.add.return_value = {"id": 30, "label": "Vibe"}
        client.tags.add.return_value = {"id": 51, "label": "Dark", "categoryId": 30}
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(app, ["create-tag", "--tag", "Vibe:Dark", "--yes"])
        assert result.exit_code == 0
        assert "Created category 'Vibe'" in result.stdout
        assert "Created tag 'Vibe:Dark'" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_create_new_tag_new_category_declined(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(
            app, ["create-tag", "--tag", "Vibe:Dark"], input="n\n"
        )
        assert result.exit_code == 1
        assert "Aborted" in result.stdout

    def test_invalid_format(self):
        result = self.runner.invoke(app, ["create-tag", "--tag", "NoColon"])
        assert result.exit_code == 1
        assert "Category:Label" in result.output

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_tag_add_failure(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.add.return_value = None
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(app, ["create-tag", "--tag", "Genre:FailTag"])
        assert result.exit_code == 1
        assert "failed to create tag" in result.output

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_category_add_failure(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.categories.add.return_value = None
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(app, ["create-tag", "--tag", "NewCat:Tag", "--yes"])
        assert result.exit_code == 1
        assert "failed to create category" in result.output


class TestUpdateTag(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_update_label(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.update.return_value = {
            "id": 1,
            "label": "Deep House",
            "categoryId": 10,
        }
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["update-tag", "--tag", "Genre:House", "--label", "Deep House"]
        )
        assert result.exit_code == 0
        assert "Updated tag" in result.stdout
        client.tags.update.assert_called_once_with(1, label="Deep House")

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_update_category(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.update.return_value = {"id": 1, "label": "House", "categoryId": 20}
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["update-tag", "--tag", "Genre:House", "--category", "Mood"]
        )
        assert result.exit_code == 0
        assert "Updated tag" in result.stdout
        client.tags.update.assert_called_once_with(1, category_id=20)

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_update_tag_not_found(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(
            app, ["update-tag", "--tag", "Nope:Nada", "--label", "X"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_update_no_changes(self):
        result = self.runner.invoke(app, ["update-tag", "--tag", "Genre:House"])
        assert result.exit_code == 1
        assert "--label and/or --category" in result.output

    def test_update_invalid_format(self):
        result = self.runner.invoke(app, ["update-tag", "--tag", "Bad", "--label", "X"])
        assert result.exit_code == 1
        assert "Category:Label" in result.output

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_update_new_category_with_yes(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.categories.add.return_value = {"id": 30, "label": "Vibe"}
        client.tags.update.return_value = {"id": 1, "label": "House", "categoryId": 30}
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["update-tag", "--tag", "Genre:House", "--category", "Vibe", "--yes"]
        )
        assert result.exit_code == 0
        assert "Created category 'Vibe'" in result.stdout
        assert "Updated tag" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_update_failure(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.update.return_value = None
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["update-tag", "--tag", "Genre:House", "--label", "X"]
        )
        assert result.exit_code == 1
        assert "failed to update" in result.output


class TestDeleteTag(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_delete_with_yes(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.delete.return_value = True
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["delete-tag", "--tag", "Genre:House", "--yes"]
        )
        assert result.exit_code == 0
        assert "Deleted tag 'Genre:House'" in result.stdout
        client.tags.delete.assert_called_once_with(1)

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_delete_confirmed(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.delete.return_value = True
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["delete-tag", "--tag", "Genre:House"], input="y\n"
        )
        assert result.exit_code == 0
        assert "Deleted tag" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_delete_declined(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(
            app, ["delete-tag", "--tag", "Genre:House"], input="n\n"
        )
        assert result.exit_code == 1
        assert "Aborted" in result.stdout

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_delete_not_found(self, mock_lexicon_class):
        mock_lexicon_class.return_value = _mock_client()
        result = self.runner.invoke(app, ["delete-tag", "--tag", "Nope:Nada", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_delete_invalid_format(self):
        result = self.runner.invoke(app, ["delete-tag", "--tag", "Bad"])
        assert result.exit_code == 1
        assert "Category:Label" in result.output

    @patch("lexicon.cli.commands.tags.Lexicon")
    def test_delete_failure(self, mock_lexicon_class):
        client = _mock_client()
        client.tags.delete.return_value = False
        mock_lexicon_class.return_value = client
        result = self.runner.invoke(
            app, ["delete-tag", "--tag", "Genre:House", "--yes"]
        )
        assert result.exit_code == 1
        assert "failed to delete" in result.output
