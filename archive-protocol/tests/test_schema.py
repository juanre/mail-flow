# ABOUTME: Tests for Pydantic schema models in archive_protocol.schema
# ABOUTME: Validates document metadata, content metadata, and schema validation

from datetime import datetime

import pytest
from pydantic import ValidationError

from archive_protocol.schema import (
    ContentMetadata,
    DocumentMetadata,
    DocumentType,
    IngestMetadata,
    LLMemoryMetadata,
    RelationshipMetadata,
    SourceType,
    validate_metadata,
)


class TestDocumentType:
    """Test DocumentType enum."""

    def test_document_type_values(self):
        """Test that all document types are defined."""
        assert DocumentType.RECEIPT == "receipt"
        assert DocumentType.INVOICE == "invoice"
        assert DocumentType.TAX_DOCUMENT == "tax-document"
        assert DocumentType.CONTRACT == "contract"
        assert DocumentType.REPORT == "report"
        assert DocumentType.EMAIL == "email"
        assert DocumentType.MESSAGE == "message"
        assert DocumentType.DOCUMENT == "document"
        assert DocumentType.OTHER == "other"

    def test_document_type_string_conversion(self):
        """Test that DocumentType can be used as string."""
        doc_type = DocumentType.RECEIPT
        assert doc_type.value == "receipt"


class TestSourceType:
    """Test SourceType enum."""

    def test_source_type_values(self):
        """Test that all source types are defined."""
        assert SourceType.MAIL == "mail"
        assert SourceType.SLACK == "slack"
        assert SourceType.GDOCS == "gdocs"
        assert SourceType.LOCALDOCS == "localdocs"
        assert SourceType.OTHER == "other"

    def test_source_type_string_conversion(self):
        """Test that SourceType can be used as string."""
        source_type = SourceType.MAIL
        assert source_type.value == "mail"


class TestContentMetadata:
    """Test ContentMetadata model."""

    def test_content_metadata_valid(self):
        """Test ContentMetadata with valid data."""
        content = ContentMetadata(
            path="content.pdf",
            hash="sha256:" + "a" * 64,
            size_bytes=1024,
            mimetype="application/pdf"
        )

        assert content.path == "content.pdf"
        assert content.hash.startswith("sha256:")
        assert content.size_bytes == 1024
        assert content.mimetype == "application/pdf"
        assert content.attachments == []

    def test_content_metadata_with_attachments(self):
        """Test ContentMetadata with attachments."""
        content = ContentMetadata(
            path="content.pdf",
            hash="sha256:" + "a" * 64,
            size_bytes=1024,
            mimetype="application/pdf",
            attachments=["att1.jpg", "att2.png"]
        )

        assert content.attachments == ["att1.jpg", "att2.png"]

    def test_content_metadata_hash_pattern_validation(self):
        """Test that hash pattern is validated."""
        # Valid hash
        ContentMetadata(
            path="test.pdf",
            hash="sha256:" + "a" * 64,
            size_bytes=100,
            mimetype="text/plain"
        )

        # Invalid hash - wrong prefix
        with pytest.raises(ValidationError) as exc:
            ContentMetadata(
                path="test.pdf",
                hash="md5:" + "a" * 64,
                size_bytes=100,
                mimetype="text/plain"
            )
        assert "hash" in str(exc.value).lower()

        # Invalid hash - wrong length
        with pytest.raises(ValidationError):
            ContentMetadata(
                path="test.pdf",
                hash="sha256:abc",
                size_bytes=100,
                mimetype="text/plain"
            )

        # Invalid hash - uppercase hex
        with pytest.raises(ValidationError):
            ContentMetadata(
                path="test.pdf",
                hash="sha256:" + "A" * 64,
                size_bytes=100,
                mimetype="text/plain"
            )

    def test_content_metadata_size_validation(self):
        """Test that size_bytes must be positive."""
        # Valid size
        ContentMetadata(
            path="test.pdf",
            hash="sha256:" + "a" * 64,
            size_bytes=1,
            mimetype="text/plain"
        )

        # Invalid - zero
        with pytest.raises(ValidationError) as exc:
            ContentMetadata(
                path="test.pdf",
                hash="sha256:" + "a" * 64,
                size_bytes=0,
                mimetype="text/plain"
            )
        assert "size_bytes" in str(exc.value).lower()

        # Invalid - negative
        with pytest.raises(ValidationError):
            ContentMetadata(
                path="test.pdf",
                hash="sha256:" + "a" * 64,
                size_bytes=-1,
                mimetype="text/plain"
            )

    def test_content_metadata_required_fields(self):
        """Test that all required fields are enforced."""
        # Missing path
        with pytest.raises(ValidationError):
            ContentMetadata(
                hash="sha256:" + "a" * 64,
                size_bytes=100,
                mimetype="text/plain"
            )

        # Missing hash
        with pytest.raises(ValidationError):
            ContentMetadata(
                path="test.pdf",
                size_bytes=100,
                mimetype="text/plain"
            )

        # Missing size_bytes
        with pytest.raises(ValidationError):
            ContentMetadata(
                path="test.pdf",
                hash="sha256:" + "a" * 64,
                mimetype="text/plain"
            )

        # Missing mimetype
        with pytest.raises(ValidationError):
            ContentMetadata(
                path="test.pdf",
                hash="sha256:" + "a" * 64,
                size_bytes=100
            )


