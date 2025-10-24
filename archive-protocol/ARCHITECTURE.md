# archive-protocol Architecture

## Vision

Build a **unified personal knowledge repository** that preserves documents and conversations from multiple sources (email, Slack, Google Docs, local files) with consistent metadata, enabling powerful cross-source search and retrieval through llmemory integration.

## Problem Statement

### What We're Solving

Personal and professional knowledge is scattered across:
- Email (receipts, invoices, contracts, correspondence)
- Slack conversations and shared files
- Google Docs and Drive files
- Local scanned documents and downloads

Each source has its own:
- Storage format and location
- Search mechanism
- Access patterns
- Metadata structure

**Result:** Impossible to answer questions like:
- "Find all Acme-related documents from any source"
- "Show me all expenses from last quarter (email + scanned receipts + Slack attachments)"
- "What contracts mention the renewal clause?"

### Why Separate Packages?

**Original mailflow** became a monolith:
- Email processing + Slack ingestion + GDocs export all in one package
- Every install ships dependencies for all sources (heavy)
- Tight coupling makes changes risky
- Hard to deploy connectors independently

**Solution:** Connector-based architecture with shared protocol:
- Each source is independent package (mailflow, slack-archive, gdocs-archive)
- All use `archive-protocol` for consistent output
- Install only what you need
- Connectors can run on different machines/schedules
- Easy to add new sources without modifying existing code

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                  Consumers (UI/CLI)                      │
│            Search, Browse, Analyze Documents             │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│                  llmemory (Search Engine)                │
│         Vector Search + Full-Text + Hybrid              │
│          PostgreSQL + pgvector + FTS                    │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│               archive-indexer (This Layer)               │
│    Watches metadata, extracts text, feeds llmemory     │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│              Shared Repository (Filesystem)              │
│  ~/Archive/entities/{entity}/workflows/ + streams/      │
│         + metadata/ + indexes/                          │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│            archive-protocol (This Package)               │
│   RepositoryWriter + Metadata Schema + Utilities        │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│                    Connectors                            │
│   mailflow │ slack-archive │ gdocs-archive │ ...       │
│   (Independent packages, different machines OK)          │
└─────────────────────────────────────────────────────────┘
```

## Repository Structure

### Directory Organization

```
~/Archive/
  entities/                           # One directory per entity (person/company)
    {entity}/                         # e.g., jro, tsm, gsk

      workflows/                      # CLASSIFIED documents from any source
        {workflow}/                   # e.g., jro-expense, jro-invoice, jro-tax-doc
          {YYYY}/                     # Year directory (all files for that year)
            {YYYY}-{MM}-{DD}-{source}-{filename}.pdf

      streams/                        # UNCLASSIFIED message/conversation flows
        {source}/                     # e.g., slack, mail
          {context}/                  # e.g., channel-name, thread-id
            {YYYY}/
              {YYYY}-{MM}-{DD}.md     # Daily aggregation
              {YYYY}-{MM}-{DD}.json   # Raw API response

      metadata/                       # Mirrors workflows/ and streams/
        workflows/{workflow}/{YYYY}/
          {YYYY}-{MM}-{DD}-{source}-{filename}.json
        streams/{source}/{context}/{YYYY}/
          {YYYY}-{MM}-{DD}.json

      indexes/                        # Per-entity search indexes
        fts.sqlite                    # SQLite full-text search
        llmemory_checkpoints/         # llmemory state (if used)
```

### Key Design Principles

**1. Workflow-First for Classified Documents**

All receipts, invoices, contracts go to `workflows/{workflow}/` regardless of source:
```
workflows/jro-expense/2025/
  2025-10-23-mail-amazon-receipt.pdf        # Email attachment
  2025-10-23-localdocs-scanned-receipt.pdf  # Scanned document
  2025-10-24-slack-contractor-invoice.pdf   # Slack attachment
```

**Why:** You think "show me expenses", not "show me mail expenses, then scanned expenses, then Slack expenses"

**2. Streams for Unclassified Content**

Conversations and message flows stay in source-organized streams:
```
streams/slack/expenses-channel/2025/
  2025-10-23.md    # Daily Slack messages
  2025-10-23.json  # Raw API data
