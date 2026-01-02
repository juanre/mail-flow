# ABOUTME: Tests for MetadataBuilder class
# ABOUTME: Validates metadata generation, document ID creation, and schema compliance

from datetime import datetime, timezone
from pathlib import Path

import pytest

from archive_protocol.metadata import MetadataBuilder
from archive_protocol.schema import validate_metadata


class TestMetadataBuilder:
    """Test MetadataBuilder functionality."""

    def test_init(self):
        """Test MetadataBuilder initialization."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses",
            connector_version="1.0.0"
        )

        assert builder.entity == "test-entity"
        assert builder.source == "mail"
        assert builder.workflow == "expenses"
        assert builder.connector_version == "1.0.0"

    def test_init_without_workflow(self):
        """Test MetadataBuilder initialization without workflow."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail"
        )

        assert builder.entity == "test-entity"
        assert builder.source == "mail"
        assert builder.workflow is None
        assert builder.connector_version == "0.1.0"

    def test_build_minimal(self):
        """Test building metadata with minimal required fields."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        created_at = datetime(2025, 10, 23, 14, 30, 0, tzinfo=timezone.utc)
        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345", "subject": "Test"},
            created_at=created_at
        )

        # Validate against schema
        validated = validate_metadata(metadata)
        assert validated.id == "mail=expenses/2025-10-23T14:30:00Z/sha256:abc123"
        assert validated.entity == "test-entity"
        assert validated.source == "mail"
        assert validated.workflow == "expenses"
        assert validated.type == "document"
        assert validated.content.path == "content.pdf"
        assert validated.content.hash.startswith("sha256:")
        assert validated.content.size_bytes == 1024
        assert validated.content.mimetype == "application/pdf"
        assert validated.origin == {"email_id": "12345", "subject": "Test"}
        assert validated.ingest.connector == "mail@0.1.0"
        assert validated.tags == []
        assert validated.relationships == []

    def test_build_with_all_fields(self):
        """Test building metadata with all optional fields."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses",
            connector_version="2.0.0"
        )

        created_at = datetime(2025, 10, 23, 14, 30, 0, tzinfo=timezone.utc)
        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=2048,
            mimetype="application/pdf",
            origin={"email_id": "12345", "subject": "Test"},
            created_at=created_at,
            document_type="receipt",
            document_subtype="digital",
            attachments=["att1.jpg", "att2.png"],
            tags=["expense", "travel"],
            relationships=[
                {"type": "reply-to", "target_id": "mail=inbox/2025-10-20T10:00:00Z/sha256:xyz789"}
            ]
        )

        # Validate against schema
        validated = validate_metadata(metadata)
        assert validated.type == "receipt"
        assert validated.subtype == "digital"
        assert validated.content.attachments == ["att1.jpg", "att2.png"]
        assert validated.tags == ["expense", "travel"]
        assert len(validated.relationships) == 1
        assert validated.relationships[0].type == "reply-to"
        assert validated.ingest.connector == "mail@2.0.0"

    def test_build_with_path_object(self):
        """Test building metadata with Path object for content_path."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path=Path("subdir/content.pdf"),
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"}
        )

        validated = validate_metadata(metadata)
        assert validated.content.path == "subdir/content.pdf"

    def test_build_with_path_attachments(self):
        """Test building metadata with Path objects for attachments."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"},
            attachments=[Path("att1.jpg"), Path("att2.png")]
        )

        validated = validate_metadata(metadata)
        assert validated.content.attachments == ["att1.jpg", "att2.png"]

    def test_build_defaults_created_at(self):
        """Test that build defaults created_at to current time."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        before = datetime.now(timezone.utc)
        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"}
        )
        after = datetime.now(timezone.utc)

        validated = validate_metadata(metadata)
        assert before <= validated.created_at <= after

    def test_build_sets_ingest_timestamp(self):
        """Test that build sets ingest timestamp to current time."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        before = datetime.now(timezone.utc)
        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"},
            created_at=datetime(2025, 10, 20, 10, 0, 0, tzinfo=timezone.utc)  # Earlier date
        )
        after = datetime.now(timezone.utc)

        validated = validate_metadata(metadata)
        assert before <= validated.ingest.ingested_at <= after

    def test_build_sets_hostname(self):
        """Test that build sets hostname."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"}
        )

        validated = validate_metadata(metadata)
        assert validated.ingest.hostname is not None
        assert len(validated.ingest.hostname) > 0

    def test_build_initializes_empty_llmemory(self):
        """Test that build initializes empty llmemory metadata."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"}
        )

        validated = validate_metadata(metadata)
        assert validated.llmemory.indexed_at is None
        assert validated.llmemory.document_id is None
        assert validated.llmemory.chunks_created is None
        assert validated.llmemory.embedding_model is None

    def test_generate_document_id(self):
        """Test document ID generation."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        created_at = datetime(2025, 10, 23, 14, 30, 0, tzinfo=timezone.utc)
        content_hash = "sha256:abc123def456" + "0" * 52

        doc_id = builder.generate_document_id(
            workflow_or_context="expenses",
            created_at=created_at,
            content_hash=content_hash
        )

        expected = f"mail=expenses/2025-10-23T14:30:00Z/{content_hash}"
        assert doc_id == expected

    def test_generate_document_id_formats_timestamp(self):
        """Test document ID timestamp formatting."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail"
        )

        created_at = datetime(2025, 1, 5, 9, 5, 3, tzinfo=timezone.utc)
        content_hash = "sha256:abc123" + "0" * 58

        doc_id = builder.generate_document_id(
            workflow_or_context="test",
            created_at=created_at,
            content_hash=content_hash
        )

        assert "2025-01-05T09:05:03Z" in doc_id

    def test_generate_document_id_for_stream(self):
        """Test document ID generation for stream (no workflow)."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow=None
        )

        created_at = datetime(2025, 10, 23, 14, 30, 0, tzinfo=timezone.utc)
        content_hash = "sha256:abc123" + "0" * 58

        doc_id = builder.generate_document_id(
            workflow_or_context="inbox-stream",
            created_at=created_at,
            content_hash=content_hash
        )

        assert doc_id.startswith("mail=inbox-stream/2025-10-23T14:30:00Z/")

    def test_build_with_invalid_hash_format_fails(self):
        """Test that invalid hash format fails validation."""
        from pydantic import ValidationError as PydanticValidationError

        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        # Building with invalid hash should fail immediately
        with pytest.raises(PydanticValidationError):
            metadata = builder.build(
                document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
                content_path="content.pdf",
                content_hash="invalid_hash",  # Invalid format
                content_size=1024,
                mimetype="application/pdf",
                origin={"email_id": "12345"}
            )

    def test_build_with_empty_relationships(self):
        """Test building with empty relationships list."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"},
            relationships=[]
        )

        validated = validate_metadata(metadata)
        assert validated.relationships == []

    def test_build_multiple_relationships(self):
        """Test building with multiple relationships."""
        builder = MetadataBuilder(
            entity="test-entity",
            source="mail",
            workflow="expenses"
        )

        metadata = builder.build(
            document_id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc123",
            content_path="content.pdf",
            content_hash="sha256:abc123def456" + "0" * 52,
            content_size=1024,
            mimetype="application/pdf",
            origin={"email_id": "12345"},
            relationships=[
                {"type": "reply-to", "target_id": "mail=inbox/2025-10-20T10:00:00Z/sha256:xyz789"},
                {"type": "references", "target_id": "mail=sent/2025-10-19T15:30:00Z/sha256:def456"}
            ]
        )

        validated = validate_metadata(metadata)
        assert len(validated.relationships) == 2
        assert validated.relationships[0].type == "reply-to"
        assert validated.relationships[1].type == "references"
