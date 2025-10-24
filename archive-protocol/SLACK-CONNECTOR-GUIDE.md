# Slack Connector Implementation Guide

**For the mailflow-memory team building slack-archive**

This guide shows you exactly how to use archive-protocol to build the Slack connector.

## What You're Building

**slack-archive** - A standalone package that:
1. Fetches Slack message history using the Slack API
2. Classifies content as:
   - **Classified attachments** → `workflows/{workflow}/` (e.g., invoices, receipts)
   - **Message transcripts** → `streams/slack/{channel}/` (daily conversation logs)
3. Writes everything using archive-protocol for consistency
4. Maintains deduplication to avoid re-processing

## Package Setup

### 1. Create Package

```bash
cd /path/to/mailflow-memory
uv init slack-archive
cd slack-archive

# Add dependencies
uv add archive-protocol
uv add slack-sdk
uv add click  # for CLI
uv add pyyaml  # for configuration

# Dev dependencies
uv add --dev pytest
uv add --dev pytest-asyncio
```

### 2. Package Structure

```
slack-archive/
├── pyproject.toml
├── README.md
├── config.example.yaml
├── src/slack_archive/
│   ├── __init__.py
│   ├── cli.py              # CLI interface
│   ├── fetcher.py          # Slack API client
│   ├── classifier.py       # Map content to workflows
│   ├── writer.py           # Uses archive-protocol
│   ├── tracker.py          # Deduplication tracking
│   └── config.py           # Configuration management
└── tests/
    ├── conftest.py
    ├── test_fetcher.py
    ├── test_classifier.py
    └── test_writer.py
```

## Using archive-protocol: Complete Examples

### Example 1: Write Daily Message Transcript

```python
# src/slack_archive/writer.py
from datetime import datetime
from pathlib import Path
from archive_protocol import RepositoryWriter, RepositoryConfig

class SlackWriter:
    def __init__(self, entity: str, archive_path: str = "~/Archive"):
        config = RepositoryConfig(base_path=archive_path)
        self.writer = RepositoryWriter(
            config=config,
            entity=entity,
            source="slack",
            connector_version="0.1.0"
        )
        self.entity = entity

    def write_daily_transcript(
        self,
        channel_name: str,
        channel_id: str,
        date: datetime,
        messages: list[dict],
        markdown_content: str
    ) -> tuple[str, Path, Path]:
        """Write daily Slack messages to streams/.

        Args:
            channel_name: Channel name (e.g., "general")
            channel_id: Slack channel ID (e.g., "C12345ABC")
            date: Date of messages
            messages: List of message dicts from Slack API
            markdown_content: Rendered markdown of messages

        Returns:
            Tuple of (document_id, content_path, metadata_path)
        """
        # Write to streams/ (unclassified conversation)
        document_id, content_path, metadata_path = self.writer.write_stream(
            stream_name=channel_name,
            content=markdown_content.encode('utf-8'),
            mimetype="text/markdown",
            origin={
                "channel_id": channel_id,
                "channel_name": channel_name,
                "message_count": len(messages),
                "first_message_ts": messages[0]["ts"] if messages else None,
                "last_message_ts": messages[-1]["ts"] if messages else None,
                "user_count": len(set(m.get("user") for m in messages if m.get("user")))
            },
            created_at=date,
            document_type="conversation",
            original_filename=f"{date.strftime('%Y-%m-%d')}.md"
        )

        # Also save raw JSON
        import json
        raw_json = json.dumps(messages, indent=2, sort_keys=True)

        self.writer.write_stream(
            stream_name=channel_name,
            content=raw_json.encode('utf-8'),
            mimetype="application/json",
            origin={
                "channel_id": channel_id,
                "channel_name": channel_name,
                "format": "raw_api_response"
            },
            created_at=date,
            document_type="raw_data",
            original_filename=f"{date.strftime('%Y-%m-%d')}.json"
        )

        return document_id, content_path, metadata_path
```

### Example 2: Write Classified Attachment

