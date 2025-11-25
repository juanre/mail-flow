# ABOUTME: Tests for TUI components (email display, workflow choices).
"""Tests for TUI components."""

from io import StringIO

from rich.console import Console

from mailflow.tui import display_email, format_attachment_indicator


class TestFormatAttachmentIndicator:
    def test_pdf_shown_with_emoji(self):
        attachments = [{"filename": "invoice.pdf", "size": 1024}]
        result = format_attachment_indicator(attachments)
        assert "📎" in result
        assert "invoice.pdf" in result

    def test_multiple_pdfs(self):
        attachments = [
            {"filename": "invoice.pdf", "size": 1024},
            {"filename": "receipt.pdf", "size": 2048},
        ]
        result = format_attachment_indicator(attachments)
        assert "invoice.pdf" in result
        assert "receipt.pdf" in result

    def test_no_attachments(self):
        result = format_attachment_indicator([])
        assert result == ""

    def test_non_pdf_not_highlighted(self):
        attachments = [{"filename": "image.jpg", "size": 1024}]
        result = format_attachment_indicator(attachments)
        assert "image.jpg" in result
        assert "📎" not in result  # No PDF emoji for non-PDFs


class TestDisplayEmail:
    def test_displays_basic_info(self):
        email = {
            "from": "test@example.com",
            "subject": "Test Subject",
            "body": "Test body content",
            "attachments": [],
            "date": "2025-01-01",
        }
        output = StringIO()
        console = Console(file=output, width=80, force_terminal=False)

        display_email(console, email, position=1, total=10, thread_info=None)

        result = output.getvalue()
        assert "test@example.com" in result
        assert "Test Subject" in result

    def test_displays_thread_info(self):
        from mailflow.thread_detector import ThreadInfo

        email = {
            "from": "test@example.com",
            "subject": "Test Subject",
            "body": "Test body",
            "attachments": [],
            "date": "2025-01-01",
        }
        thread_info = ThreadInfo(position=2, count=5, is_first=False, pdf_in_thread=4)
        output = StringIO()
        console = Console(file=output, width=80, force_terminal=False)

        display_email(console, email, position=1, total=10, thread_info=thread_info)

        result = output.getvalue()
        assert "Thread 2/5" in result or "2/5" in result
