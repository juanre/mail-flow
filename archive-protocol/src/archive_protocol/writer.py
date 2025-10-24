# ABOUTME: Repository writer for archive-protocol documents and metadata
# ABOUTME: Handles atomic writes, path resolution, and manifest management

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from archive_protocol.config import RepositoryConfig
from archive_protocol.exceptions import PathError, ValidationError, WriteError
from archive_protocol.metadata import MetadataBuilder
from archive_protocol.schema import validate_metadata
from archive_protocol.utils import compute_hash, sanitize_filename, write_atomically

logger = logging.getLogger(__name__)


class RepositoryWriter:
    """Write documents and metadata to archive repository."""

    def __init__(
        self,
        config: RepositoryConfig,
        entity: str,
        source: str,
        connector_version: str = "0.1.0"
    ):
        """Initialize repository writer.

        Args:
            config: Repository configuration
            entity: Entity identifier (lowercase)
            source: Source system identifier (lowercase)
            connector_version: Version of the connector
        """
        self.config = config
        self.entity = entity
        self.source = source
        self.connector_version = connector_version
        self.base_path = config.resolve_base_path()

        # Validate entity and source
        if not entity.islower() or not entity.replace('-', '').replace('_', '').isalnum():
            raise ValidationError(
                f"Invalid entity: {entity}",
                recovery_hint="Entity must be lowercase alphanumeric with hyphens/underscores"
            )
        if not source.islower() or not source.replace('-', '').replace('_', '').isalnum():
            raise ValidationError(
                f"Invalid source: {source}",
                recovery_hint="Source must be lowercase alphanumeric with hyphens/underscores"
            )

        logger.info(f"Initialized RepositoryWriter for {entity}/{source} at {self.base_path}")

    def write_document(
        self,
        workflow: str,
        content: bytes,
        mimetype: str,
        origin: dict[str, Any],
        created_at: datetime | None = None,
        document_type: str = "document",
        document_subtype: str | None = None,
        attachments: list[bytes] | None = None,
        attachment_mimetypes: list[str] | None = None,
        tags: list[str] | None = None,
        relationships: list[dict] | None = None,
        original_filename: str | None = None
    ) -> tuple[str, Path, Path]:
        """Write classified document to workflows directory.

        Args:
            workflow: Workflow name (lowercase)
            content: Document content as bytes
            mimetype: MIME type of content
            origin: Source-specific metadata
            created_at: Creation timestamp (defaults to now)
            document_type: Document type
            document_subtype: Document subtype
            attachments: List of attachment content bytes
            attachment_mimetypes: List of attachment MIME types
            tags: List of tags
            relationships: List of relationship dicts
            original_filename: Original filename for extension detection

        Returns:
            Tuple of (document_id, content_path, metadata_path)

        Raises:
            ValidationError: If validation fails
            WriteError: If write operation fails
        """
        if created_at is None:
            created_at = datetime.now()

        # Validate workflow
        if not workflow.islower() or not workflow.replace('-', '').replace('_', '').isalnum():
            raise ValidationError(
                f"Invalid workflow: {workflow}",
                recovery_hint="Workflow must be lowercase alphanumeric with hyphens/underscores"
            )

        # Compute content hash
        content_hash = compute_hash(content) if self.config.compute_hashes else "sha256:" + "0" * 64

        # Build metadata
        builder = MetadataBuilder(
            entity=self.entity,
            source=self.source,
            workflow=workflow,
            connector_version=self.connector_version
        )

        document_id = builder.generate_document_id(
            workflow_or_context=workflow,
            created_at=created_at,
            content_hash=content_hash
        )

        # Resolve paths
        workflow_dir = self._resolve_workflow_path(workflow)

        # Generate filename
        extension = self._get_extension_from_mimetype(mimetype, original_filename)
        filename_base = self._generate_filename(created_at, extension)

        # Handle attachments
        attachment_paths = []
        if attachments:
            if not attachment_mimetypes or len(attachments) != len(attachment_mimetypes):
                raise ValidationError(
                    "Attachments and attachment_mimetypes must have same length",
                    recovery_hint="Provide mimetype for each attachment"
                )
            attachment_paths = self._write_attachments(
                workflow_dir, filename_base, attachments, attachment_mimetypes
            )

        # Write content and metadata
        content_path, metadata_path = self._write_content_and_metadata(
            directory=workflow_dir,
            filename_base=filename_base,
            content=content,
            builder=builder,
            document_id=document_id,
            content_hash=content_hash,
            mimetype=mimetype,
            origin=origin,
            created_at=created_at,
            document_type=document_type,
            document_subtype=document_subtype,
            attachment_paths=attachment_paths,
            tags=tags,
            relationships=relationships,
            extension=extension
        )

        # Append to manifest
        if self.config.enable_manifest:
            self._append_to_manifest(workflow_dir, metadata_path, document_id)

        logger.info(f"Wrote document {document_id} to {content_path}")
        return document_id, content_path, metadata_path

    def write_stream(
        self,
        stream_name: str,
        content: bytes,
        mimetype: str,
        origin: dict[str, Any],
        created_at: datetime | None = None,
        tags: list[str] | None = None,
        original_filename: str | None = None
    ) -> tuple[str, Path, Path]:
        """Write unclassified document to streams directory.

        Args:
            stream_name: Stream name (lowercase)
            content: Document content as bytes
            mimetype: MIME type of content
            origin: Source-specific metadata
            created_at: Creation timestamp (defaults to now)
            tags: List of tags
            original_filename: Original filename for extension detection

        Returns:
            Tuple of (document_id, content_path, metadata_path)

        Raises:
            ValidationError: If validation fails
            WriteError: If write operation fails
        """
        if created_at is None:
            created_at = datetime.now()

        # Validate stream name
        if not stream_name.islower() or not stream_name.replace('-', '').replace('_', '').isalnum():
            raise ValidationError(
                f"Invalid stream_name: {stream_name}",
                recovery_hint="Stream name must be lowercase alphanumeric with hyphens/underscores"
            )

        # Compute content hash
        content_hash = compute_hash(content) if self.config.compute_hashes else "sha256:" + "0" * 64

        # Build metadata (workflow=None for streams)
        builder = MetadataBuilder(
            entity=self.entity,
            source=self.source,
            workflow=None,
            connector_version=self.connector_version
        )

        document_id = builder.generate_document_id(
            workflow_or_context=stream_name,
            created_at=created_at,
            content_hash=content_hash
        )

        # Resolve paths
        stream_dir = self._resolve_stream_path(stream_name)

        # Generate filename
        extension = self._get_extension_from_mimetype(mimetype, original_filename)
        filename_base = self._generate_filename(created_at, extension)

        # Write content and metadata
        content_path, metadata_path = self._write_content_and_metadata(
            directory=stream_dir,
            filename_base=filename_base,
            content=content,
            builder=builder,
            document_id=document_id,
            content_hash=content_hash,
            mimetype=mimetype,
            origin=origin,
            created_at=created_at,
            document_type="document",
            document_subtype=None,
            attachment_paths=[],
            tags=tags,
            relationships=None,
            extension=extension
        )

        # Append to manifest
        if self.config.enable_manifest:
            self._append_to_manifest(stream_dir, metadata_path, document_id)

        logger.info(f"Wrote stream document {document_id} to {content_path}")
        return document_id, content_path, metadata_path

    def _resolve_workflow_path(self, workflow: str) -> Path:
        """Resolve path for workflow directory.

        Path format: {base_path}/{entity}/workflows/{workflow}

        Args:
            workflow: Workflow name

        Returns:
            Absolute path to workflow directory

        Raises:
            PathError: If path resolution fails
        """
        try:
            path = self.base_path / self.entity / "workflows" / workflow
            if self.config.create_directories:
                path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return path
        except Exception as e:
            raise PathError(
                f"Failed to resolve workflow path for {workflow}: {e}",
                recovery_hint="Check filesystem permissions and path validity"
            ) from e

    def _resolve_stream_path(self, stream_name: str) -> Path:
        """Resolve path for stream directory.

        Path format: {base_path}/{entity}/streams/{stream_name}

        Args:
            stream_name: Stream name

        Returns:
            Absolute path to stream directory

        Raises:
            PathError: If path resolution fails
        """
        try:
            path = self.base_path / self.entity / "streams" / stream_name
            if self.config.create_directories:
                path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return path
        except Exception as e:
            raise PathError(
                f"Failed to resolve stream path for {stream_name}: {e}",
                recovery_hint="Check filesystem permissions and path validity"
            ) from e

    def _generate_filename(self, created_at: datetime, extension: str) -> str:
        """Generate filename with collision handling.

        Format: yyyy-mm-dd-{source}-{base36_timestamp}.{extension}

        Args:
            created_at: Document creation timestamp
            extension: File extension (without dot)

        Returns:
            Sanitized filename base (without extension for metadata)
        """
        date_str = created_at.strftime("%Y-%m-%d")
        timestamp = int(created_at.timestamp())

        # Convert timestamp to base36 for compactness
        base36_ts = self._int_to_base36(timestamp)

        # Build filename base
        filename_base = f"{date_str}-{self.source}-{base36_ts}"

        return filename_base

    def _int_to_base36(self, num: int) -> str:
        """Convert integer to base36 string."""
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        if num == 0:
            return "0"

        result = []
        while num:
            num, rem = divmod(num, 36)
            result.append(alphabet[rem])

        return ''.join(reversed(result))

    def _get_extension_from_mimetype(
        self, mimetype: str, original_filename: str | None = None
    ) -> str:
        """Get file extension from mimetype or filename.

        Args:
            mimetype: MIME type
            original_filename: Optional original filename

        Returns:
            File extension without dot
        """
        # Try to get from original filename first
        if original_filename:
            ext = Path(original_filename).suffix.lstrip('.')
            if ext:
                return ext

        # Common mimetype mappings
        mimetype_map = {
            'application/pdf': 'pdf',
            'text/plain': 'txt',
            'text/html': 'html',
            'text/markdown': 'md',
            'application/json': 'json',
            'image/jpeg': 'jpg',
            'image/png': 'png',
            'image/gif': 'gif',
            'application/zip': 'zip',
            'application/x-gzip': 'gz',
            'text/csv': 'csv',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
        }

        return mimetype_map.get(mimetype, 'bin')

    def _write_attachments(
        self,
        directory: Path,
        filename_base: str,
        attachments: list[bytes],
        attachment_mimetypes: list[str]
    ) -> list[str]:
        """Write attachments and return relative paths.

        Args:
            directory: Directory to write to
            filename_base: Base filename
            attachments: List of attachment content
            attachment_mimetypes: List of attachment MIME types

        Returns:
            List of relative paths to attachments
        """
        attachment_paths = []

        for idx, (att_content, att_mimetype) in enumerate(zip(attachments, attachment_mimetypes)):
            att_ext = self._get_extension_from_mimetype(att_mimetype)
            att_filename = f"{filename_base}-att{idx + 1}.{att_ext}"
            att_path = directory / att_filename

            try:
                if self.config.atomic_writes:
                    write_atomically(att_path, att_content)
                else:
                    att_path.write_bytes(att_content)

                attachment_paths.append(att_filename)
                logger.debug(f"Wrote attachment to {att_path}")
            except Exception as e:
                raise WriteError(
                    f"Failed to write attachment {att_filename}: {e}",
                    recovery_hint="Check filesystem permissions and disk space"
                ) from e

        return attachment_paths

    def _write_content_and_metadata(
        self,
        directory: Path,
        filename_base: str,
        content: bytes,
        builder: MetadataBuilder,
        document_id: str,
        content_hash: str,
        mimetype: str,
        origin: dict[str, Any],
        created_at: datetime,
        document_type: str,
        document_subtype: str | None,
        attachment_paths: list[str],
        tags: list[str] | None,
        relationships: list[dict] | None,
        extension: str
    ) -> tuple[Path, Path]:
        """Write content file and metadata file atomically.

        Args:
            directory: Directory to write to
            filename_base: Base filename without extension
            content: Content bytes
            builder: MetadataBuilder instance
            document_id: Document ID
            content_hash: Content hash
            mimetype: MIME type
            origin: Origin metadata
            created_at: Creation timestamp
            document_type: Document type
            document_subtype: Document subtype
            attachment_paths: List of attachment paths
            tags: List of tags
            relationships: List of relationships
            extension: File extension without dot

        Returns:
            Tuple of (content_path, metadata_path)

        Raises:
            WriteError: If write operation fails
            ValidationError: If metadata validation fails
        """
        # Build paths with provided extension
        content_filename = f"{filename_base}.{extension}"
        metadata_filename = f"{filename_base}.json"

        content_path = directory / content_filename
        metadata_path = directory / metadata_filename

        # Handle collisions
        if content_path.exists() or metadata_path.exists():
            content_path, metadata_path = self._handle_collision(
                directory, filename_base, extension
            )
            content_filename = content_path.name
            metadata_filename = metadata_path.name

        # Build metadata
        metadata_dict = builder.build(
            document_id=document_id,
            content_path=content_filename,
            content_hash=content_hash,
            content_size=len(content),
            mimetype=mimetype,
            origin=origin,
            created_at=created_at,
            document_type=document_type,
            document_subtype=document_subtype,
            attachments=attachment_paths,
            tags=tags,
            relationships=relationships
        )

        # Validate metadata
        try:
            validate_metadata(metadata_dict)
        except Exception as e:
            raise ValidationError(
                f"Metadata validation failed: {e}",
                recovery_hint="Check metadata fields match schema"
            ) from e

        # Write files
        try:
            # Write content
            if self.config.atomic_writes:
                write_atomically(content_path, content)
            else:
                content_path.write_bytes(content)

            # Write metadata
            metadata_json = json.dumps(metadata_dict, indent=2, default=str)
            if self.config.atomic_writes:
                write_atomically(metadata_path, metadata_json.encode('utf-8'))
            else:
                metadata_path.write_text(metadata_json, encoding='utf-8')

            logger.debug(f"Wrote content to {content_path}")
            logger.debug(f"Wrote metadata to {metadata_path}")

        except Exception as e:
            # Clean up partial writes
            for path in [content_path, metadata_path]:
                if path.exists():
                    try:
                        path.unlink()
                    except:
                        pass
            raise WriteError(
                f"Failed to write files: {e}",
                recovery_hint="Check filesystem permissions and disk space"
            ) from e

        return content_path, metadata_path

    def _handle_collision(
        self, directory: Path, filename_base: str, extension: str
    ) -> tuple[Path, Path]:
        """Handle filename collision by adding suffix.

        Args:
            directory: Directory containing files
            filename_base: Base filename
            extension: File extension

        Returns:
            Tuple of (content_path, metadata_path) with unique names

        Raises:
            WriteError: If unable to find unique filename after many attempts
        """
        for i in range(1, 1000):
            new_base = f"{filename_base}-{i}"
            content_path = directory / f"{new_base}.{extension}"
            metadata_path = directory / f"{new_base}.json"

            if not content_path.exists() and not metadata_path.exists():
                logger.warning(f"Collision detected, using {new_base}")
                return content_path, metadata_path

        raise WriteError(
            f"Unable to resolve filename collision for {filename_base}",
            recovery_hint="Check for excessive duplicate documents"
        )

    def _append_to_manifest(
        self, directory: Path, metadata_path: Path, document_id: str
    ) -> None:
        """Append entry to manifest.jsonl file.

        Args:
            directory: Directory containing manifest
            metadata_path: Path to metadata file
            document_id: Document ID

        Raises:
            WriteError: If manifest write fails
        """
        manifest_path = directory / "manifest.jsonl"

        entry = {
            "document_id": document_id,
            "metadata_path": metadata_path.name,
            "timestamp": datetime.now().isoformat()
        }

        try:
            # Append to manifest (create if doesn't exist)
            with open(manifest_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')

            logger.debug(f"Appended to manifest: {manifest_path}")
        except Exception as e:
            raise WriteError(
                f"Failed to write manifest: {e}",
                recovery_hint="Check filesystem permissions"
            ) from e
