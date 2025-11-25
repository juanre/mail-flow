# Interactive TUI Design for Mailflow

## Overview

Redesign mailflow's interactive email processing UI using `rich` library to enable informed workflow decisions.

## Requirements

- **Display**: Subject, rendered content (HTML→text), PDF attachments with names
- **Thread awareness**: Show position within email chain, hint if PDF exists in another email
- **Learning**: Train classifier on both positive (workflow selected) and negative (skip) examples
- **Default suggestion**: Similarity engine suggests workflow, Enter accepts

## UI Layout (Sequential Approach)

```
━━━ Email 12/47 (Thread 2/5 - PDF in email 4) ━━━━━━━━
From: billing@cloudflare.com
Subject: Invoice #CF-2025-1234
📎 Cloudflare_Invoice_Nov2025.pdf (142KB)

┌─ Preview ─────────────────────────────────────────┐
│ Your invoice for November 2025 is attached.      │
│ Amount due: $45.00                               │
│ Payment due: December 1, 2025                    │
│ [...more - press e to expand]                    │
└──────────────────────────────────────────────────┘

Suggested: gsk-invoice (78% confidence)

Workflows:
  [1] gsk-invoice ←   [2] gsk-receipt    [3] gsk-tax-doc
  [4] tsm-invoice     [5] tsm-receipt    [6] tsm-tax-doc

  [s] skip    [e] expand    [n] next    [?] help

Choice [Enter=gsk-invoice]: _
```

## Keybindings

| Key | Action | Training Effect |
|-----|--------|-----------------|
| Enter | Accept suggested workflow | Positive reinforcement |
| 1-9 | Select workflow by number | Correction signal |
| s | Skip (don't archive) | Negative example |
| e | Expand full content | None (re-prompts) |
| n | Next without action | None |
| ? | Show help | None |

## Components

### 1. Email Display (`display_email`)

Renders email header, PDF indicator, and body preview using `rich`:

- Thread position in header: `(Thread 2/5)`
- PDF attachments highlighted in green with 📎 emoji
- HTML body converted to plain text via `html2text`
- Truncated to 8 lines, expandable with `e`

### 2. Thread Detection (`detect_threads`)

Groups emails by conversation using `In-Reply-To` and `References` headers:

```python
def detect_threads(emails: list[dict]) -> dict[str, list[dict]]:
    threads = {}
    for email in emails:
        references = email.get('references', '').split()
        thread_id = references[0] if references else email.get('message_id')
        threads.setdefault(thread_id, []).append(email)
    return threads
```

Provides context hints:
- `(Thread 1/3 - first in chain)` for first email
- `(Thread 2/5 - PDF in email 4)` when another email has attachment

### 3. Content Rendering (`render_email_body`)

Converts HTML to readable text:

```python
def render_email_body(body: str, is_html: bool, max_lines: int = 8) -> str:
    if is_html:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 80
        text = h.handle(body)
    else:
        text = body

    lines = text.strip().split('\n')[:max_lines]
    return '\n'.join(lines)
```

### 4. Workflow Selection (`prompt_workflow_choice`)

- Shows suggested workflow as default (if confidence > threshold)
- Number keys for quick selection
- Tab completion for typing workflow names
- Returns choice for processing

### 5. Skip Workflow & Training

Reserved `_skip` workflow for negative examples:

```python
def record_skip(email_data: dict, data_store: DataStore):
    criteria = CriteriaInstance(
        workflow="_skip",
        features=email_data['features'],
        timestamp=datetime.now()
    )
    data_store.add_criteria_instance(criteria)
    tracker.mark_as_processed(message, message_id, workflow="_skip")
```

Classifier learns:
- Emails similar to past skips → suggest skip
- Reduces noise from newsletters, casual replies, etc.

## Processing Flow

```python
def process_mailbox_interactive(emails, config):
    threads = detect_threads(emails)
    sorted_emails = sorted(emails, key=lambda e: e.get('date', ''))

    for i, email in enumerate(sorted_emails, 1):
        thread_info = get_thread_info(email, threads)
        suggestion = similarity_engine.get_suggestion(email['features'])

        display_email(email, i, len(sorted_emails), thread_info)

        choice = prompt_workflow_choice(
            workflows=data_store.workflows,
            default=suggestion.workflow if suggestion else None
        )

        if choice == 'skip':
            record_skip(email, data_store)
        elif choice == 'next':
            pass
        elif choice == 'expand':
            show_full_content(email)
            continue
        else:
            execute_workflow(email, choice, config)
            record_positive_example(email, choice, data_store)
```

## Dependencies

New dependencies required:
- `html2text` - HTML to text conversion

Already available:
- `rich` - TUI rendering

## File Changes

| File | Changes |
|------|---------|
| `src/mailflow/ui.py` | Replace `WorkflowSelector` with new TUI components |
| `src/mailflow/thread_detector.py` | New file for thread grouping |
| `src/mailflow/content_renderer.py` | New file for HTML→text |
| `src/mailflow/models.py` | Handle `_skip` as reserved workflow |
| `pyproject.toml` | Add `html2text` dependency |
