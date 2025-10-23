"""Test PDF conversion functionality"""

from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mailflow.exceptions import WorkflowError
from mailflow.pdf_converter import (
    convert_email_to_pdf,
    extract_best_html_from_message,
    save_email_as_pdf,
    wrap_email_html,
)


class TestPDFConverter:
    def test_extract_plain_text_to_html(self):
        """Test converting plain text email to HTML"""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test Email"
        msg.set_content("This is a test email.\nWith multiple lines.")

        html_content, is_original = extract_best_html_from_message(msg)

        # Should convert to HTML
        assert is_original is False
        assert "This is a test email." in html_content
        assert "<br>" in html_content

    def test_wrap_email_with_attachments(self):
        """Test wrapping HTML with email headers"""
        html_content = "<html><body>Email content</body></html>"

        email_data = {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Invoice",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "body": "Please find attached invoice.",
            "attachments": [
                {"filename": "invoice.pdf", "size": 102400},
                {"filename": "receipt.jpg", "size": 51200},
            ],
        }

        wrapped = wrap_email_html(html_content, email_data, is_original_html=True)

        assert "sender@example.com" in wrapped
        assert "Invoice" in wrapped

    def test_wrap_email_escapes_headers(self):
        """Test that HTML special characters are escaped in headers"""
        html_content = "<html><body>Content</body></html>"

        email_data = {
            "from": "<script>alert('xss')</script>",
            "to": "test@example.com",
            "subject": "Test & <b>Demo</b>",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "body": "Content with <script> tags",
            "attachments": [],
        }

        wrapped = wrap_email_html(html_content, email_data, is_original_html=True)

        # Headers should be escaped
        assert "&lt;script&gt;" in wrapped
        assert "&amp;" in wrapped
        assert "&lt;b&gt;" in wrapped

    def test_extract_html_from_multipart(self):
        """Test extracting HTML from multipart email"""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "HTML Email"
        msg.set_content("Plain text version")
        msg.add_alternative("<h1>HTML version</h1>", subtype="html")

        html_content, is_original = extract_best_html_from_message(msg)

        # Should prefer HTML version
        assert is_original is True
        assert "<h1>HTML version</h1>" in html_content
        assert "Plain text version" not in html_content

    def test_save_email_as_pdf(self, temp_config_dir):
        """Test save_email_as_pdf function requires message object"""
        email_data = {
            "from": "invoice@company.com",
            "to": "user@example.com",
            "subject": "Invoice #123",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "body": "Invoice details",
            "attachments": [],
            "features": {"from_domain": "company.com"},
        }

        # Test with custom directory
        receipts_dir = Path(temp_config_dir) / "receipts"

        # Should raise error without message object
        with pytest.raises(WorkflowError) as exc_info:
            save_email_as_pdf(
                email_data,
                directory=str(receipts_dir),
                filename_template="{from}_{subject}.pdf",
                use_year_dirs=False,
                store_metadata=False,
            )
        assert "Message object is required" in str(exc_info.value)

    def test_save_email_as_pdf_with_message_obj(self, temp_config_dir):
        """Test PDF conversion with Message object for better HTML extraction"""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "HTML Email"
        msg.set_content("Plain text version")
        msg.add_alternative("<h1>HTML version</h1>", subtype="html")

        email_data = {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "HTML Email",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "body": "<h1>HTML version</h1>",
            "attachments": [],
            "features": {"from_domain": "example.com"},
        }

        receipts_dir = Path(temp_config_dir) / "receipts"

        save_email_as_pdf(
            email_data,
            message_obj=msg,
            directory=str(receipts_dir),
            use_year_dirs=False,
            store_metadata=False,
        )

        # Should create PDF file
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 1

        # PDF should exist and have content
        assert pdf_files[0].exists()
        assert pdf_files[0].stat().st_size > 1000

    @patch("mailflow.pdf_converter.sync_playwright")
    def test_convert_email_to_pdf_with_playwright(self, mock_playwright, temp_config_dir):
        """Test PDF conversion with Playwright"""
        # Mock Playwright
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_p = MagicMock()

        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        html_content = "<html><body>Test PDF</body></html>"
        pdf_path = Path(temp_config_dir) / "test.pdf"

        # Should succeed
        convert_email_to_pdf(html_content, pdf_path)

        # Verify calls
        mock_p.chromium.launch.assert_called_once_with(headless=True)
        mock_page.set_content.assert_called_once_with(
            html_content, timeout=30000, wait_until="networkidle"
        )
        mock_page.pdf.assert_called_once()
        mock_browser.close.assert_called_once()

    @patch("mailflow.pdf_converter.sync_playwright")
    def test_convert_email_to_pdf_no_browser(self, mock_playwright, temp_config_dir):
        """Test helpful error when Playwright browser not installed"""
        # Mock Playwright throwing browser error
        mock_p = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.side_effect = Exception(
            "Executable doesn't exist at /path/to/chromium"
        )

        html_content = "<html><body>Test</body></html>"
        pdf_path = Path(temp_config_dir) / "test.pdf"

        # Should raise WorkflowError with helpful message
        with pytest.raises(WorkflowError) as exc_info:
            convert_email_to_pdf(html_content, pdf_path)

        assert "Playwright browsers not installed" in str(exc_info.value)
        assert "playwright install chromium" in str(exc_info.value.recovery_hint)
