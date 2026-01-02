"""Tests for llmemory indexing integration."""

import json
import tempfile
from pathlib import Path

import pytest

from mailflow.config import Config, ConfigurationError
from mailflow.llmemory_indexer import index_to_llmemory, run_indexing


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


class TestIndexToLLMemoryFailFast:
    """Test fail-fast behavior when llmemory not configured."""

    @pytest.mark.asyncio
    async def test_fails_fast_when_not_configured(self, temp_config_dir):
        """Test that indexing raises ConfigurationError when llmemory not configured."""
        config = Config(config_dir=temp_config_dir)

        # Create a dummy content file and sidecar
        content_path = Path(temp_config_dir) / "test.txt"
        content_path.write_text("Test content")
        metadata_path = Path(temp_config_dir) / "test.json"
        metadata_path.write_text('{"id": "test-123"}')

        with pytest.raises(ConfigurationError) as exc_info:
            await index_to_llmemory(
                config=config,
                entity="test",
                document_id="doc-123",
                content_path=content_path,
                metadata_path=metadata_path,
            )

        assert "llmemory.database_url" in str(exc_info.value)

    def test_run_indexing_fails_fast_when_not_configured(self, temp_config_dir):
        """Test run_indexing raises ConfigurationError when llmemory not configured."""
        config = Config(config_dir=temp_config_dir)

        # Create a dummy content file and sidecar
        content_path = Path(temp_config_dir) / "test.txt"
        content_path.write_text("Test content")
        metadata_path = Path(temp_config_dir) / "test.json"
        metadata_path.write_text('{"id": "test-123"}')

        with pytest.raises(ConfigurationError) as exc_info:
            run_indexing(
                config=config,
                entity="test",
                document_id="doc-123",
                content_path=content_path,
                metadata_path=metadata_path,
            )

        assert "llmemory.database_url" in str(exc_info.value)


class TestIndexToLLMemoryIntegration:
    """Integration tests for llmemory indexing with real database."""

    @pytest.mark.asyncio
    async def test_indexes_text_file(self, temp_config_with_llmemory):
        """Test indexing a text file to llmemory."""
        config = temp_config_with_llmemory
        archive_dir = Path(config.settings["archive"]["base_path"])

        # Create content file and sidecar
        content_path = archive_dir / "test.txt"
        content_path.write_text("This is test content for indexing.")

        metadata_path = archive_dir / "test.json"
        metadata_path.write_text(json.dumps({
            "id": "doc-123",
            "source": "mail",
            "workflow": "test-workflow",
            "mimetype": "text/plain",
        }))

        result = await index_to_llmemory(
            config=config,
            entity="test-entity",
            document_id="doc-123",
            content_path=content_path,
            metadata_path=metadata_path,
        )

        assert result["success"] is True
        assert result["document_id"] is not None
        assert result["chunks_created"] >= 1

        # Verify sidecar was updated
        with open(metadata_path) as f:
            updated_sidecar = json.load(f)

        assert "llmemory" in updated_sidecar
        assert updated_sidecar["llmemory"]["document_id"] == result["document_id"]
        assert "indexed_at" in updated_sidecar["llmemory"]

    @pytest.mark.asyncio
    async def test_indexes_markdown_file(self, temp_config_with_llmemory):
        """Test indexing a markdown file to llmemory."""
        config = temp_config_with_llmemory
        archive_dir = Path(config.settings["archive"]["base_path"])

        # Create content file and sidecar
        content_path = archive_dir / "document.md"
        content_path.write_text("# Test Document\n\nThis is a test markdown document.")

        metadata_path = archive_dir / "document.json"
        metadata_path.write_text(json.dumps({
            "id": "doc-456",
            "source": "mail",
            "mimetype": "text/markdown",
        }))

        result = await index_to_llmemory(
            config=config,
            entity="test-entity",
            document_id="doc-456",
            content_path=content_path,
            metadata_path=metadata_path,
        )

        assert result["success"] is True
        assert result["chunks_created"] >= 1

    @pytest.mark.asyncio
    async def test_returns_error_for_unsupported_file_type(self, temp_config_with_llmemory):
        """Test that unsupported file types return error result."""
        config = temp_config_with_llmemory
        archive_dir = Path(config.settings["archive"]["base_path"])

        # Create binary content file and sidecar
        content_path = archive_dir / "binary.bin"
        content_path.write_bytes(b"\x00\x01\x02\x03")

        metadata_path = archive_dir / "binary.json"
        metadata_path.write_text(json.dumps({
            "id": "doc-789",
            "source": "mail",
            "mimetype": "application/octet-stream",
        }))

        result = await index_to_llmemory(
            config=config,
            entity="test-entity",
            document_id="doc-789",
            content_path=content_path,
            metadata_path=metadata_path,
        )

        # Should fail because no text could be extracted
        assert result["success"] is False


class TestRunIndexingIntegration:
    """Integration tests for run_indexing sync wrapper."""

    def test_run_indexing_indexes_file(self, temp_config_with_llmemory):
        """Test run_indexing successfully indexes a file."""
        config = temp_config_with_llmemory
        archive_dir = Path(config.settings["archive"]["base_path"])

        # Create content file and sidecar
        content_path = archive_dir / "sync_test.txt"
        content_path.write_text("Content for synchronous indexing test.")

        metadata_path = archive_dir / "sync_test.json"
        metadata_path.write_text(json.dumps({
            "id": "sync-doc-123",
            "source": "mail",
        }))

        result = run_indexing(
            config=config,
            entity="test-entity",
            document_id="sync-doc-123",
            content_path=content_path,
            metadata_path=metadata_path,
        )

        assert result["success"] is True
        assert result["document_id"] is not None

    @pytest.mark.asyncio
    async def test_run_indexing_from_async_context(self, temp_config_with_llmemory):
        """Test run_indexing works from async context (uses thread pool)."""
        config = temp_config_with_llmemory
        archive_dir = Path(config.settings["archive"]["base_path"])

        # Create content file and sidecar
        content_path = archive_dir / "async_test.txt"
        content_path.write_text("Content for async context test.")

        metadata_path = archive_dir / "async_test.json"
        metadata_path.write_text(json.dumps({
            "id": "async-doc-123",
            "source": "mail",
        }))

        # This should work even though we're in an async context
        result = run_indexing(
            config=config,
            entity="test-entity",
            document_id="async-doc-123",
            content_path=content_path,
            metadata_path=metadata_path,
        )

        assert result["success"] is True