class TestIngestMetadata:
    """Test IngestMetadata model."""

    def test_ingest_metadata_valid(self):
        """Test IngestMetadata with valid data."""
        ingest = IngestMetadata(
            connector="mail@1.0.0",
            ingested_at=datetime(2025, 10, 23, 14, 30, 0),
            hostname="test-host",
            workflow_run_id="run-123"
        )

        assert ingest.connector == "mail@1.0.0"
        assert ingest.ingested_at == datetime(2025, 10, 23, 14, 30, 0)
        assert ingest.hostname == "test-host"
        assert ingest.workflow_run_id == "run-123"

    def test_ingest_metadata_optional_fields(self):
        """Test IngestMetadata with optional fields as None."""
        ingest = IngestMetadata(
            connector="mail@1.0.0",
            ingested_at=datetime(2025, 10, 23, 14, 30, 0)
        )

        assert ingest.hostname is None
        assert ingest.workflow_run_id is None

    def test_ingest_metadata_required_fields(self):
        """Test that required fields are enforced."""
        # Missing connector
        with pytest.raises(ValidationError):
            IngestMetadata(
                ingested_at=datetime(2025, 10, 23, 14, 30, 0)
            )

        # Missing ingested_at
        with pytest.raises(ValidationError):
            IngestMetadata(
                connector="mail@1.0.0"
            )


class TestLLMemoryMetadata:
    """Test LLMemoryMetadata model."""

    def test_llmemory_metadata_empty(self):
        """Test LLMemoryMetadata with all None values."""
        llmemory = LLMemoryMetadata()

        assert llmemory.indexed_at is None
        assert llmemory.document_id is None
        assert llmemory.chunks_created is None
        assert llmemory.embedding_model is None
        assert llmemory.embedding_provider is None

    def test_llmemory_metadata_populated(self):
        """Test LLMemoryMetadata with values."""
        llmemory = LLMemoryMetadata(
            indexed_at=datetime(2025, 10, 23, 15, 0, 0),
            document_id="doc-123",
            chunks_created=5,
            embedding_model="text-embedding-ada-002",
            embedding_provider="openai"
        )

        assert llmemory.indexed_at == datetime(2025, 10, 23, 15, 0, 0)
        assert llmemory.document_id == "doc-123"
        assert llmemory.chunks_created == 5
        assert llmemory.embedding_model == "text-embedding-ada-002"
        assert llmemory.embedding_provider == "openai"


class TestRelationshipMetadata:
    """Test RelationshipMetadata model."""

    def test_relationship_metadata_valid(self):
        """Test RelationshipMetadata with valid data."""
        rel = RelationshipMetadata(
            type="reply-to",
            target_id="mail=inbox/2025-10-20T10:00:00Z/sha256:xyz"
        )

        assert rel.type == "reply-to"
        assert rel.target_id == "mail=inbox/2025-10-20T10:00:00Z/sha256:xyz"

    def test_relationship_metadata_required_fields(self):
        """Test that required fields are enforced."""
        # Missing type
        with pytest.raises(ValidationError):
            RelationshipMetadata(
                target_id="mail=inbox/2025-10-20T10:00:00Z/sha256:xyz"
            )

        # Missing target_id
        with pytest.raises(ValidationError):
            RelationshipMetadata(
                type="reply-to"
            )