```python
def write_classified_attachment(
    self,
    workflow: str,
    file_data: dict,
    file_content: bytes,
    message_context: dict
) -> tuple[str, Path, Path]:
    """Write Slack attachment classified to a workflow.

    Args:
        workflow: Workflow name (e.g., "jro-expense")
        file_data: Slack file object from API
        file_content: Downloaded file bytes
        message_context: Context from the message (channel, user, timestamp)

    Returns:
        Tuple of (document_id, content_path, metadata_path)
    """
    # Write to workflows/ (classified document)
    document_id, content_path, metadata_path = self.writer.write_document(
        workflow=workflow,
        content=file_content,
        mimetype=file_data.get("mimetype", "application/octet-stream"),
        origin={
            "file_id": file_data["id"],
            "filename": file_data["name"],
            "user_id": file_data.get("user"),
            "user_name": message_context.get("user_name"),
            "channel_id": message_context["channel_id"],
            "channel_name": message_context["channel_name"],
            "message_ts": message_context["message_ts"],
            "permalink": file_data.get("permalink"),
            "title": file_data.get("title"),
            "size": file_data.get("size"),
            "created": file_data.get("created")
        },
        created_at=datetime.fromtimestamp(float(file_data.get("created", 0))),
        document_type="document",
        document_subtype=self._infer_doc_type(file_data),
        tags=self._generate_tags(file_data, message_context),
        original_filename=file_data["name"]
    )

    return document_id, content_path, metadata_path

def _infer_doc_type(self, file_data: dict) -> str:
    """Infer document subtype from filename/mimetype."""
    name = file_data["name"].lower()

    if "invoice" in name:
        return "invoice"
    elif "receipt" in name:
        return "receipt"
    elif "contract" in name:
        return "contract"
    elif file_data.get("mimetype", "").startswith("image/"):
        return "image"
    else:
        return "document"

def _generate_tags(self, file_data: dict, message_context: dict) -> list[str]:
    """Generate tags for the document."""
    tags = [
        "slack",
        message_context["channel_name"]
    ]

    # Add file-type tag
    if file_data.get("mimetype"):
        mime_type = file_data["mimetype"].split("/")[0]
        tags.append(mime_type)

    return tags
```

### Example 3: Render Slack Messages as Markdown

```python
# src/slack_archive/renderer.py
from datetime import datetime

class MarkdownRenderer:
    """Render Slack messages as readable markdown."""

    def __init__(self, users: dict):
        """
        Args:
            users: Map of user_id -> user info from Slack API
        """
        self.users = users

    def render_day(self, messages: list[dict], date: datetime) -> str:
        """Render one day of Slack messages as markdown.

        Args:
            messages: List of message objects from Slack API
            date: Date being rendered

        Returns:
            Markdown string
        """
        lines = [
            f"# Slack Messages - {date.strftime('%Y-%m-%d')}",
            "",
            f"**Channel:** {messages[0].get('channel_name', 'Unknown')}",
            f"**Message Count:** {len(messages)}",
            "",
            "---",
            ""
        ]

        for msg in messages:
            lines.extend(self._render_message(msg))
            lines.append("")

        return "\n".join(lines)

    def _render_message(self, msg: dict) -> list[str]:
        """Render single message."""
        user_id = msg.get("user", "unknown")
        user_name = self.users.get(user_id, {}).get("real_name", user_id)

        timestamp = datetime.fromtimestamp(float(msg["ts"]))
        time_str = timestamp.strftime("%H:%M:%S")

        text = msg.get("text", "")

        lines = [f"### {time_str} - {user_name}"]

        # Handle threading
        if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
            lines.append("↪️ *Reply in thread*")

        lines.append("")
        lines.append(text)

        # Files
        if msg.get("files"):
            lines.append("")
            lines.append("**Attachments:**")
            for f in msg["files"]:
                lines.append(f"- [{f['name']}]({f.get('permalink', '#')})")

        # Reactions
        if msg.get("reactions"):
            reactions = " ".join(
                f"{r['name']}×{r['count']}"
                for r in msg["reactions"]
            )
            lines.append("")
            lines.append(f"*Reactions: {reactions}*")

        return lines
```

