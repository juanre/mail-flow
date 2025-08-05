"""Test PDF conversion functionality"""

import pytest
from pathlib import Path
from email.message import EmailMessage
from unittest.mock import patch, MagicMock

from pmail.pdf_converter import (
    email_to_html,
    convert_email_to_pdf,
    save_email_as_pdf,
    clean_html_for_pdf,
)


class TestPDFConverter:
    def test_email_to_html_plain_text(self):
        """Test converting plain text email to HTML"""
        email_data = {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Test Email",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "body": "This is a test email.\nWith multiple lines.",
            "attachments": [],
        }

        html = email_to_html(email_data)

        assert "sender@example.com" in html
        assert "recipient@example.com" in html
        assert "Test Email" in html
        assert "This is a test email.<br>" in html
        assert "With multiple lines." in html

    def test_email_to_html_with_attachments(self):
        """Test HTML generation includes attachment list"""
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

        html = email_to_html(email_data)

        assert "Attachments:" in html
        assert "invoice.pdf (100.0 KB)" in html
        assert "receipt.jpg (50.0 KB)" in html
        assert "📎" in html

    def test_email_to_html_escapes_content(self):
        """Test that HTML special characters are escaped"""
        email_data = {
            "from": "<script>alert('xss')</script>",
            "to": "test@example.com",
            "subject": "Test & <b>Demo</b>",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "body": "Content with <script> tags",
            "attachments": [],
        }

        html = email_to_html(email_data)

        # Should escape HTML tags
        assert "&lt;script&gt;" in html
        assert "<script>" not in html
        assert "Test &amp; &lt;b&gt;Demo&lt;/b&gt;" in html

    def test_clean_html_for_pdf(self):
        """Test HTML cleaning for PDF conversion"""
        html_with_scripts = """
        <html>
        <head><script>alert('test');</script></head>
        <body>
            <p style="color: red; position: absolute; transform: rotate(45deg);">Text</p>
            <img src="http://example.com/image.jpg" alt="External">
        </body>
        </html>
        """

        cleaned = clean_html_for_pdf(html_with_scripts)

        # Scripts should be removed
        assert "<script>" not in cleaned
        assert "alert" not in cleaned

        # Complex styles simplified
        assert "position: absolute" not in cleaned
        assert "color: red" in cleaned  # Basic styles kept

        # External images replaced
        assert "http://example.com" not in cleaned
        assert "[Image:" in cleaned

    def test_save_email_as_pdf(self, temp_config_dir):
        """Test the main save_email_as_pdf function"""
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

        save_email_as_pdf(
            email_data,
            directory=str(receipts_dir),
            filename_template="{from}_{subject}.pdf",
            use_year_dirs=False,
            store_metadata=False,
        )

        # Should create directory
        assert receipts_dir.exists()

        # Should create actual PDF file
        pdf_files = list(receipts_dir.glob("*.pdf"))
        assert len(pdf_files) == 1
        assert "company.com" in pdf_files[0].name
        assert "Invoice" in pdf_files[0].name

        # PDF should have content
        assert pdf_files[0].stat().st_size > 1000  # Should be at least 1KB

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

    @patch("pmail.pdf_converter.sync_playwright")
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
        mock_page.set_content.assert_called_once_with(html_content, timeout=30000)
        mock_page.pdf.assert_called_once()
        mock_browser.close.assert_called_once()

    @patch("pmail.pdf_converter.sync_playwright")
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
        from pmail.exceptions import WorkflowError

        with pytest.raises(WorkflowError) as exc_info:
            convert_email_to_pdf(html_content, pdf_path)

        assert "Playwright browsers not installed" in str(exc_info.value)
        assert "playwright install chromium" in str(exc_info.value.recovery_hint)
