"""Test the smart save_pdf workflow"""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from mailflow.email_extractor import EmailExtractor
from mailflow.workflow import save_pdf


class TestSaveReceiptWorkflow:
    def test_save_receipt_with_pdf_attachment(self, temp_config_with_llmemory):
        """Test that save_pdf saves PDF attachment when present"""
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

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Run save_pdf workflow
        result = save_pdf(
            message=email_data,
            workflow="test-invoice",
            config=config
        )

        # Should have saved the PDF attachment
        assert result["success"]
        assert result["count"] == 1
        assert len(result["documents"]) == 1

        # Check that file exists in archive
        content_path = Path(result["documents"][0]["content_path"])
        assert content_path.exists()

        # Verify content
        assert content_path.read_bytes() == pdf_content

    def test_save_receipt_without_pdf_creates_pdf(self, temp_config_with_llmemory):
        """Test that save_pdf converts email to PDF when no PDF attachment"""
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

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Run save_pdf workflow
        result = save_pdf(
            message=email_data,
            workflow="test-order",
            config=config
        )

        # Should have created a PDF from the email
        assert result["success"]
        assert "document_id" in result

        # Check that file exists in archive
        content_path = Path(result["content_path"])
        assert content_path.exists()
        assert content_path.stat().st_size > 1000

    def test_save_receipt_with_multiple_pdfs(self, temp_config_with_llmemory):
        """Test that save_pdf saves all PDF attachments"""
        # Create email with multiple PDF attachments
        msg = MIMEMultipart()
        msg["From"] = "accounting@company.com"
        msg["Subject"] = "Monthly Documents"
        msg["Date"] = "Mon, 15 Jan 2024 10:00:00 +0000"

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

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Run save_pdf workflow
        result = save_pdf(
            message=email_data,
            workflow="test-docs",
            config=config
        )

        # Should have saved all PDF attachments
        assert result["success"]
        assert result["count"] == 3
        assert len(result["documents"]) == 3

        # Check that all files exist
        for doc in result["documents"]:
            content_path = Path(doc["content_path"])
            assert content_path.exists()

    def test_save_receipt_with_non_pdf_attachments(self, temp_config_with_llmemory):
        """Test that save_pdf creates PDF when only non-PDF attachments exist"""
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

        # Use config with archive and llmemory configured
        config = temp_config_with_llmemory

        # Run save_pdf workflow
        result = save_pdf(
            message=email_data,
            workflow="test-receipt",
            config=config
        )

        # Should have created PDF from email (not saved the JPG)
        assert result["success"]
        assert "document_id" in result

        # Check that PDF exists
        content_path = Path(result["content_path"])
        assert content_path.exists()
        assert content_path.suffix == ".pdf"
