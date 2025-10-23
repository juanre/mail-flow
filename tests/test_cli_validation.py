# ABOUTME: Tests for CLI input validation in interactive workflow setup
# ABOUTME: Validates entity_name and doc_desc input sanitization and length checks
"""Tests for CLI input validation"""

import pytest
from click.testing import CliRunner
from pathlib import Path
from mailflow.cli import cli


class TestInteractiveWorkflowSetupValidation:
    """Test validation of user inputs in _interactive_workflow_setup"""

    def test_entity_name_length_validation(self, tmp_config):
        """Entity name should be limited to 100 characters"""
        runner = CliRunner()

        # Try to create entity with name > 100 chars
        long_name = "a" * 101

        result = runner.invoke(
            cli,
            ["init"],
            input=f"test\n{long_name}\n\n\n",  # entity_code, long entity_name, done entities, done doc_types
        )

        # Should reject the long name
        assert "Entity name must be 1-100 characters" in result.output
        assert result.exit_code == 0  # Should continue prompting

    def test_entity_name_default_accepted(self, tmp_config):
        """Entity name can use default (entity code)"""
        runner = CliRunner()

        # When user just presses Enter, click.prompt uses the default (entity_code)
        # This is valid behavior
        result = runner.invoke(
            cli,
            ["init"],
            input="test\n\n\n\n\n",  # entity_code, use default, done entities, done doc_types
        )

        # Should accept default and create workflow
        assert result.exit_code == 0
        assert "test-doc" in result.output

    def test_entity_name_control_character_sanitization(self, tmp_config):
        """Entity name should be sanitized to remove control characters"""
        runner = CliRunner()

        # Name with control characters (tabs, newlines, etc.)
        name_with_controls = "Test\x00Company\x01\x02"

        result = runner.invoke(
            cli,
            ["init"],
            input=f"test\n{name_with_controls}\n\n\ndoc\nDocuments\n\n",
        )

        # Should sanitize and accept
        assert result.exit_code == 0
        # Verify workflow was created with sanitized name
        assert "test-doc" in result.output

    def test_entity_name_all_control_chars_rejected(self, tmp_config):
        """Entity name with only control characters should be rejected"""
        runner = CliRunner()

        # Name with only control characters
        name_only_controls = "\x00\x01\x02\x03"

        result = runner.invoke(
            cli,
            ["init"],
            input=f"test\n{name_only_controls}\n\n\n",
        )

        # Should reject after sanitization leaves nothing
        assert "Entity name contains no valid characters" in result.output

    def test_doc_desc_length_validation(self, tmp_config):
        """Document description should be limited to 200 characters"""
        runner = CliRunner()

        long_desc = "a" * 201

        result = runner.invoke(
            cli,
            ["init"],
            input=f"test\nTest Entity\n\ndoc\n{long_desc}\n\n",
        )

        # Should reject the long description
        assert "Description must be 1-200 characters" in result.output

    def test_doc_desc_default_accepted(self, tmp_config):
        """Document description can use default"""
        runner = CliRunner()

        # When user presses Enter, click.prompt uses default (doc_code with dashes replaced)
        result = runner.invoke(
            cli,
            ["init"],
            input="test\nTest Entity\n\n\ndoc\n\n\n\n",
        )

        # Should accept default and create workflow
        assert result.exit_code == 0
        assert "test-doc" in result.output

    def test_doc_desc_control_character_sanitization(self, tmp_config):
        """Document description should be sanitized to remove control characters"""
        runner = CliRunner()

        desc_with_controls = "Tax\x00documents\x01for\x02company"

        result = runner.invoke(
            cli,
            ["init"],
            input=f"test\nTest Entity\n\n\ndoc\n{desc_with_controls}\n\n",
        )

        # Should sanitize and accept
        assert result.exit_code == 0
        assert "test-doc" in result.output

    def test_doc_desc_all_control_chars_rejected(self, tmp_config):
        """Document description with only control characters should be rejected"""
        runner = CliRunner()

        desc_only_controls = "\x00\x01\x02\x03"

        result = runner.invoke(
            cli,
            ["init"],
            input=f"test\nTest Entity\n\ndoc\n{desc_only_controls}\n\n",
        )

        # Should reject after sanitization leaves nothing
        assert "Description contains no valid characters" in result.output

    def test_valid_entity_and_doc_creation(self, tmp_config):
        """Valid inputs should create workflows successfully"""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["init"],
            input="testco\nTest Company\n\nexpense\nExpense reports\n\n",
        )

        assert result.exit_code == 0
        assert "testco-expense" in result.output
        assert "Created 1 new workflows" in result.output


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Create a temporary config directory for testing"""
    config_dir = tmp_path / ".config" / "mailflow"
    config_dir.mkdir(parents=True)

    # Point XDG_CONFIG_HOME to temp directory
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

    return config_dir