class TestDocumentMetadata:
    """Test DocumentMetadata model."""

    def test_document_metadata_valid_minimal(self):
        """Test DocumentMetadata with minimal required fields."""
        doc = DocumentMetadata(
            id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc",
            entity="test-entity",
            source="mail",
            workflow="expenses",
            type="document",
            created_at=datetime(2025, 10, 23, 14, 30, 0),
            content=ContentMetadata(
                path="content.pdf",
                hash="sha256:" + "a" * 64,
                size_bytes=1024,
                mimetype="application/pdf"
            ),
            origin={"email_id": "12345"},
            ingest=IngestMetadata(
                connector="mail@1.0.0",
                ingested_at=datetime(2025, 10, 23, 14, 35, 0)
            )
        )

        assert doc.id == "mail=expenses/2025-10-23T14:30:00Z/sha256:abc"
        assert doc.entity == "test-entity"
        assert doc.source == "mail"
        assert doc.workflow == "expenses"
        assert doc.type == "document"
        assert doc.subtype is None
        assert doc.tags == []
        assert doc.relationships == []

    def test_document_metadata_valid_complete(self):
        """Test DocumentMetadata with all fields populated."""
        doc = DocumentMetadata(
            id="mail=expenses/2025-10-23T14:30:00Z/sha256:abc",
            entity="test-entity",
            source="mail",
            workflow="expenses",
            type="receipt",
            subtype="digital",
            created_at=datetime(2025, 10, 23, 14, 30, 0),
            content=ContentMetadata(
                path="content.pdf",
                hash="sha256:" + "a" * 64,
                size_bytes=1024,
                mimetype="application/pdf",
                attachments=["att1.jpg"]
            ),
            origin={"email_id": "12345", "subject": "Receipt"},
            tags=["expense", "travel"],
            relationships=[
                RelationshipMetadata(
                    type="reply-to",
                    target_id="mail=inbox/2025-10-20T10:00:00Z/sha256:xyz"
                )
            ],
            ingest=IngestMetadata(
                connector="mail@1.0.0",
                ingested_at=datetime(2025, 10, 23, 14, 35, 0),
                hostname="test-host"
            ),
            llmemory=LLMemoryMetadata(
                indexed_at=datetime(2025, 10, 23, 15, 0, 0),
                document_id="doc-123",
                chunks_created=5
            )
        )

        assert doc.type == "receipt"
        assert doc.subtype == "digital"
        assert doc.tags == ["expense", "travel"]
        assert len(doc.relationships) == 1
        assert doc.llmemory.document_id == "doc-123"

    def test_document_metadata_entity_pattern_validation(self):
        """Test that entity pattern is validated."""
        # Valid patterns
        valid_entities = [
            "test-entity",
            "test_entity",
            "entity123",
            "123entity",
            "my-test-entity"
        ]

        for entity in valid_entities:
            doc = DocumentMetadata(
                id="test-id",
                entity=entity,
                source="mail",
                workflow="test",
                type="document",
                created_at=datetime.now(),
                content=ContentMetadata(
                    path="test.pdf",
                    hash="sha256:" + "a" * 64,
                    size_bytes=100,
                    mimetype="text/plain"
                ),
                origin={},
                ingest=IngestMetadata(
                    connector="test@1.0.0",
                    ingested_at=datetime.now()
                )
            )
            assert doc.entity == entity

        # Invalid patterns
        invalid_entities = [
            "Test-Entity",  # Uppercase
            "test.entity",  # Dot not allowed
            "test entity",  # Space not allowed
            "test/entity",  # Slash not allowed
        ]

        for entity in invalid_entities:
            with pytest.raises(ValidationError):
                DocumentMetadata(
                    id="test-id",
                    entity=entity,
                    source="mail",
                    workflow="test",
                    type="document",
                    created_at=datetime.now(),
                    content=ContentMetadata(
                        path="test.pdf",
                        hash="sha256:" + "a" * 64,
                        size_bytes=100,
                        mimetype="text/plain"
                    ),
                    origin={},
                    ingest=IngestMetadata(
                        connector="test@1.0.0",
                        ingested_at=datetime.now()
                    )
                )

    def test_document_metadata_source_pattern_validation(self):
        """Test that source pattern is validated."""
        # Valid patterns
        valid_sources = ["mail", "slack", "my-source", "source_123"]

        for source in valid_sources:
            doc = DocumentMetadata(
                id="test-id",
                entity="test-entity",
                source=source,
                workflow="test",
                type="document",
                created_at=datetime.now(),
                content=ContentMetadata(
                    path="test.pdf",
                    hash="sha256:" + "a" * 64,
                    size_bytes=100,
                    mimetype="text/plain"
                ),
                origin={},
                ingest=IngestMetadata(
                    connector="test@1.0.0",
                    ingested_at=datetime.now()
                )
            )
            assert doc.source == source

        # Invalid patterns
        invalid_sources = ["MAIL", "My-Source", "source.name"]

        for source in invalid_sources:
            with pytest.raises(ValidationError):
                DocumentMetadata(
                    id="test-id",
                    entity="test-entity",
                    source=source,
                    workflow="test",
                    type="document",
                    created_at=datetime.now(),
                    content=ContentMetadata(
                        path="test.pdf",
                        hash="sha256:" + "a" * 64,
                        size_bytes=100,
                        mimetype="text/plain"
                    ),
                    origin={},
                    ingest=IngestMetadata(
                        connector="test@1.0.0",
                        ingested_at=datetime.now()
                    )
                )

    def test_document_metadata_workflow_pattern_validation(self):
        """Test that workflow pattern is validated."""
        # Valid patterns (including None)
        doc = DocumentMetadata(
            id="test-id",
            entity="test-entity",
            source="mail",
            workflow=None,
            type="document",
            created_at=datetime.now(),
            content=ContentMetadata(
                path="test.pdf",
                hash="sha256:" + "a" * 64,
                size_bytes=100,
                mimetype="text/plain"
            ),
            origin={},
            ingest=IngestMetadata(
                connector="test@1.0.0",
                ingested_at=datetime.now()
            )
        )
        assert doc.workflow is None

        # Invalid pattern
        with pytest.raises(ValidationError):
            DocumentMetadata(
                id="test-id",
                entity="test-entity",
                source="mail",
                workflow="Invalid-Workflow",  # Uppercase not allowed
                type="document",
                created_at=datetime.now(),
                content=ContentMetadata(
                    path="test.pdf",
                    hash="sha256:" + "a" * 64,
                    size_bytes=100,
                    mimetype="text/plain"
                ),
                origin={},
                ingest=IngestMetadata(
                    connector="test@1.0.0",
                    ingested_at=datetime.now()
                )
            )

    def test_document_metadata_lowercase_validation(self):
        """Test that entity and source are validated as lowercase."""
        # Uppercase entity should fail (pattern validation catches it)
        with pytest.raises(ValidationError):
            DocumentMetadata(
                id="test-id",
                entity="TestEntity",
                source="mail",
                workflow="test",
                type="document",
                created_at=datetime.now(),
                content=ContentMetadata(
                    path="test.pdf",
                    hash="sha256:" + "a" * 64,
                    size_bytes=100,
                    mimetype="text/plain"
                ),
                origin={},
                ingest=IngestMetadata(
                    connector="test@1.0.0",
                    ingested_at=datetime.now()
                )
            )

        # Uppercase source should fail (pattern validation catches it)
        with pytest.raises(ValidationError):
            DocumentMetadata(
                id="test-id",
                entity="test-entity",
                source="MAIL",
                workflow="test",
                type="document",
                created_at=datetime.now(),
                content=ContentMetadata(
                    path="test.pdf",
                    hash="sha256:" + "a" * 64,
                    size_bytes=100,
                    mimetype="text/plain"
                ),
                origin={},
                ingest=IngestMetadata(
                    connector="test@1.0.0",
                    ingested_at=datetime.now()
                )
            )

    def test_document_metadata_origin_any_dict(self):
        """Test that origin accepts any dictionary."""
        origins = [
            {},
            {"email_id": "123"},
            {"complex": {"nested": {"structure": True}}},
            {"list": [1, 2, 3]},
            {"mixed": "string", "number": 42, "bool": True}
        ]

        for origin in origins:
            doc = DocumentMetadata(
                id="test-id",
                entity="test-entity",
                source="mail",
                workflow="test",
                type="document",
                created_at=datetime.now(),
                content=ContentMetadata(
                    path="test.pdf",
                    hash="sha256:" + "a" * 64,
                    size_bytes=100,
                    mimetype="text/plain"
                ),
                origin=origin,
                ingest=IngestMetadata(
                    connector="test@1.0.0",
                    ingested_at=datetime.now()
                )
            )
            assert doc.origin == origin


