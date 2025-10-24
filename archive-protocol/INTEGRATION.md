# Connector Integration Guide

This guide shows how to build a connector that uses archive-protocol to write to the shared repository.

## Quick Start - Build a Connector

### 1. Create Package

```bash
uv init my-connector
cd my-connector
uv add archive-protocol
```

### 2. Basic Connector Structure

```python
# src/my_connector/writer.py
from archive_protocol import RepositoryWriter
from datetime import datetime

class MyConnector:
    """Fetch and archive content from My Source."""

    def __init__(self, entity: str, archive_path: str = "~/Archive"):
        self.entity = entity
        self.writer = RepositoryWriter(
            base_path=archive_path,
            entity=entity
        )

    def sync(self):
        """Fetch content and write to archive."""
        # 1. Fetch from your source
        items = self.fetch_from_source()

        # 2. Process each item
        for item in items:
            # 3. Classify (workflow or stream?)
            workflow = self.classify(item)

            if workflow:
                # Classified document -> workflows/
                self.write_document(item, workflow)
            else:
                # Unclassified -> streams/
                self.write_stream(item)

    def write_document(self, item, workflow):
        """Write classified document to workflows/."""
        result = self.writer.write_document(
            source="mysource",
            workflow=workflow,
            content=item.content_bytes,
            filename=item.filename,
            document_type=item.type,
            origin_metadata={
                "mysource": {
                    "item_id": item.id,
                    "created": item.created_at.isoformat(),
                    # ... other source-specific fields
                }
            }
        )
        return result

    def write_stream(self, item):
        """Write unclassified content to streams/."""
        result = self.writer.write_stream(
            source="mysource",
            stream_context=item.context,  # e.g., channel, folder
            content=item.content,
            filename=f"{item.date}.md",
            origin_metadata={
                "mysource": {
                    "context_id": item.context_id,
                    # ... other fields
                }
            }
        )
        return result
```

### 3. Add CLI

```python
# src/my_connector/cli.py
import click
from my_connector.writer import MyConnector

@click.command()
@click.option("--entity", required=True, help="Entity identifier (jro, tsm, gsk)")
@click.option("--archive-path", default="~/Archive", help="Archive base path")
def sync(entity, archive_path):
    """Sync content from My Source to archive."""
    connector = MyConnector(entity=entity, archive_path=archive_path)
    count = connector.sync()
    click.echo(f"Synced {count} items to {archive_path}")

if __name__ == "__main__":
    sync()
```

### 4. Test and Deploy

```bash
# Test
uv run my-connector sync --entity jro

# Verify files created
ls ~/Archive/entities/jro/workflows/
ls ~/Archive/entities/jro/streams/
```

## Classification Strategies

### Strategy 1: Manual Rules

Map source context to workflows:
```python
WORKFLOW_MAPPINGS = {
    "expenses-channel": "jro-expense",
    "invoices-folder": "jro-invoice",
    "tax-docs": "jro-tax-doc"
}

def classify(item):
    return WORKFLOW_MAPPINGS.get(item.context)
```

### Strategy 2: Filename Patterns

```python
import re

PATTERNS = [
    (r"invoice.*\.pdf", "jro-invoice"),
    (r"receipt.*\.pdf", "jro-expense"),
    (r".*contract.*\.pdf", "jro-contract"),
]

def classify(item):
    for pattern, workflow in PATTERNS:
        if re.match(pattern, item.filename, re.IGNORECASE):
            return workflow
    return None
```

### Strategy 3: LLM Classification

```python
from llmring import Chat

async def classify_with_llm(item):
    """Use LLM to classify documents to workflows."""
    prompt = f"""
    Classify this document to a workflow:
    Filename: {item.filename}
    Content preview: {item.content[:500]}

    Available workflows:
    - jro-expense: Receipts and expense documents
    - jro-invoice: Invoices
    - jro-tax-doc: Tax documents
    - jro-contract: Contracts and agreements

    Respond with just the workflow name or "unclassified".
    """

    chat = Chat()
    response = await chat.ask(prompt)

    workflow = response.strip().lower()
    if workflow in ["jro-expense", "jro-invoice", "jro-tax-doc", "jro-contract"]:
        return workflow
    return None
```

