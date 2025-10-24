# archive-protocol

Shared protocol for multi-source document archiving with consistent metadata.

## Overview

`archive-protocol` is a minimal library (~500 lines) that provides the "plumbing" for document archiving connectors. It ensures all connectors (mailflow, slack-archive, gdocs-archive, etc.) write to a consistent repository structure with validated metadata.

## Installation

```bash
uv add archive-protocol
```

## Quick Start

```python
from archive_protocol import RepositoryWriter

# Initialize writer
writer = RepositoryWriter(
    base_path="~/Archive",
    entity="jro"  # Your entity identifier
)

# Write a classified document
result = writer.write_document(
    source="mail",
    workflow="jro-expense",
    content=pdf_bytes,
    filename="receipt.pdf",
    document_type="receipt",
    origin_metadata={
        "mail": {
            "message_id": "<...>",
            "from": "billing@example.com",
            "subject": "Your receipt"
        }
    }
)

# Files created:
# ~/Archive/entities/jro/workflows/jro-expense/2025/2025-10-23-mail-receipt.pdf
# ~/Archive/entities/jro/metadata/workflows/jro-expense/2025/2025-10-23-mail-receipt.json
# ~/Archive/manifest.jsonl (appended)

print(f"Saved to: {result['content_path']}")
print(f"Document ID: {result['document_id']}")
```

## Repository Structure

```
~/Archive/
  manifest.jsonl                    # Optional append-only change stream
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
writer = RepositoryWriter(base_path="~/Archive", entity="jro")

# Write classified document to workflows/
result = writer.write_document(
    source="mail",                    # Source connector
    workflow="jro-expense",           # Workflow name
    content=bytes | Path,             # Content as bytes or path to file
    filename="receipt.pdf",           # Base filename
    document_type="receipt",          # Document classification
    origin_metadata={...},            # Source-specific metadata
    attachments=[("logo.png", bytes)],  # Optional attachments
    created_at=datetime(...),         # Optional, defaults to now
)

# Write unclassified stream to streams/
result = writer.write_stream(
    source="slack",
    stream_context="general",         # e.g., channel name
    content="# Daily messages\n...",
    filename="2025-10-23.md",
    origin_metadata={...},
    created_at=datetime(...)
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
safe_name = sanitize_filename("Receipt (2024).pdf")  # ’ "Receipt-2024.pdf"

# Compute SHA-256 hash
hash_str = compute_hash(b"content")  # ’ "sha256:abc123..."

# Write atomically
write_atomically(Path("file.pdf"), pdf_bytes)  # Temp + fsync + rename
```

## Integration with Connectors

### mailflow (email workflows)
```python
from archive_protocol import RepositoryWriter

writer = RepositoryWriter(base_path="~/Archive", entity=entity)
result = writer.write_document(
    source="mail",
    workflow=workflow_name,
    content=pdf_bytes,
    filename=f"{subject}.pdf",
    document_type="receipt",
    origin_metadata={"mail": email_metadata}
)
```

### slack-archive
```python
# Daily message transcript (unclassified)
writer.write_stream(
    source="slack",
    stream_context="general-channel",
    content=markdown_text,
    filename=f"{date}.md",
    origin_metadata={"slack": channel_metadata}
)

# Classified attachment
writer.write_document(
    source="slack",
    workflow="jro-expense",
    content=attachment_bytes,
    filename="invoice.pdf",
    document_type="invoice",
    origin_metadata={"slack": message_metadata}
)
```

## Testing

```bash
uv run pytest tests/
```

All 108 tests pass:
- Filename sanitization (15 tests)
- Hash computation (8 tests)
- Atomic writes (13 tests)
- Schema validation (44 tests)
- Metadata building (16 tests)
- Repository writer (28 tests)

## Development

```bash
# Clone and setup
git clone <repo>
cd archive-protocol
uv sync

# Run tests
uv run pytest tests/ -v

# Add dependencies
uv add <package>
uv add --dev <dev-package>
```

## License

See parent project for license information.
