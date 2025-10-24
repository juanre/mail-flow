"""Tests for entity parsing from workflow names."""

import pytest

from mailflow.utils import parse_entity_from_workflow


class TestParseEntityFromWorkflow:
    """Test entity extraction from workflow names."""

    def test_parse_simple_entity(self):
        """Test parsing simple entity-doctype format."""
        assert parse_entity_from_workflow("jro-expense") == "jro"
        assert parse_entity_from_workflow("tsm-invoice") == "tsm"
        assert parse_entity_from_workflow("gsk-tax-doc") == "gsk"

    def test_parse_with_multiple_hyphens(self):
        """Test workflow names with multiple hyphens in doctype."""
        assert parse_entity_from_workflow("jro-tax-doc") == "jro"
        assert parse_entity_from_workflow("tsm-w2-form") == "tsm"

    def test_parse_with_underscore_in_entity(self):
        """Test entity names with underscores."""
        assert parse_entity_from_workflow("my_entity-expense") == "my_entity"

    def test_invalid_no_hyphen(self):
        """Test that workflow without hyphen raises error."""
        with pytest.raises(ValueError, match="Expected format: entity-doctype"):
            parse_entity_from_workflow("jroexpense")

    def test_invalid_empty_string(self):
        """Test that empty string raises error."""
        with pytest.raises(ValueError, match="Invalid workflow name"):
            parse_entity_from_workflow("")

    def test_invalid_none(self):
        """Test that None raises error."""
        with pytest.raises(ValueError, match="Invalid workflow name"):
            parse_entity_from_workflow(None)

    def test_invalid_uppercase(self):
        """Test that uppercase entity raises error."""
        with pytest.raises(ValueError, match="Invalid entity"):
            parse_entity_from_workflow("JRO-expense")

    def test_invalid_special_chars(self):
        """Test that special characters in entity raise error."""
        with pytest.raises(ValueError, match="Invalid entity"):
            parse_entity_from_workflow("jr@o-expense")

    def test_single_char_entity(self):
        """Test single character entity works."""
        assert parse_entity_from_workflow("j-expense") == "j"

    def test_numeric_entity(self):
        """Test numeric entity works."""
        assert parse_entity_from_workflow("entity1-expense") == "entity1"