## Classification Strategies

### Strategy 1: Channel-Based (Simple)

Map Slack channels to workflows:

```python
# src/slack_archive/classifier.py
class ChannelClassifier:
    """Map Slack channels to workflows."""

    # Define your mappings
    CHANNEL_MAPPINGS = {
        "expenses": "jro-expense",
        "invoices": "jro-invoice",
        "receipts": "jro-expense",
        "tax-documents": "jro-tax-doc",
        "contracts": "jro-contract",
    }

    def classify_attachment(
        self,
        channel_name: str,
        file_data: dict
    ) -> str | None:
        """Classify Slack attachment to workflow.

        Args:
            channel_name: Slack channel name
            file_data: File object from Slack API

        Returns:
            Workflow name or None if unclassified
        """
        # Only classify PDF/documents
        mimetype = file_data.get("mimetype", "")
        if not (mimetype == "application/pdf" or
                mimetype.startswith("image/") or
                mimetype.startswith("application/")):
            return None

        # Map channel to workflow
        workflow = self.CHANNEL_MAPPINGS.get(channel_name)
        return workflow
```

### Strategy 2: Filename Pattern Matching

```python
import re

class PatternClassifier:
    """Classify based on filename patterns."""

    PATTERNS = [
        (r"invoice[-_]?\d+", "jro-invoice"),
        (r"receipt", "jro-expense"),
        (r"contract", "jro-contract"),
        (r"statement", "jro-tax-doc"),
        (r"tax[-_]", "jro-tax-doc"),
    ]

    def classify_attachment(self, file_data: dict) -> str | None:
        """Classify based on filename."""
        filename = file_data["name"].lower()

        for pattern, workflow in self.PATTERNS:
            if re.search(pattern, filename):
                return workflow

        return None
```

### Strategy 3: Combined (Recommended)

```python
class HybridClassifier:
    """Combine channel and pattern matching."""

    def __init__(self):
        self.channel_classifier = ChannelClassifier()
        self.pattern_classifier = PatternClassifier()

    def classify_attachment(
        self,
        channel_name: str,
        file_data: dict
    ) -> str | None:
        """Classify using channel first, then filename pattern."""
        # Try channel mapping first
        workflow = self.channel_classifier.classify_attachment(
            channel_name, file_data
        )

        if workflow:
            return workflow

        # Fall back to pattern matching
        return self.pattern_classifier.classify_attachment(file_data)
```

## Complete Implementation Example

### Main Sync Logic

