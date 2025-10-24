# ABOUTME: Workflow action implementations for mailflow email processing.
# ABOUTME: Provides functions to save attachments, create PDFs, and generate todos from emails.
import datetime
import logging
import os
from pathlib import Path
from typing import Any

from mailflow.attachment_handler import extract_attachments
from mailflow.exceptions import WorkflowError
from mailflow.pdf_converter import email_to_pdf_bytes
from mailflow.security import validate_path

logger = logging.getLogger(__name__)


def save_attachment(
    message: dict[str, Any],
    workflow: str,
    config,
    pattern: str = "*.*"
) -> dict:
    """Save attachments matching pattern using archive-protocol

    Args:
        message: Email data
        workflow: Workflow name (e.g., "jro-invoice")
        config: Config object
        pattern: Pattern for attachment matching (default: "*.*")

    Returns:
        dict with success status and saved documents
    """
    try:
        from archive_protocol import RepositoryWriter, RepositoryConfig
        from mailflow.utils import parse_entity_from_workflow

        entity = parse_entity_from_workflow(workflow)

        archive_config = RepositoryConfig(
            base_path=config.settings["archive"]["base_path"]
        )

        writer = RepositoryWriter(
            config=archive_config,
            entity=entity,
            source="mail"
        )

        message_obj = message.get("_message_obj")
        if not message_obj:
            raise WorkflowError("Message object not available for attachment extraction")

        # Extract attachments matching pattern
        attachments = extract_attachments(message_obj, pattern=pattern)

        if not attachments:
            logger.info(f"No attachments matching '{pattern}' found")
            return {
                "success": True,
                "count": 0,
                "documents": []
            }

        # Save each attachment
        results = []
        for filename, content, mimetype in attachments:
            document_id, content_path, metadata_path = writer.write_document(
                workflow=workflow,
                content=content,
                mimetype=mimetype,
                origin={
                    "message_id": message.get("message_id"),
                    "subject": message.get("subject"),
                    "from": message.get("from"),
                    "to": message.get("to"),
                    "date": message.get("date"),
                    "attachment_filename": filename
                },
                document_type="attachment",
                original_filename=filename
            )
            logger.info(f"Saved attachment {filename} to {content_path}")
            results.append({
                "document_id": document_id,
                "content_path": str(content_path),
                "metadata_path": str(metadata_path),
                "filename": filename
            })

        logger.info(f"Saved {len(results)} attachment(s)")
        return {
            "success": True,
            "count": len(results),
            "documents": results
        }

    except Exception as e:
        raise WorkflowError(
            f"Failed to save attachments: {e}",
            recovery_hint="Check archive configuration and pattern",
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

        # Determine format based on file extension
        file_ext = todo_path.suffix.lower()
        if file_ext in [".org", ".orgmode"]:
            # Orgmode format
            todo_entry = f"* TODO {date} - Email from {from_addr}: {subject}\n"
        else:
            # Markdown format (default)
            todo_entry = f"[ ] {date} - Email from {from_addr}: {subject}\n"

        # Append to file
        with open(todo_path, "a", encoding="utf-8") as f:
            f.write(todo_entry)

        logger.info(f"Created todo for message {message_id} at {todo_path}: {todo_entry.strip()}")

    except Exception as e:
        raise WorkflowError(
            f"Failed to create todo: {e}",
            recovery_hint="Check file permissions and path",
        )


def save_email_pdf(
    message: dict[str, Any],
    workflow: str,
    config
) -> dict:
    """Save the entire email as a PDF file using archive-protocol

    Note: Requires Playwright browsers: playwright install chromium

    Args:
        message: Email data
        workflow: Workflow name (e.g., "jro-receipt")
        config: Config object

    Returns:
        dict with document_id, content_path, success status
    """
    try:
        from archive_protocol import RepositoryWriter, RepositoryConfig
        from mailflow.utils import parse_entity_from_workflow

        entity = parse_entity_from_workflow(workflow)

        archive_config = RepositoryConfig(
            base_path=config.settings["archive"]["base_path"]
        )

        writer = RepositoryWriter(
            config=archive_config,
            entity=entity,
            source="mail"
        )

        message_obj = message.get("_message_obj")
        if not message_obj:
            raise WorkflowError("Message object not available for PDF conversion")

        # Convert email to PDF
        pdf_bytes = email_to_pdf_bytes(message_obj, message)

        document_id, content_path, metadata_path = writer.write_document(
            workflow=workflow,
            content=pdf_bytes,
            mimetype="application/pdf",
            origin={
                "message_id": message.get("message_id"),
                "subject": message.get("subject"),
                "from": message.get("from"),
                "to": message.get("to"),
                "date": message.get("date"),
                "converted_from_email": True
            },
            document_type="email",
            original_filename=f"{message.get('subject', 'email')}.pdf"
        )
        logger.info(f"Converted email to PDF at {content_path}")

        return {
            "success": True,
            "document_id": document_id,
            "content_path": str(content_path),
            "metadata_path": str(metadata_path)
        }

    except Exception as e:
        raise WorkflowError(
            f"Failed to save email as PDF: {e}",
            recovery_hint="Check if Playwright is installed: 'playwright install chromium'",
        )


def save_pdf(
    message: dict[str, Any],
    workflow: str,
    config,
    pattern: str = "*.pdf"
) -> dict:
    """Save PDF: extracts PDF attachment if exists, otherwise converts email to PDF

    This is a generic PDF saving function that:
    1. Checks if email has PDF attachments
    2. If yes: saves the PDF attachment(s) with their original names
    3. If no: converts the email itself to PDF using the filename template

    Args:
        message: Email data
        workflow: Workflow name (e.g., "jro-expense")
        config: Config object
        pattern: Pattern for attachment matching (default: "*.pdf")

    Returns:
        dict with document_id, content_path, success status
    """
    try:
        from archive_protocol import RepositoryWriter, RepositoryConfig
        from mailflow.utils import parse_entity_from_workflow

        entity = parse_entity_from_workflow(workflow)

        archive_config = RepositoryConfig(
            base_path=config.settings["archive"]["base_path"]
        )

        writer = RepositoryWriter(
            config=archive_config,
            entity=entity,
            source="mail"
        )

        message_obj = message.get("_message_obj")
        if not message_obj:
            raise WorkflowError("Message object not available for PDF extraction")

        # Try to find PDF attachments first
        pdf_attachments = extract_attachments(message_obj, pattern="*.pdf")

        if pdf_attachments:
            # Save PDF attachments
            logger.info(f"Found {len(pdf_attachments)} PDF attachment(s)")
            results = []
            for filename, content, mimetype in pdf_attachments:
                document_id, content_path, metadata_path = writer.write_document(
                    workflow=workflow,
                    content=content,
                    mimetype=mimetype,
                    origin={
                        "message_id": message.get("message_id"),
                        "subject": message.get("subject"),
                        "from": message.get("from"),
                        "to": message.get("to"),
                        "date": message.get("date"),
                        "attachment_filename": filename
                    },
                    document_type="document",
                    original_filename=filename
                )
                logger.info(f"Saved PDF attachment to {content_path}")
                results.append({
                    "document_id": document_id,
                    "content_path": str(content_path),
                    "metadata_path": str(metadata_path),
                    "filename": filename
                })

            return {
                "success": True,
                "count": len(results),
                "documents": results
            }
        else:
            # Convert email to PDF
            logger.info("No PDF attachments found, converting email to PDF")
            pdf_bytes = email_to_pdf_bytes(message_obj, message)

            document_id, content_path, metadata_path = writer.write_document(
                workflow=workflow,
                content=pdf_bytes,
                mimetype="application/pdf",
                origin={
                    "message_id": message.get("message_id"),
                    "subject": message.get("subject"),
                    "from": message.get("from"),
                    "to": message.get("to"),
                    "date": message.get("date"),
                    "converted_from_email": True
                },
                document_type="email",
                original_filename=f"{message.get('subject', 'email')}.pdf"
            )
            logger.info(f"Converted email to PDF at {content_path}")

            return {
                "success": True,
                "document_id": document_id,
                "content_path": str(content_path),
                "metadata_path": str(metadata_path)
            }

    except Exception as e:
        raise WorkflowError(
            f"Failed to save PDF: {e}",
            recovery_hint="Check archive configuration and Playwright installation",
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
