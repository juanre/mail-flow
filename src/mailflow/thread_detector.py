# ABOUTME: Email thread detection using References and In-Reply-To headers.
"""Email thread detection using References and In-Reply-To headers."""

from dataclasses import dataclass


@dataclass
class ThreadInfo:
    """Information about an email's position in a thread."""
    position: int  # 1-indexed position in thread
    count: int  # Total emails in thread
    is_first: bool  # Is this the first email in the thread
    pdf_in_thread: int | None  # Position of email with PDF, if not this one


def detect_threads(emails: list[dict]) -> dict[str, list[dict]]:
    """Group emails by thread using References header.

    Args:
        emails: List of email dicts with message_id, references, date

    Returns:
        Dict mapping thread_id to list of emails in that thread (sorted by date)
    """
    threads: dict[str, list[dict]] = {}

    for email in emails:
        references = (email.get('references') or '').split()
        # Thread ID is first reference (original message) or own message_id
        thread_id = references[0] if references else email.get('message_id', '')

        if thread_id not in threads:
            threads[thread_id] = []
        threads[thread_id].append(email)

    # Sort each thread by date
    for thread_id in threads:
        threads[thread_id].sort(key=lambda e: e.get('date', ''))

    return threads


def get_thread_info(email: dict, threads: dict[str, list[dict]]) -> ThreadInfo | None:
    """Get thread context for an email.

    Args:
        email: The email to get info for
        threads: Thread dict from detect_threads()

    Returns:
        ThreadInfo if email is part of a multi-email thread, None otherwise
    """
    # Find which thread this email belongs to
    references = (email.get('references') or '').split()
    thread_id = references[0] if references else email.get('message_id', '')

    thread_emails = threads.get(thread_id, [])

    # Single email threads don't need thread info
    if len(thread_emails) <= 1:
        return None

    # Find position in thread
    position = 1
    for i, e in enumerate(thread_emails, 1):
        if e.get('message_id') == email.get('message_id'):
            position = i
            break

    # Check if another email in thread has PDF
    pdf_in_thread = None
    for i, e in enumerate(thread_emails, 1):
        if e.get('message_id') == email.get('message_id'):
            continue
        attachments = e.get('attachments', [])
        has_pdf = any(a.get('filename', '').lower().endswith('.pdf') for a in attachments)
        if has_pdf:
            pdf_in_thread = i
            break

    return ThreadInfo(
        position=position,
        count=len(thread_emails),
        is_first=(position == 1),
        pdf_in_thread=pdf_in_thread
    )