```

**Why:** Slack conversations aren't "documents" - they're temporal message flows. Different access pattern.

**3. Self-Documenting Filenames**

Format: `{YYYY}-{MM}-{DD}-{source}-{filename}`

**Why:**
- Complete date in filename (can move file anywhere, context preserved)
- Source visible at a glance (mail-, slack-, localdocs-)
- Easy to filter: `ls | grep mail` or `ls | grep 2025-10`
- Single year directory, not nested year/month (simpler)

**4. Metadata Sidecars**

Every content file has a matching `.json` metadata file:
```
workflows/jro-expense/2025/2025-10-23-mail-receipt.pdf
metadata/workflows/jro-expense/2025/2025-10-23-mail-receipt.json
```

**Why:**
- Trivial to find metadata for any file
- Metadata stays with content (both are portable)
- Supports rich querying without parsing content
- llmemory integration point

## Metadata Schema

### Complete Example

```json
{
  "id": "mail=jro-expense/2025-10-23T13:45:01Z/sha256:abc123...",
  "entity": "jro",
  "source": "mail",
  "workflow": "jro-expense",
  "type": "receipt",
  "subtype": "expense",
  "created_at": "2025-10-23T13:45:01Z",

  "content": {
    "path": "../workflows/jro-expense/2025/2025-10-23-mail-amazon-receipt.pdf",
    "hash": "sha256:abc123...",
    "size_bytes": 123456,
    "mimetype": "application/pdf",
    "attachments": [
      "../workflows/jro-expense/2025/2025-10-23-mail-amazon-receipt-logo.png"
    ]
  },

  "origin": {
    "mail": {
      "message_id": "<msg@amazon.com>",
      "subject": "Your Amazon receipt",
      "from": "billing@amazon.com",
      "to": ["juan@example.com"],
      "date": "2025-10-23T13:44:57Z",
      "workflow_name": "jro-expense",
      "confidence_score": 0.91,
      "headers": {"x-priority": "normal"}
    }
  },

  "tags": ["receipt", "amazon", "expense"],

  "relationships": [
    {
      "type": "derived_from_email",
      "target_id": "mail=raw/2025-10-23T13:44:57Z/sha256:def456..."
    }
  ],

  "ingest": {
    "connector": "mail@0.4.0",
    "ingested_at": "2025-10-23T13:45:05Z",
    "hostname": "laptop",
    "workflow_run_id": "uuid-123"
  },

  "llmemory": {
    "indexed_at": "2025-10-23T14:00:00Z",
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "chunks_created": 3,
    "embedding_model": "text-embedding-3-small",
    "embedding_provider": "openai"
  }
}
```

### Field Purposes

**Core Classification:**
- `entity`: Who owns this (jro, tsm, gsk) → maps to llmemory owner_id
- `source`: Where it came from (mail, slack, localdocs) → enables source filtering
- `workflow`: Business category (jro-expense, jro-invoice) → enables workflow filtering
- `type`/`subtype`: Document classification for smart chunking

**Content:**
- `path`: Relative to metadata file (portable references)
- `hash`: SHA-256 for deduplication
- `size_bytes`: For storage monitoring
- `mimetype`: For rendering/extraction
- `attachments`: Related files (logos, etc.)

**Origin:**
- Flexible dict keyed by source
- Each source defines its own schema
- Preserves full provenance

**llmemory Integration:**
- Initially null (connector just writes files)
- Set by archive-indexer after indexing
- Tracks indexing status, prevents re-indexing

## Integration with llmemory

### Two-Stage Process

**Stage 1: Connector Writes (Immediate)**
```
Connector → archive-protocol → Filesystem
                              ↓
                         metadata.json (llmemory: null)
```

**Stage 2: Indexing (Asynchronous)**
```
archive-indexer → reads metadata
                → extracts text from content
                → adds to llmemory
                → updates metadata (llmemory: {...})
```

### Mapping to llmemory

**Entity = owner_id:**
```python
# Filesystem
~/Archive/entities/jro/workflows/...
~/Archive/entities/tsm/workflows/...

# llmemory
owner_id="jro"  # Complete isolation per entity
owner_id="tsm"
```

**Metadata flattening:**
```python
# archive-protocol metadata
{
  "workflow": "jro-expense",
  "source": "mail",
  "origin": {
    "mail": {
      "from": "billing@amazon.com",
      "subject": "Receipt"
    }
  }
}

