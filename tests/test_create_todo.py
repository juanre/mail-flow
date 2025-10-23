# ABOUTME: Tests for create_todo function with markdown and orgmode format support
# ABOUTME: Verifies that todo entries are created in the correct format based on file extension

from pathlib import Path

import pytest

from mailflow.workflow import create_todo


class TestCreateTodo:
    @pytest.fixture
    def sample_message(self):
        """Sample email message for testing"""
        return {
            "from": "sender@example.com",
            "subject": "Test Email Subject",
            "message_id": "test123@example.com",
        }

    def test_create_todo_markdown_format(self, temp_config_dir, sample_message):
        """Test creating todo in markdown format (.md extension)"""
        todo_file = Path(temp_config_dir) / "todos.md"

        create_todo(sample_message, str(todo_file))

        # Verify file was created
        assert todo_file.exists()

        # Read and verify content
        content = todo_file.read_text()
        assert "[ ] " in content
        assert "Email from sender@example.com" in content
        assert "Test Email Subject" in content

    def test_create_todo_txt_format(self, temp_config_dir, sample_message):
        """Test creating todo in markdown format (.txt extension - default)"""
        todo_file = Path(temp_config_dir) / "todos.txt"

        create_todo(sample_message, str(todo_file))

        # Verify file was created
        assert todo_file.exists()

        # Read and verify content
        content = todo_file.read_text()
        assert "[ ] " in content
        assert "Email from sender@example.com" in content
        assert "Test Email Subject" in content

    def test_create_todo_orgmode_format(self, temp_config_dir, sample_message):
        """Test creating todo in orgmode format (.org extension)"""
        todo_file = Path(temp_config_dir) / "todos.org"

        create_todo(sample_message, str(todo_file))

        # Verify file was created
        assert todo_file.exists()

        # Read and verify content
        content = todo_file.read_text()
        assert "* TODO " in content
        assert "Email from sender@example.com" in content
        assert "Test Email Subject" in content
        # Should not have markdown format
        assert "[ ] " not in content

    def test_create_todo_orgmode_extension_variant(self, temp_config_dir, sample_message):
        """Test creating todo with .orgmode extension"""
        todo_file = Path(temp_config_dir) / "todos.orgmode"

        create_todo(sample_message, str(todo_file))

        # Verify file was created
        assert todo_file.exists()

        # Read and verify content
        content = todo_file.read_text()
        assert "* TODO " in content
        assert "Email from sender@example.com" in content
        assert "Test Email Subject" in content
        # Should not have markdown format
        assert "[ ] " not in content

    def test_create_todo_append_multiple_entries(self, temp_config_dir, sample_message):
        """Test that multiple todos are appended correctly"""
        todo_file = Path(temp_config_dir) / "todos.org"

        # Create first todo
        create_todo(sample_message, str(todo_file))

        # Create second todo with different content
        second_message = {
            "from": "another@example.com",
            "subject": "Different Subject",
            "message_id": "test456@example.com",
        }
        create_todo(second_message, str(todo_file))

        # Verify both entries exist
        content = todo_file.read_text()
        lines = [line for line in content.split("\n") if line.strip()]
        assert len(lines) == 2
        assert "sender@example.com" in content
        assert "another@example.com" in content

    def test_create_todo_creates_parent_dirs(self, temp_config_dir, sample_message):
        """Test that parent directories are created if they don't exist"""
        todo_file = Path(temp_config_dir) / "subdir" / "nested" / "todos.org"

        create_todo(sample_message, str(todo_file))

        # Verify file and parent dirs were created
        assert todo_file.exists()
        assert todo_file.parent.exists()

    def test_create_todo_handles_long_subject(self, temp_config_dir):
        """Test that long subjects are properly truncated"""
        long_message = {
            "from": "sender@example.com",
            "subject": "A" * 600,  # Longer than the 500 char limit
            "message_id": "test123@example.com",
        }
        todo_file = Path(temp_config_dir) / "todos.org"

        create_todo(long_message, str(todo_file))

        content = todo_file.read_text()
        # Subject should be truncated to 500 chars
        assert "A" * 500 in content
        assert len(content) < 700  # Should not have all 600 A's

    def test_create_todo_handles_missing_fields(self, temp_config_dir):
        """Test that missing fields are handled gracefully"""
        minimal_message = {}  # No fields at all
        todo_file = Path(temp_config_dir) / "todos.org"

        create_todo(minimal_message, str(todo_file))

        content = todo_file.read_text()
        # Should use default values
        assert "Unknown" in content
        assert "No subject" in content
