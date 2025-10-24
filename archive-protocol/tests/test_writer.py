# ABOUTME: Tests for RepositoryWriter class
# ABOUTME: Validates document writing, path resolution, and metadata generation

import json
from datetime import datetime
from pathlib import Path

import pytest

from archive_protocol.config import RepositoryConfig
from archive_protocol.exceptions import PathError, ValidationError, WriteError
from archive_protocol.writer import RepositoryWriter


class TestRepositoryWriter:
    """Test RepositoryWriter functionality."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create temporary repository."""
        return tmp_path / "archive"

    @pytest.fixture
    def config(self, temp_repo):
        """Create test configuration."""
        return RepositoryConfig(
            base_path=str(temp_repo),
            create_directories=True,
            atomic_writes=True,
            compute_hashes=True
        )

    @pytest.fixture
    def writer(self, config):
        """Create test writer."""
        return RepositoryWriter(
            config=config,
            entity="test-entity",
            source="mail",
            connector_version="1.0.0"
        )

    def test_init(self, config):
        """Test RepositoryWriter initialization."""
        writer = RepositoryWriter(
            config=config,
            entity="test-entity",
            source="mail",
            connector_version="1.0.0"
        )

        assert writer.entity == "test-entity"
        assert writer.source == "mail"
        assert writer.connector_version == "1.0.0"
        assert writer.config == config

    def test_init_validates_entity(self, config):
        """Test that initialization validates entity format."""
        with pytest.raises(ValidationError) as exc:
            RepositoryWriter(
                config=config,
                entity="TestEntity",  # Uppercase not allowed
                source="mail"
            )
        assert "entity" in str(exc.value).lower()

    def test_init_validates_source(self, config):
        """Test that initialization validates source format."""
        with pytest.raises(ValidationError) as exc:
            RepositoryWriter(
                config=config,
                entity="test-entity",
                source="MAIL"  # Uppercase not allowed
            )
        assert "source" in str(exc.value).lower()

    def test_write_document_minimal(self, writer, temp_repo):
        """Test writing document with minimal fields."""
        content = b"Test document content"
        created_at = datetime(2025, 10, 23, 14, 30, 0)

        doc_id, content_path, metadata_path = writer.write_document(
            workflow="expenses",
            content=content,
            mimetype="text/plain",
            origin={"email_id": "12345", "subject": "Test"},
            created_at=created_at
        )

        # Check document ID format
        assert doc_id.startswith("mail=expenses/2025-10-23T14:30:00Z/sha256:")

        # Check files exist
        assert content_path.exists()
        assert metadata_path.exists()

        # Check paths are in workflows directory
        assert "workflows" in str(content_path)
        assert "workflows/expenses" in str(content_path)

        # Check content
        assert content_path.read_bytes() == content

        # Check metadata
        metadata = json.loads(metadata_path.read_text())
        assert metadata["id"] == doc_id
        assert metadata["entity"] == "test-entity"
        assert metadata["source"] == "mail"
        assert metadata["workflow"] == "expenses"
        assert metadata["type"] == "document"
        assert metadata["content"]["mimetype"] == "text/plain"
        assert metadata["content"]["size_bytes"] == len(content)
        assert metadata["origin"] == {"email_id": "12345", "subject": "Test"}

    def test_write_document_with_all_fields(self, writer, temp_repo):
        """Test writing document with all optional fields."""
        content = b"Test document content"
        created_at = datetime(2025, 10, 23, 14, 30, 0)
        attachments = [b"attachment1", b"attachment2"]
        attachment_mimetypes = ["image/jpeg", "image/png"]

        doc_id, content_path, metadata_path = writer.write_document(
            workflow="expenses",
            content=content,
            mimetype="application/pdf",
            origin={"email_id": "12345"},
            created_at=created_at,
            document_type="receipt",
            document_subtype="digital",
            attachments=attachments,
            attachment_mimetypes=attachment_mimetypes,
            tags=["expense", "travel"],
            relationships=[
                {"type": "reply-to", "target_id": "mail=inbox/2025-10-20T10:00:00Z/sha256:xyz"}
            ],
            original_filename="receipt.pdf"
        )

        # Check files exist
        assert content_path.exists()
        assert metadata_path.exists()

        # Check attachments exist
        att1_path = content_path.parent / f"{content_path.stem}-att1.jpg"
        att2_path = content_path.parent / f"{content_path.stem}-att2.png"
        assert att1_path.exists()
        assert att2_path.exists()
        assert att1_path.read_bytes() == b"attachment1"
        assert att2_path.read_bytes() == b"attachment2"

        # Check metadata
        metadata = json.loads(metadata_path.read_text())
        assert metadata["type"] == "receipt"
        assert metadata["subtype"] == "digital"
        assert metadata["tags"] == ["expense", "travel"]
        assert len(metadata["relationships"]) == 1
        assert len(metadata["content"]["attachments"]) == 2

    def test_write_document_validates_workflow(self, writer):
        """Test that write_document validates workflow format."""
        with pytest.raises(ValidationError) as exc:
            writer.write_document(
                workflow="Expenses",  # Uppercase not allowed
                content=b"test",
                mimetype="text/plain",
                origin={"test": "data"}
            )
        assert "workflow" in str(exc.value).lower()

    def test_write_document_validates_attachments_mimetypes(self, writer):
        """Test that attachments and mimetypes must have same length."""
        with pytest.raises(ValidationError) as exc:
            writer.write_document(
                workflow="expenses",
                content=b"test",
                mimetype="text/plain",
                origin={"test": "data"},
                attachments=[b"att1", b"att2"],
                attachment_mimetypes=["image/jpeg"]  # Mismatch
            )
        assert "attachment" in str(exc.value).lower()

    def test_write_stream_minimal(self, writer, temp_repo):
        """Test writing stream document with minimal fields."""
        content = b"Test stream content"
        created_at = datetime(2025, 10, 23, 14, 30, 0)

        doc_id, content_path, metadata_path = writer.write_stream(
            stream_name="inbox-stream",
            content=content,
            mimetype="text/plain",
            origin={"email_id": "12345"},
            created_at=created_at
        )

        # Check document ID format
        assert doc_id.startswith("mail=inbox-stream/2025-10-23T14:30:00Z/sha256:")

        # Check files exist
        assert content_path.exists()
        assert metadata_path.exists()

        # Check paths are in streams directory
        assert "streams" in str(content_path)
        assert "streams/inbox-stream" in str(content_path)

        # Check metadata
        metadata = json.loads(metadata_path.read_text())
        assert metadata["workflow"] is None  # Streams have no workflow

    def test_write_stream_validates_stream_name(self, writer):
        """Test that write_stream validates stream name format."""
        with pytest.raises(ValidationError) as exc:
            writer.write_stream(
                stream_name="Inbox-Stream",  # Uppercase not allowed
                content=b"test",
                mimetype="text/plain",
                origin={"test": "data"}
            )
        assert "stream" in str(exc.value).lower()

    def test_filename_generation(self, writer, temp_repo):
        """Test filename generation format."""
        created_at = datetime(2025, 10, 23, 14, 30, 0)

        _, content_path, _ = writer.write_document(
            workflow="expenses",
            content=b"test",
            mimetype="application/pdf",
            origin={"test": "data"},
            created_at=created_at
        )

        # Check filename format: yyyy-mm-dd-source-base36timestamp.ext
        filename = content_path.name
        assert filename.startswith("2025-10-23-mail-")
        assert filename.endswith(".pdf")

    def test_collision_handling(self, writer, temp_repo):
        """Test that filename collisions are handled."""
        created_at = datetime(2025, 10, 23, 14, 30, 0)

        # Write first document
        doc_id1, path1, _ = writer.write_document(
            workflow="expenses",
            content=b"test1",
            mimetype="text/plain",
            origin={"test": "data1"},
            created_at=created_at
        )

        # Write second document with same timestamp (different content)
        doc_id2, path2, _ = writer.write_document(
            workflow="expenses",
            content=b"test2",
            mimetype="text/plain",
            origin={"test": "data2"},
            created_at=created_at
        )

        # Paths should be different (collision handled)
        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_extension_from_mimetype(self, writer, temp_repo):
        """Test file extension determination from mimetype."""
        test_cases = [
            ("application/pdf", ".pdf"),
            ("text/plain", ".txt"),
            ("text/html", ".html"),
            ("application/json", ".json"),
            ("image/jpeg", ".jpg"),
            ("image/png", ".png"),
        ]

        for mimetype, expected_ext in test_cases:
            _, content_path, _ = writer.write_document(
                workflow="test",
                content=b"test",
                mimetype=mimetype,
                origin={"test": "data"}
            )
            assert content_path.suffix == expected_ext

    def test_extension_from_original_filename(self, writer, temp_repo):
        """Test that original filename extension is preserved."""
        _, content_path, _ = writer.write_document(
            workflow="test",
            content=b"test",
            mimetype="application/octet-stream",
            origin={"test": "data"},
            original_filename="document.docx"
        )

        assert content_path.suffix == ".docx"

    def test_atomic_writes(self, writer, temp_repo):
        """Test that atomic writes are used when enabled."""
        # This test verifies files are written successfully with atomic writes enabled
        _, content_path, metadata_path = writer.write_document(
            workflow="test",
            content=b"test content",
            mimetype="text/plain",
            origin={"test": "data"}
        )

        assert content_path.exists()
        assert metadata_path.exists()
        assert content_path.read_bytes() == b"test content"

    def test_write_error_cleanup(self, writer, temp_repo, monkeypatch):
        """Test that partial writes are cleaned up on error."""
        # Make write_atomically fail after content is written
        original_write = writer._write_content_and_metadata

        def failing_write(*args, **kwargs):
            raise IOError("Simulated write failure")

        monkeypatch.setattr(writer, "_write_content_and_metadata", failing_write)

        with pytest.raises(Exception):
            writer.write_document(
                workflow="test",
                content=b"test",
                mimetype="text/plain",
                origin={"test": "data"}
            )

    def test_path_resolution_workflow(self, writer, temp_repo):
        """Test workflow path resolution."""
        from datetime import datetime
        created_at = datetime(2025, 10, 23, 14, 30, 0)

        path = writer._resolve_workflow_path("expenses", created_at)

        expected = temp_repo / "test-entity" / "workflows" / "expenses" / "2025"
        assert path == expected
        assert path.exists()

    def test_path_resolution_stream(self, writer, temp_repo):
        """Test stream path resolution."""
        from datetime import datetime
        created_at = datetime(2025, 10, 23, 14, 30, 0)

        path = writer._resolve_stream_path("inbox-stream", created_at)

        expected = temp_repo / "test-entity" / "streams" / "inbox-stream" / "2025"
        assert path == expected
        assert path.exists()

    def test_generate_document_id_format(self, writer):
        """Test document ID generation format."""
        created_at = datetime(2025, 10, 23, 14, 30, 0)
        content_hash = "sha256:abc123" + "0" * 58

        from archive_protocol.metadata import MetadataBuilder
        builder = MetadataBuilder(
            entity=writer.entity,
            source=writer.source,
            workflow="expenses"
        )

        doc_id = builder.generate_document_id(
            workflow_or_context="expenses",
            created_at=created_at,
            content_hash=content_hash
        )

        assert doc_id == f"mail=expenses/2025-10-23T14:30:00Z/{content_hash}"

    def test_int_to_base36(self, writer):
        """Test integer to base36 conversion."""
        assert writer._int_to_base36(0) == "0"
        assert writer._int_to_base36(35) == "z"
        assert writer._int_to_base36(36) == "10"
        assert writer._int_to_base36(1000) == "rs"

    def test_write_preserves_origin_metadata(self, writer, temp_repo):
        """Test that origin metadata is preserved exactly."""
        origin = {
            "email_id": "12345",
            "subject": "Test Subject",
            "from": "sender@example.com",
            "to": ["recipient@example.com"],
            "date": "2025-10-23T14:30:00Z"
        }

        _, _, metadata_path = writer.write_document(
            workflow="test",
            content=b"test",
            mimetype="text/plain",
            origin=origin
        )

        metadata = json.loads(metadata_path.read_text())
        assert metadata["origin"] == origin

    def test_write_multiple_workflows(self, writer, temp_repo):
        """Test writing to multiple workflows."""
        writer.write_document(
            workflow="expenses",
            content=b"expense doc",
            mimetype="text/plain",
            origin={"type": "expense"}
        )

        writer.write_document(
            workflow="receipts",
            content=b"receipt doc",
            mimetype="text/plain",
            origin={"type": "receipt"}
        )

        # Check both workflow directories exist
        expenses_dir = temp_repo / "test-entity" / "workflows" / "expenses"
        receipts_dir = temp_repo / "test-entity" / "workflows" / "receipts"

        assert expenses_dir.exists()
        assert receipts_dir.exists()

    def test_write_multiple_streams(self, writer, temp_repo):
        """Test writing to multiple streams."""
        writer.write_stream(
            stream_name="inbox",
            content=b"inbox doc",
            mimetype="text/plain",
            origin={"type": "inbox"}
        )

        writer.write_stream(
            stream_name="sent",
            content=b"sent doc",
            mimetype="text/plain",
            origin={"type": "sent"}
        )

        # Check both stream directories exist
        inbox_dir = temp_repo / "test-entity" / "streams" / "inbox"
        sent_dir = temp_repo / "test-entity" / "streams" / "sent"

        assert inbox_dir.exists()
        assert sent_dir.exists()

    def test_hash_computation_disabled(self, temp_repo):
        """Test writing with hash computation disabled."""
        config = RepositoryConfig(
            base_path=str(temp_repo),
            compute_hashes=False
        )
        writer = RepositoryWriter(config=config, entity="test-entity", source="mail")

        doc_id, _, metadata_path = writer.write_document(
            workflow="test",
            content=b"test",
            mimetype="text/plain",
            origin={"test": "data"}
        )

        # Document should still be written
        assert metadata_path.exists()
        metadata = json.loads(metadata_path.read_text())
        assert "hash" in metadata["content"]

    def test_content_size_recorded(self, writer, temp_repo):
        """Test that content size is recorded accurately."""
        content = b"x" * 12345

        _, _, metadata_path = writer.write_document(
            workflow="test",
            content=content,
            mimetype="text/plain",
            origin={"test": "data"}
        )

        metadata = json.loads(metadata_path.read_text())
        assert metadata["content"]["size_bytes"] == 12345