# Maps to llmemory metadata
{
  "workflow": "jro-expense",
  "source": "mail",
  "from": "billing@amazon.com",
  "subject": "Receipt"
}
```

### Search Patterns

**Find all jro expenses:**
```python
results = await memory.search(
    owner_id="jro",
    query_text="",
    metadata_filter={"workflow": "jro-expense"}
)
```

**Find all mail from sender:**
```python
results = await memory.search(
    owner_id="jro",
    query_text="",
    metadata_filter={"source": "mail", "from": "billing@amazon.com"}
)
```

**Semantic search across all sources:**
```python
results = await memory.search(
    owner_id="jro",
    query_text="contractor payment terms",
    search_type=SearchType.HYBRID  # Vector + full-text
)
```

## Design Decisions

### Why SHA-256 Instead of MD5?

MD5 is cryptographically broken. Attackers could craft collision documents. SHA-256 provides:
- Collision resistance
- Content addressing for true deduplication
- Security for content verification

### Why Relative Paths in Metadata?

```json
"path": "../workflows/jro-expense/2025/2025-10-23-mail-receipt.pdf"
```

**Benefits:**
- Repository is portable (can move ~/Archive)
- Metadata files can be read from any location
- No hardcoded absolute paths

### Why workflows/ and streams/?

**Different access patterns:**
- **workflows/**: Browse all expenses, all invoices (business-centric)
- **streams/**: Browse Slack channel history, email threads (temporal/contextual)

**Different retention:**
- **workflows/**: Keep forever (legal, tax, business records)
- **streams/**: Might archive/compress older data

**Different search:**
- **workflows/**: Mostly structured (invoice #, date, vendor)
- **streams/**: Free-text conversation search

### Why yyyy/yyyy-mm-dd- Format?

**Single year directory:**
- One level deep, not two (year/month)
- Simpler to browse and backup
- Still organized (all 2025 files together)

**Self-documenting filenames:**
- `2025-10-23-mail-receipt.pdf` tells you everything
- Can copy file anywhere, date is preserved
- Easy to sort chronologically
- Easy to filter by date range

## Connector Development

### Creating a New Connector

Each connector is independent but follows the pattern:

**1. Package Structure:**
```
slack-archive/
├── pyproject.toml           # depends on: archive-protocol
├── src/slack_archive/
│   ├── __init__.py
│   ├── fetcher.py           # Fetch from Slack API
│   ├── classifier.py        # Map messages/files to workflows
│   ├── cli.py               # CLI interface
│   └── config.py            # Slack-specific config
└── tests/
```

**2. Workflow:**
```python
from archive_protocol import RepositoryWriter

# Initialize
writer = RepositoryWriter(base_path="~/Archive", entity="jro")

# Fetch from source
messages = fetch_slack_messages(channel="expenses", date="2025-10-23")

# Write message transcript (unclassified stream)
writer.write_stream(
    source="slack",
    stream_context="expenses",
    content=render_markdown(messages),
    filename=f"{date}.md",
    origin_metadata={
        "slack": {
            "channel_id": "C12345",
            "channel_name": "expenses",
            "message_count": len(messages),
            "date_range": "2025-10-23"
        }
    }
)

# Process attachments
for attachment in get_attachments(messages):
    # Classify attachment
    workflow = classify_to_workflow(attachment)  # e.g., "jro-expense"

    if workflow:
        # Write to workflows/ (classified)
        writer.write_document(
            source="slack",
            workflow=workflow,
            content=download_attachment(attachment),
            filename=attachment.name,
            document_type="document",
            origin_metadata={
                "slack": {
                    "channel_id": "C12345",
                    "message_ts": attachment.timestamp,
                    "user_id": attachment.user,
                    "permalink": attachment.url
                }
            }
        )
    else:
        # Store with messages (unclassified)
        save_to_stream_attachments(attachment)
```

**3. Classification Strategy:**

Connectors can classify documents via:
- Manual rules (e.g., #expenses channel → jro-expense workflow)
- Filename patterns (e.g., "invoice*.pdf" → jro-invoice)
- Directory mapping (e.g., ~/Downloads/receipts → jro-expense)
- LLM classification (using llmring)
- Interactive UI prompts
- Learning from past classifications

### Connector Independence

Each connector:
- Runs on its own schedule (cron, webhook, manual)
- Has its own dependencies
- Can run on different machines
- Doesn't know about other connectors
- Only contract: write using archive-protocol

## Data Flow

### Document Lifecycle

```
1. Source Event
   ↓
2. Connector Fetches
   ↓
3. Connector Classifies (workflow or stream)
   ↓
4. archive-protocol Writes (filesystem)
   ├─ Content file
   └─ Metadata JSON
   ↓
5. archive-indexer Detects (watches metadata)
   ↓
6. Extract Text
   ↓
7. llmemory Index (vector + full-text)
   ↓
