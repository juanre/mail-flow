"""Test the improved PDF converter that preserves original email content"""

from email import message_from_string

import pytest

from mailflow.pdf_converter import (
    extract_best_html_from_message,
    sanitize_html_for_pdf,
    save_email_as_pdf,
    wrap_email_html,
)


class TestImprovedPDFConverter:
    """Test the improved PDF conversion functionality"""

    def test_extract_html_with_inline_images(self):
        """Test extraction of HTML with inline images"""
        # Create email with HTML and inline image
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Test with inline image
MIME-Version: 1.0
Content-Type: multipart/related; boundary="boundary1"

--boundary1
Content-Type: text/html; charset=utf-8

<html>
<body>
<h1>Test Email</h1>
<img src="cid:image1" alt="Test Image">
<p>This email has an inline image.</p>
</body>
</html>

--boundary1
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <image1>

iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVQI12P4DwABAQEAG7buVgAAAABJRU5ErkJggg==

--boundary1--
"""
        msg = message_from_string(email_content)
        html_content, is_original = extract_best_html_from_message(msg)

        # Should extract HTML
        assert is_original is True
        assert "<h1>Test Email</h1>" in html_content

        # Should replace CID reference with data URL
        assert "cid:image1" not in html_content
        assert "data:image/png;base64," in html_content

    def test_extract_plain_text_email(self):
        """Test extraction from plain text email"""
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Plain text email
Content-Type: text/plain; charset=utf-8

This is a plain text email.
It has multiple lines.

And a URL: https://example.com

Best regards,
Sender
"""
        msg = message_from_string(email_content)
        html_content, is_original = extract_best_html_from_message(msg)

        # Should convert to HTML
        assert is_original is False
        assert "This is a plain text email." in html_content

        # Should convert URLs to links
        assert '<a href="https://example.com">https://example.com</a>' in html_content

        # Should preserve line breaks
        assert "<br>" in html_content

    def test_extract_multipart_alternative(self):
        """Test extraction from multipart/alternative email"""
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Multipart email
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="boundary1"

--boundary1
Content-Type: text/plain; charset=utf-8

Plain text version

--boundary1
Content-Type: text/html; charset=utf-8

<html>
<body>
<h1>HTML version</h1>
<p style="color: blue;">This is the HTML version with styling.</p>
</body>
</html>

--boundary1--
"""
        msg = message_from_string(email_content)
        html_content, is_original = extract_best_html_from_message(msg)

        # Should prefer HTML version
        assert is_original is True
        assert "<h1>HTML version</h1>" in html_content
        assert "Plain text version" not in html_content

    def test_wrap_email_html_preserves_original(self):
        """Test that wrapping preserves original HTML structure"""
        original_html = """<html>
<head>
    <style>
        .custom { color: red; }
    </style>
</head>
<body>
    <div class="custom">Original content</div>
</body>
</html>"""

        email_data = {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Test Subject",
            "date": "Mon, 1 Jan 2024 12:00:00 +0000",
        }

        wrapped = wrap_email_html(original_html, email_data, is_original_html=True)

        # Should preserve original style
        assert ".custom { color: red; }" in wrapped

        # Should preserve original content
        assert '<div class="custom">Original content</div>' in wrapped

        # Should add email headers
        assert "sender@example.com" in wrapped
        assert "Test Subject" in wrapped

    def test_save_email_requires_message_object(self, tmp_path):
        """Test that save_email_as_pdf requires message object"""
        email_data = {
            "from": "sender@example.com",
            "subject": "Test",
            "body": "Test body",
            "features": {"from_domain": "example.com"},
        }

        with pytest.raises(Exception) as exc_info:
            save_email_as_pdf(
                email_data,
                message_obj=None,  # No message object
                directory=str(tmp_path),
            )

        assert "Message object is required" in str(exc_info.value)

    def test_html_email_with_external_images(self):
        """Test that external images are preserved (not blocked)"""
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Email with external image
Content-Type: text/html; charset=utf-8

<html>
<body>
<img src="https://example.com/logo.png" alt="Company Logo">
<p>This email has an external image.</p>
</body>
</html>
"""
        msg = message_from_string(email_content)
        html_content, is_original = extract_best_html_from_message(msg)

        # Should preserve external image URL
        assert is_original is True
        assert 'src="https://example.com/logo.png"' in html_content

    def test_complex_html_preservation(self):
        """Test preservation of complex HTML with CSS and JavaScript"""
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Complex HTML email
Content-Type: text/html; charset=utf-8

<html>
<head>
    <style>
        @media (max-width: 600px) {
            .responsive { width: 100% !important; }
        }
        .button {
            background-color: #4CAF50;
            border: none;
            color: white;
            padding: 15px 32px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
        }
    </style>
