"""Test the smart save_receipt workflow"""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pytest

from pmail.email_extractor import EmailExtractor
from pmail.workflow import save_pdf


class TestSaveReceiptWorkflow:
    def test_save_receipt_with_pdf_attachment(self, temp_config_dir):
        """Test that save_receipt saves PDF attachment when present"""
        # Create email with PDF attachment
        msg = MIMEMultipart()
        msg["From"] = "billing@company.com"
        msg["To"] = "customer@example.com"
        msg["Subject"] = "Invoice #12345"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"

        # Add body
        msg.attach(MIMEText("Please find attached your invoice.", "plain"))

        # Add PDF attachment
        pdf_att = MIMEBase("application", "pdf")
        pdf_content = b"%PDF-1.4\n%Invoice PDF content\n"
        pdf_att.set_payload(pdf_content)
        encoders.encode_base64(pdf_att)
        pdf_att.add_header("Content-Disposition", 'attachment; filename="invoice_12345.pdf"')
        msg.attach(pdf_att)

        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Run save_receipt workflow
        receipts_dir = Path(temp_config_dir) / "receipts"
        save_pdf(
            email_data, directory=str(receipts_dir), use_year_dirs=False, store_metadata=False
        )

        # Should have saved the PDF attachment
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 1
        # Check for date prefix (could be email date or today's date) and original filename
        assert pdf_files[0].name.endswith("-invoice_12345.pdf")
        # Verify it has a date prefix in YYYY-MM-DD format
        import re

        assert re.match(r"\d{4}-\d{2}-\d{2}-invoice_12345\.pdf", pdf_files[0].name)

        # Verify content
        with open(pdf_files[0], "rb") as f:
            saved_content = f.read()
        assert saved_content == pdf_content

    def test_save_receipt_without_pdf_creates_pdf(self, temp_config_dir):
        """Test that save_receipt converts email to PDF when no PDF attachment"""
        # Create email without PDF attachment
        msg = MIMEMultipart()
        msg["From"] = "orders@store.com"
        msg["To"] = "customer@example.com"
        msg["Subject"] = "Order Confirmation #98765"
        msg["Date"] = "Tue, 20 Jan 2024 15:30:00 +0000"

        # Receipt in email body
        body = """
        <html>
        <body>
            <h1>Order Confirmation</h1>
            <p>Order #98765</p>
            <p>Total: $49.98</p>
            <p>Thank you for your order!</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Run save_receipt workflow
        receipts_dir = Path(temp_config_dir) / "receipts"
        save_pdf(
            email_data,
            directory=str(receipts_dir),
            filename_template="{date}_{from}_order",
            use_year_dirs=False,
            store_metadata=False,
        )

        # Should have created a PDF from the email
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 1
        assert "store.com" in pdf_files[0].name
        assert "order" in pdf_files[0].name

        # PDF should exist and have content
        assert pdf_files[0].exists()
        assert pdf_files[0].stat().st_size > 1000

    def test_save_receipt_with_multiple_pdfs(self, temp_config_dir):
        """Test that save_receipt saves all PDF attachments"""
        # Create email with multiple PDF attachments
        msg = MIMEMultipart()
        msg["From"] = "accounting@company.com"
        msg["Subject"] = "Monthly Documents"

        # Add multiple PDF attachments
        for i, (filename, content) in enumerate(
            [
                ("invoice_jan.pdf", b"%PDF-1.4\nJanuary Invoice"),
                ("receipt_jan.pdf", b"%PDF-1.4\nJanuary Receipt"),
                ("statement.pdf", b"%PDF-1.4\nBank Statement"),
            ]
        ):
            pdf_att = MIMEBase("application", "pdf")
            pdf_att.set_payload(content)
            encoders.encode_base64(pdf_att)
            pdf_att.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(pdf_att)

        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Run save_receipt workflow
        receipts_dir = Path(temp_config_dir) / "receipts"
        save_pdf(
            email_data, directory=str(receipts_dir), use_year_dirs=False, store_metadata=False
        )

        # Should have saved all PDF attachments
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 3

        # Check that all expected files were saved (with date prefixes)
        pdf_names = [f.name for f in pdf_files]
        assert any("invoice_jan.pdf" in name for name in pdf_names)
        assert any("receipt_jan.pdf" in name for name in pdf_names)
        assert any("statement.pdf" in name for name in pdf_names)

    def test_save_receipt_with_non_pdf_attachments(self, temp_config_dir):
        """Test that save_receipt creates PDF when only non-PDF attachments exist"""
        # Create email with non-PDF attachments
        msg = MIMEMultipart()
        msg["From"] = "receipts@store.com"
        msg["Subject"] = "Purchase Receipt"
        msg["Date"] = "Wed, 21 Jan 2024 09:00:00 +0000"

        # Add body
        msg.attach(MIMEText("Your purchase receipt is attached as an image.", "plain"))

        # Add image attachment
        img_att = MIMEBase("image", "jpeg")
        img_att.set_payload(b"JPEG image data")
        img_att.add_header("Content-Disposition", 'attachment; filename="receipt.jpg"')
        msg.attach(img_att)

        # Extract email
        extractor = EmailExtractor()
        email_data = extractor.extract(msg.as_string())

        # Run save_receipt workflow
        receipts_dir = Path(temp_config_dir) / "receipts"
        save_pdf(
            email_data, directory=str(receipts_dir), use_year_dirs=False, store_metadata=False
        )

        # Should have created PDF from email (not saved the JPG)
        pdf_files = list(receipts_dir.glob("*.pdf"))
        jpg_files = list(receipts_dir.glob("*.jpg"))

        assert len(pdf_files) == 1
        assert len(jpg_files) == 0  # JPG not saved
        assert "store.com" in pdf_files[0].name
