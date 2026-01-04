"""Test complete workflow integration with Message objects"""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import patch

from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_attachment, save_email_pdf


class TestWorkflowIntegration:
    def create_invoice_email(self):
        """Create a test invoice email with PDF attachment"""
        msg = MIMEMultipart()
        msg["From"] = "billing@company.com"
        msg["To"] = "customer@example.com"
        msg["Subject"] = "Invoice #12345 - January 2024"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"
        msg["Message-ID"] = "<invoice12345@company.com>"

        # HTML body
        html_body = """
        <html>
        <body>
            <h1>Invoice #12345</h1>
            <p>Dear Customer,</p>
            <p>Please find attached your invoice for January 2024.</p>
            <p>Amount due: $99.99</p>
        </body>
        </html>
        """

        # Add both plain text and HTML parts
        msg.attach(MIMEText("Invoice #12345\nAmount due: $99.99", "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Add PDF attachment
        pdf_att = MIMEBase("application", "pdf")
        pdf_content = b"%PDF-1.4\n%Fake PDF content for invoice\n"
        pdf_att.set_payload(pdf_content)
        encoders.encode_base64(pdf_att)
        pdf_att.add_header("Content-Disposition", 'attachment; filename="invoice_12345.pdf"')
        msg.attach(pdf_att)

        return msg.as_string()

    def test_save_attachment_workflow(self, temp_config_with_llmemory):
        """Test saving PDF attachments from email"""
        # Create test email
        email_text = self.create_invoice_email()

        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(email_text)

        # Verify Message object is included
        assert "_message_obj" in email_data
        assert email_data["_message_obj"] is not None

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Run save_attachment workflow
        result = save_attachment(
            message=email_data,
            workflow="test-invoice",
            config=config,
            entity="acme",
            directory="invoice",
            pattern="*.pdf"
        )

        # Check PDF was saved
        assert result["success"]
        assert result["count"] == 1
        assert len(result["documents"]) == 1

        # Check that file exists
        content_path = Path(result["documents"][0]["content_path"])
        assert content_path.exists()

    def test_save_email_as_pdf_workflow(self, temp_config_with_llmemory):
        """Test saving entire email as PDF"""
        # Create test email
        email_text = self.create_invoice_email()

        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(email_text)

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Run save_email_pdf workflow
        with patch("builtins.print") as mock_print:
            result = save_email_pdf(
                message=email_data,
                workflow="test-receipt",
                config=config,
                entity="acme",
                directory="receipts",
            )

        # Check PDF was created
        assert result["success"]
        assert "document_id" in result

        # Check PDF exists and has content
        content_path = Path(result["content_path"])
        assert content_path.exists()
        assert content_path.stat().st_size > 1000  # Should be at least 1KB

    def test_receipt_email_no_attachment(self, temp_config_with_llmemory):
        """Test handling receipt emails without attachments"""
        # Create receipt email without attachment
        msg = MIMEMultipart()
        msg["From"] = "noreply@store.com"
        msg["To"] = "customer@example.com"
        msg["Subject"] = "Order Confirmation #98765"
        msg["Date"] = "Tue, 20 Jan 2024 15:30:00 +0000"

        # Receipt in email body
        body = """
        Order Confirmation

        Order #98765
        Date: January 20, 2024

        Items:
        - Widget A: $29.99
        - Widget B: $19.99

        Total: $49.98

        Thank you for your order!
        """
        msg.attach(MIMEText(body, "plain"))

        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Save as PDF since no attachments
        with patch("builtins.print") as mock_print:
            result = save_email_pdf(
                message=email_data,
                workflow="test-order",
                config=config,
                entity="acme",
                directory="orders",
            )

        # Check PDF was created
        assert result["success"]
        assert "document_id" in result

        # Verify PDF exists and has content
        content_path = Path(result["content_path"])
        assert content_path.exists()
        assert content_path.stat().st_size > 1000

    def test_multiple_attachments_filter(self, temp_config_with_llmemory):
        """Test filtering specific attachment types"""
        msg = MIMEMultipart()
        msg["From"] = "docs@company.com"
        msg["Subject"] = "Monthly Documents"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"

        # Add multiple attachments
        attachments = [
            ("report.pdf", b"%PDF-1.4\nReport"),
            ("data.xlsx", b"PK\x03\x04Excel"),
            ("image.jpg", b"\xff\xd8\xff\xe0JPEG"),
            ("contract.pdf", b"%PDF-1.4\nContract"),
        ]

        for filename, content in attachments:
            att = MIMEBase("application", "octet-stream")
            att.set_payload(content)
            att.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(att)

        # Extract
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Save only PDFs
        result = save_attachment(
            message=email_data,
            workflow="test-docs",
            config=config,
            entity="acme",
            directory="docs",
            pattern="*.pdf"
        )

        # Check only PDFs were saved
        assert result["success"]
        assert result["count"] == 2
        assert len(result["documents"]) == 2

        # Check that both PDFs were saved
        for doc in result["documents"]:
            content_path = Path(doc["content_path"])
            assert content_path.exists()
            assert content_path.suffix == ".pdf"
