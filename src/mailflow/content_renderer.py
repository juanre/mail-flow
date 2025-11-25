# ABOUTME: Email content rendering - converts HTML to text and handles truncation.
"""Email content rendering - converts HTML to text and handles truncation."""

import html2text


def render_email_body(body: str, is_html: bool, max_lines: int = 8) -> str:
    """Convert email body to displayable text.

    Args:
        body: Email body content
        is_html: Whether the body is HTML
        max_lines: Maximum lines to show in preview

    Returns:
        Rendered text, truncated with indicator if needed
    """
    if is_html:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 80
        text = h.handle(body)
    else:
        text = body

    lines = text.strip().split('\n')

    if len(lines) > max_lines:
        preview_lines = lines[:max_lines]
        preview = '\n'.join(preview_lines)
        preview += '\n[...more - press e to expand]'
        return preview

    return '\n'.join(lines)
