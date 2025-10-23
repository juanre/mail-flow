# archive-protocol Implementation Plan

## Overview

Create a minimal shared library that provides the "plumbing" for all connectors (mailflow, slack-archive, gdocs-archive, etc.) to write to a common repository structure with consistent metadata.

## Package Structure

```
archive-protocol/
├── pyproject.toml
├── README.md
├── src/
│   └── archive_protocol/
│       ├── __init__.py
│       ├── writer.py           # RepositoryWriter class
│       ├── metadata.py         # Metadata schema and validation
│       ├── config.py           # RepositoryConfig
│       ├── schema.py           # JSON schema definitions
│       ├── utils.py            # Path sanitization, hash utilities
│       └── exceptions.py       # Custom exceptions
└── tests/
    ├── test_writer.py
    ├── test_metadata.py
    └── test_integration.py
```

## Core Components

### 1. RepositoryWriter Class

**Purpose:** Atomic writing of documents to the repository with metadata generation.

**API:**
```python
from archive_protocol import RepositoryWriter, DocumentType

writer = RepositoryWriter(
    base_path="~/Archive",
    entity="jro"
)

result = writer.write_document(
    source="mail",                    # mail, slack, localdocs, gdocs
    workflow="jro-expense",           # Workflow name (or None if unclassified)
    content=pdf_bytes,                # Bytes or Path to file
    filename="amazon-receipt.pdf",    # Base filename
    document_type=DocumentType.RECEIPT,
    origin_metadata={                 # Source-specific metadata
        "mail": {
            "message_id": "<...>",
            "subject": "Receipt from Amazon",
            "from": "billing@amazon.com",
            "date": "2025-10-23T13:44:57Z",
            "confidence_score": 0.91
        }
    },
    attachments=[                     # Optional list of attachment bytes/paths
        ("logo.png", logo_bytes)
    ]
)

# Returns:
# {
#   "document_id": "mail=jro-expense/2025-10-23T13:45:01Z/sha256:abc...",
#   "content_path": Path("~/Archive/entities/jro/workflows/jro-expense/2025/2025-10-23-mail-amazon-receipt.pdf"),
#   "metadata_path": Path("~/Archive/entities/jro/metadata/workflows/jro-expense/2025/2025-10-23-mail-amazon-receipt.json"),
#   "attachment_paths": [Path("...logo.png")],
#   "manifest_appended": True
# }
```

**Key Methods:**
```python
class RepositoryWriter:
    def __init__(self, base_path: str, entity: str)

    def write_document(
        source: str,
        workflow: str | None,
        content: bytes | Path,
        filename: str,
        document_type: DocumentType,
        origin_metadata: dict,
        attachments: list[tuple[str, bytes | Path]] = None,
        created_at: datetime | None = None
    ) -> dict

    def write_stream(
        source: str,
        stream_context: str,  # e.g., channel name
        content: str | bytes,
        filename: str,
        origin_metadata: dict,
        created_at: datetime | None = None
    ) -> dict

    def _resolve_workflow_path(workflow: str, year: int) -> Path
    def _resolve_stream_path(source: str, context: str, year: int) -> Path
    def _generate_filename(date: str, source: str, base_filename: str) -> str
    def _compute_hash(content: bytes) -> str
    def _write_atomically(path: Path, content: bytes) -> None
    def _append_to_manifest(metadata: dict) -> None
```

**Implementation Details:**
- Use atomic writes (temp file + fsync + rename)
- Compute SHA-256 hashes for content
- Handle filename collisions by appending content hash suffix
- Create year directories automatically
- Generate yyyy-mm-dd-source- filename prefixes
- Write metadata JSON alongside content
- Optionally append to manifest.jsonl

### 2. Metadata Schema

**Metadata Structure:**
```python
from archive_protocol import MetadataBuilder

builder = MetadataBuilder(
    entity="jro",
    source="mail",
    workflow="jro-expense"
)

metadata = builder.build(
    content_path=Path("workflows/jro-expense/2025/2025-10-23-mail-receipt.pdf"),
    content_hash="sha256:abc...",
    content_size=123456,
    mimetype="application/pdf",
    origin={
        "mail": {
            "message_id": "<...>",
            "subject": "...",
            ...
        }
    },
    attachments=[
        "workflows/jro-expense/2025/2025-10-23-mail-receipt-logo.png"
    ],
    tags=["receipt", "amazon"],
    document_type="receipt",
    document_subtype="expense"
)

# Returns complete metadata dict with:
# - id, entity, source, workflow, type, created_at
# - content{}, origin{}, tags[], relationships[]
# - ingest{}, llmemory{}
```

