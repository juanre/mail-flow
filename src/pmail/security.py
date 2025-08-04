"""Security utilities for input validation and sanitization"""

import os
import re
import pathlib
from typing import Optional, List
from pathlib import Path


class SecurityError(Exception):
    """Base exception for security violations"""

    pass


class PathSecurityError(SecurityError):
    """Path validation failed"""

    pass


class InputValidationError(SecurityError):
    """Input validation failed"""

    pass


def validate_path(user_path: str, allowed_base_dirs: Optional[List[str]] = None) -> Path:
    """
    Validate and sanitize user-provided paths.

    Args:
        user_path: User-provided path string
        allowed_base_dirs: List of allowed base directories. If None, defaults to user's home

    Returns:
        Validated Path object

    Raises:
        PathSecurityError: If path is invalid or outside allowed directories
    """
    if not user_path:
        raise PathSecurityError("Empty path provided")

    # Check for suspicious patterns
    suspicious_patterns = [
        "..",  # Path traversal
        "\x00",  # Null bytes
        "|",
        "&",
        ";",
        "$",
        "`",  # Shell metacharacters
        "\n",
        "\r",  # Newlines
    ]

    for pattern in suspicious_patterns:
        if pattern in user_path:
            raise PathSecurityError(f"Suspicious pattern '{pattern}' in path")

    # Expand user home directory
    expanded = os.path.expanduser(user_path)

    # Resolve to absolute path
    try:
        resolved = Path(expanded).resolve()
    except (OSError, RuntimeError) as e:
        raise PathSecurityError(f"Invalid path: {e}")

    # Set default allowed directories
    if allowed_base_dirs is None:
        allowed_base_dirs = [os.path.expanduser("~")]

    # Check if path is under allowed directories
    allowed = False
    for base_dir in allowed_base_dirs:
        base = Path(base_dir).resolve()
        try:
            resolved.relative_to(base)
            allowed = True
            break
        except ValueError:
            continue

    if not allowed:
        raise PathSecurityError(f"Path '{user_path}' is outside allowed directories")

    return resolved


def validate_email_address(email: str) -> str:
    """
    Validate and sanitize email address.

    Args:
        email: Email address string

    Returns:
        Sanitized email address

    Raises:
        InputValidationError: If email is invalid
    """
    if not email:
        return ""

    # Basic email regex (simplified)
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    # Extract email from "Name <email@domain>" format
    match = re.search(r"<([^>]+)>", email)
    if match:
        email_part = match.group(1)
    else:
        email_part = email.strip()

    if not re.match(email_pattern, email_part):
        # Don't reveal the exact email in error message
        raise InputValidationError("Invalid email address format")

    return email_part


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file operations.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"

    # Remove path components
    filename = os.path.basename(filename)

    # Replace dangerous characters
    safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

    # Limit length
    max_length = 255
    if len(safe_filename) > max_length:
        name, ext = os.path.splitext(safe_filename)
        safe_filename = name[: max_length - len(ext)] + ext

    # Don't allow hidden files
    if safe_filename.startswith("."):
        safe_filename = "_" + safe_filename[1:]

    return safe_filename


def sanitize_shell_arg(arg: str) -> str:
    """
    Sanitize argument for shell display (NOT for execution).

    Args:
        arg: Argument to sanitize

    Returns:
        Sanitized argument safe for display
    """
    # This is only for display purposes
    # NEVER use this for actual shell execution
    return re.sub(r"[^a-zA-Z0-9._@/-]", "_", arg)


def validate_json_size(json_path: Path, max_size_mb: int = 10) -> None:
    """
    Check if JSON file is within size limits.

    Args:
        json_path: Path to JSON file
        max_size_mb: Maximum size in megabytes

    Raises:
        InputValidationError: If file is too large
    """
    if not json_path.exists():
        return

    size_bytes = json_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)

    if size_mb > max_size_mb:
        raise InputValidationError(f"File too large: {size_mb:.1f}MB (max: {max_size_mb}MB)")


def validate_message_id(message_id: str) -> str:
    """
    Validate and sanitize message ID.

    Args:
        message_id: Email message ID

    Returns:
        Sanitized message ID
    """
    if not message_id:
        return ""

    # Message IDs should only contain certain characters
    sanitized = re.sub(r"[^a-zA-Z0-9@._-]", "", message_id)

    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]

    return sanitized


# Constants for limits
MAX_EMAIL_SIZE_MB = 25
MAX_SUBJECT_LENGTH = 500
MAX_BODY_PREVIEW_LENGTH = 10000
MAX_ATTACHMENT_COUNT = 100
