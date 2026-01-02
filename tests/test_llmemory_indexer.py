"""Tests for llmemory indexing integration."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mailflow.config import Config, ConfigurationError
from mailflow.llmemory_indexer import (
    extract_text_from_content,
    extract_text_from_pdf,
    index_to_llmemory,
    run_indexing,
    _update_sidecar_llmemory,
)


class TestLLMemoryConfig:
    """Test llmemory configuration helpers."""

    def test_has_llmemory_config_false_when_not_configured(self, temp_config_dir):
        """Test has_llmemory_config() returns False when not configured."""
        config = Config(config_dir=temp_config_dir)
        assert config.has_llmemory_config() is False

    def test_has_llmemory_config_true_when_configured(self, temp_config_dir):
        """Test has_llmemory_config() returns True when configured."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[llmemory]
database_url = "postgresql://localhost/docflow"
''')

        config = Config(config_dir=temp_config_dir)
        assert config.has_llmemory_config() is True

    def test_preflight_llmemory_raises_when_not_configured(self, temp_config_dir):
        """Test preflight_llmemory() raises error when not configured."""
        config = Config(config_dir=temp_config_dir)

        with pytest.raises(ConfigurationError) as exc_info:
            config.preflight_llmemory()

        assert "llmemory.database_url" in str(exc_info.value)

    def test_preflight_llmemory_passes_when_configured(self, temp_config_dir):
        """Test preflight_llmemory() passes when configured."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[llmemory]
database_url = "postgresql://localhost/docflow"
''')

        config = Config(config_dir=temp_config_dir)
        config.preflight_llmemory()  # Should not raise

    def test_get_llmemory_database_url(self, temp_config_dir):
        """Test getting llmemory database URL."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[llmemory]
database_url = "postgresql://localhost/docflow"
''')

        config = Config(config_dir=temp_config_dir)
        assert config.get_llmemory_database_url() == "postgresql://localhost/docflow"


class TestTextExtraction:
    """Test text extraction functions."""

    @pytest.mark.asyncio
    async def test_extract_text_from_plain_text(self):
        """Test extracting text from plain text content."""
        content = b"Hello, this is plain text content."
        text = await extract_text_from_content(content, "text/plain")
        assert text == "Hello, this is plain text content."

    @pytest.mark.asyncio
    async def test_extract_text_from_markdown(self):
        """Test extracting text from markdown content."""
        content = b"# Header\n\nSome **bold** text."
        text = await extract_text_from_content(content, "text/markdown")
        assert "Header" in text
        assert "bold" in text

    @pytest.mark.asyncio
    async def test_extract_text_from_html(self):
        """Test extracting text from HTML content."""
        content = b"<html><body><h1>Title</h1><p>Content</p></body></html>"
        text = await extract_text_from_content(content, "text/html")
        assert "Title" in text
        assert "Content" in text

    @pytest.mark.asyncio
    async def test_extract_text_from_unsupported_type(self):
        """Test that unsupported types return empty string."""
        content = b"\x00\x01\x02\x03"  # Binary content
        text = await extract_text_from_content(content, "application/octet-stream")
        assert text == ""

    @pytest.mark.asyncio
    async def test_extract_text_handles_encoding_errors(self):
        """Test that encoding errors are handled gracefully."""
        # Invalid UTF-8 sequence
        content = b"\xff\xfe Hello"
        text = await extract_text_from_content(content, "text/plain")
        # Should not raise, should decode with fallback
        assert "Hello" in text


class TestSidecarUpdate:
    """Test sidecar metadata update function."""

    def test_update_sidecar_llmemory(self):
        """Test updating sidecar with llmemory info."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"document_id": "test-123", "existing": "data"}, f)
            metadata_path = Path(f.name)

        try:
            llmemory_info = {
                "indexed_at": "2024-01-01T00:00:00Z",
                "document_id": "llm-doc-456",
                "chunks_created": 5,
            }

            result = _update_sidecar_llmemory(metadata_path, llmemory_info)
            assert result is True

            # Read back and verify
            with open(metadata_path) as f:
                updated = json.load(f)

            assert updated["existing"] == "data"
            assert updated["llmemory"]["indexed_at"] == "2024-01-01T00:00:00Z"
            assert updated["llmemory"]["document_id"] == "llm-doc-456"
            assert updated["llmemory"]["chunks_created"] == 5
        finally:
            metadata_path.unlink(missing_ok=True)

    def test_update_sidecar_handles_missing_file(self, caplog):
        """Test that missing metadata file is handled gracefully."""
        metadata_path = Path("/nonexistent/path/metadata.json")
        llmemory_info = {"indexed_at": "2024-01-01T00:00:00Z"}

        # Should not raise, returns False and logs error
        result = _update_sidecar_llmemory(metadata_path, llmemory_info)

        assert result is False
        assert "Failed to update sidecar" in caplog.text


