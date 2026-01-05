# ABOUTME: Handles extraction of email attachments as bytes for docflow-archive workflows.
# ABOUTME: Supports pattern matching and returns attachment data in-memory without filesystem operations.
"""Attachment extraction handler for mailflow"""

import logging
from email.message import Message

logger = logging.getLogger(__name__)


def extract_attachments(message_obj: Message, pattern: str = "*") -> list[tuple[str, bytes, str]]:
    """Extract attachments from email as bytes.

    Args:
        message_obj: Email message object
        pattern: File pattern to match (e.g., "*.pdf", "*.*")

    Returns:
        List of (filename, content_bytes, mimetype) tuples
    """
    import fnmatch

    attachments = []

    for part in message_obj.walk():
        if part.get_content_maintype() == "multipart":
            continue

        content_disposition = part.get("Content-Disposition", "")
        if "attachment" not in content_disposition:
            continue

        filename = part.get_filename()
        if not filename:
            continue

        # Pattern matching
        if not fnmatch.fnmatch(filename, pattern):
            continue

        # Get content
        payload = part.get_payload(decode=True)
        if not payload:
            continue

        # Get mimetype
        mimetype = part.get_content_type()

        attachments.append((filename, payload, mimetype))

    return attachments

