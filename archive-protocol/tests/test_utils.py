# ABOUTME: Tests for utility functions in archive_protocol.utils
# ABOUTME: Validates filename sanitization, hashing, and atomic write operations

import os
import tempfile
from pathlib import Path

import pytest

from archive_protocol.utils import compute_hash, sanitize_filename, write_atomically


class TestSanitizeFilename:
    """Test filename sanitization functionality."""

    def test_sanitize_simple_filename(self):
        """Test sanitization of simple, valid filename."""
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_sanitize_removes_path_components(self):
        """Test that path components are removed."""
        result = sanitize_filename("/path/to/document.pdf")
        assert result == "document.pdf"

        result = sanitize_filename("path/to/document.pdf")
        assert result == "document.pdf"

        result = sanitize_filename("../../../etc/passwd")
        assert result == "passwd"

    def test_sanitize_removes_dangerous_characters(self):
        """Test that dangerous characters are replaced."""
        # Test various dangerous characters
        dangerous = 'file<name>with:bad|chars?.txt'
        result = sanitize_filename(dangerous)
        assert '<' not in result
        assert '>' not in result
        assert ':' not in result
        assert '|' not in result
        assert '?' not in result
        assert '-' in result  # Replaced with hyphens

    def test_sanitize_removes_control_characters(self):
        """Test that control characters are removed."""
        # Control characters (0x00-0x1f)
        filename = "file\x00name\x01test\x1f.txt"
        result = sanitize_filename(filename)
        assert '\x00' not in result
        assert '\x01' not in result
        assert '\x1f' not in result

    def test_sanitize_replaces_slashes(self):
        """Test that slashes are replaced with hyphens."""
        result = sanitize_filename("file/name\\test.txt")
        assert '/' not in result
        assert '\\' not in result
        assert '-' in result

    def test_sanitize_collapses_multiple_hyphens(self):
        """Test that multiple hyphens/spaces are collapsed."""
        result = sanitize_filename("file---name   test.txt")
        assert "---" not in result
        assert "   " not in result

    def test_sanitize_removes_leading_trailing_hyphens(self):
        """Test that leading/trailing hyphens and dots are removed."""
        result = sanitize_filename("---file.txt---")
        assert not result.startswith('-')
        assert not result.endswith('-')

        result = sanitize_filename("...file.txt...")
        assert not result.startswith('.')

    def test_sanitize_empty_filename(self):
        """Test that empty filename gets default name."""
        result = sanitize_filename("")
        assert result == "unnamed"

        result = sanitize_filename("---")
        assert result == "unnamed"

    def test_sanitize_long_filename(self):
        """Test that long filenames are truncated."""
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name, max_length=200)
        assert len(result) <= 200
        assert result.endswith(".txt")  # Extension preserved

    def test_sanitize_long_filename_preserves_extension(self):
        """Test that extension is preserved when truncating."""
        long_stem = "a" * 250
        filename = long_stem + ".pdf"
        result = sanitize_filename(filename, max_length=100)
        assert len(result) <= 100
        assert result.endswith(".pdf")
        assert result.count('.') == 1

    def test_sanitize_custom_max_length(self):
        """Test custom max_length parameter."""
        long_name = "a" * 150 + ".txt"
        result = sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50
        assert result.endswith(".txt")

    def test_sanitize_windows_reserved_names(self):
        """Test handling of Windows reserved filenames."""
        # While we replace dangerous chars, the function doesn't
        # explicitly handle reserved names like CON, PRN, etc.
        # This test documents current behavior
        result = sanitize_filename("CON")
        assert result == "CON"  # Not modified

    def test_sanitize_unicode_characters(self):
        """Test that unicode characters are preserved."""
        result = sanitize_filename("документ.pdf")
        assert result == "документ.pdf"

        result = sanitize_filename("文档.txt")
        assert result == "文档.txt"

    def test_sanitize_multiple_extensions(self):
        """Test handling of multiple extensions."""
        result = sanitize_filename("archive.tar.gz")
        assert result == "archive.tar.gz"

    def test_sanitize_no_extension(self):
        """Test handling of files without extension."""
        result = sanitize_filename("README")
        assert result == "README"


