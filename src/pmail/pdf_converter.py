"""Convert emails to PDF format"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from email.message import Message
import html
from datetime import datetime

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from pmail.security import validate_path, sanitize_filename
from pmail.exceptions import WorkflowError

logger = logging.getLogger(__name__)


def email_to_html(email_data: Dict[str, Any], message_obj: Optional[Message] = None) -> str:
    """Convert email data to HTML format"""

    # Extract data
    from_addr = html.escape(email_data.get("from", ""))
    to_addr = html.escape(email_data.get("to", ""))
    subject = html.escape(email_data.get("subject", ""))
    date = html.escape(email_data.get("date", ""))
    body = email_data.get("body", "")

    # Check if body is HTML or plain text
    is_html = False
    if message_obj:
        for part in message_obj.walk():
            if part.get_content_type() == "text/html":
                is_html = True
                break

    if not is_html:
        # Convert plain text to HTML
        body = html.escape(body)
        body = body.replace("\n", "<br>\n")

    # Create HTML document
    html_content = f"""<!DOCTYPE html>
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
        .header {{
            background-color: #f0f0f0;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .header-item {{
            margin: 5px 0;
        }}
        .label {{
            font-weight: bold;
            display: inline-block;
            width: 80px;
        }}
        .content {{
            padding: 20px;
            background-color: #ffffff;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        .attachments {{
            margin-top: 20px;
            padding: 10px;
            background-color: #f9f9f9;
            border-radius: 5px;
        }}
        .attachment-item {{
            margin: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-item"><span class="label">From:</span> {from_addr}</div>
        <div class="header-item"><span class="label">To:</span> {to_addr}</div>
        <div class="header-item"><span class="label">Subject:</span> {subject}</div>
        <div class="header-item"><span class="label">Date:</span> {date}</div>
    </div>
    
    <div class="content">
        {body}
    </div>
"""

    # Add attachments list if any
    if email_data.get("attachments"):
        html_content += """
    <div class="attachments">
        <h3>Attachments:</h3>
"""
        for att in email_data["attachments"]:
            filename = html.escape(att.get("filename", ""))
            size = att.get("size", 0)
            size_kb = size / 1024
            html_content += (
                f'        <div class="attachment-item">📎 {filename} ({size_kb:.1f} KB)</div>\n'
            )

        html_content += "    </div>\n"

    html_content += """
</body>
</html>"""

    return html_content


def clean_html_for_pdf(html_content: str) -> str:
    """Clean and simplify HTML for better PDF conversion"""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove scripts, styles, and other problematic elements
    for tag in soup(["script", "style", "meta", "link"]):
        tag.decompose()

    # Remove external images that might cause issues
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith(("http://", "https://", "//")):
            img["alt"] = f"[Image: {img.get('alt', 'external image')}]"
            img["src"] = ""

    # Simplify overly complex styles
    for element in soup.find_all(style=True):
        style = element["style"]
        # Keep only basic styles
        allowed_props = [
            "color",
            "background-color",
            "font-weight",
            "font-size",
            "text-align",
        ]
        style_parts = []
        for prop in style.split(";"):
            if any(allowed in prop for allowed in allowed_props):
                style_parts.append(prop.strip())
        element["style"] = "; ".join(style_parts)

    return str(soup)


def convert_email_to_pdf(html_content: str, output_path: Path) -> None:
    """Convert HTML to PDF using Playwright"""
    # Check HTML size (limit to 10MB)
    MAX_HTML_SIZE = 10 * 1024 * 1024
    if len(html_content) > MAX_HTML_SIZE:
        raise WorkflowError(
            f"HTML content too large: {len(html_content) / 1024 / 1024:.1f}MB (max: 10MB)",
            recovery_hint="Email is too large to convert to PDF",
        )

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

            # Block external requests for security and performance
            page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.url.startswith(("http://", "https://"))
                    else route.continue_()
                ),
            )

            # Set content with timeout
            page.set_content(html_content, timeout=30000)  # 30 second timeout

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

        logger.info(f"Successfully created PDF: {output_path}")
    except WorkflowError:
        raise
    except Exception as e:
        raise WorkflowError(
            f"PDF conversion failed: {e}",
            recovery_hint="Check if Playwright is properly installed",
        )


def save_email_as_pdf(
    email_data: Dict[str, Any],
    message_obj: Optional[Message] = None,
    directory: str = "~/receipts",
    filename_template: str = "{date}_{from}_{subject}.pdf",
) -> None:
    """
    Save email as PDF file using Playwright.

    Note: Requires Playwright browsers to be installed:
        playwright install chromium

    Args:
        email_data: Extracted email data
        message_obj: Original email Message object (for better HTML extraction)
        directory: Directory to save PDF
        filename_template: Template for filename generation
    """
    try:
        # Validate directory - allow the provided directory as base
        dir_path = validate_path(directory, allowed_base_dirs=[os.path.expanduser("~"), directory])
        dir_path.mkdir(parents=True, exist_ok=True)

        # Generate filename from template
        from_domain = email_data.get("features", {}).get("from_domain", "unknown")
        date_str = datetime.now().strftime("%Y%m%d")

        # Parse date from email if available
        if email_data.get("date"):
            try:
                from email.utils import parsedate_to_datetime

                email_date = parsedate_to_datetime(email_data["date"])
                date_str = email_date.strftime("%Y%m%d")
            except:
                pass

        # Build filename
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

        output_path = dir_path / filename

        # Check if file exists
        if output_path.exists():
            base = output_path.stem
            counter = 1
            while output_path.exists():
                output_path = dir_path / f"{base}_{counter}.pdf"
                counter += 1

        # Convert email to HTML
        html_content = email_to_html(email_data, message_obj)

        # Convert to PDF using Playwright
        convert_email_to_pdf(html_content, output_path)

        print(f"  ✓ Saved email as PDF: {output_path}")

    except Exception as e:
        if isinstance(e, WorkflowError):
            raise
        raise WorkflowError(
            f"Failed to save email as PDF: {e}",
            recovery_hint="Check directory permissions and PDF library installation",
        )