**Schema Validation:**
```python
from archive_protocol import validate_metadata, MetadataSchema

# Validates against JSON schema
validate_metadata(metadata_dict)

# Required fields:
# - id, entity, source, created_at, content, ingest
# Optional fields:
# - workflow, type, subtype, origin, tags, relationships, llmemory
```

### 3. Configuration

```python
from archive_protocol import RepositoryConfig

config = RepositoryConfig(
    base_path="~/Archive",
    enable_manifest=True,
    create_directories=True,
    atomic_writes=True,
    compute_hashes=True,
    hash_algorithm="sha256"
)

# Or from environment
config = RepositoryConfig.from_env()
# Reads ARCHIVE_BASE_PATH, ARCHIVE_ENABLE_MANIFEST, etc.
```

### 4. Integration with llmemory

**Two-Stage Process:**

**Stage 1: RepositoryWriter writes to filesystem**
```python
# In mailflow
result = writer.write_document(
    source="mail",
    workflow="jro-expense",
    content=pdf_bytes,
    ...
)

# Result contains:
# - content_path: Where PDF was saved
# - metadata_path: Where JSON was saved
# - document_id: Unique identifier
```

**Stage 2: Indexer reads metadata and adds to llmemory**
```python
# Separate indexer process (archive-indexer)
from archive_protocol import MetadataReader
from llmemory import AwordMemory

reader = MetadataReader(base_path="~/Archive")
memory = AwordMemory(connection_string="postgresql://...")

# Find unindexed documents
for metadata_file in reader.find_unindexed():
    metadata = reader.load_metadata(metadata_file)

    # Extract text from content
    content_path = metadata["content"]["path"]
    text = extract_text(content_path)  # PDF -> text, etc.

    # Add to llmemory
    result = await memory.add_document(
        owner_id=metadata["entity"],        # jro, tsm, gsk
        id_at_origin=metadata["id"],        # mail=jro-expense/...
        document_name=content_path.name,
        document_type=metadata.get("type", "document"),
        content=text,
        metadata={
            "workflow": metadata.get("workflow"),
            "source": metadata["source"],
            **metadata.get("origin", {}).get(metadata["source"], {})
        }
    )

    # Update metadata with llmemory info
    metadata["llmemory"] = {
        "indexed_at": datetime.now().isoformat(),
        "document_id": str(result.document_id),
        "chunks_created": result.chunks_created
    }
    reader.update_metadata(metadata_file, metadata)
```

### 5. Filesystem to llmemory Mapping

**Entity-based isolation:**
```
Filesystem                              llmemory
~/Archive/entities/jro/workflows/... -> owner_id="jro"
~/Archive/entities/tsm/workflows/... -> owner_id="tsm"
~/Archive/entities/gsk/workflows/... -> owner_id="gsk"
```

**Metadata mapping:**
```python
# From archive-protocol metadata to llmemory
archive_metadata = {
    "id": "mail=jro-expense/2025-10-23T13:45:01Z/sha256:abc...",
    "entity": "jro",
    "source": "mail",
    "workflow": "jro-expense",
    "type": "document",
    "subtype": "receipt",
    "origin": {
        "mail": {
            "from": "billing@amazon.com",
            "subject": "Your receipt",
            ...
        }
    }
}

# Maps to llmemory call:
await memory.add_document(
    owner_id="jro",                    # entity
    id_at_origin=archive_metadata["id"],  # Unique ID from archive-protocol
    document_name="2025-10-23-mail-amazon-receipt.pdf",
    document_type=DocumentType.EMAIL,  # or map from type/subtype
    content=extracted_text,
    metadata={
        "workflow": "jro-expense",
        "source": "mail",
        "from": "billing@amazon.com",
        "subject": "Your receipt",
        ...  # Flatten origin.mail into metadata
    }
)
```

**Search patterns:**
```python
# Find all jro expenses
results = await memory.search(
    owner_id="jro",
    query_text="amazon receipt",
    metadata_filter={"workflow": "jro-expense"}
)

# Find all mail from specific sender
results = await memory.search(
    owner_id="jro",
    query_text="",
    metadata_filter={"source": "mail", "from": "billing@amazon.com"}
)

# Cross-workflow search
results = await memory.search(
    owner_id="jro",
    query_text="contractor payment",
    # No metadata_filter = searches all workflows
)
```

## Implementation Steps

### Phase 1: Core archive-protocol Package (Week 1)

**Day 1-2: Setup and Schema**
- Create uv project: `uv init archive-protocol`
- Define metadata JSON schema
- Implement MetadataBuilder class
- Write schema validation
- Tests for metadata generation

