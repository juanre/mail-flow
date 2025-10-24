# archive-protocol

Shared protocol for multi-source document archiving with consistent metadata.

## What Is This?

Personal knowledge is scattered: email receipts, Slack conversations, Google Docs, scanned files. Each lives in its own silo with different storage, search, and metadata.

**archive-protocol** solves this by providing a shared "plumbing" library that enables independent connectors (mailflow for email, slack-archive for Slack, etc.) to write to a **unified repository** with **consistent metadata**, making everything searchable through llmemory.

## Vision

Build a unified personal knowledge repository where you can:
- Browse all expenses in one place (email receipts + scanned docs + Slack attachments)
- Search semantically: "Find Acme contract mentions across all sources"
- Preserve provenance: Know where each document came from
- Install only what you need: Email-only? Just mailflow. Need Slack? Add slack-archive.

## Why Separate Packages?

The original mailflow became a monolith (email + Slack + GDocs all in one). This architecture separates concerns:

```
archive-protocol  ← Tiny shared library (this package, ~500 lines)
    ↓
mailflow         ← Email workflows (independent package)
slack-archive    ← Slack ingestion (independent package)
gdocs-archive    ← Google Docs (independent package)
    ↓
~/Archive/       ← Shared repository (filesystem)
    ↓
llmemory         ← Unified search (PostgreSQL + vector search)
```

Each connector is independent but writes compatible data. Install only what you need.

## Overview

`archive-protocol` is the minimal shared library that:
- Defines repository structure (workflows/ + streams/ + metadata/)
- Provides RepositoryWriter for atomic file operations
- Enforces metadata schema via Pydantic
- Generates self-documenting filenames (yyyy-mm-dd-source-)
- Handles collisions, hashing, and validation

**Total:** ~500 lines, 2 dependencies (pydantic, python-dateutil)

## Installation

```bash
uv add archive-protocol
```

## Quick Start

```python
from archive_protocol import RepositoryWriter, RepositoryConfig

# Initialize writer
config = RepositoryConfig(base_path="~/Archive")
writer = RepositoryWriter(
    config=config,
    entity="jro",  # Your entity identifier
    source="mail"   # Source connector name
)

# Write a classified document
result = writer.write_document(
    workflow="jro-expense",
    content=pdf_bytes,
    mimetype="application/pdf",
    origin={
        "message_id": "<...>",
        "from": "billing@example.com",
        "subject": "Your receipt"
    },
    document_type="receipt"
)

# Files created:
# ~/Archive/entities/jro/workflows/jro-expense/2025/2025-10-23-mail-receipt.pdf
# ~/Archive/entities/jro/metadata/workflows/jro-expense/2025/2025-10-23-mail-receipt.json

print(f"Saved to: {result['content_path']}")
print(f"Document ID: {result['document_id']}")
```

## Repository Structure

```
~/Archive/
  entities/
    {entity}/
      workflows/                    # Classified documents from any source
        {workflow}/
          {YYYY}/
            {YYYY}-{MM}-{DD}-{source}-{filename}.pdf
      streams/                      # Unclassified message streams
        {source}/
          {context}/
            {YYYY}/
              {YYYY}-{MM}-{DD}.md
      metadata/
        workflows/{workflow}/{YYYY}/
          {YYYY}-{MM}-{DD}-{source}-{filename}.json
        streams/{source}/{context}/{YYYY}/
          {YYYY}-{MM}-{DD}.json
      indexes/
        fts.sqlite
        llmemory_checkpoints/
```

## Features

- **Atomic writes**: Temp file + fsync + rename for durability
- **SHA-256 hashing**: Content-addressed deduplication
- **Collision handling**: Automatic suffix on filename conflicts
- **Metadata validation**: Pydantic-based schema enforcement
- **Self-documenting filenames**: yyyy-mm-dd-source- format
- **Workflow-first organization**: All classified docs in one place
- **Source transparency**: Filename prefix shows origin

## API Reference

### RepositoryWriter