### Strategy 4: Interactive Prompts

```python
import click

def classify_interactive(item):
    """Ask user to classify."""
    click.echo(f"\nClassify: {item.filename}")
    click.echo(f"Preview: {item.content[:200]}")

    workflows = ["jro-expense", "jro-invoice", "jro-tax-doc", "skip"]
    for i, w in enumerate(workflows, 1):
        click.echo(f"  {i}. {w}")

    choice = click.prompt("Select workflow", type=int)
    selected = workflows[choice - 1]

    return None if selected == "skip" else selected
```

## Real-World Examples

### Example 1: Slack Connector

```python
from archive_protocol import RepositoryWriter
from slack_sdk import WebClient
from datetime import datetime
import json

class SlackArchive:
    def __init__(self, entity: str, token: str):
        self.entity = entity
        self.slack = WebClient(token=token)
        self.writer = RepositoryWriter(
            base_path="~/Archive",
            entity=entity
        )

    def sync_channel(self, channel: str, date: str):
        """Sync one day of Slack messages for a channel."""
        # Fetch messages
        messages = self._fetch_messages(channel, date)

        # Render as markdown
        markdown = self._render_markdown(messages)

        # Write to streams/ (unclassified conversation)
        self.writer.write_stream(
            source="slack",
            stream_context=channel,
            content=markdown,
            filename=f"{date}.md",
            origin_metadata={
                "slack": {
                    "channel_id": self._get_channel_id(channel),
                    "channel_name": channel,
                    "message_count": len(messages),
                    "date": date
                }
            },
            created_at=datetime.fromisoformat(f"{date}T00:00:00")
        )

        # Also save raw JSON
        self.writer.write_stream(
            source="slack",
            stream_context=channel,
            content=json.dumps(messages, indent=2),
            filename=f"{date}.json",
            origin_metadata={"slack": {"raw": True}},
            created_at=datetime.fromisoformat(f"{date}T00:00:00")
        )

        # Process attachments
        for msg in messages:
            for file in msg.get("files", []):
                self._process_attachment(file, channel)

    def _process_attachment(self, file, channel):
        """Process Slack attachment - classify if possible."""
        # Try to classify based on channel
        workflow = self._classify_channel(channel)

        if workflow and file["mimetype"] == "application/pdf":
            # Download and write to workflows/
            content = self._download_file(file["url"])

            self.writer.write_document(
                source="slack",
                workflow=workflow,
                content=content,
                filename=file["name"],
                document_type="document",
                origin_metadata={
                    "slack": {
                        "channel": channel,
                        "user": file["user"],
                        "timestamp": file["timestamp"],
                        "permalink": file["permalink"]
                    }
                }
            )
```

### Example 2: Local Document Scanner

```python
from archive_protocol import RepositoryWriter
from pathlib import Path
import mimetypes

class LocalDocsSync:
    def __init__(self, entity: str):
        self.entity = entity
        self.writer = RepositoryWriter(
            base_path="~/Archive",
            entity=entity
        )

    def sync_directory(self, source_dir: Path, workflow: str):
        """Sync local directory to a workflow."""
        for file_path in source_dir.glob("**/*"):
            if not file_path.is_file():
                continue

            # Skip hidden files
            if file_path.name.startswith("."):
                continue

            # Read content
            with open(file_path, "rb") as f:
                content = f.read()

            # Determine mimetype
            mimetype, _ = mimetypes.guess_type(file_path)
            mimetype = mimetype or "application/octet-stream"

            # Write to archive
            self.writer.write_document(
                source="localdocs",
                workflow=workflow,
                content=content,
                filename=file_path.name,
                document_type="document",
                origin_metadata={
                    "localdocs": {
                        "original_path": str(file_path),
                        "mtime": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    }
                },
                created_at=datetime.fromtimestamp(file_path.stat().st_mtime)
            )
```

## Handling Special Cases

### Large Files