class TestComputeHash:
    """Test content hashing functionality."""

    def test_compute_hash_simple_content(self):
        """Test hash computation for simple content."""
        content = b"test content"
        result = compute_hash(content)
        assert result.startswith("sha256:")
        assert len(result) == 71  # "sha256:" (7) + 64 hex chars

    def test_compute_hash_format(self):
        """Test that hash has correct format."""
        content = b"test"
        result = compute_hash(content)
        assert result.startswith("sha256:")
        # Verify it's all lowercase hex after prefix
        hash_part = result[7:]
        assert all(c in "0123456789abcdef" for c in hash_part)

    def test_compute_hash_empty_content(self):
        """Test hash of empty content."""
        content = b""
        result = compute_hash(content)
        # SHA-256 of empty string is known value
        expected = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert result == expected

    def test_compute_hash_deterministic(self):
        """Test that hash is deterministic."""
        content = b"deterministic test"
        hash1 = compute_hash(content)
        hash2 = compute_hash(content)
        assert hash1 == hash2

    def test_compute_hash_different_content(self):
        """Test that different content produces different hashes."""
        content1 = b"content 1"
        content2 = b"content 2"
        hash1 = compute_hash(content1)
        hash2 = compute_hash(content2)
        assert hash1 != hash2

    def test_compute_hash_large_content(self):
        """Test hash computation for large content."""
        # 10MB of data
        content = b"x" * (10 * 1024 * 1024)
        result = compute_hash(content)
        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_compute_hash_binary_content(self):
        """Test hash computation for binary content."""
        # Binary content with all byte values
        content = bytes(range(256))
        result = compute_hash(content)
        assert result.startswith("sha256:")
        assert len(result) == 71

    def test_compute_hash_known_value(self):
        """Test hash against known value."""
        content = b"hello world"
        result = compute_hash(content)
        # Known SHA-256 of "hello world"
        expected = "sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert result == expected


