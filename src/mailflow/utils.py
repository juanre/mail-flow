# ABOUTME: Common utility functions for atomic file operations and JSON handling
# ABOUTME: Provides file locking, safe writes, hashing, and retry logic with backoff
"""Utility functions for mailflow"""

import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from mailflow.exceptions import DataError

logger = logging.getLogger(__name__)


def atomic_write(filepath: Path, content: str, mode: str = "w") -> None:
    """
    Write file atomically to prevent data corruption.

    Args:
        filepath: Target file path
        content: Content to write
        mode: File mode ('w' or 'wb')

    Raises:
        DataError: If write fails
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory (for same filesystem)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=filepath.parent, prefix=f".{filepath.name}.", suffix=".tmp"
    )

    try:
        # Write to temp file
        with os.fdopen(temp_fd, mode) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk

        # Atomic rename
        os.replace(temp_path, filepath)

    except Exception as e:
        # Clean up temp file on error
        with suppress(OSError):
            os.unlink(temp_path)
        raise DataError(
            f"Failed to write {filepath}: {e}",
            recovery_hint="Check disk space and permissions",
        )


def atomic_json_write(filepath: Path, data: Any, **json_kwargs) -> None:
    """
    Write JSON file atomically.

    Args:
        filepath: Target file path
        data: Data to serialize to JSON
        **json_kwargs: Additional arguments for json.dump
    """
    json_kwargs.setdefault("indent", 2)
    json_kwargs.setdefault("sort_keys", True)

    content = json.dumps(data, **json_kwargs)
    atomic_write(filepath, content)


def safe_json_load(filepath: Path, default: Any = None) -> Any:
    """
    Load JSON file with validation and error handling.

    Args:
        filepath: JSON file path
        default: Default value if file doesn't exist or is invalid

    Returns:
        Loaded data or default value
    """
    if not filepath.exists():
        return default

    try:
        with open(filepath) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        # Create backup of corrupted file
        backup_path = filepath.with_suffix(f".corrupted.{int(time.time())}")
        filepath.rename(backup_path)
        logger.info(f"Corrupted file backed up to {backup_path}")
        return default
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return default


@contextmanager
def file_lock(filepath: Path, timeout: float = 10.0):
    """
    Context manager for file locking.

    Args:
        filepath: File to lock
        timeout: Maximum time to wait for lock

    Yields:
        None

    Raises:
        DataError: If lock cannot be acquired
    """
    lock_path = filepath.with_suffix(filepath.suffix + ".lock")
    lock_file = None
    start_time = time.time()

    try:
        while True:
            try:
                # Try to create lock file exclusively
                lock_file = open(lock_path, "x")
                break
            except FileExistsError:
                # Lock exists, check timeout
                if time.time() - start_time > timeout:
                    raise DataError(
                        f"Could not acquire lock for {filepath}",
                        recovery_hint="Another process may be using this file",
                    )
                time.sleep(0.1)

        # Write PID to lock file for debugging
        lock_file.write(str(os.getpid()))
        lock_file.flush()

        yield

    finally:
        # Release lock
        if lock_file:
            lock_file.close()
            with suppress(OSError):
                lock_path.unlink()


def calculate_file_hash(filepath: Path, algorithm: str = "sha256") -> str:
    """
    Calculate hash of file contents.

    Args:
        filepath: File to hash
        algorithm: Hash algorithm to use

    Returns:
        Hex digest of file hash
    """
    hash_func = hashlib.new(algorithm)

    with open(filepath, "rb") as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(65536), b""):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate string to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text

    if max_length <= len(suffix):
        return text[:max_length]

    return text[: max_length - len(suffix)] + suffix


def retry_operation(
    operation: Callable,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Any:
    """
    Retry an operation with exponential backoff.

    Args:
        operation: Function to retry
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts
        backoff: Backoff multiplier
        exceptions: Tuple of exceptions to catch

    Returns:
        Result of successful operation

    Raises:
        Last exception if all attempts fail
    """
    last_exception = None
    current_delay = delay

    for attempt in range(max_attempts):
        try:
            return operation()
        except exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. " f"Retrying in {current_delay:.1f}s..."
                )
                time.sleep(current_delay)
                current_delay *= backoff
            else:
                logger.error(f"All {max_attempts} attempts failed")

    raise last_exception
