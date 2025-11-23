# ABOUTME: Configuration management for archive-protocol
# ABOUTME: Defines RepositoryConfig with base paths and behavior settings

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepositoryConfig:
    """Configuration for repository writer operations."""

    base_path: str = "~/Archive"
    create_directories: bool = True
    atomic_writes: bool = True
    compute_hashes: bool = True
    hash_algorithm: str = "sha256"

    @classmethod
    def from_env(cls) -> "RepositoryConfig":
        """Create config from environment variables."""
        return cls(
            base_path=os.environ.get("ARCHIVE_BASE_PATH", "~/Archive"),
        )

    def resolve_base_path(self) -> Path:
        """Resolve and expand base path."""
        return Path(self.base_path).expanduser().resolve()

    # Global indexes are managed by consumers; writer does not manage indexes paths.
