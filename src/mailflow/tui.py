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
    if attachments:
        att_indicator = format_attachment_indicator(attachments)
        console.print(att_indicator, style="bold green")
    else:
        console.print("(no attachments)", style="dim")

    # Body preview
    body = email.get('body', '')
    is_html = '<html' in body.lower() or '<body' in body.lower()
    preview = render_email_body(body, is_html=is_html, max_lines=max_preview_lines)

    if preview.strip():
        console.print(Panel(preview, title="Preview", border_style="dim"))

    console.print()


def format_workflow_choices(
    workflows: dict,
    default: str | None,
    confidence: float
) -> str:
    """Format workflow choices for display.

    Args:
        workflows: Dict of workflow name -> WorkflowDefinition
        default: Suggested default workflow name or None
        confidence: Confidence score for default (0-1)

    Returns:
        Formatted string showing workflow options
    """
    lines = []

    # Show suggestion if we have one
    if default and confidence > 0:
        lines.append(f"Suggested: {default} ({confidence:.0%} confidence)")
        lines.append("")

    # Show workflows in rows of 3
    lines.append("Workflows:")
    workflow_names = sorted(workflows.keys())
    row = []
    for i, name in enumerate(workflow_names, 1):
        marker = " ←" if name == default else ""
        row.append(f"[{i}] {name}{marker}")
        if len(row) == 3:
            lines.append("  " + "  ".join(row))
            row = []
    if row:
        lines.append("  " + "  ".join(row))

    # Action keys - escape brackets with backslash so Rich doesn't interpret as markup
    lines.append("")
    lines.append("  \\[s] skip    \\[e] expand    \\[n] next    \\[?] help")

    return '\n'.join(lines)


def get_workflow_prompt(default: str | None) -> str:
    """Get the input prompt string.

    Args:
        default: Default workflow name or None

    Returns:
        Prompt string for input
    """
    if default:
        return f"Choice [Enter={default}]: "
    return "Choice: "
