"""Test complete workflow integration with Message objects"""

import pytest
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from unittest.mock import patch, MagicMock

from pmail.config import Config
from pmail.email_extractor import EmailExtractor
from pmail.workflow import save_attachment, save_email_pdf


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

    def test_save_attachment_workflow(self, temp_config_dir):
        """Test saving PDF attachments from email"""
        # Create test email
        email_text = self.create_invoice_email()

        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(email_text)

        # Verify Message object is included
        assert "_message_obj" in email_data
        assert email_data["_message_obj"] is not None

        # Set up directory
        invoices_dir = Path(temp_config_dir) / "invoices"

        # Run save_attachment workflow
        with patch("builtins.print") as mock_print:
            save_attachment(email_data, directory=str(invoices_dir), pattern="*.pdf")

        # Check directory was created
        assert invoices_dir.exists()

        # Check PDF was saved
        pdf_files = list(invoices_dir.glob("*.pdf"))
        assert len(pdf_files) == 1
        assert pdf_files[0].name == "invoice_12345.pdf"

        # Verify print output
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("Saved 1 attachment(s)" in str(call) for call in print_calls)

    def test_save_email_as_pdf_workflow(self, temp_config_dir):
        """Test saving entire email as PDF"""
        # Create test email
        email_text = self.create_invoice_email()

        # Extract email data
        extractor = EmailExtractor()
        email_data = extractor.extract(email_text)

        # Set up directory
        receipts_dir = Path(temp_config_dir) / "receipts"

        # Run save_email_pdf workflow
        with patch("builtins.print") as mock_print:
            save_email_pdf(
                email_data,
                directory=str(receipts_dir),
                filename_template="{date}_{from}_invoice.pdf",
            )

        # Check directory was created
        assert receipts_dir.exists()

        # Check PDF was created
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 1
        assert "company.com" in pdf_files[0].name
        assert "invoice" in pdf_files[0].name

        # Check PDF exists and has content
        assert pdf_files[0].exists()
        assert pdf_files[0].stat().st_size > 1000  # Should be at least 1KB

    def test_receipt_email_no_attachment(self, temp_config_dir):
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

        # Save as PDF since no attachments
        receipts_dir = Path(temp_config_dir) / "receipts"

        with patch("builtins.print") as mock_print:
            save_email_pdf(email_data, directory=str(receipts_dir))

        # Check PDF was created
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 1

        # Verify PDF exists and has content
        assert pdf_files[0].exists()
        assert pdf_files[0].stat().st_size > 1000
        assert "store.com" in pdf_files[0].name

    def test_multiple_attachments_filter(self, temp_config_dir):
        """Test filtering specific attachment types"""
        msg = MIMEMultipart()
        msg["From"] = "docs@company.com"
        msg["Subject"] = "Monthly Documents"

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

        # Save only PDFs
        docs_dir = Path(temp_config_dir) / "documents"

        save_attachment(email_data, directory=str(docs_dir), pattern="*.pdf")

        # Check only PDFs were saved
        pdf_files = list(docs_dir.glob("*.pdf"))
        assert len(pdf_files) == 2

        pdf_names = {f.name for f in pdf_files}
        assert pdf_names == {"report.pdf", "contract.pdf"}
