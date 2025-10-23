import datetime
import logging
import os
from pathlib import Path
from typing import Any

from mailflow.attachment_handler import save_attachments_from_message
from mailflow.exceptions import WorkflowError
from mailflow.pdf_converter import save_email_as_pdf
from mailflow.security import validate_path

logger = logging.getLogger(__name__)


def save_attachment(
    message: dict[str, Any],
    directory: str,
    pattern: str = "*.pdf",
    use_year_dirs: bool = True,
    store_metadata: bool = True,
):
    """Save attachments matching pattern to directory"""
    try:
        # Get the Message object if available
        message_obj = message.get("_message_obj")

        if not message_obj:
            # Fallback to old behavior if no Message object
            logger.warning("No Message object available for attachment extraction")
            print("\n⚠️  Attachment extraction requires the full email object")
            return

        # Use the attachment handler to save attachments
        saved_count = save_attachments_from_message(
            message_obj=message_obj,
            email_data=message,
            directory=directory,
            pattern=pattern,
            use_year_dirs=use_year_dirs,
            store_metadata=store_metadata,
        )

        if saved_count == 0:
            print(f"\n  ℹ️  No attachments matching '{pattern}' found")
        else:
            print(f"\n✓ Saved {saved_count} attachment(s) to {directory}")

    except Exception as e:
        raise WorkflowError(
            f"Failed to save attachments: {e}",
            recovery_hint="Check directory permissions and path",
        )


def create_todo(message: dict[str, Any], todo_file: str = "~/todos.txt"):
    """Create a todo item from the email"""
    try:
        # Validate todo file path - allow the provided path as base
        todo_path = validate_path(
            todo_file,
            allowed_base_dirs=[os.path.expanduser("~"), str(Path(todo_file).parent)],
        )
        todo_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract todo information safely
        from_addr = message.get("from", "Unknown")[:200]  # Limit length
        subject = message.get("subject", "No subject")[:500]  # Limit length
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        message_id = message.get("message_id", "")[:100]

        # Create todo entry
        todo_entry = f"[ ] {date} - Email from {from_addr}: {subject}\n"

        # Append to file
        with open(todo_path, "a", encoding="utf-8") as f:
            f.write(todo_entry)

        print(f"\n✓ Added todo to {todo_path}:")
        print(f"  {todo_entry.strip()}")

        if message_id:
            print(f"\nMessage ID: {message_id}")

        logger.info(f"Created todo for message {message_id}")

    except Exception as e:
        raise WorkflowError(
            f"Failed to create todo: {e}",
            recovery_hint="Check file permissions and path",
        )


def save_email_pdf(
    message: dict[str, Any],
    directory: str = "~/receipts",
    filename_template: str = "{date}-{from}-{subject}.pdf",
    use_year_dirs: bool = True,
    store_metadata: bool = True,
):
    """Save the entire email as a PDF file

    Note: Requires Playwright browsers: playwright install chromium

    Args:
        message: Email data
        directory: Where to save PDFs
        filename_template: Template for filename
        use_year_dirs: Whether to create year subdirectories
        store_metadata: Whether to store metadata in SQLite
    """
    try:
        # Get the Message object if available
        message_obj = message.get("_message_obj")

        # Use the PDF converter
        save_email_as_pdf(
            email_data=message,
            message_obj=message_obj,
            directory=directory,
            filename_template=filename_template,
            use_year_dirs=use_year_dirs,
            store_metadata=store_metadata,
        )

    except Exception as e:
        raise WorkflowError(
            f"Failed to save email as PDF: {e}",
            recovery_hint="Check if Playwright is installed: 'playwright install chromium'",
        )


def save_pdf(
    message: dict[str, Any],
    directory: str,
    filename_template: str = "{date}-{from}-{subject}",
    use_year_dirs: bool = True,
    store_metadata: bool = True,
):
    """Save PDF: extracts PDF attachment if exists, otherwise converts email to PDF

    This is a generic PDF saving function that:
    1. Checks if email has PDF attachments
    2. If yes: saves the PDF attachment(s) with their original names
    3. If no: converts the email itself to PDF using the filename template

    Args:
        message: Email data
        directory: Where to save PDFs
        filename_template: Template for email PDF (attachments keep original names)
    """
    try:
        # Check if we have PDF attachments
        pdf_attachments = [
            att
            for att in message.get("attachments", [])
            if att.get("filename", "").lower().endswith(".pdf")
        ]

        if pdf_attachments:
            # Has PDF attachments - save them
            print(f"  ℹ️  Found {len(pdf_attachments)} PDF attachment(s)")
            save_attachment(
                message,
                directory=directory,
                pattern="*.pdf",
                use_year_dirs=use_year_dirs,
                store_metadata=store_metadata,
            )
        else:
            # No PDF attachments - convert email to PDF
            print("  ℹ️  No PDF attachments found, converting email to PDF")
            # Ensure template doesn't already end with .pdf
            if not filename_template.endswith(".pdf"):
                filename_template = filename_template + ".pdf"
            save_email_pdf(
                message,
                directory=directory,
                filename_template=filename_template,
                use_year_dirs=use_year_dirs,
                store_metadata=store_metadata,
            )

    except Exception as e:
        raise WorkflowError(
            f"Failed to save PDF: {e}",
            recovery_hint="Check directory permissions and Playwright installation",
        )


# Action type mapping - maps action types to functions
Workflows = {
    "save_attachment": save_attachment,
    "save_email_as_pdf": save_email_pdf,
    "save_pdf": save_pdf,
    "create_todo": create_todo,
}


# Note: The old Criteria and Rules classes have been moved to models.py
# as CriteriaInstance and DataStore for better organization
