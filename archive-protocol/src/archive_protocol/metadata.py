# ABOUTME: Metadata generation and building utilities
# ABOUTME: Creates consistent metadata documents for all connectors

import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from archive_protocol.schema import (
    ContentMetadata,
    DocumentMetadata,
    IngestMetadata,
    LLMemoryMetadata,
    RelationshipMetadata,
)


class MetadataBuilder:
    """Build consistent metadata documents for archive repository."""

    def __init__(
        self,
        entity: str,
        source: str,
        workflow: str | None = None,
        connector_version: str = "0.1.0"
    ):
        """Initialize metadata builder.

        Args:
            entity: Entity identifier (lowercase)
            source: Source system identifier (lowercase)
            workflow: Optional workflow name (lowercase)
            connector_version: Version of the connector
        """
        self.entity = entity
        self.source = source
        self.workflow = workflow
        self.connector_version = connector_version

    def build(
        self,
        document_id: str,
        content_path: Path | str,
        content_hash: str,
        content_size: int,
        mimetype: str,
        origin: dict[str, Any],
        created_at: datetime | None = None,
        document_type: str = "document",
        document_subtype: str | None = None,
        attachments: list[str | Path] | None = None,
        tags: list[str] | None = None,
        relationships: list[dict] | None = None,
    ) -> dict:
        """Build complete metadata document.

        Args:
            document_id: Unique document ID
            content_path: Relative path from metadata file to content
            content_hash: SHA-256 hash of content (format: sha256:hexdigest)
            content_size: Size in bytes
            mimetype: MIME type
            origin: Source-specific metadata dict
            created_at: Creation timestamp (defaults to now)
            document_type: Document type
            document_subtype: Document subtype
            attachments: List of attachment paths
            tags: List of tags
            relationships: List of relationship dicts with 'type' and 'target_id'

        Returns:
            Complete metadata dictionary
        """
        if created_at is None:
            created_at = datetime.now()

        # Build content metadata
        content_meta = ContentMetadata(
            path=str(content_path) if isinstance(content_path, Path) else content_path,
            hash=content_hash,
            size_bytes=content_size,
            mimetype=mimetype,
            attachments=[str(a) for a in (attachments or [])]
        )

        # Build ingest metadata
        ingest_meta = IngestMetadata(
            connector=f"{self.source}@{self.connector_version}",
            ingested_at=datetime.now(),
            hostname=socket.gethostname(),
            workflow_run_id=None
        )

        # Build llmemory metadata (initially empty)
        llmemory_meta = LLMemoryMetadata()

        # Build relationships
        rel_objects = [
            RelationshipMetadata(**rel) for rel in (relationships or [])
        ]

        # Build complete metadata
        metadata = DocumentMetadata(
            id=document_id,
            entity=self.entity,
            source=self.source,
            workflow=self.workflow,
            type=document_type,
            subtype=document_subtype,
            created_at=created_at,
            content=content_meta,
            origin=origin,
            tags=tags or [],
            relationships=rel_objects,
            ingest=ingest_meta,
            llmemory=llmemory_meta
        )

        return metadata.model_dump(mode='json')

    def generate_document_id(
        self,
        workflow_or_context: str,
        created_at: datetime,
        content_hash: str
    ) -> str:
        """Generate unique document ID.

        Format: {source}={workflow_or_context}/{timestamp}/{hash}
        Example: mail=jro-expense/2025-10-23T13:45:01Z/sha256:abc...

        Args:
            workflow_or_context: Workflow name or context identifier
            created_at: Document creation timestamp
            content_hash: Content hash (format: sha256:hexdigest)

        Returns:
            Formatted document ID string
        """
        timestamp = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"{self.source}={workflow_or_context}/{timestamp}/{content_hash}"
