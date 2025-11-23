# ABOUTME: Converts emails to PDF format using Playwright, preserving HTML and inline images.
# ABOUTME: Extracts email content, wraps with headers, and generates searchable PDFs with metadata.
"""Convert emails to PDF format - preserving original content"""

import base64
import html
import logging
import os
from datetime import datetime
from email.message import Message
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from mailflow.exceptions import WorkflowError
from archive_protocol.utils import sanitize_filename
from mailflow.security import validate_path

logger = logging.getLogger(__name__)


def text_to_pdf_bytes(text: str) -> bytes:
    """Convert plain text to a minimal PDF and return bytes.

    This avoids heavyweight dependencies for simple text attachments
    and provides a consistent converter surface.
    """
    content = (
        "BT /F1 12 Tf 72 720 Td ("
        + text[:200].replace("(", "[").replace(")", "]")
        + ") Tj ET\n"
    )
    stream = (
        b"%PDF-1.4\n"
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents 4 0 R >>endobj\n"
        + f"4 0 obj<< /Length {len(content)} >>stream\n".encode("utf-8")
        + content.encode("utf-8")
        + b"endstream endobj\nxref\n0 5\n0000000000 65535 f\n0000000010 00000 n\n0000000061 00000 n\n0000000115 00000 n\n0000000329 00000 n\ntrailer<< /Size 5 /Root 1 0 R >>\nstartxref\n409\n%%EOF\n"
    )
    return stream

def sanitize_html_for_pdf(html_content: str) -> str:
    """Sanitize HTML content for safe PDF conversion."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove dangerous elements
    for tag in soup.find_all(["script", "iframe", "object", "embed", "link"]):
        tag.decompose()

    # Remove event handlers from all tags
    for tag in soup.find_all(True):
        attrs_to_remove = [attr for attr in tag.attrs if attr.startswith("on")]
        for attr in attrs_to_remove:
            del tag[attr]

        # Remove javascript: URLs
        for attr in ["href", "src", "data", "action"]:
            if attr in tag.attrs and isinstance(tag[attr], str):
                if tag[attr].strip().lower().startswith("javascript:"):
                    del tag[attr]

    return str(soup)


def extract_best_html_from_message(message_obj: Message) -> tuple[str, bool]:
    """
    Extract the best HTML representation from an email message.
    Returns (html_content, is_html_original)

    Priority:
    1. text/html part (original HTML)
    2. multipart/related with text/html (HTML with inline images)
    3. text/plain converted to HTML
    """
    html_content = None
    plain_content = None
    inline_images = {}

    # First pass: collect all parts
    for part in message_obj.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))

        # Skip attachments
        if "attachment" in content_disposition:
            continue

        if content_type == "text/html":
            try:
                charset = part.get_content_charset() or "utf-8"
                html_content = part.get_payload(decode=True).decode(charset, errors="replace")
            except Exception as e:
                logger.warning(f"Failed to decode HTML part: {e}")

        elif content_type == "text/plain" and not plain_content:
            try:
                charset = part.get_content_charset() or "utf-8"
                plain_content = part.get_payload(decode=True).decode(charset, errors="replace")
            except Exception as e:
                logger.warning(f"Failed to decode plain text part: {e}")

        elif content_type.startswith("image/") and part.get("Content-ID"):
            # Inline image - store for embedding
            try:
                image_data = part.get_payload(decode=True)
                content_id = part.get("Content-ID").strip("<>")

                # Create data URL for embedding
                mime_type = content_type
                data_url = f"data:{mime_type};base64,{base64.b64encode(image_data).decode()}"
                inline_images[content_id] = data_url

                # Also store by filename if available
                filename = part.get_filename()
                if filename:
                    inline_images[filename] = data_url
            except Exception as e:
                logger.warning(f"Failed to process inline image: {e}")

    # If we have HTML, process it
    if html_content:
        # Replace CID references with data URLs for inline images
        for cid, data_url in inline_images.items():
            html_content = html_content.replace(f"cid:{cid}", data_url)
            html_content = html_content.replace(f'"cid:{cid}"', f'"{data_url}"')
            html_content = html_content.replace(f"'cid:{cid}'", f"'{data_url}'")

        return html_content, True

    # Fallback to plain text converted to HTML
    if plain_content:
        # Basic HTML conversion preserving structure
        escaped = html.escape(plain_content)
        # Convert URLs to links
        import re

        url_pattern = r'(https?://[^\s<>"{}|\\^`\[\]]+)'
        escaped = re.sub(url_pattern, r'<a href="\1">\1</a>', escaped)
        # Convert newlines to <br>
        escaped = escaped.replace("\n", "<br>\n")

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: monospace;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin: 20px;
        }}
    </style>
</head>
<body>
{escaped}
</body>
</html>"""
        return html_content, False

    # Last resort - empty HTML
    return "<html><body>No content available</body></html>", False