**Day 3-4: RepositoryWriter**
- Implement path resolution (workflows/ vs streams/)
- Implement filename generation (yyyy-mm-dd-source-)
- Implement atomic file writes with SHA-256 hashing
- Handle collisions gracefully
- Tests for all edge cases

**Day 5: Utilities and Polish**
- Implement manifest.jsonl appending
- Add MetadataReader for reading/updating metadata
- Configuration management
- Documentation and examples
- Integration tests

**Deliverable:** `archive-protocol==0.1.0` package published to PyPI (or private index)

### Phase 2: Mailflow Integration (Week 2)

**Day 1: Preparation**
- Add `archive-protocol` dependency to mailflow
- Create adapter layer between mailflow and archive-protocol
- Parse entity from workflow name (jro-expense → jro)

**Day 2-3: Refactor Workflows**
- Update workflow.py to use RepositoryWriter
- Update attachment_handler.py to use RepositoryWriter
- Update pdf_converter.py to use RepositoryWriter
- Preserve all security/validation logic

**Day 4: Migration and Testing**
- Update default paths from ~/Documents/mailflow to ~/Archive/entities
- Update UI suggestions to match new structure
- Run all tests, fix breakages
- Test with real emails end-to-end

**Day 5: Polish**
- Update documentation
- Update CLI help text
- Create migration guide (if needed)
- Final testing

**Deliverable:** `mailflow==0.4.0` using archive-protocol

### Phase 3: Indexer Service (Week 3)

**Day 1-2: Archive Indexer**
- Create standalone `archive-indexer` package
- Scan metadata files for unindexed documents
- Extract text from PDFs/files
- Add to llmemory with proper owner_id/metadata mapping

**Day 3: Background Processing**
- Implement watch mode for continuous indexing
- Add rate limiting for llmemory API calls
- Error handling and retry logic
- Progress tracking

**Day 4-5: CLI and Tooling**
- CLI commands: index, reindex, status, stats
- Validation utilities for repository
- Documentation
- Testing

**Deliverable:** `archive-indexer==0.1.0`

### Phase 4: Additional Connectors (As Needed)

Each connector (slack-archive, gdocs-archive, localdocs-sync) follows the same pattern:
1. Depends on archive-protocol
2. Fetches content from source
3. Classifies to workflow (or stores in streams/)
4. Calls RepositoryWriter.write_document()
5. Indexer picks it up automatically

## archive-protocol Package Details

### Dependencies (Minimal)

```toml
[project]
name = "archive-protocol"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",      # Schema validation
    "python-dateutil",    # Date handling
]
```

### Public API

```python
# Main exports
from archive_protocol import (
    # Core classes
    RepositoryWriter,
    MetadataBuilder,
    MetadataReader,
    RepositoryConfig,

    # Enums
    DocumentType,
    SourceType,

    # Schema
    validate_metadata,
    MetadataSchema,

    # Utilities
    sanitize_filename,
    compute_hash,
    generate_document_id,

    # Exceptions
    ArchiveError,
    ValidationError,
    WriteError,
)
```

### Key Design Decisions

**1. Use Pydantic for Validation**
```python
from pydantic import BaseModel, Field

class ContentMetadata(BaseModel):
    path: str = Field(..., description="Relative path from metadata file")
    hash: str = Field(..., pattern=r"^sha256:[a-f0-9]{64}$")
    size_bytes: int = Field(..., gt=0)
    mimetype: str
    attachments: list[str] = Field(default_factory=list)

class DocumentMetadata(BaseModel):
    id: str
    entity: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    source: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    workflow: str | None = Field(None, pattern=r"^[a-z0-9_-]+$")
    type: str
    subtype: str | None = None
    created_at: datetime
    content: ContentMetadata
    origin: dict
    tags: list[str] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)
    ingest: dict
    llmemory: dict = Field(default_factory=lambda: {
        "indexed_at": None,
        "document_id": None,
        "chunks_created": None
    })
```

