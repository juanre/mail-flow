# ABOUTME: Tests for security validation functions
# ABOUTME: Validates email address format checking and path security
"""Tests for security validation"""

import os
import tempfile

import pytest

from mailflow.security import (
    InputValidationError,
    PathSecurityError,
    validate_email_address,
    validate_path,
    sanitize_filename,
)


class TestPathValidation:
    """Test path validation security"""

    def test_path_traversal_simple_dotdot(self):
        """Path traversal with ../ should be prevented when escaping allowed dirs"""
        # Use a temp directory as the allowed base to make the test deterministic.
        # The relative path resolves from CWD and won't be under the temp dir.
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathSecurityError, match="outside allowed directories"):
                validate_path("../../../etc/passwd", allowed_base_dirs=[tmpdir])

    def test_path_traversal_with_home_expansion(self):
        """Path traversal via home expansion should be prevented"""
        with pytest.raises(PathSecurityError):
            validate_path("~/docs/../../etc/passwd")

    def test_path_traversal_mixed_expansion(self):
        """Mixed path traversal attempts should be prevented"""
        with pytest.raises(PathSecurityError):
            validate_path("~/../../../../../../etc/passwd")

    def test_valid_path_in_home(self):
        """Valid paths in home directory should work"""
        home = os.path.expanduser("~")
        result = validate_path("~/documents")
        assert str(result).startswith(home)

    def test_valid_path_with_allowed_base(self):
        """Paths work with explicit allowed base directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "test.txt")
            result = validate_path(test_path, allowed_base_dirs=[tmpdir])
            # Check that the path is under the temp directory (accounting for symlinks)
            from pathlib import Path
            assert result.is_relative_to(Path(tmpdir).resolve())

    def test_path_outside_allowed_base_raises_error(self):
        """Paths outside allowed directories should be rejected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathSecurityError, match="outside allowed directories"):
                validate_path("/etc/passwd", allowed_base_dirs=[tmpdir])

    def test_null_byte_in_path(self):
        """Null bytes in paths should be rejected"""
        with pytest.raises(PathSecurityError):
            validate_path("test\x00file.txt")

    def test_newline_in_path(self):
        """Newlines in paths should be rejected"""
        with pytest.raises(PathSecurityError):
            validate_path("test\nfile.txt")

    def test_empty_path_raises_error(self):
        """Empty paths should be rejected"""
        with pytest.raises(PathSecurityError, match="Empty path"):
            validate_path("")


class TestFilenameValidation:
    """Test filename sanitization"""

    def test_sanitize_removes_path_components(self):
        """Path separators should be removed"""
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert result == "passwd"

    def test_sanitize_replaces_dangerous_chars(self):
        """Dangerous characters should be replaced"""
        result = sanitize_filename("file$name&test.txt")
        assert "$" not in result
        assert "&" not in result

    def test_sanitize_handles_hidden_files(self):
        """Hidden files should be made visible"""
        result = sanitize_filename(".hidden")
        assert not result.startswith(".")

    def test_sanitize_empty_filename(self):
        """Empty filenames should get default name"""
        result = sanitize_filename("")
        assert result == "unnamed"


class TestEmailValidation:
    """Test email address validation"""

    def test_valid_simple_email(self):
        """Valid simple email should pass"""
        result = validate_email_address("user@example.com")
        assert result == "user@example.com"

    def test_valid_email_with_dots(self):
        """Valid email with single dots should pass"""
        result = validate_email_address("valid.user@example.com")
        assert result == "valid.user@example.com"

    def test_valid_email_with_plus(self):
        """Valid email with plus sign should pass"""
        result = validate_email_address("user+tag@example.com")
        assert result == "user+tag@example.com"

    def test_valid_email_with_hyphen(self):
        """Valid email with hyphen should pass"""
        result = validate_email_address("user-name@example.com")
        assert result == "user-name@example.com"

    def test_valid_email_with_numbers(self):
        """Valid email with numbers should pass"""
        result = validate_email_address("user123@example.com")
        assert result == "user123@example.com"

    def test_valid_email_in_angle_brackets(self):
        """Valid email in angle brackets should extract correctly"""
        result = validate_email_address("John Doe <john@example.com>")
        assert result == "john@example.com"

    def test_empty_email(self):
        """Empty email should return empty string"""
        result = validate_email_address("")
        assert result == ""

    def test_consecutive_dots(self):
        """Email with consecutive dots should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test..user@example.com")

    def test_leading_dot(self):
        """Email with leading dot should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address(".test@example.com")

    def test_trailing_dot_in_local_part(self):
        """Email with trailing dot in local part should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test.@example.com")

    def test_no_at_symbol(self):
        """Email without @ symbol should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("testexample.com")

    def test_multiple_at_symbols(self):
        """Email with multiple @ symbols should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test@user@example.com")

    def test_no_domain(self):
        """Email without domain should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test@")

    def test_no_tld(self):
        """Email without TLD should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test@example")

    def test_invalid_characters(self):
        """Email with invalid characters should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test user@example.com")

    def test_consecutive_dots_in_domain(self):
        """Email with consecutive dots in domain should fail"""
        with pytest.raises(InputValidationError, match="Invalid email address format"):
            validate_email_address("test@example..com")
