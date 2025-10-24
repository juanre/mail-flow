# ABOUTME: Public API exports for archive-protocol
# ABOUTME: Provides RepositoryWriter, metadata schema, and utilities for connectors

"""archive-protocol - Shared protocol for multi-source document archiving."""

__version__ = "0.1.0"

# Core classes
from archive_protocol.writer import RepositoryWriter
from archive_protocol.metadata import MetadataBuilder
from archive_protocol.config import RepositoryConfig

# Schema and validation
from archive_protocol.schema import (
    DocumentType,
    SourceType,
    DocumentMetadata,
    ContentMetadata,
    validate_metadata,
)

# Utilities
from archive_protocol.utils import (
    sanitize_filename,
    compute_hash,
    write_atomically,
)

# Exceptions
from archive_protocol.exceptions import (
    ArchiveError,
    ValidationError,
    WriteError,
    PathError,
)

__all__ = [
    # Core
    "RepositoryWriter",
    "MetadataBuilder",
    "RepositoryConfig",
    # Schema
    "DocumentType",
    "SourceType",
    "DocumentMetadata",
    "ContentMetadata",
    "validate_metadata",
    # Utilities
    "sanitize_filename",
    "compute_hash",
    "write_atomically",
    # Exceptions
    "ArchiveError",
    "ValidationError",
    "WriteError",
    "PathError",
    # Version
    "__version__",
]