**2. Atomic Writes (Reuse mailflow's atomic_json_write pattern)**
```python
def _write_atomically(path: Path, content: bytes) -> None:
    """Write file atomically with fsync."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)

    temp_file = path.parent / f".tmp_{path.name}_{os.getpid()}"
    try:
        with open(temp_file, "xb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        temp_file.rename(path)
    finally:
        if temp_file.exists():
            temp_file.unlink()
```

**3. Path Resolution**
```python
def _resolve_path(
    entity: str,
    category: str,  # "workflows" or "streams"
    source: str,
    workflow_or_context: str,
    year: int
) -> Path:
    """Resolve path for content or metadata."""
    base = self.base_path / "entities" / entity / category

    if category == "workflows":
        # workflows/{workflow}/{YYYY}/
        return base / workflow_or_context / str(year)
    else:
        # streams/{source}/{context}/{YYYY}/
        return base / source / workflow_or_context / str(year)
```

**4. Filename Generation**
```python
def _generate_filename(
    date: datetime,
    source: str,
    base_filename: str,
    content_hash: str | None = None
) -> str:
    """Generate yyyy-mm-dd-source-filename with collision handling."""
    date_str = date.strftime("%Y-%m-%d")
    safe_name = sanitize_filename(base_filename)

    filename = f"{date_str}-{source}-{safe_name}"

    # If collision, append short hash
    if content_hash:
        hash_suffix = content_hash.split(":")[1][:8]
        stem, ext = os.path.splitext(filename)
        filename = f"{stem}-{hash_suffix}{ext}"

    return filename
```

**5. Manifest Management**
```python
def _append_to_manifest(self, metadata: dict) -> None:
    """Append metadata to manifest.jsonl for streaming consumers."""
    if not self.config.enable_manifest:
        return

    manifest_path = self.base_path / "manifest.jsonl"

    # Use file locking for concurrent writes
    with file_lock(manifest_path):
        with open(manifest_path, "a") as f:
            f.write(json.dumps(metadata, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
```

### 6. llmemory Integration Points

**In archive-protocol metadata:**
```json
{
  "llmemory": {
    "indexed_at": null,           // Set by indexer after processing
    "document_id": null,          // llmemory's UUID
    "chunks_created": null,       // How many chunks generated
    "embedding_model": null,      // Which model was used
    "embedding_provider": null    // openai, local-minilm, etc.
  }
}
```

**Indexer workflow:**
1. Watch for metadata files where `llmemory.indexed_at == null`
2. Extract text from content file
3. Call llmemory.add_document()
4. Update metadata with llmemory fields
5. Atomically rewrite metadata file

**Search integration:**
```python
# In archive CLI/UI
results = await memory.search(
    owner_id="jro",  # Entity
    query_text="amazon receipt october",
    metadata_filter={
        "workflow": "jro-expense",
        "source": "mail"
    }
)

# Results include llmemory chunks with archive-protocol metadata
for result in results:
    # Get full document from archive
    archive_id = result.metadata["archive_id"]  # or id_at_origin
    metadata = reader.load_metadata_by_id(archive_id)
    content_path = metadata["content"]["path"]
    # Open PDF, display to user
```

## Migration Path for mailflow

### Current State:
```python
# workflow.py current code
def save_pdf(...):
    output_path = directory / filename
    save_email_as_pdf(message, output_path, ...)

    # Store in metadata_store (SQLite FTS)
    metadata_store.store_pdf_metadata(
        filepath=output_path,
        email_data=email_data,
        ...
    )
```

### After archive-protocol:
```python
# workflow.py refactored
from archive_protocol import RepositoryWriter

def save_pdf(...):
    # Extract entity from workflow name
    entity = workflow_name.split('-')[0]  # jro-expense -> jro

    writer = RepositoryWriter(
        base_path=config.settings.get("archive", {}).get("base_path", "~/Archive"),
        entity=entity
    )

    # Convert email to PDF in memory
    pdf_bytes = convert_email_to_pdf_bytes(message, ...)

    # Write to repository
    result = writer.write_document(
        source="mail",
        workflow=workflow_name,
        content=pdf_bytes,
        filename=f"{email_data['subject']}.pdf",
        document_type="receipt",  # or classify dynamically
        origin_metadata={
            "mail": {
                "message_id": email_data["message_id"],
                "subject": email_data["subject"],
                "from": email_data["from"],
                "date": email_data["date"],
                "confidence_score": confidence,
            }
        }
    )

    logger.info(f"Saved to {result['content_path']}")
    return result
```

**Backward Compatibility:**
- Add config option: `archive.enabled = true/false`
- If disabled, use old code path (current ~/Documents/mailflow)
- If enabled, use archive-protocol
- Allow gradual migration

## Testing Strategy

### archive-protocol Tests:
```python
# test_writer.py
def test_write_document_to_workflow():
    """Test writing classified document to workflows/."""

def test_write_stream_to_streams():
    """Test writing unclassified content to streams/."""

def test_filename_collision_handling():
    """Test hash suffix added on collision."""

def test_atomic_write_cleanup_on_failure():
    """Test temp files cleaned up on error."""

def test_metadata_validation():
    """Test metadata schema enforcement."""
```

### Integration Tests:
```python
# In mailflow tests
def test_mailflow_with_archive_protocol(tmp_path):
    """Test mailflow writes to archive-protocol structure."""
    # Process email with archive.enabled=true
    # Verify files in ~/Archive/entities/jro/workflows/...
    # Verify metadata correct
```

## Repository Structure Examples

### Example 1: Email Receipt
```
~/Archive/
  manifest.jsonl
  entities/jro/
    workflows/jro-expense/2025/
      2025-10-23-mail-amazon-receipt.pdf
      2025-10-23-mail-amazon-receipt-logo.png
    metadata/workflows/jro-expense/2025/
      2025-10-23-mail-amazon-receipt.json
    indexes/
      fts.sqlite
      llmemory_checkpoints/
```

### Example 2: Slack Attachment
```
~/Archive/
  entities/jro/
    workflows/jro-expense/2025/
      2025-10-24-slack-contractor-invoice.pdf
    streams/slack/expenses/2025/
      2025-10-24.md         # Daily conversation transcript
      2025-10-24.json       # Raw API response
    metadata/
      workflows/jro-expense/2025/
        2025-10-24-slack-contractor-invoice.json
      streams/slack/expenses/2025/
        2025-10-24.json
```

### Example 3: Scanned Document
```
~/Archive/
  entities/jro/
    workflows/jro-tax-doc/2025/
      2025-01-31-localdocs-w2-form.pdf
    metadata/workflows/jro-tax-doc/2025/
      2025-01-31-localdocs-w2-form.json
```

## Archive-Indexer Service

**Purpose:** Keep llmemory in sync with archive repository.

**Modes:**
```bash
# One-shot: Index everything not indexed
archive-indexer run --entity jro

# Watch mode: Continuously monitor for new files
archive-indexer watch --entity jro

# Reindex: Force reindex all documents
archive-indexer reindex --entity jro --workflow jro-expense

# Status: Show indexing statistics
archive-indexer status --entity jro
```

**Implementation:**
```python
class ArchiveIndexer:
    def __init__(
        self,
        archive_path: Path,
        memory: AwordMemory,
        entity: str
    ):
        self.reader = MetadataReader(archive_path)
        self.memory = memory
        self.entity = entity

    async def index_unindexed(self) -> int:
        """Index all documents where llmemory.indexed_at is null."""
        count = 0

        for metadata_file in self.reader.find_unindexed(entity=self.entity):
            try:
                metadata = self.reader.load_metadata(metadata_file)
                await self._index_document(metadata)
                count += 1
            except Exception as e:
                logger.error(f"Failed to index {metadata_file}: {e}")

        return count

    async def _index_document(self, metadata: dict) -> None:
        """Index a single document in llmemory."""
        # Extract text from content
        content_path = self.reader.resolve_content_path(metadata)
        text = self._extract_text(content_path, metadata["content"]["mimetype"])

        # Add to llmemory
        result = await self.memory.add_document(
            owner_id=metadata["entity"],
            id_at_origin=metadata["id"],
            document_name=content_path.name,
            document_type=self._map_document_type(metadata.get("type")),
            content=text,
            metadata=self._flatten_metadata(metadata)
        )

        # Update archive metadata
        metadata["llmemory"] = {
            "indexed_at": datetime.now().isoformat(),
            "document_id": str(result.document_id),
            "chunks_created": result.chunks_created
        }
        self.reader.update_metadata(metadata_file, metadata)
```

## Configuration

### mailflow config.json:
```json
{
  "archive": {
    "enabled": true,
    "base_path": "~/Archive",
    "enable_manifest": true
  },
  "llmemory": {
    "enabled": true,
    "connection_string": "postgresql://localhost/archive",
    "auto_index": false  // If true, mailflow indexes immediately; if false, archive-indexer does it
  }
}
```

### Environment Variables:
```bash
# For all connectors
export ARCHIVE_BASE_PATH=~/Archive
export ARCHIVE_ENABLE_MANIFEST=true

# For llmemory integration
export DATABASE_URL=postgresql://localhost/archive
export OPENAI_API_KEY=sk-...
```

## Summary

**archive-protocol package:**
- ~500 lines of code
- Minimal dependencies (pydantic, dateutil)
- Reusable by all connectors
- Enforces consistent structure

**Benefits:**
- ✅ Mailflow stays focused on email
- ✅ Each connector is independent
- ✅ Shared protocol ensures compatibility
- ✅ llmemory integration clean and consistent
- ✅ Can build connectors as needed

**Timeline:**
- Week 1: archive-protocol package
- Week 2: Integrate into mailflow
- Week 3: Archive indexer for llmemory
- Future: Other connectors as needed

Ready to start on archive-protocol?