def wrap_email_html(html_content: str, email_data: dict[str, Any], is_original_html: bool) -> str:
    """
    Wrap email HTML content with headers and proper structure.
    Preserves original HTML as much as possible.
    """
    # Sanitize HTML content for security
    html_content = sanitize_html_for_pdf(html_content)

    # Extract headers
    from_addr = html.escape(email_data.get("from", ""))
    to_addr = html.escape(email_data.get("to", ""))
    subject = html.escape(email_data.get("subject", ""))
    date = html.escape(email_data.get("date", ""))

    # If we have original HTML, try to preserve it better
    if is_original_html and "<html" in html_content.lower():
        # Parse the HTML to insert headers
        soup = BeautifulSoup(html_content, "html.parser")

        # Create header div
        header_html = f"""
<div style="background-color: #f0f0f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; font-family: Arial, sans-serif;">
    <div style="margin: 5px 0;"><strong>From:</strong> {from_addr}</div>
    <div style="margin: 5px 0;"><strong>To:</strong> {to_addr}</div>
    <div style="margin: 5px 0;"><strong>Subject:</strong> {subject}</div>
    <div style="margin: 5px 0;"><strong>Date:</strong> {date}</div>
</div>
"""

        # Find body tag and insert header at the beginning
        body_tag = soup.find("body")
        if body_tag:
            # Parse header as BeautifulSoup object and insert
            header_soup = BeautifulSoup(header_html, "html.parser")
            body_tag.insert(0, header_soup)
        else:
            # No body tag, wrap everything
            return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{subject}</title>
</head>
<body>
    {header_html}
    {html_content}
</body>
</html>"""

        return str(soup)

    else:
        # Simple HTML or converted from plain text
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{subject}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }}
        .email-header {{
            background-color: #f0f0f0;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .header-item {{
            margin: 5px 0;
        }}
        .email-content {{
            padding: 20px;
            background-color: #ffffff;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="email-header">
        <div class="header-item"><strong>From:</strong> {from_addr}</div>
        <div class="header-item"><strong>To:</strong> {to_addr}</div>
        <div class="header-item"><strong>Subject:</strong> {subject}</div>
        <div class="header-item"><strong>Date:</strong> {date}</div>
    </div>

    <div class="email-content">
        {html_content}
    </div>
</body>
</html>"""


def add_attachments_list(html_content: str, email_data: dict[str, Any]) -> str:
    """Add a list of attachments to the HTML if any exist"""
    if not email_data.get("attachments"):
        return html_content

    attachments_html = """
<div style="margin-top: 20px; padding: 10px; background-color: #f9f9f9; border-radius: 5px; font-family: Arial, sans-serif;">
    <h3 style="margin-top: 0;">Attachments:</h3>
"""

    for att in email_data["attachments"]:
        filename = html.escape(att.get("filename", ""))
        size = att.get("size", 0)
        size_kb = size / 1024
        attachments_html += (
            f'    <div style="margin: 5px 0;">📎 {filename} ({size_kb:.1f} KB)</div>\n'
        )

    attachments_html += "</div>"

    # Insert before closing body tag
    if "</body>" in html_content:
        return html_content.replace("</body>", f"{attachments_html}\n</body>")
    else:
        return html_content + attachments_html


def convert_email_to_pdf(html_content: str, output_path: Path) -> None:
    """Convert HTML to PDF using Playwright"""
    # Check HTML size (limit to 10MB)
    MAX_HTML_SIZE = 10 * 1024 * 1024
    if len(html_content) > MAX_HTML_SIZE:
        raise WorkflowError(
            f"HTML content too large: {len(html_content) / 1024 / 1024:.1f}MB (max: 10MB)",
            recovery_hint="Email is too large to convert to PDF",
        )

    browser = None
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as browser_error:
                if "Executable doesn't exist" in str(browser_error):
                    logger.error(
                        "Playwright browsers not installed. Run: playwright install chromium"
                    )
                    raise WorkflowError(
                        "Playwright browsers not installed",
                        recovery_hint="Run: playwright install chromium",
                    )
                raise

            page = browser.new_page()

            # Set default timeout to prevent hanging
            page.set_default_timeout(60000)  # 60 second max

            # Set content with timeout
            # Let Playwright handle external images naturally
            page.set_content(html_content, timeout=30000, wait_until="networkidle")

            # Generate PDF with good defaults
            page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                margin={
                    "top": "20mm",
                    "bottom": "20mm",
                    "left": "15mm",
                    "right": "15mm",
                },
            )

            browser.close()
            browser = None

        logger.info(f"Successfully created PDF: {output_path}")
    except WorkflowError:
        raise
    except Exception as e:
        # Clean up browser if still open
        if browser:
            try:
                browser.close()
            except:
                pass

        # Clean up partial PDF
        if output_path.exists():
            try:
                output_path.unlink()
            except:
                pass

        raise WorkflowError(
            f"PDF conversion failed: {e}",
            recovery_hint="Check if Playwright is properly installed",
        )


