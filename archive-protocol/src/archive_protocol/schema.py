# ABOUTME: Pydantic models for metadata schema validation
# ABOUTME: Defines structure for documents, content, and llmemory integration

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DocumentType(str, Enum):
    """Document types for classification."""
    RECEIPT = "receipt"
    INVOICE = "invoice"
    TAX_DOCUMENT = "tax-document"
    CONTRACT = "contract"
    REPORT = "report"
    EMAIL = "email"
    MESSAGE = "message"
    DOCUMENT = "document"
    OTHER = "other"


class SourceType(str, Enum):
    """Source types for connectors."""
    MAIL = "mail"
    SLACK = "slack"
    GDOCS = "gdocs"
    LOCALDOCS = "localdocs"
    OTHER = "other"


class ContentMetadata(BaseModel):
    """Content file information."""
    path: str = Field(..., description="Relative path from metadata file")
    hash: str = Field(..., pattern=r"^sha256:[a-f0-9]{64}$")
    size_bytes: int = Field(..., gt=0)
    mimetype: str
    attachments: list[str] = Field(default_factory=list)


class IngestMetadata(BaseModel):
    """Ingestion tracking information."""
    connector: str = Field(..., description="Connector name and version")
    ingested_at: datetime
    hostname: str | None = None
    workflow_run_id: str | None = None


class LLMemoryMetadata(BaseModel):
    """llmemory indexing status."""
    indexed_at: datetime | None = None
    document_id: str | None = None
    chunks_created: int | None = None
    embedding_model: str | None = None
    embedding_provider: str | None = None


class RelationshipMetadata(BaseModel):
    """Document relationship."""
    type: str
    target_id: str


class DocumentMetadata(BaseModel):
    """Complete document metadata schema."""

    # Core fields
    id: str = Field(..., description="Unique document ID")
    entity: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    source: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    workflow: str | None = Field(None, pattern=r"^[a-z0-9_-]+$")
    type: str
    subtype: str | None = None
    created_at: datetime

    # Content and provenance
    content: ContentMetadata
    origin: dict[str, Any]  # Source-specific metadata

    # Classification and linking
    tags: list[str] = Field(default_factory=list)
    relationships: list[RelationshipMetadata] = Field(default_factory=list)

    # System metadata
    ingest: IngestMetadata
    llmemory: LLMemoryMetadata = Field(default_factory=LLMemoryMetadata)

    @field_validator('entity', 'source')
    @classmethod
    def validate_lowercase(cls, v: str) -> str:
        """Ensure entity and source are lowercase."""
        if not v.islower():
            raise ValueError(f"Must be lowercase: {v}")
        return v


def validate_metadata(metadata: dict) -> DocumentMetadata:
    """Validate metadata against schema.

    Args:
        metadata: Dictionary to validate

    Returns:
        Validated DocumentMetadata model

    Raises:
        ValidationError: If validation fails
    """
    return DocumentMetadata.model_validate(metadata)
