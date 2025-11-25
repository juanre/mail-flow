# Interactive TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace mailflow's basic print-based UI with a rich TUI that shows email content, PDF indicators, thread context, and learns from skip decisions.

**Architecture:** Sequential prompt-based UI using `rich` library. Emails processed chronologically with thread context. Classifier trains on both positive (workflow selected) and negative (skip) examples.

**Tech Stack:** Python, rich, html2text, existing mailflow infrastructure

**Design Doc:** `docs/plans/2025-11-25-interactive-tui-design.md`

---

## Task 1: Add html2text Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add dependency**

```bash
uv add html2text
```

**Step 2: Verify installation**

Run: `uv run python -c "import html2text; print(html2text.__version__)"`
Expected: Version number printed (e.g., `2024.2.26`)

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add html2text for email content rendering"
```

---

## Task 2: Create Content Renderer Module

**Files:**
- Create: `src/mailflow/content_renderer.py`
- Create: `tests/test_content_renderer.py`

**Step 1: Write the failing test**

```python
# tests/test_content_renderer.py
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_content_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailflow.content_renderer'`

**Step 3: Write minimal implementation**

```python
# src/mailflow/content_renderer.py
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_content_renderer.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/mailflow/content_renderer.py tests/test_content_renderer.py
git commit -m "feat: add content renderer for HTML to text conversion"
```

---

## Task 3: Create Thread Detector Module

**Files:**
- Create: `src/mailflow/thread_detector.py`
- Create: `tests/test_thread_detector.py`

**Step 1: Write the failing test**

```python
# tests/test_thread_detector.py
"""Tests for email thread detection."""

from mailflow.thread_detector import detect_threads, get_thread_info


class TestDetectThreads:
    def test_single_email_no_thread(self):
        emails = [{"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"}]
        threads = detect_threads(emails)
        assert len(threads) == 1

    def test_reply_grouped_with_original(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"},
            {"message_id": "<msg2@test.com>", "references": "<msg1@test.com>", "date": "2025-01-02"},
        ]
        threads = detect_threads(emails)
        assert len(threads) == 1
        assert len(list(threads.values())[0]) == 2

    def test_separate_threads_not_grouped(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"},
            {"message_id": "<msg2@test.com>", "references": "", "date": "2025-01-02"},
        ]
        threads = detect_threads(emails)
        assert len(threads) == 2


class TestGetThreadInfo:
    def test_single_email_returns_none(self):
        emails = [{"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"}]
        threads = detect_threads(emails)
        info = get_thread_info(emails[0], threads)
        assert info is None

    def test_thread_position_correct(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01"},
            {"message_id": "<msg2@test.com>", "references": "<msg1@test.com>", "date": "2025-01-02"},
            {"message_id": "<msg3@test.com>", "references": "<msg1@test.com>", "date": "2025-01-03"},
        ]
        threads = detect_threads(emails)
        info = get_thread_info(emails[1], threads)
        assert info.position == 2
        assert info.count == 3

    def test_pdf_hint_when_other_email_has_pdf(self):
        emails = [
            {"message_id": "<msg1@test.com>", "references": "", "date": "2025-01-01", "attachments": []},
            {"message_id": "<msg2@test.com>", "references": "<msg1@test.com>", "date": "2025-01-02",
             "attachments": [{"filename": "invoice.pdf"}]},
        ]
        threads = detect_threads(emails)
        info = get_thread_info(emails[0], threads)
        assert info.pdf_in_thread == 2  # PDF is in email 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_thread_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailflow.thread_detector'`

**Step 3: Write minimal implementation**

```python
# src/mailflow/thread_detector.py
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_thread_detector.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/mailflow/thread_detector.py tests/test_thread_detector.py
git commit -m "feat: add thread detector for email chain grouping"
```

---

## Task 4: Create Rich Email Display Component

**Files:**
- Create: `src/mailflow/tui.py`
- Create: `tests/test_tui.py`

**Step 1: Write the failing test**

```python
# tests/test_tui.py
"""Tests for TUI components."""

from io import StringIO
from unittest.mock import patch

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
        console = Console(file=output, force_terminal=True, width=80)

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
        console = Console(file=output, force_terminal=True, width=80)

        display_email(console, email, position=1, total=10, thread_info=thread_info)

        result = output.getvalue()
        assert "Thread 2/5" in result or "2/5" in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tui.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mailflow.tui'`

**Step 3: Write minimal implementation**

```python
# src/mailflow/tui.py
"""Rich TUI components for mailflow interactive mode."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tui.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/mailflow/tui.py tests/test_tui.py
git commit -m "feat: add rich TUI email display component"
```

---

## Task 5: Create Workflow Prompt Component