```python
# src/slack_archive/sync.py
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_archive.writer import SlackWriter
from slack_archive.classifier import HybridClassifier
from slack_archive.renderer import MarkdownRenderer
from slack_archive.tracker import ProcessedTracker

class SlackSync:
    """Sync Slack content to archive."""

    def __init__(
        self,
        entity: str,
        slack_token: str,
        archive_path: str = "~/Archive"
    ):
        self.entity = entity
        self.client = WebClient(token=slack_token)
        self.writer = SlackWriter(entity=entity, archive_path=archive_path)
        self.classifier = HybridClassifier()
        self.tracker = ProcessedTracker(entity=entity)

        # Fetch user list once for rendering
        self.users = self._fetch_users()
        self.renderer = MarkdownRenderer(self.users)

    def sync_channel(
        self,
        channel_name: str,
        start_date: datetime,
        end_date: datetime
    ) -> dict:
        """Sync a date range from a Slack channel.

        Args:
            channel_name: Channel name (without #)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Statistics dict with counts
        """
        stats = {
            "days_processed": 0,
            "messages_archived": 0,
            "attachments_classified": 0,
            "attachments_unclassified": 0
        }

        # Get channel ID
        channel_id = self._get_channel_id(channel_name)

        # Process each day
        current_date = start_date
        while current_date <= end_date:
            self._sync_one_day(channel_name, channel_id, current_date, stats)
            current_date += timedelta(days=1)

        return stats

    def _sync_one_day(
        self,
        channel_name: str,
        channel_id: str,
        date: datetime,
        stats: dict
    ):
        """Sync one day of messages."""
        # Calculate time range
        day_start = date.replace(hour=0, minute=0, second=0)
        day_end = day_start + timedelta(days=1)

        oldest_ts = str(day_start.timestamp())
        latest_ts = str(day_end.timestamp())

        # Fetch messages
        messages = self._fetch_messages(
            channel_id=channel_id,
            oldest=oldest_ts,
            latest=latest_ts
        )

        if not messages:
            return

        # Add channel name to each message for context
        for msg in messages:
            msg["channel_name"] = channel_name

        # Render as markdown
        markdown = self.renderer.render_day(messages, date)

        # Write transcript
        self.writer.write_daily_transcript(
            channel_name=channel_name,
            channel_id=channel_id,
            date=date,
            messages=messages,
            markdown_content=markdown
        )

        stats["days_processed"] += 1
        stats["messages_archived"] += len(messages)

        # Process attachments
        for msg in messages:
            if msg.get("files"):
                self._process_attachments(
                    files=msg["files"],
                    channel_name=channel_name,
                    channel_id=channel_id,
                    message_ts=msg["ts"],
                    user_id=msg.get("user"),
                    stats=stats
                )

    def _process_attachments(
        self,
        files: list[dict],
        channel_name: str,
        channel_id: str,
        message_ts: str,
        user_id: str,
        stats: dict
    ):
        """Process attachments from a message."""
        for file_data in files:
            # Skip if already processed
            if self.tracker.is_processed(file_data["id"]):
                continue

            # Try to classify
            workflow = self.classifier.classify_attachment(
                channel_name=channel_name,
                file_data=file_data
            )

            # Download file
            file_content = self._download_file(file_data["url_private"])

            # Get user name for context
            user_name = self.users.get(user_id, {}).get("real_name", user_id)

            message_context = {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "message_ts": message_ts,
                "user_name": user_name
            }

            if workflow:
                # Write to workflows/ (classified)
                self.writer.write_classified_attachment(
                    workflow=workflow,
                    file_data=file_data,
                    file_content=file_content,
                    message_context=message_context
                )
                stats["attachments_classified"] += 1
            else:
                # Could store unclassified attachments in streams/
                # or just skip them (they're in the message transcript)
                stats["attachments_unclassified"] += 1

            # Mark as processed
            self.tracker.mark_processed(file_data["id"])

    def _fetch_messages(
        self,
        channel_id: str,
        oldest: str,
        latest: str
    ) -> list[dict]:
        """Fetch messages from Slack API."""
        messages = []
        cursor = None

        while True:
            response = self.client.conversations_history(
                channel=channel_id,
                oldest=oldest,
                latest=latest,
                cursor=cursor,
                limit=200
            )

            messages.extend(response["messages"])

            if not response.get("has_more"):
                break

            cursor = response["response_metadata"]["next_cursor"]

        # Sort chronologically
        messages.sort(key=lambda m: m["ts"])
        return messages

    def _download_file(self, url: str) -> bytes:
        """Download file from Slack."""
        import requests
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.client.token}"}
        )
        response.raise_for_status()
        return response.content

    def _fetch_users(self) -> dict:
        """Fetch user list for name resolution."""
        response = self.client.users_list()
        users = {}
        for user in response["members"]:
            users[user["id"]] = {
                "real_name": user.get("real_name", user.get("name")),
                "display_name": user.get("profile", {}).get("display_name"),
                "email": user.get("profile", {}).get("email")
            }
        return users

    def _get_channel_id(self, channel_name: str) -> str:
        """Get channel ID from name."""
        response = self.client.conversations_list(types="public_channel,private_channel")
        for channel in response["channels"]:
            if channel["name"] == channel_name:
                return channel["id"]
        raise ValueError(f"Channel not found: {channel_name}")
```