class TestWriteAtomically:
    """Test atomic file writing functionality."""

    def test_write_atomically_creates_file(self, tmp_path):
        """Test that atomic write creates the file."""
        target_path = tmp_path / "test.txt"
        content = b"test content"

        write_atomically(target_path, content)

        assert target_path.exists()
        assert target_path.read_bytes() == content

    def test_write_atomically_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created."""
        target_path = tmp_path / "subdir1" / "subdir2" / "test.txt"
        content = b"test content"

        write_atomically(target_path, content)

        assert target_path.exists()
        assert target_path.parent.exists()
        assert target_path.read_bytes() == content

    def test_write_atomically_parent_directory_mode(self, tmp_path):
        """Test that parent directories have correct mode."""
        target_path = tmp_path / "subdir" / "test.txt"
        content = b"test content"

        write_atomically(target_path, content)

        # Check directory mode (0o755)
        parent_stat = target_path.parent.stat()
        # Mode includes file type bits, so mask them out
        mode = parent_stat.st_mode & 0o777
        assert mode == 0o755

    def test_write_atomically_overwrites_existing(self, tmp_path):
        """Test that atomic write overwrites existing file."""
        target_path = tmp_path / "test.txt"
        target_path.write_bytes(b"old content")

        content = b"new content"
        write_atomically(target_path, content)

        assert target_path.read_bytes() == content

    def test_write_atomically_binary_content(self, tmp_path):
        """Test atomic write with binary content."""
        target_path = tmp_path / "binary.bin"
        content = bytes(range(256))

        write_atomically(target_path, content)

        assert target_path.read_bytes() == content

    def test_write_atomically_large_content(self, tmp_path):
        """Test atomic write with large content."""
        target_path = tmp_path / "large.bin"
        # 5MB of data
        content = b"x" * (5 * 1024 * 1024)

        write_atomically(target_path, content)

        assert target_path.exists()
        assert len(target_path.read_bytes()) == len(content)

    def test_write_atomically_empty_content(self, tmp_path):
        """Test atomic write with empty content."""
        target_path = tmp_path / "empty.txt"
        content = b""

        write_atomically(target_path, content)

        assert target_path.exists()
        assert target_path.read_bytes() == b""

    def test_write_atomically_cleans_up_temp_file(self, tmp_path):
        """Test that temporary file is cleaned up."""
        target_path = tmp_path / "test.txt"
        content = b"test content"

        write_atomically(target_path, content)

        # Check no temp files remain
        temp_files = list(tmp_path.glob(".tmp_*"))
        assert len(temp_files) == 0

    def test_write_atomically_temp_file_pattern(self, tmp_path):
        """Test temporary file naming pattern."""
        target_path = tmp_path / "test.txt"
        content = b"test content"

        # Temporarily patch the function to check temp file exists during write
        original_rename = Path.rename
        temp_file_found = []

        def patched_rename(self, target):
            # Check temp files exist before rename
            temp_files = list(self.parent.glob(f".tmp_{target_path.name}_*"))
            temp_file_found.extend(temp_files)
            return original_rename(self, target)

        Path.rename = patched_rename
        try:
            write_atomically(target_path, content)
        finally:
            Path.rename = original_rename

        # Verify temp file pattern included PID
        assert len(temp_file_found) > 0
        temp_name = temp_file_found[0].name
        assert temp_name.startswith(".tmp_test.txt_")
        assert str(os.getpid()) in temp_name

    def test_write_atomically_fails_on_exclusive_create_collision(self, tmp_path):
        """Test that exclusive create ('xb') mode prevents overwrites during temp creation."""
        target_path = tmp_path / "test.txt"
        content = b"test content"

        # Create a temp file that would collide
        temp_file = tmp_path / f".tmp_test.txt_{os.getpid()}"
        temp_file.write_bytes(b"existing temp")

        # Should raise FileExistsError because temp file exists
        with pytest.raises(FileExistsError):
            write_atomically(target_path, content)

    def test_write_atomically_cleanup_on_error(self, tmp_path, monkeypatch):
        """Test that temp file is cleaned up on error."""
        target_path = tmp_path / "test.txt"
        content = b"test content"

        # Make fsync fail
        original_fsync = os.fsync

        def failing_fsync(fd):
            raise OSError("Simulated fsync failure")

        monkeypatch.setattr(os, "fsync", failing_fsync)

        # Write should fail but clean up temp file
        with pytest.raises(OSError):
            write_atomically(target_path, content)

        # Verify no temp files remain
        temp_files = list(tmp_path.glob(".tmp_*"))
        assert len(temp_files) == 0

    def test_write_atomically_permissions(self, tmp_path):
        """Test that written file has correct permissions."""
        target_path = tmp_path / "test.txt"
        content = b"test content"

        write_atomically(target_path, content)

        # File should be readable/writable by owner
        assert os.access(target_path, os.R_OK)
        assert os.access(target_path, os.W_OK)

    def test_write_atomically_concurrent_writes(self, tmp_path):
        """Test that concurrent writes to same directory don't conflict."""
        import threading

        results = []

        def write_file(name, content):
            try:
                path = tmp_path / f"file_{name}.txt"
                write_atomically(path, content)
                results.append(True)
            except Exception as e:
                results.append(e)

        # Start multiple threads writing to same directory
        threads = []
        for i in range(5):
            content = f"content_{i}".encode()
            t = threading.Thread(target=write_file, args=(i, content))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All writes should succeed
        assert all(r is True for r in results)
        assert len(list(tmp_path.glob("file_*.txt"))) == 5