8. Update Metadata (llmemory.indexed_at)
   ↓
9. Search/Retrieve Available
```

### Idempotency

**Connectors must ensure:**
- Track processed items (like mailflow's processed_emails_tracker)
- Use content hash for deduplication
- Check if document_id already exists before writing

**archive-protocol provides:**
- Content hash computation
- Collision detection (filename exists)

## Scalability

### Storage Estimates

**Classified Documents (workflows/):**
- 10 emails/day × 365 days × 5 years = 18,250 documents
- Average 200KB per document = ~3.6GB
- With attachments: ~10GB per entity

**Unclassified Streams (streams/):**
- Slack: 100 messages/day × 365 days = 36,500 messages/year
- ~50KB per day markdown = ~18MB/year
- Compresses well (can archive old years)

**Metadata:**
- ~2KB per document
- 20,000 documents = 40MB
- Negligible storage

**llmemory:**
- Text chunks + embeddings
- ~50KB per document in PostgreSQL
- 20,000 documents = ~1GB

**Total per entity:** ~15GB/year (manageable on any modern system)

### Performance

**Writes:**
- Atomic operations, no locking needed
- ~50ms per document write (including metadata)
- Can parallelize across entities

**Indexing:**
- Batch processing: 100+ docs/minute
- Background process, doesn't block connectors

**Search:**
- llmemory: sub-100ms p95 latency
- FTS: <10ms for most queries
- Hybrid search: ~100-200ms

## Future Extensions

### Planned Features

1. **Deduplication across sources** - If same file arrives via email and Slack, link them
2. **Relationship tracking** - Link emails to documents mentioned
3. **Version tracking** - Handle document updates (v1, v2)
4. **Archival** - Compress/archive old streams
5. **Replication** - Sync archives across machines
6. **Validation tools** - Verify repository integrity

### Potential New Connectors

- **jira-archive** - Issue tracking, attachments
- **notion-export** - Export Notion pages
- **github-archive** - Code, issues, PRs
- **calendar-archive** - Meeting notes, agendas
- **browser-archive** - Saved pages, bookmarks

Each connector is ~200-500 lines that:
1. Fetches from source
2. Classifies content
3. Calls archive-protocol
4. Done

## Goals and Non-Goals

### Goals

✅ **Unified repository** - One place for all knowledge
✅ **Consistent metadata** - Same schema across all sources
✅ **Powerful search** - Semantic + full-text across all sources
✅ **Simple connectors** - Easy to add new sources
✅ **Data safety** - Atomic writes, content hashing, provenance
✅ **Portability** - Archive is self-contained, can backup/move
✅ **Modularity** - Install only what you need

### Non-Goals

❌ **Real-time sync** - Connectors run periodically, not live
❌ **Collaboration** - Single-user archive (could extend later)
❌ **Version control** - Documents are immutable (new doc = new file)
❌ **ACLs** - Entity-level isolation only
❌ **Web UI** - CLI and filesystem browsing (could add later)

## Success Criteria

A successful implementation enables:

1. **Unified search:** "Find all Acme documents from any source"
2. **Workflow browsing:** Browse all jro-expense files in Finder
3. **Source filtering:** Filter by mail, slack, localdocs
4. **Data preservation:** No data loss, all provenance tracked
5. **Easy extension:** Adding new sources takes days, not weeks
6. **Independence:** Connectors don't interfere with each other

## Team Handoff

### What's Complete

✅ archive-protocol package (this repo)
- RepositoryWriter implementation
- Metadata schema and validation
- Atomic write utilities
- 105 tests passing
- Complete documentation

### What's Next

The implementation plan (IMPLEMENTATION-PLAN-archive-protocol.md) outlines:

**Week 2:** Integrate into mailflow
- Add archive-protocol dependency
- Refactor workflow.py to use RepositoryWriter
- Update paths to ~/Archive/entities/{entity}/workflows/
- Preserve all security/validation

**Week 3:** Create archive-indexer
- Watch metadata for llmemory.indexed_at == null
- Extract text, add to llmemory
- Update metadata with indexing status

**Future:** Additional connectors as needed

### Questions to Resolve

1. **PostgreSQL setup** - Where will llmemory database run?
2. **Backup strategy** - How to backup ~/Archive?
3. **Multi-machine** - Will connectors run on different machines?
4. **Entity management** - How to add new entities?
5. **Workflow creation** - UI for creating workflows in other connectors?

### Getting Started

See DEVELOPMENT.md and INTEGRATION.md for implementation guides.