```python
def write_large_file(self, file_path: Path, workflow: str):
    """Write large file without loading into memory."""
    # For files, RepositoryWriter accepts Path
    result = self.writer.write_document(
        source="localdocs",
        workflow=workflow,
        content=file_path,  # Pass Path, not bytes
        filename=file_path.name,
        document_type="document",
        origin_metadata={...}
    )
```

### Attachments with Main Document

```python
def write_email_with_attachments(self, email):
    """Write email PDF with image attachments."""
    # Prepare attachments
    attachments = []
    for att in email.attachments:
        if att.mimetype.startswith("image/"):
            attachments.append((att.filename, att.content))

    # Write main document with attachments
    result = self.writer.write_document(
        source="mail",
        workflow="jro-expense",
        content=email.pdf_bytes,
        filename=f"{email.subject}.pdf",
        document_type="receipt",
        origin_metadata={...},
        attachments=attachments  # Will be saved alongside
    )

    # Attachments get names like:
    # 2025-10-23-mail-receipt-logo.png
```

### Deduplication

```python
from archive_protocol import compute_hash

def write_with_dedup(self, content: bytes, filename: str):
    """Check if content already exists before writing."""
    content_hash = compute_hash(content)

    # Check if hash exists in your tracker
    if self.is_already_archived(content_hash):
        logger.info(f"Skipping duplicate: {filename}")
        return None

    # Write new document
    result = self.writer.write_document(...)

    # Track hash
    self.mark_as_archived(content_hash, result["document_id"])

    return result
```

## Testing Your Connector

### Test Template

```python
# tests/test_my_connector.py
import pytest
from pathlib import Path
from my_connector import MyConnector

@pytest.fixture
def temp_archive(tmp_path):
    """Create temporary archive directory."""
    archive = tmp_path / "archive"
    archive.mkdir()
    return archive

def test_sync_creates_files(temp_archive):
    """Test connector creates files in correct structure."""
    connector = MyConnector(
        entity="test",
        archive_path=str(temp_archive)
    )

    # Sync content
    connector.sync()

    # Verify structure
    workflows_dir = temp_archive / "entities" / "test" / "workflows"
    assert workflows_dir.exists()

    # Verify files created
    files = list(workflows_dir.rglob("*.pdf"))
    assert len(files) > 0

    # Verify metadata
    metadata_files = list(
        (temp_archive / "entities" / "test" / "metadata" / "workflows").rglob("*.json")
    )
    assert len(metadata_files) == len(files)
```

## Common Patterns

### Pattern 1: Batch Processing

```python
def sync_batch(self, items, workflow):
    """Process multiple items efficiently."""
    results = []
    failed = []

    for item in items:
        try:
            result = self.writer.write_document(
                source="mysource",
                workflow=workflow,
                content=item.content,
                filename=item.name,
                document_type="document",
                origin_metadata={"mysource": item.metadata}
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to write {item.name}: {e}")
            failed.append(item.name)

    logger.info(f"Synced {len(results)} items, {len(failed)} failed")
    return results, failed
```

### Pattern 2: Incremental Sync

```python
class IncrementalConnector:
    """Only sync new items since last run."""

    def __init__(self, entity: str):
        self.entity = entity
        self.writer = RepositoryWriter(base_path="~/Archive", entity=entity)
        self.tracker_file = Path("~/.config/my-connector/last-sync.txt").expanduser()

    def sync(self):
        """Sync only new items."""
        # Load last sync timestamp
        last_sync = self._load_last_sync()

        # Fetch items since last sync
        items = self.fetch_since(last_sync)

        # Write to archive
        for item in items:
            self.writer.write_document(...)

        # Update tracker
        self._save_last_sync(datetime.now())

    def _load_last_sync(self) -> datetime:
        if self.tracker_file.exists():
            with open(self.tracker_file) as f:
                return datetime.fromisoformat(f.read().strip())
        return datetime(2000, 1, 1)  # Beginning of time

    def _save_last_sync(self, timestamp: datetime):
        self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tracker_file, "w") as f:
            f.write(timestamp.isoformat())
```

### Pattern 3: With Deduplication

