"""Test attachment extraction functionality"""

import pytest
from pathlib import Path
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from pmail.attachment_handler import (
    extract_and_save_attachment,
    save_attachments_from_message,
)


class TestAttachmentHandler:
    def create_test_message_with_attachment(self):
        """Create a test email with PDF attachment"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test with attachment"

        # Add body
        body = MIMEText("This email has an attachment")
        msg.attach(body)

        # Add PDF attachment
        attachment = MIMEBase("application", "pdf")
        # Create fake PDF content
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        attachment.set_payload(pdf_content)
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", 'attachment; filename="test_document.pdf"')
        msg.attach(attachment)

        return msg, pdf_content

    def test_extract_and_save_attachment(self, temp_config_dir):
        """Test extracting and saving a single attachment"""
        msg, pdf_content = self.create_test_message_with_attachment()

        # Get the attachment part
        attachment_part = None
        for part in msg.walk():
            if part.get("Content-Disposition", "").startswith("attachment"):
                attachment_part = part
                break

        assert attachment_part is not None

        # Save attachment
        save_dir = Path(temp_config_dir) / "attachments"
        save_dir.mkdir()

        saved_path = extract_and_save_attachment(attachment_part, save_dir, "test_document.pdf")

        assert saved_path is not None
        assert saved_path.exists()
        assert saved_path.name == "test_document.pdf"

        # Verify content
        with open(saved_path, "rb") as f:
            saved_content = f.read()
        assert saved_content == pdf_content

    def test_extract_with_duplicate_filename(self, temp_config_dir):
        """Test handling duplicate filenames"""
        msg, pdf_content = self.create_test_message_with_attachment()

        # Get the attachment part
        attachment_part = None
        for part in msg.walk():
            if part.get("Content-Disposition", "").startswith("attachment"):
                attachment_part = part
                break

        save_dir = Path(temp_config_dir) / "attachments"
        save_dir.mkdir()

        # Save first time
        path1 = extract_and_save_attachment(attachment_part, save_dir, "test.pdf")

        # Save second time - should add number
        path2 = extract_and_save_attachment(attachment_part, save_dir, "test.pdf")

        assert path1.name == "test.pdf"
        assert path2.name == "test_1.pdf"
        assert path1.exists()
        assert path2.exists()

    def test_save_attachments_from_message_pdf_only(self, temp_config_dir):
        """Test saving only PDF attachments"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"
        msg["Subject"] = "Multiple attachments"

        # Add text attachment
        text_att = MIMEText("Text file content")
        text_att.add_header("Content-Disposition", 'attachment; filename="notes.txt"')
        msg.attach(text_att)

        # Add PDF attachment
        pdf_att = MIMEBase("application", "pdf")
        pdf_att.set_payload(b"%PDF-1.4\nfake pdf")
        pdf_att.add_header("Content-Disposition", 'attachment; filename="invoice.pdf"')
        msg.attach(pdf_att)

        # Email data with sanitized filenames
        email_data = {
            "attachments": [
                {"filename": "notes.txt", "original_filename": "notes.txt"},
                {"filename": "invoice.pdf", "original_filename": "invoice.pdf"},
            ]
        }

        save_dir = str(Path(temp_config_dir) / "pdfs")

        # Save only PDFs
        count = save_attachments_from_message(
            message_obj=msg, email_data=email_data, directory=save_dir, pattern="*.pdf"
        )

        assert count == 1
        saved_files = list(Path(save_dir).glob("*"))
        assert len(saved_files) == 1
        assert saved_files[0].name == "invoice.pdf"

    def test_save_attachments_all_files(self, temp_config_dir):
        """Test saving all attachments"""
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"

        # Add multiple attachments
        for filename, content in [
            ("doc1.pdf", b"PDF1"),
            ("image.jpg", b"JPG"),
            ("data.csv", b"CSV"),
        ]:
            att = MIMEBase("application", "octet-stream")
            att.set_payload(content)
            att.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(att)

        email_data = {
            "attachments": [
                {"filename": "doc1.pdf", "original_filename": "doc1.pdf"},
                {"filename": "image.jpg", "original_filename": "image.jpg"},
                {"filename": "data.csv", "original_filename": "data.csv"},
            ]
        }

        save_dir = str(Path(temp_config_dir) / "all")

        # Save all files
        count = save_attachments_from_message(
            message_obj=msg, email_data=email_data, directory=save_dir, pattern="*.*"
        )

        assert count == 3
        saved_files = list(Path(save_dir).glob("*"))
        assert len(saved_files) == 3

        filenames = {f.name for f in saved_files}
        assert filenames == {"doc1.pdf", "image.jpg", "data.csv"}

    def test_save_attachments_no_multipart(self, temp_config_dir):
        """Test handling non-multipart messages"""
        # Simple text email
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["Subject"] = "Plain text"
        msg.set_content("No attachments here")

        email_data = {"attachments": []}

        count = save_attachments_from_message(
            message_obj=msg,
            email_data=email_data,
            directory=temp_config_dir,
            pattern="*.pdf",
        )

        assert count == 0