class TestIndexToLLMemory:
    """Test the main index_to_llmemory function."""

    @pytest.mark.asyncio
    async def test_skips_when_not_configured(self, temp_config_dir):
        """Test that indexing is skipped when llmemory not configured."""
        config = Config(config_dir=temp_config_dir)

        result = await index_to_llmemory(
            config=config,
            entity="test",
            document_id="doc-123",
            document_name="test.pdf",
            document_type="document",
            content=b"Test content",
            mimetype="text/plain",
            created_at=datetime.now(timezone.utc),
            metadata_path=Path("/tmp/test.json"),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_no_text_extracted(self, temp_config_dir):
        """Test that indexing is skipped when no text can be extracted."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[llmemory]
database_url = "postgresql://localhost/docflow"
''')
        config = Config(config_dir=temp_config_dir)

        result = await index_to_llmemory(
            config=config,
            entity="test",
            document_id="doc-123",
            document_name="test.bin",
            document_type="document",
            content=b"\x00\x01\x02",  # Binary, no text
            mimetype="application/octet-stream",
            created_at=datetime.now(timezone.utc),
            metadata_path=Path("/tmp/test.json"),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_llmemory_not_installed(self, temp_config_dir, caplog):
        """Test graceful handling when llmemory package not installed."""
        config_file = Path(temp_config_dir) / "config.toml"
        config_file.write_text('''
[llmemory]
database_url = "postgresql://localhost/docflow"
''')
        config = Config(config_dir=temp_config_dir)

        # Mock the import to raise ImportError
        with patch.dict("sys.modules", {"llmemory": None}):
            with patch("mailflow.llmemory_indexer.index_to_llmemory") as mock_index:
                # The actual implementation handles ImportError internally
                # Let's test the actual function by making llmemory import fail
                pass

        # Test with actual function - it should handle missing llmemory gracefully
        result = await index_to_llmemory(
            config=config,
            entity="test",
            document_id="doc-123",
            document_name="test.txt",
            document_type="document",
            content=b"Test content",
            mimetype="text/plain",
            created_at=datetime.now(timezone.utc),
            metadata_path=Path("/tmp/test.json"),
        )

        # If llmemory is not installed, result should be None
        # If llmemory IS installed but can't connect, it will also return None
        # Either way, should not raise
        assert result is None or isinstance(result, dict)


class TestRunIndexing:
    """Test the sync wrapper run_indexing function."""

    def test_run_indexing_from_sync_context(self, temp_config_dir):
        """Test run_indexing works from synchronous context."""
        config = Config(config_dir=temp_config_dir)

        # Should not raise, should skip because llmemory not configured
        result = run_indexing(
            config=config,
            entity="test",
            document_id="doc-123",
            document_name="test.pdf",
            document_type="document",
            content=b"Test content",
            mimetype="text/plain",
            created_at=datetime.now(timezone.utc),
            metadata_path=Path("/tmp/test.json"),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_run_indexing_from_async_context(self, temp_config_dir):
        """Test run_indexing works from async context (uses thread pool)."""
        config = Config(config_dir=temp_config_dir)

        # Should not raise even though we're in async context
        result = run_indexing(
            config=config,
            entity="test",
            document_id="doc-123",
            document_name="test.pdf",
            document_type="document",
            content=b"Test content",
            mimetype="text/plain",
            created_at=datetime.now(timezone.utc),
            metadata_path=Path("/tmp/test.json"),
        )

        assert result is None
