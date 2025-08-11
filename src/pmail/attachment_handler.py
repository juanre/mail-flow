"""Attachment extraction handler for pmail"""

import base64
import logging
import os
from email.message import Message
from pathlib import Path
from typing import Any, Dict, Optional

from pmail.exceptions import WorkflowError
from pmail.security import sanitize_filename, validate_path

logger = logging.getLogger(__name__)


def extract_and_save_attachment(part: Message, directory: Path, filename: str) -> Optional[Path]:
    """
    Extract and save a single attachment.

    Args:
        part: Email message part containing attachment
        directory: Directory to save to
        filename: Sanitized filename

    Returns:
        Path to saved file or None if failed
    """
    try:
        # Get the payload
        payload = part.get_payload(decode=True)
        if not payload:
            logger.warning(f"No payload found for attachment {filename}")
            return None

        # Create full path
        filepath = directory / filename

        # Check if file already exists
        if filepath.exists():
            # Add number to filename
            base = filepath.stem
            ext = filepath.suffix
            counter = 1
            while filepath.exists():
                filepath = directory / f"{base}_{counter}{ext}"
                counter += 1

        # Write the file
        with open(filepath, "wb") as f:
            f.write(payload)

        logger.info(f"Saved attachment: {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Failed to save attachment {filename}: {e}")
        return None


def save_attachments_from_message(
    message_obj: Message,
    email_data: Dict[str, Any],
    directory: str,
    pattern: str = "*.pdf",
    use_year_dirs: bool = True,
    store_metadata: bool = True,
) -> int:
    """
    Save attachments from email message object.

    Args:
        message_obj: Email message object
        email_data: Extracted email data with attachment info
        directory: Directory to save attachments
        pattern: File pattern to match
        use_year_dirs: Whether to create year subdirectories
        store_metadata: Whether to store metadata in SQLite

    Returns:
        Number of attachments saved
    """
    try:
        from datetime import datetime

        # Validate directory - allow the provided directory as base
        base_dir = validate_path(directory, allowed_base_dirs=[os.path.expanduser("~"), directory])

        # Parse email date for year-based organization
        email_date = None
        if use_year_dirs and email_data.get("date"):
            try:
                from email.utils import parsedate_to_datetime

                email_date = parsedate_to_datetime(email_data["date"])
            except Exception as e:
                logger.warning(f"Could not parse email date: {e}")

        if not email_date:
            email_date = datetime.now()

        # Create year directory if requested
        if use_year_dirs:
            dir_path = base_dir / str(email_date.year)
        else:
            dir_path = base_dir

        dir_path.mkdir(parents=True, exist_ok=True)

        saved_count = 0

        # We need the actual message object to extract attachments
        if not message_obj.is_multipart():
            logger.info("Email is not multipart, no attachments to extract")
            return 0

        for part in message_obj.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            # Use our pre-sanitized filename from email_data
            safe_filename = None
            for att_info in email_data.get("attachments", []):
                if att_info.get("original_filename") == filename:
                    safe_filename = att_info.get("filename")
                    break

            if not safe_filename:
                safe_filename = sanitize_filename(filename)

            # Check pattern match
            if pattern == "*.*":
                matches = True
            elif pattern.startswith("*."):
                ext = pattern[2:]
                matches = safe_filename.lower().endswith(f".{ext}")
            else:
                matches = safe_filename == pattern

            if matches:
                # Add date prefix to filename
                date_prefix = email_date.strftime("%Y-%m-%d")
                final_filename = f"{date_prefix}-{safe_filename}"

                saved_path = extract_and_save_attachment(part, dir_path, final_filename)
                if saved_path:
                    saved_count += 1
                    print(f"  ✓ Saved: {final_filename} to {saved_path}")

                    # Store metadata if requested
                    if store_metadata:
                        try:
                            from pmail.metadata_store import MetadataStore

                            store = MetadataStore(str(base_dir))

                            # Get suggested classification
                            doc_type, doc_category = MetadataStore.suggest_document_classification(
                                email_data
                            )

                            store.store_pdf_metadata(
                                pdf_path=saved_path,
                                email_data=email_data,
                                workflow_name=email_data.get("_workflow_name", "save_attachment"),
                                pdf_type="attachment",
                                confidence_score=email_data.get("_confidence_score"),
                                document_type=doc_type,
                                document_category=doc_category,
                            )
                        except Exception as e:
                            logger.warning(f"Failed to store metadata: {e}")

        return saved_count

    except Exception as e:
        raise WorkflowError(
            f"Failed to save attachments: {e}",
            recovery_hint="Check directory permissions and available disk space",
        )


# Note: To fully implement attachment saving, we would need to modify
# the process flow to pass the original Message object through to the
# workflow execution. Currently, we only pass the extracted data dictionary.
# This would require changes to the process.py and workflow.py files.