## Deduplication

### Track Processed Items

```python
# src/slack_archive/tracker.py
import sqlite3
from pathlib import Path
from datetime import datetime

class ProcessedTracker:
    """Track processed Slack items to avoid duplicates."""

    def __init__(self, entity: str):
        self.entity = entity
        self.db_path = Path(f"~/.config/slack-archive/{entity}/processed.db").expanduser()
        self._init_db()

    def _init_db(self):
        """Create tracking database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    processed_at TIMESTAMP NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_days (
                    channel_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    processed_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (channel_id, date)
                )
            """)

            conn.commit()

    def is_processed(self, file_id: str) -> bool:
        """Check if file already processed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_files WHERE file_id = ?",
                (file_id,)
            )
            return cursor.fetchone() is not None

    def mark_processed(self, file_id: str, channel_id: str = "", document_id: str = ""):
        """Mark file as processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO processed_files (file_id, channel_id, document_id, processed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_id) DO NOTHING
                """,
                (file_id, channel_id, document_id, datetime.now())
            )
            conn.commit()

    def is_day_processed(self, channel_id: str, date: datetime) -> bool:
        """Check if a day's messages are processed."""
        date_str = date.strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_days WHERE channel_id = ? AND date = ?",
                (channel_id, date_str)
            )
            return cursor.fetchone() is not None

    def mark_day_processed(
        self,
        channel_id: str,
        date: datetime,
        message_count: int
    ):
        """Mark a day as processed."""
        date_str = date.strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO processed_days (channel_id, date, message_count, processed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(channel_id, date) DO UPDATE SET
                    message_count = excluded.message_count,
                    processed_at = excluded.processed_at
                """,
                (channel_id, date_str, message_count, datetime.now())
            )
            conn.commit()
```

## CLI Interface

```python
# src/slack_archive/cli.py
import click
from datetime import datetime, timedelta
from slack_archive.sync import SlackSync

@click.group()
def cli():
    """Slack archive connector for archive-protocol."""
    pass

@cli.command()
@click.option("--entity", required=True, help="Entity identifier (jro, tsm, gsk)")
@click.option("--channel", required=True, help="Slack channel name (without #)")
@click.option("--days", default=7, help="Number of days to sync (default: 7)")
@click.option("--archive-path", default="~/Archive", help="Archive base path")
def sync(entity, channel, days, archive_path):
    """Sync Slack channel to archive.

    Example:
        slack-archive sync --entity jro --channel expenses --days 30
    """
    import os
    slack_token = os.environ.get("SLACK_TOKEN")
    if not slack_token:
        click.echo("Error: SLACK_TOKEN environment variable not set")
        return 1

    syncer = SlackSync(
        entity=entity,
        slack_token=slack_token,
        archive_path=archive_path
    )

    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days - 1)

    click.echo(f"Syncing #{channel} from {start_date.date()} to {end_date.date()}")

    stats = syncer.sync_channel(
        channel_name=channel,
        start_date=start_date,
        end_date=end_date
    )

    click.echo(f"\nSync complete:")
    click.echo(f"  Days processed: {stats['days_processed']}")
    click.echo(f"  Messages archived: {stats['messages_archived']}")
    click.echo(f"  Attachments classified: {stats['attachments_classified']}")
    click.echo(f"  Attachments unclassified: {stats['attachments_unclassified']}")

@cli.command()
@click.option("--entity", required=True)
def list_channels(entity):
    """List available Slack channels."""
    import os
    client = WebClient(token=os.environ["SLACK_TOKEN"])
    response = client.conversations_list(types="public_channel,private_channel")

    click.echo("\nAvailable channels:")
    for channel in response["channels"]:
        click.echo(f"  #{channel['name']}")

if __name__ == "__main__":
    cli()
```

## Configuration

### config.yaml