class TestValidateMetadata:
    """Test validate_metadata function."""

    def test_validate_metadata_valid_dict(self, sample_metadata):
        """Test validating valid metadata dictionary."""
        result = validate_metadata(sample_metadata)

        assert isinstance(result, DocumentMetadata)
        assert result.id == sample_metadata["id"]
        assert result.entity == sample_metadata["entity"]

    def test_validate_metadata_invalid_dict(self):
        """Test validating invalid metadata dictionary."""
        invalid_metadata = {
            "id": "test-id",
            "entity": "test-entity",
            # Missing required fields
        }

        with pytest.raises(ValidationError):
            validate_metadata(invalid_metadata)

    def test_validate_metadata_returns_model(self, sample_metadata):
        """Test that validate_metadata returns DocumentMetadata model."""
        result = validate_metadata(sample_metadata)
        assert isinstance(result, DocumentMetadata)
        assert hasattr(result, 'model_dump')

    def test_validate_metadata_invalid_hash_format(self, sample_metadata):
        """Test validation fails for invalid hash format."""
        sample_metadata["content"]["hash"] = "invalid_hash"

        with pytest.raises(ValidationError) as exc:
            validate_metadata(sample_metadata)
        assert "hash" in str(exc.value).lower()

    def test_validate_metadata_invalid_size(self, sample_metadata):
        """Test validation fails for invalid size."""
        sample_metadata["content"]["size_bytes"] = 0

        with pytest.raises(ValidationError):
            validate_metadata(sample_metadata)

    def test_validate_metadata_missing_required_field(self, sample_metadata):
        """Test validation fails when required field is missing."""
        del sample_metadata["entity"]

        with pytest.raises(ValidationError) as exc:
            validate_metadata(sample_metadata)
        assert "entity" in str(exc.value).lower()