```python
from archive_protocol import compute_hash
import sqlite3

class DeduplicatingConnector:
    """Track processed items to avoid duplicates."""

    def __init__(self, entity: str):
        self.entity = entity
        self.writer = RepositoryWriter(base_path="~/Archive", entity=entity)
        self.db_path = Path("~/.config/my-connector/processed.db").expanduser()
        self._init_db()

    def _init_db(self):
        """Create tracking database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed (
                    source_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    processed_at TIMESTAMP NOT NULL
                )
            """)

    def write_if_new(self, source_id: str, content: bytes, **kwargs):
        """Write only if not already processed."""
        # Check if already processed
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT document_id FROM processed WHERE source_id = ?",
                (source_id,)
            )
            if cursor.fetchone():
                logger.info(f"Skipping duplicate: {source_id}")
                return None

        # Compute hash
        content_hash = compute_hash(content)

        # Check hash
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT document_id FROM processed WHERE content_hash = ?",
                (content_hash,)
            )
            if cursor.fetchone():
                logger.info(f"Skipping duplicate content: {source_id}")
                return None

        # Write to archive
        result = self.writer.write_document(content=content, **kwargs)

        # Track as processed
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO processed VALUES (?, ?, ?, ?)",
                (source_id, content_hash, result["document_id"], datetime.now())
            )

        return result
```

## Metadata Best Practices

### What to Put in origin_metadata

**Always include:**
- Source identifier (message ID, doc ID, file path)
- Created/modified timestamp from source
- Creator/sender/author information

**Often useful:**
- URL or permalink to original
- Source-specific classification (labels, tags, folders)
- Access control info (who can see it)
- Modification history

**Example for email (mail):**
```python
origin_metadata = {
    "mail": {
        "message_id": "<unique@domain.com>",
        "subject": "Email subject",
        "from": "sender@example.com",
        "to": ["recipient@example.com"],
        "cc": ["other@example.com"],
        "date": "2025-10-23T13:44:57Z",
        "thread_id": "thread-123",
        "labels": ["Important", "Work"],
        "workflow_name": "jro-expense",
        "confidence_score": 0.91,
        "has_attachments": True
    }
}
```

**Example for Slack:**
```python
origin_metadata = {
    "slack": {
        "channel_id": "C12345ABC",
        "channel_name": "expenses",
        "message_ts": "1634567890.123456",
        "user_id": "U9876XYZ",
        "user_name": "john.doe",
        "thread_ts": "1634567890.123456",  # If part of thread
        "permalink": "https://workspace.slack.com/archives/...",
        "reaction_count": 3
    }
}
```

## Error Handling

### Graceful Degradation

```python
def sync_with_error_handling(self):
    """Sync with comprehensive error handling."""
    successful = 0
    failed = []

    items = self.fetch_items()

    for item in items:
        try:
            result = self.writer.write_document(
                source="mysource",
                workflow=self.classify(item),
                content=item.content,
                filename=item.name,
                document_type="document",
                origin_metadata={"mysource": item.to_dict()}
            )
            successful += 1
            logger.info(f"Wrote {item.name} -> {result['document_id']}")

        except ValidationError as e:
            logger.error(f"Invalid metadata for {item.name}: {e}")
            failed.append((item.name, "validation", str(e)))

        except WriteError as e:
            logger.error(f"Failed to write {item.name}: {e}")
            failed.append((item.name, "write", str(e)))

        except Exception as e:
            logger.exception(f"Unexpected error for {item.name}: {e}")
            failed.append((item.name, "unexpected", str(e)))

    # Report
    logger.info(f"Sync complete: {successful} successful, {len(failed)} failed")

    if failed:
        logger.warning("Failed items:")
        for name, error_type, error_msg in failed:
            logger.warning(f"  {name} ({error_type}): {error_msg}")

    return successful, failed
```

## Configuration

### Connector Configuration