```yaml
# slack-archive configuration
entity: jro
archive_path: ~/Archive

slack:
  # Set SLACK_TOKEN environment variable instead of storing here
  workspace: your-workspace

# Channel to workflow mappings
channel_mappings:
  expenses: jro-expense
  invoices: jro-invoice
  receipts: jro-expense
  tax-documents: jro-tax-doc
  contracts: jro-contract

# What to sync
channels:
  - expenses
  - invoices
  - contracts

# Sync settings
sync:
  days_back: 7              # How many days to sync
  include_threads: true     # Include thread replies
  download_attachments: true
  classify_attachments: true

# Storage
storage:
  save_raw_json: true       # Save API responses
  save_markdown: true       # Save rendered markdown
```

### Load Configuration

```python
# src/slack_archive/config.py
import yaml
import os
from pathlib import Path

class SlackConfig:
    def __init__(self, config_file: str | Path):
        with open(config_file) as f:
            data = yaml.safe_load(f)

        self.entity = data["entity"]
        self.archive_path = os.path.expanduser(data["archive_path"])
        self.slack_token = os.environ.get("SLACK_TOKEN")
        self.workspace = data["slack"]["workspace"]
        self.channel_mappings = data.get("channel_mappings", {})
        self.channels = data.get("channels", [])
        self.days_back = data.get("sync", {}).get("days_back", 7)

        if not self.slack_token:
            raise ValueError("SLACK_TOKEN environment variable not set")
```

## Testing

### Test with archive-protocol

```python
# tests/test_writer.py
import pytest
from datetime import datetime
from pathlib import Path
from archive_protocol import RepositoryConfig
from slack_archive.writer import SlackWriter

@pytest.fixture
def temp_archive(tmp_path):
    """Temporary archive for testing."""
    return tmp_path / "archive"

@pytest.fixture
def slack_writer(temp_archive):
    """Slack writer for testing."""
    return SlackWriter(
        entity="test-entity",
        archive_path=str(temp_archive)
    )

def test_write_daily_transcript(slack_writer, temp_archive):
    """Test writing daily message transcript."""
    messages = [
        {
            "ts": "1634567890.123456",
            "user": "U123",
            "text": "Hello world",
            "channel_name": "general"
        }
    ]

    markdown = "# Messages\n\nHello world"

    doc_id, content_path, meta_path = slack_writer.write_daily_transcript(
        channel_name="general",
        channel_id="C123",
        date=datetime(2025, 10, 23),
        messages=messages,
        markdown_content=markdown
    )

    # Verify structure
    assert content_path.exists()
    assert meta_path.exists()

    # Verify location
    assert "streams/slack/general/2025" in str(content_path)
    assert content_path.name.startswith("2025-10-23-")

    # Verify metadata
    import json
    with open(meta_path) as f:
        metadata = json.load(f)

    assert metadata["entity"] == "test-entity"
    assert metadata["source"] == "slack"
    assert metadata["workflow"] is None  # Streams have no workflow
    assert metadata["origin"]["channel_name"] == "general"

def test_write_classified_attachment(slack_writer, temp_archive):
    """Test writing classified Slack attachment."""
    file_data = {
        "id": "F123",
        "name": "invoice.pdf",
        "mimetype": "application/pdf",
        "size": 12345,
        "created": 1634567890,
        "user": "U123"
    }

    message_context = {
        "channel_id": "C123",
        "channel_name": "expenses",
        "message_ts": "1634567890.123456",
        "user_name": "John Doe"
    }

    doc_id, content_path, meta_path = slack_writer.write_classified_attachment(
        workflow="jro-expense",
        file_data=file_data,
        file_content=b"PDF content here",
        message_context=message_context
    )

    # Verify workflow directory
    assert "workflows/jro-expense/2025" in str(content_path)
    assert content_path.name.startswith("2025-10-")
    assert "-slack-" in content_path.name

    # Verify metadata
    import json
    with open(meta_path) as f:
        metadata = json.load(f)

    assert metadata["workflow"] == "jro-expense"
    assert metadata["source"] == "slack"
    assert metadata["origin"]["file_id"] == "F123"
    assert metadata["origin"]["channel_name"] == "expenses"
```

