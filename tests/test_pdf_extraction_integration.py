"""Integration tests for PDF extraction from real emails using docflow-archive workflows."""

from pathlib import Path

import pytest

from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_attachment, save_email_pdf


class TestPDFExtractionIntegration:
    @pytest.fixture
    def cloudflare_email(self):
        """Load the Cloudflare invoice email with PDF attachment."""
        email_path = Path(__file__).parent / "res" / "cloudflare_invoice.eml"
        with open(email_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @pytest.fixture
    def amazon_email(self):
        """Load the Amazon invoice email."""
        email_path = Path(__file__).parent / "res" / "amazon_invoice.eml"
        with open(email_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def test_extract_pdf_from_cloudflare_email(self, temp_config_with_llmemory, cloudflare_email):
        """Test extracting and saving PDF attachment from real Cloudflare email using docflow-archive."""
        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(cloudflare_email)

        # Verify email was parsed correctly
        assert "cloudflare.com" in email_data["from"]
        assert "cloudflare" in email_data["subject"].lower()
        assert email_data["_message_obj"] is not None

        # Check attachments were detected
        assert len(email_data["attachments"]) > 0
        pdf_attachments = [
            att for att in email_data["attachments"] if att["filename"].endswith(".pdf")
        ]
        assert len(pdf_attachments) == 1
        assert pdf_attachments[0]["filename"] == "cloudflare-invoice-2025-02-26.pdf"

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Save the PDF attachment using docflow-archive workflow
        result = save_attachment(
            message=email_data,
            workflow="cloudflare-invoice",
            config=config,
            entity="acme",
            directory="invoice",
            pattern="*.pdf"
        )

        assert result["success"]
        assert result["count"] == 1
        assert len(result["documents"]) == 1

        # Verify PDF was saved
        content_path = Path(result["documents"][0]["content_path"])
        assert content_path.exists()
        assert content_path.name.endswith(".pdf")

        # Verify it's a valid PDF by checking header
        with open(content_path, "rb") as f:
            header = f.read(4)
            assert header == b"%PDF"

        # Check metadata was stored
        metadata_path = Path(result["documents"][0]["metadata_path"])
        assert metadata_path.exists()

    def test_save_email_without_pdf_attachment_as_pdf(self, temp_config_with_llmemory, amazon_email):
        """Test converting email without PDF attachment to PDF using docflow-archive."""
        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(amazon_email)

        # Check no PDF attachments
        pdf_attachments = [
            att for att in email_data.get("attachments", []) if att["filename"].endswith(".pdf")
        ]
        assert len(pdf_attachments) == 0

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Convert email to PDF using docflow-archive workflow
        result = save_email_pdf(
            message=email_data,
            workflow="amazon-receipt",
            config=config,
            entity="acme",
            directory="receipt",
        )

        assert result["success"]
        assert "document_id" in result

        # Verify PDF was created
        content_path = Path(result["content_path"])
        assert content_path.exists()
        assert content_path.suffix == ".pdf"
        assert content_path.stat().st_size > 1000

        # Verify it's a valid PDF
        with open(content_path, "rb") as f:
            header = f.read(4)
            assert header == b"%PDF"

        # Check metadata was stored
        metadata_path = Path(result["metadata_path"])
        assert metadata_path.exists()

    def test_workflow_saves_multiple_pdf_attachments(self, temp_config_with_llmemory):
        """Test saving multiple PDF attachments from a single email."""
        from email.mime.base import MIMEBase
        from email.mime.multipart import MIMEMultipart
        from email import encoders

        # Create test email with multiple PDFs
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"
        msg["Subject"] = "Multiple invoices"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"
        msg["Message-ID"] = "<multi-invoice@example.com>"

        # Add three PDF attachments
        for i in range(3):
            pdf_att = MIMEBase("application", "pdf")
            pdf_content = f"%PDF-1.4\nInvoice {i+1}\n".encode()
            pdf_att.set_payload(pdf_content)
            encoders.encode_base64(pdf_att)
            pdf_att.add_header("Content-Disposition", f'attachment; filename="invoice_{i+1}.pdf"')
            msg.attach(pdf_att)

        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Save all PDF attachments
        result = save_attachment(
            message=email_data,
            workflow="multi-invoice",
            config=config,
            entity="acme",
            directory="invoice",
            pattern="*.pdf"
        )

        assert result["success"]
        assert result["count"] == 3
        assert len(result["documents"]) == 3

        # Verify all PDFs were saved
        for doc in result["documents"]:
            content_path = Path(doc["content_path"])
            assert content_path.exists()
            assert content_path.suffix == ".pdf"

    def test_workflow_with_pattern_filtering(self, temp_config_with_llmemory):
        """Test that pattern filtering works with docflow-archive workflows."""
        from email.mime.base import MIMEBase
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email import encoders

        # Create test email with mixed attachments
        msg = MIMEMultipart()
        msg["From"] = "sender@example.com"
        msg["Subject"] = "Mixed attachments"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"
        msg["Message-ID"] = "<mixed@example.com>"

        # Add PDF
        pdf_att = MIMEBase("application", "pdf")
        pdf_att.set_payload(b"%PDF-1.4\nPDF content")
        encoders.encode_base64(pdf_att)
        pdf_att.add_header("Content-Disposition", 'attachment; filename="document.pdf"')
        msg.attach(pdf_att)

        # Add text file
        text_att = MIMEText("Text content")
        text_att.add_header("Content-Disposition", 'attachment; filename="notes.txt"')
        msg.attach(text_att)

        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Save only PDFs
        result = save_attachment(
            message=email_data,
            workflow="pdf-only",
            config=config,
            entity="acme",
            directory="docs",
            pattern="*.pdf"
        )

        # Should save only the PDF, not the text file
        assert result["success"]
        assert result["count"] == 1
        assert result["documents"][0]["filename"] == "document.pdf"
