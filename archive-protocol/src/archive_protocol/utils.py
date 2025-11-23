# ABOUTME: Utility functions for filename sanitization and content hashing
# ABOUTME: Provides SHA-256 hashing, safe filename generation, and atomic writes

import hashlib
import os
import re
from pathlib import Path


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize filename to be filesystem-safe.

    Removes path components, dangerous characters, and limits length.
    """
    # Remove path components
    filename = os.path.basename(filename)

    # Replace dangerous characters
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '-', filename)
    filename = filename.replace('/', '-').replace('\\', '-')

    # Collapse multiple hyphens/spaces
    filename = re.sub(r'[-\s]+', '-', filename)

    # Remove leading/trailing hyphens/dots
    filename = filename.strip('.-')

    # Ensure not empty
    if not filename:
        filename = "unnamed"

    # Limit length while preserving extension
    stem, ext = os.path.splitext(filename)
    if len(filename) > max_length:
        stem = stem[:max_length - len(ext) - 1]
        filename = stem + ext

    return filename


def normalize_name_base(name: str, max_length: int = 120) -> str:
    """Normalize a name for use in content filenames (basename without extension).

    Rules:
    - lowercase
    - replace whitespace with '-'
    - keep only [a-z0-9._-]
    - collapse multiple dashes
    - trim leading/trailing dashes/underscores/dots
    - limit length
    """
    if not name:
        return "document"

    name = name.strip().lower()
    # Replace whitespace with dash
    name = re.sub(r"\s+", "-", name)
    # Keep safe characters only
    name = re.sub(r"[^a-z0-9._-]", "-", name)
    # Collapse multiple dashes/underscores/dots combos
    name = re.sub(r"[-_\.]{2,}", "-", name)
    # Strip leading/trailing separators
    name = name.strip("-_.")
    if not name:
        name = "document"
    if len(name) > max_length:
        name = name[:max_length]
    return name


def compute_hash(content: bytes) -> str:
    """Compute SHA-256 hash of content.

    Returns:
        Hash in format "sha256:hexdigest"
    """
    hash_obj = hashlib.sha256(content)
    return f"sha256:{hash_obj.hexdigest()}"


def write_atomically(path: Path, content: bytes) -> None:
    """Write file atomically with fsync.

    Uses temp file + fsync + rename for atomic operation.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

    temp_file = path.parent / f".tmp_{path.name}_{os.getpid()}"
    try:
        with open(temp_file, "xb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        temp_file.rename(path)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except:
                pass
