# ABOUTME: Rich TUI components for mailflow interactive mode.
"""Rich TUI components for mailflow interactive mode."""

from rich.console import Console
from rich.panel import Panel

from mailflow.content_renderer import render_email_body
from mailflow.thread_detector import ThreadInfo


def format_size(size_bytes: int) -> str:
    """Format file size in human readable form."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024}KB"
    else:
        return f"{size_bytes // (1024 * 1024)}MB"


def format_attachment_indicator(attachments: list[dict]) -> str:
    """Format attachment list with PDF highlighting.

    Args:
        attachments: List of attachment dicts with filename and size

    Returns:
        Formatted string with attachments, PDFs get 📎 emoji
    """
    if not attachments:
        return ""

    lines = []
    for att in attachments:
        filename = att.get('filename', 'unknown')
        size = att.get('size', 0)
        size_str = format_size(size) if size else ''

        if filename.lower().endswith('.pdf'):
            lines.append(f"📎 {filename} ({size_str})")
        else:
            lines.append(f"   {filename} ({size_str})")

    return '\n'.join(lines)


def display_email(
    console: Console,
    email: dict,
    position: int,
    total: int,
    thread_info: ThreadInfo | None,
    max_preview_lines: int = 8
) -> None:
    """Display email with rich formatting.

    Args:
        console: Rich console to write to
        email: Email data dict
        position: Current position (1-indexed)
        total: Total emails
        thread_info: Thread context or None
        max_preview_lines: Max lines for body preview
    """
    # Build header line
    header = f"━━━ Email {position}/{total}"
    if thread_info:
        header += f" (Thread {thread_info.position}/{thread_info.count}"
        if thread_info.is_first:
            header += " - first in chain"
        elif thread_info.pdf_in_thread:
            header += f" - PDF in email {thread_info.pdf_in_thread}"
        header += ")"
    header += " " + "━" * max(0, 50 - len(header))

    console.print(header, style="bold blue")

    # From and Subject
    console.print(f"From: {email.get('from', 'unknown')}")
    console.print(f"Subject: {email.get('subject', '(no subject)')}", style="bold")

    # Date
    if email.get('date'):
        console.print(f"Date: {email.get('date')}", style="dim")

    # Attachments with PDF highlighting
    attachments = email.get('attachments', [])
    att_indicator = format_attachment_indicator(attachments)
    if att_indicator:
        console.print(att_indicator, style="bold green")

    # Body preview
    body = email.get('body', '')
    is_html = '<html' in body.lower() or '<body' in body.lower()
    preview = render_email_body(body, is_html=is_html, max_lines=max_preview_lines)

    if preview.strip():
        console.print(Panel(preview, title="Preview", border_style="dim"))

    console.print()