## Deployment

### Environment Setup

```bash
# Set Slack token
export SLACK_TOKEN=xoxb-your-token-here

# Test
uv run slack-archive sync --entity jro --channel expenses --days 7

# Verify
ls ~/Archive/entities/jro/workflows/jro-expense/2025/
ls ~/Archive/entities/jro/streams/slack/expenses/2025/
```

### Cron Schedule

```bash
# Sync daily at 2am
0 2 * * * cd ~/slack-archive && /usr/local/bin/uv run slack-archive sync --entity jro --channel expenses --days 1

# Weekly full sync on Sundays
0 3 * * 0 cd ~/slack-archive && /usr/local/bin/uv run slack-archive sync --entity jro --channel expenses --days 30
```

### Error Handling

```python
def sync_with_retry(self, channel_name, start_date, end_date, max_retries=3):
    """Sync with retry logic."""
    for attempt in range(max_retries):
        try:
            return self.sync_channel(channel_name, start_date, end_date)
        except Exception as e:
            logger.error(f"Sync attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise

            # Exponential backoff
            import time
            time.sleep(2 ** attempt)
```

## Key Points for Slack Connector

### What Goes to workflows/

✅ **Classify these to workflows/**:
- PDF attachments (invoices, receipts, contracts)
- Images that are documents (scanned receipts, photos of invoices)
- Spreadsheets (expense reports, financial docs)
- Any file the user wants organized by workflow

### What Goes to streams/

✅ **Keep these in streams/**:
- Daily message transcripts (.md files)
- Raw API responses (.json files)
- Unclassified attachments (optional)
- Thread conversations
- Reaction history

### Directory Structure Example

After syncing #expenses channel for October 2025:

```
~/Archive/entities/jro/
  workflows/jro-expense/2025/
    2025-10-15-slack-contractor-invoice.pdf     # Classified attachment
    2025-10-23-slack-receipt-photo.jpg          # Classified image

  streams/slack/expenses/2025/
    2025-10-01.md                               # Daily messages
    2025-10-01.json                             # Raw API data
    2025-10-02.md
    2025-10-02.json
    ...
    2025-10-31.md
    2025-10-31.json

  metadata/
    workflows/jro-expense/2025/
      2025-10-15-slack-contractor-invoice.json
      2025-10-23-slack-receipt-photo.json
    streams/slack/expenses/2025/
      2025-10-01.json
      2025-10-02.json
      ...
```

## Finding Content

**All jro expenses (from any source):**
```bash
ls ~/Archive/entities/jro/workflows/jro-expense/2025/
# Shows: mail-, slack-, localdocs- prefixed files
```

**All Slack expenses:**
```bash
ls ~/Archive/entities/jro/workflows/jro-expense/2025/ | grep slack
# Shows only slack- prefixed files
```

**Expenses conversation history:**
```bash
ls ~/Archive/entities/jro/streams/slack/expenses/2025/
# Shows daily .md and .json files
```

## Questions?

- **Architecture questions:** See archive-protocol/ARCHITECTURE.md
- **Development standards:** See archive-protocol/DEVELOPMENT.md
- **API reference:** See archive-protocol/README.md
- **General connector patterns:** See archive-protocol/INTEGRATION.md

## Checklist for slack-archive

- [ ] Package created with uv
- [ ] archive-protocol dependency added
- [ ] Slack SDK integrated
- [ ] Channel-to-workflow mapping implemented
- [ ] Daily transcript rendering working
- [ ] Attachment classification working
- [ ] Deduplication tracking implemented
- [ ] CLI with sync command
- [ ] Tests for all components
- [ ] Configuration file support
- [ ] Error handling with retries
- [ ] Documentation (README)
- [ ] Example config.yaml provided

Good luck! The architecture is solid and archive-protocol handles all the complexity.