def email_to_pdf_bytes(message_obj: Message, email_data: dict[str, Any]) -> bytes:
    """Convert email to PDF and return bytes.

    Args:
        message_obj: Email message object
        email_data: Extracted email data

    Returns:
        PDF content as bytes
    """
    import tempfile

    # Extract best HTML representation
    html_content, is_original = extract_best_html_from_message(message_obj)

    # Wrap with headers
    html_content = wrap_email_html(html_content, email_data, is_original)

    # Add attachments list
    html_content = add_attachments_list(html_content, email_data)

    # Convert to PDF in temp file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        convert_email_to_pdf(html_content, tmp_path)
        return tmp_path.read_bytes()
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def save_email_as_pdf(
    email_data: dict[str, Any],
    message_obj: Message | None = None,
    directory: str = "~/receipts",
    filename_template: str = "{date}-{from}-{subject}.pdf",
    use_year_dirs: bool = True,
    store_metadata: bool = True,
) -> None:
    """
    Save email as PDF file using Playwright - preserving original content.

    Note: Requires Playwright browsers to be installed:
        playwright install chromium

    Args:
        email_data: Extracted email data
        message_obj: Original email Message object (required for proper conversion)
        directory: Directory to save PDF
        filename_template: Template for filename generation
        use_year_dirs: Whether to create year subdirectories
        store_metadata: Whether to store metadata in SQLite
    """
    if not message_obj:
        raise WorkflowError(
            "Email Message object is required for PDF conversion",
            recovery_hint="Ensure the email is properly parsed before conversion",
        )

    try:
        # Validate directory
        base_dir = validate_path(directory, allowed_base_dirs=[os.path.expanduser("~"), directory])

        # Generate filename from template
        from_domain = email_data.get("features", {}).get("from_domain", "unknown")
        date_str = datetime.now().strftime("%Y%m%d")

        # Parse date from email if available
        email_date = None
        if email_data.get("date"):
            try:
                from email.utils import parsedate_to_datetime

                email_date = parsedate_to_datetime(email_data["date"])
                date_str = email_date.strftime("%Y%m%d")
            except:
                email_date = None

        if not email_date:
            email_date = datetime.now()
            date_str = email_date.strftime("%Y%m%d")

        # Create year directory if requested
        dir_path = base_dir / str(email_date.year) if use_year_dirs else base_dir

        dir_path.mkdir(parents=True, exist_ok=True)

        # Build filename with date prefix
        date_prefix = email_date.strftime("%Y-%m-%d")
        filename_parts = {
            "date": date_str,
            "from": from_domain,
            "subject": email_data.get("subject", "email")[:50],
        }

        filename = filename_template.format(**filename_parts)
        filename = sanitize_filename(filename)

        # Ensure .pdf extension
        if not filename.endswith(".pdf"):
            filename += ".pdf"

        # Add date prefix
        filename = f"{date_prefix}-{filename}"
        output_path = dir_path / filename

        # Check if file exists
        if output_path.exists():
            base = output_path.stem
            counter = 1
            while output_path.exists():
                output_path = dir_path / f"{base}_{counter}.pdf"
                counter += 1

        # Extract best HTML representation
        html_content, is_original = extract_best_html_from_message(message_obj)

        # Wrap with headers
        html_content = wrap_email_html(html_content, email_data, is_original)

        # Add attachments list
        html_content = add_attachments_list(html_content, email_data)

        # Convert to PDF
        convert_email_to_pdf(html_content, output_path)

        logger.info(f"Saved email as PDF: {output_path}")

        # Metadata is indexed by the global indexer. No direct DB writes here.

    except Exception as e:
        if isinstance(e, WorkflowError):
            raise
        raise WorkflowError(
            f"Failed to save email as PDF: {e}",
            recovery_hint="Check directory permissions and PDF library installation",
        )
