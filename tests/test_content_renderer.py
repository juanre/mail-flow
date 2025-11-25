# ABOUTME: Tests for email content rendering (HTML to text conversion, truncation)
"""Tests for email content rendering."""

from mailflow.content_renderer import render_email_body


class TestRenderEmailBody:
    def test_plain_text_unchanged(self):
        body = "Hello,\n\nThis is a test email.\n\nBest regards"
        result = render_email_body(body, is_html=False, max_lines=10)
        assert "Hello," in result
        assert "This is a test email." in result

    def test_html_converted_to_text(self):
        html = "<html><body><p>Hello</p><p>World</p></body></html>"
        result = render_email_body(html, is_html=True, max_lines=10)
        assert "Hello" in result
        assert "World" in result
        assert "<p>" not in result

    def test_truncation_with_indicator(self):
        body = "\n".join([f"Line {i}" for i in range(20)])
        result = render_email_body(body, is_html=False, max_lines=5)
        assert "Line 0" in result
        assert "Line 4" in result
        assert "Line 10" not in result
        assert "[...more" in result

    def test_no_truncation_indicator_when_short(self):
        body = "Short email"
        result = render_email_body(body, is_html=False, max_lines=10)
        assert "[...more" not in result