</head>
<body>
    <table class="responsive">
        <tr>
            <td>
                <a href="https://example.com" class="button">Click Here</a>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        msg = message_from_string(email_content)
        html_content, is_original = extract_best_html_from_message(msg)

        # Should preserve all styles
        assert is_original is True
        assert "@media (max-width: 600px)" in html_content
        assert "background-color: #4CAF50" in html_content
        assert 'class="button"' in html_content
        assert 'class="responsive"' in html_content


class TestHTMLSanitization:
    """Test HTML sanitization for security"""

    def test_sanitize_removes_script_tags(self):
        """Test that script tags are removed"""
        html = """<html>
<body>
<h1>Safe content</h1>
<script>alert('XSS')</script>
<p>More safe content</p>
</body>
</html>"""
        sanitized = sanitize_html_for_pdf(html)

        assert "<script>" not in sanitized
        assert "alert('XSS')" not in sanitized
        assert "<h1>Safe content</h1>" in sanitized
        assert "<p>More safe content</p>" in sanitized

    def test_sanitize_removes_iframe_tags(self):
        """Test that iframe tags are removed"""
        html = '<div>Content</div><iframe src="http://evil.com"></iframe>'
        sanitized = sanitize_html_for_pdf(html)

        assert "<iframe" not in sanitized
        assert "evil.com" not in sanitized
        assert "<div>Content</div>" in sanitized

    def test_sanitize_removes_object_embed_tags(self):
        """Test that object and embed tags are removed"""
        html = """<div>Content</div>
<object data="evil.swf"></object>
<embed src="evil.swf">"""
        sanitized = sanitize_html_for_pdf(html)

        assert "<object" not in sanitized
        assert "<embed" not in sanitized
        assert "<div>Content</div>" in sanitized

    def test_sanitize_removes_event_handlers(self):
        """Test that event handlers are removed"""
        html = """<div onclick="alert('XSS')">Click me</div>
<img src="image.jpg" onerror="alert('XSS')">
<a href="#" onmouseover="stealCookies()">Link</a>"""
        sanitized = sanitize_html_for_pdf(html)

        assert "onclick" not in sanitized
        assert "onerror" not in sanitized
        assert "onmouseover" not in sanitized
        assert "alert" not in sanitized
        assert "stealCookies" not in sanitized
        assert "Click me" in sanitized
        assert "Link" in sanitized

    def test_sanitize_removes_javascript_urls(self):
        """Test that javascript: URLs are removed"""
        html = """<a href="javascript:alert('XSS')">Link</a>
<img src="javascript:alert('XSS')">
<form action="javascript:void(0)">"""
        sanitized = sanitize_html_for_pdf(html)

        assert "javascript:" not in sanitized.lower()
        assert "alert" not in sanitized
        assert "<a" in sanitized
        assert "Link" in sanitized

    def test_sanitize_removes_link_tags(self):
        """Test that link tags (external stylesheets) are removed"""
        html = """<html>
<head>
<link rel="stylesheet" href="http://evil.com/style.css">
<style>.safe { color: blue; }</style>
</head>
<body>Content</body>
</html>"""
        sanitized = sanitize_html_for_pdf(html)

        assert "<link" not in sanitized
        assert "evil.com" not in sanitized
        # Inline styles should be preserved
        assert "<style>" in sanitized
        assert ".safe { color: blue; }" in sanitized

    def test_sanitize_preserves_safe_content(self):
        """Test that safe HTML content is preserved"""
        html = """<html>
<head>
<style>
body { font-family: Arial; }
.header { color: blue; }
</style>
</head>
<body>
<div class="header">
<h1>Email Subject</h1>
</div>
<p>This is <strong>safe</strong> content with <a href="https://example.com">links</a>.</p>
<img src="https://example.com/image.jpg" alt="Safe image">
<table>
<tr><td>Data</td></tr>
</table>
</body>
</html>"""
        sanitized = sanitize_html_for_pdf(html)

        # All safe elements should be preserved
        assert "<style>" in sanitized
        assert "font-family: Arial" in sanitized
        assert "<h1>Email Subject</h1>" in sanitized
        assert "<strong>safe</strong>" in sanitized
        assert 'href="https://example.com"' in sanitized
        assert 'src="https://example.com/image.jpg"' in sanitized
        assert "<table>" in sanitized

    def test_sanitize_handles_mixed_case_attacks(self):
        """Test that mixed case attack attempts are handled"""
        html = """<div OnClIcK="alert('XSS')">Content</div>
<SCRIPT>alert('XSS')</SCRIPT>
<iFrAmE src="evil.com"></iFrAmE>"""
        sanitized = sanitize_html_for_pdf(html)

        assert "onclick" not in sanitized.lower()
        assert "<script" not in sanitized.lower()
        assert "<iframe" not in sanitized.lower()
        assert "Content" in sanitized