```python
from archive_protocol import RepositoryWriter, RepositoryConfig

config = RepositoryConfig(base_path="~/Archive")
writer = RepositoryWriter(
    config=config,
    entity="jro",
    source="mail"
)

# Write classified document to workflows/
result = writer.write_document(
    workflow="jro-expense",           # Workflow name
    content=bytes,                    # Content as bytes
    mimetype="application/pdf",       # MIME type
    origin={...},                     # Source-specific metadata
    document_type="receipt",          # Document classification
    attachments=[bytes, bytes],       # Optional attachment content
    attachment_mimetypes=["image/png", "image/jpeg"],  # Attachment MIME types
    created_at=datetime(...),         # Optional, defaults to now
    original_filename="receipt.pdf"   # Optional, for extension detection
)

# Write unclassified stream to streams/
result = writer.write_stream(
    stream_name="general",            # Stream context name
    content=b"# Daily messages\n...", # Content as bytes
    mimetype="text/markdown",         # MIME type
    origin={...},                     # Source-specific metadata
    created_at=datetime(...)          # Optional, defaults to now
)
```

### MetadataBuilder

```python
from archive_protocol import MetadataBuilder

builder = MetadataBuilder(
    entity="jro",
    source="mail",
    workflow="jro-expense"
)

metadata = builder.build(
    document_id="mail=jro-expense/2025-10-23T13:45:01Z/sha256:abc...",
    content_path="../workflows/jro-expense/2025/2025-10-23-mail-receipt.pdf",
    content_hash="sha256:abc123...",
    content_size=123456,
    mimetype="application/pdf",
    origin={"mail": {...}},
    document_type="receipt"
)
```

### Utilities

```python
from archive_protocol import sanitize_filename, compute_hash, write_atomically

# Sanitize filename
safe_name = sanitize_filename("Receipt (2024).pdf")  # � "Receipt-2024.pdf"

# Compute SHA-256 hash
hash_str = compute_hash(b"content")  # � "sha256:abc123..."

# Write atomically
write_atomically(Path("file.pdf"), pdf_bytes)  # Temp + fsync + rename
```

## Integration with Connectors

### mailflow (email workflows)
```python
from archive_protocol import RepositoryWriter, RepositoryConfig

config = RepositoryConfig(base_path="~/Archive")
writer = RepositoryWriter(
    config=config,
    entity=entity,
    source="mail"
)
result = writer.write_document(
    workflow=workflow_name,
    content=pdf_bytes,
    mimetype="application/pdf",
    origin=email_metadata,
    document_type="receipt",
    original_filename=f"{subject}.pdf"
)
```

### slack-archive
```python
from archive_protocol import RepositoryWriter, RepositoryConfig

config = RepositoryConfig(base_path="~/Archive")
writer = RepositoryWriter(
    config=config,
    entity=entity,
    source="slack"
)

# Daily message transcript (unclassified)
writer.write_stream(
    stream_name="general-channel",
    content=markdown_text,
    mimetype="text/markdown",
    origin=channel_metadata
)

# Classified attachment
writer.write_document(
    workflow="jro-expense",
    content=attachment_bytes,
    mimetype="application/pdf",
    origin=message_metadata,
    document_type="invoice",
    original_filename="invoice.pdf"
)
```

## Testing

```bash
uv run pytest tests/
```

All 105 tests pass:
- Filename sanitization (15 tests)
- Hash computation (8 tests)
- Atomic writes (13 tests)
- Schema validation (44 tests)
- Metadata building (16 tests)
- Repository writer (25 tests)

## Documentation

This package has comprehensive documentation:

- **README.md** (this file) - Quick start and API reference
- **ARCHITECTURE.md** - System design, vision, and data flow
- **DEVELOPMENT.md** - Coding standards and development workflow
- **INTEGRATION.md** - Guide for building connectors
- **IMPLEMENTATION-PLAN-archive-protocol.md** - Detailed implementation timeline

### For Users
Start with README.md for API examples.

### For Connector Developers
Read INTEGRATION.md for patterns and examples.

### For Core Contributors
Read ARCHITECTURE.md and DEVELOPMENT.md for design decisions and standards.

## Development

```bash
# Clone and setup
git clone <repo>
cd archive-protocol
uv sync

# Run tests
uv run pytest tests/ -v

# Add dependencies (never edit pyproject.toml manually)
uv add <package>
uv add --dev <dev-package>
```

## Status

**Current:** v0.1.0 - Production-ready core functionality
- 105 tests passing
- Complete metadata schema
- Atomic write operations
- Comprehensive validation
- Year-based directory organization

**Next:** Integration into mailflow (Week 2 of implementation plan)

## License

See parent project for license information.