```python
# config.yaml
entity: jro
archive_path: ~/Archive
source_settings:
  api_key: ${MY_SOURCE_API_KEY}  # From environment
  workspace: my-workspace

workflow_mappings:
  expenses: jro-expense
  invoices: jro-invoice
  tax: jro-tax-doc

classification:
  strategy: llm  # manual, pattern, llm, interactive
  fallback_to_stream: true
```

### Loading Configuration

```python
import yaml
import os

class ConnectorConfig:
    def __init__(self, config_file: str):
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Expand environment variables
        self.entity = config["entity"]
        self.archive_path = os.path.expanduser(config["archive_path"])
        self.api_key = os.environ[config["source_settings"]["api_key"].strip("${}")]
        self.workflow_mappings = config["workflow_mappings"]
```

## Deployment

### Running Connectors

**Manual:**
```bash
uv run my-connector sync --entity jro
```

**Cron:**
```bash
# Sync Slack daily at 2am
0 2 * * * cd ~/connectors/slack-archive && uv run slack-archive sync --entity jro

# Sync local docs hourly
0 * * * * cd ~/connectors/localdocs-sync && uv run localdocs-sync --entity jro
```

**Systemd timer:**
```ini
# /etc/systemd/user/slack-archive.timer
[Timer]
OnCalendar=daily
OnCalendar=02:00

[Install]
WantedBy=timers.target
```

### Monitoring

**Log connector runs:**
```python
import logging

logging.basicConfig(
    filename="~/.local/state/my-connector/logs/connector.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger.info(f"Starting sync for entity {entity}")
# ... do work ...
logger.info(f"Sync complete: {count} items")
```

**Track metrics:**
```python
# Save stats after each run
stats = {
    "run_id": str(uuid.uuid4()),
    "start_time": start.isoformat(),
    "end_time": end.isoformat(),
    "items_processed": count,
    "items_failed": len(failed),
    "bytes_written": total_bytes
}

stats_file = Path("~/.local/state/my-connector/stats.jsonl").expanduser()
with open(stats_file, "a") as f:
    f.write(json.dumps(stats) + "\n")
```

## FAQ

### Q: Should I write to workflows/ or streams/?

**Use workflows/** if:
- Content is a document (PDF, image, file)
- Can be classified to a business purpose (expense, invoice, contract)
- Should be kept long-term
- User would want to browse by category

**Use streams/** if:
- Content is conversation/messages (Slack, email threads)
- Temporal in nature (daily logs, chat history)
- Not easily classified to workflows
- User would browse by source/channel/date

### Q: How do I handle updates to existing documents?

**Option 1: Immutable (Recommended)**
- Don't update, write new document
- Use relationships to link versions

**Option 2: Versioned**
- Append version to filename: `...-receipt-v2.pdf`
- Link via relationships

### Q: What if classification fails?

**Fail gracefully:**
```python
workflow = classify(item)
if not workflow:
    # Write to streams as fallback
    writer.write_stream(
        source="mysource",
        stream_context="unclassified",
        content=item.content,
        filename=item.name,
        origin_metadata={...}
    )
```

### Q: Can multiple connectors write simultaneously?

**Yes** - atomic writes prevent corruption:
- Each write is independent
- Collisions handled automatically
- manifest.jsonl uses file locking
- No coordination needed

### Q: How do I migrate existing data?

**Write a migration script:**
```python
from archive_protocol import RepositoryWriter

def migrate_old_data(old_dir: Path, entity: str, workflow: str):
    writer = RepositoryWriter(base_path="~/Archive", entity=entity)

    for old_file in old_dir.glob("**/*.pdf"):
        with open(old_file, "rb") as f:
            content = f.read()

        writer.write_document(
            source="legacy",
            workflow=workflow,
            content=content,
            filename=old_file.name,
            document_type="document",
            origin_metadata={
                "legacy": {
                    "original_path": str(old_file),
                    "migrated_at": datetime.now().isoformat()
                }
            },
            created_at=datetime.fromtimestamp(old_file.stat().st_mtime)
        )
```

## Support

For questions or issues:
1. Check ARCHITECTURE.md for design decisions
2. Check DEVELOPMENT.md for coding standards
3. Check README.md for API reference
4. Create an issue in the repository