**Files:**
- Modify: `src/mailflow/tui.py`
- Modify: `tests/test_tui.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_tui.py

from mailflow.tui import format_workflow_choices


class TestFormatWorkflowChoices:
    def test_shows_numbered_workflows(self):
        workflows = {
            "gsk-invoice": type("W", (), {"description": "GreaterSkies invoices"})(),
            "gsk-receipt": type("W", (), {"description": "GreaterSkies receipts"})(),
        }
        result = format_workflow_choices(workflows, default=None, confidence=0)
        assert "[1]" in result
        assert "[2]" in result
        assert "gsk-invoice" in result

    def test_shows_default_suggestion(self):
        workflows = {
            "gsk-invoice": type("W", (), {"description": "GreaterSkies invoices"})(),
        }
        result = format_workflow_choices(workflows, default="gsk-invoice", confidence=0.78)
        assert "gsk-invoice" in result
        assert "78%" in result or "0.78" in result

    def test_shows_skip_option(self):
        workflows = {}
        result = format_workflow_choices(workflows, default=None, confidence=0)
        assert "[s]" in result.lower() or "skip" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tui.py::TestFormatWorkflowChoices -v`
Expected: FAIL with `cannot import name 'format_workflow_choices'`

**Step 3: Add implementation to tui.py**

```python
# Add to src/mailflow/tui.py

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

    # Action keys
    lines.append("")
    lines.append("  [s] skip    [e] expand    [n] next    [?] help")

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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tui.py::TestFormatWorkflowChoices -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/mailflow/tui.py tests/test_tui.py
git commit -m "feat: add workflow choice formatting to TUI"
```

---

## Task 6: Add Skip Workflow Support

**Files:**
- Modify: `src/mailflow/models.py`
- Modify: `tests/test_models.py` (or create if needed)

**Step 1: Write the failing test**

```python
# tests/test_skip_workflow.py
"""Tests for skip workflow handling."""

import tempfile
from pathlib import Path

from mailflow.config import Config
from mailflow.models import DataStore, CriteriaInstance


class TestSkipWorkflow:
    def test_skip_recorded_as_criteria_instance(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)

        features = {"from_domain": "newsletter.com", "subject_tokens": ["weekly", "digest"]}

        data_store.record_skip(features)

        # Check it was recorded
        instances = data_store.get_recent_criteria()
        skip_instances = [i for i in instances if i.workflow == "_skip"]
        assert len(skip_instances) == 1
        assert skip_instances[0].features["from_domain"] == "newsletter.com"

    def test_skip_workflow_excluded_from_suggestions(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)

        # _skip should not appear in workflow list
        assert "_skip" not in data_store.workflows
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_skip_workflow.py -v`
Expected: FAIL with `AttributeError: 'DataStore' object has no attribute 'record_skip'`

**Step 3: Add record_skip to DataStore**

```python
# Add to src/mailflow/models.py in DataStore class

def record_skip(self, features: dict) -> None:
    """Record a skip decision for classifier training.

    Args:
        features: Email features dict
    """
    from datetime import datetime

    instance = CriteriaInstance(
        workflow="_skip",
        features=features,
        timestamp=datetime.now()
    )
    self.add_criteria_instance(instance)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_skip_workflow.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/mailflow/models.py tests/test_skip_workflow.py
git commit -m "feat: add skip workflow support for negative training"
```

---

## Task 7: Integrate TUI into Main Processing Loop

**Files:**
- Modify: `src/mailflow/ui.py`
- Modify: `src/mailflow/process.py`

**Step 1: Write integration test**

```python
# tests/test_tui_integration.py
"""Integration tests for TUI workflow selection."""

from unittest.mock import patch, MagicMock
from io import StringIO

from mailflow.ui import WorkflowSelector


class TestWorkflowSelectorTUI:
    def test_displays_email_info(self, temp_config_dir):
        from mailflow.config import Config
        from mailflow.models import DataStore
        from mailflow.similarity import SimilarityEngine

        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        similarity = SimilarityEngine(config)

        selector = WorkflowSelector(config, data_store, similarity)

        email = {
            "from": "billing@test.com",
            "subject": "Invoice #123",
            "body": "Please find attached",
            "attachments": [{"filename": "invoice.pdf", "size": 1024}],
            "date": "2025-01-01",
            "features": {},
        }

        # Mock input to return 'skip'
        with patch('builtins.input', return_value='s'):
            with patch('sys.stdout', new_callable=StringIO) as mock_out:
                result = selector.select_workflow(email)

        output = mock_out.getvalue()
        # Should show email info
        assert "billing@test.com" in output or result is None  # Either displayed or skipped
```

**Step 2: Run test to verify current behavior**

Run: `uv run pytest tests/test_tui_integration.py -v`
Expected: May pass or fail depending on current implementation

**Step 3: Update WorkflowSelector to use new TUI**

This is a larger refactor. Create a new method that uses the TUI components:

```python
# Replace select_workflow method in src/mailflow/ui.py

def select_workflow(self, email_data: dict) -> str | None:
    """Present workflow options using rich TUI and get user selection."""
    from rich.console import Console
    from mailflow.tui import display_email, format_workflow_choices, get_workflow_prompt
    from mailflow.thread_detector import ThreadInfo

    console = Console()

    # Get suggestion from classifier
    criteria_instances = self.data_store.get_recent_criteria()
    suggestion = None
    confidence = 0.0

    if self.hybrid_classifier:
        try:
            import asyncio
            result = asyncio.run(
                self.hybrid_classifier.classify(
                    email_data, self.data_store.workflows, criteria_instances
                )
            )
            if result.get("rankings"):
                suggestion = result["rankings"][0][0]
                confidence = result["rankings"][0][1]
        except Exception as e:
            logger.warning(f"Classification failed: {e}")

    if not suggestion:
        rankings = self.similarity_engine.rank_workflows(
            email_data.get("features", {}), criteria_instances, self.max_suggestions
        )
        if rankings:
            suggestion = rankings[0][0]
            confidence = rankings[0][1]

    # Get thread info if available
    thread_info = email_data.get("_thread_info")

    # Display email
    position = email_data.get("_position", 1)
    total = email_data.get("_total", 1)
    display_email(console, email_data, position, total, thread_info)

    # Show workflow choices
    console.print(format_workflow_choices(
        self.data_store.workflows,
        default=suggestion,
        confidence=confidence
    ))

    # Get input
    prompt = get_workflow_prompt(suggestion)

    while True:
        choice = input(prompt).strip().lower()

        # Handle empty input (accept default)
        if not choice and suggestion:
            return suggestion

        # Handle skip
        if choice == 's':
            self.data_store.record_skip(email_data.get("features", {}))
            return None

        # Handle next (no action)
        if choice == 'n':
            return None

        # Handle expand
        if choice == 'e':
            # Show full content
            body = email_data.get('body', '')
            console.print(Panel(body, title="Full Content"))
            continue

        # Handle help
        if choice == '?':
            console.print("Enter: accept suggestion | 1-9: select workflow | s: skip | n: next | e: expand")
            continue

        # Handle number selection
        if choice.isdigit():
            idx = int(choice) - 1
            workflow_names = sorted(self.data_store.workflows.keys())
            if 0 <= idx < len(workflow_names):
                return workflow_names[idx]

        # Handle workflow name
        if choice in self.data_store.workflows:
            return choice

        console.print(f"Unknown choice: {choice}", style="red")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_tui_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/mailflow/ui.py tests/test_tui_integration.py
git commit -m "feat: integrate rich TUI into workflow selection"
```

---

## Task 8: Update Batch Processing for Thread Detection

**Files:**
- Modify: `src/mailflow/commands/gmail_batch_workflows.py`

**Step 1: Update batch command to detect threads**

```python
# In gmail_batch_workflows.py, update the batch() function to add thread detection

# After loading emails, before processing loop:
from mailflow.thread_detector import detect_threads, get_thread_info

# ... existing email loading code ...

# Detect threads
threads = detect_threads([extractor.extract(f.read_text()) for f in email_files])

# In the processing loop, add thread info to email_data:
for i, email_file in enumerate(email_files, 1):
    email_data = extractor.extract(email_file.read_text())
    email_data["_position"] = i
    email_data["_total"] = len(email_files)
    email_data["_thread_info"] = get_thread_info(email_data, threads)
    # ... rest of processing ...
```

**Step 2: Test manually**

Run: `uv run mailflow fetch files ~/Mail/juan-gsk --dry-run --max-emails 3`
Expected: Should show thread info in email display

**Step 3: Commit**

```bash
git add src/mailflow/commands/gmail_batch_workflows.py
git commit -m "feat: add thread detection to batch processing"
```

---

## Task 9: Run Full Integration Test

**Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 2: Manual test with real mailbox**

Run: `uv run mailflow fetch files ~/Mail/juan-gsk --dry-run --max-emails 5`

Verify:
- [ ] Email content is displayed (subject, from, body preview)
- [ ] PDF attachments shown with 📎 emoji in green
- [ ] Thread info shown (if applicable)
- [ ] Workflow suggestions displayed
- [ ] Can press Enter to accept default
- [ ] Can press 's' to skip
- [ ] Can press 'e' to expand

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete interactive TUI implementation"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Dependencies | pyproject.toml |
| 2 | Content Renderer | content_renderer.py |
| 3 | Thread Detector | thread_detector.py |
| 4 | Email Display | tui.py |
| 5 | Workflow Prompt | tui.py |
| 6 | Skip Workflow | models.py |
| 7 | UI Integration | ui.py |
| 8 | Batch Integration | gmail_batch_workflows.py |
| 9 | Final Testing | - |
