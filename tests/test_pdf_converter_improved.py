"""Test the improved PDF converter that preserves original email content"""

from email import message_from_string

import pytest

from mailflow.pdf_converter import (
    extract_best_html_from_message,
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
