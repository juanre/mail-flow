# Contextual Feature Parity Implementation Design

**Date**: 2025-10-24
**Status**: Approved
**Goal**: Achieve complete feature parity between Mailflow and Contextual's email processing capabilities

---

## Executive Summary

This design integrates all production-grade email processing capabilities from Contextual (5+ years of development) into Mailflow while preserving Mailflow's superior classification and routing architecture. The implementation uses a layered architecture approach with complete feature parity.

**Key Decisions:**
- ✅ Layered architecture (Email Storage Layer + Classification Layer + Document Storage Layer)
- ✅ Store full emails like Contextual (enables all conversation features)
- ✅ Incremental implementation with agents (test each phase before proceeding)
- ✅ Archive-protocol handles document metadata (no duplicate storage)
- ✅ Single `emails.db` for email storage, threading, and deduplication

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Mailflow CLI / User Interface                   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│    Classification & Routing Layer (existing)            │
│    - HybridClassifier                                   │
│    - SimilarityEngine                                   │
│    - LLMClassifier                                      │
│    - WorkflowExecutor                                   │
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  Email Storage Layer     │  │  Document Storage Layer  │
│  (NEW - from Contextual) │  │  (existing - archive-    │
│                          │  │   protocol)              │
│  - Email extraction      │  │                          │
│  - Quote handling        │  │  - save_pdf()            │
│  - Thread reconstruction │  │  - save_attachment()     │
│  - Content cleaning      │  │  - Year-based structure  │
│  - Full email storage    │  │                          │
│  - Bidirectional linking │  │                          │
└──────────────────────────┘  └──────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│    Email Database (SQLite: emails.db)                   │
│    - emails table (full content + metadata)             │
│    - thread_links table (conversation relationships)    │
│    - attachments table (metadata + text, not bytes)     │
│    - FTS5 for full-text search                         │
└─────────────────────────────────────────────────────────┘
```

**Key Principles:**
1. **Email Storage Layer** - Handles all email persistence and retrieval (Contextual's capabilities)
2. **Classification Layer** - Uses Email Storage Layer for context (Mailflow's strength)
3. **Document Storage Layer** - Archive-protocol for organized document filing
4. **Clean interfaces** - Each layer evolves independently

---

## Email Storage Layer Components

### Module Structure

```
src/mailflow/email_storage/
├── __init__.py
├── email_store.py          # Main interface (SQLite operations)
├── email_extractor.py      # Enhanced from existing
├── quote_extraction.py     # NEW - from Contextual
├── content_cleaning.py     # NEW - from Contextual
├── thread_builder.py       # NEW - from Contextual
├── sender_extraction.py    # NEW - from Contextual
└── document_ingest.py      # NEW - from Contextual
```

### Module Responsibilities

**1. email_store.py** - Database interface
- Store/retrieve full emails with all headers
- Thread relationship management (parent-child linking)
- Full-text search across emails
- Deduplication (message-id + content hash)
- Query by thread_id, message-id, sender, date ranges

**2. email_extractor.py** - Enhanced extraction
- Current functionality preserved
- Add: in-reply-to, references, cc, bcc, reply-to headers
- Integrate quote extraction
- Integrate content cleaning
- Store full email body (not just preview)

**3. quote_extraction.py** - Three-level quote handling
- `get_current_level_content()` - new content only
- `get_most_recent_quote()` - most recent quoted reply
- `get_fullthread_quotes()` - all quotes
- Pattern recognition for Mutt/Outlook/Gmail formats

**4. content_cleaning.py** - Robust sanitization
- Remove UTF-8 BOM
- Normalize CRLF → LF
- Remove control characters
- Collapse excessive whitespace
- HTML sanitization (enhance existing)

**5. thread_builder.py** - Conversation reconstruction
- Parse In-Reply-To and References headers
- Build parent-child relationships
- Assign thread IDs
- Bidirectional linking (parent knows replies)
- Handle out-of-order delivery

**6. sender_extraction.py** - Quote attribution
- Pattern matching for "On X wrote:" formats
- Fallback to parent email lookup
- Support multiple email client formats

**7. document_ingest.py** - Attachment content extraction
- PDF text extraction (PyPDF2/pdfplumber)
- DOCX text extraction (python-docx)
- XLSX text extraction (openpyxl)
- Store in attachments.text_content for FTS indexing
- **NOTE**: Does NOT store file bytes (only extracted text)

---

## Database Schema

### Single Database: emails.db

**Handles:**
- Email storage with full content
- Thread relationships
- Attachment metadata + text
- Deduplication tracking
- Processing status

**Does NOT handle:**
- Document metadata (archive-protocol JSON files)
- Document file bytes (archive-protocol directories)

```sql
-- Main emails table
CREATE TABLE emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Unique identifiers & deduplication
    message_id TEXT UNIQUE NOT NULL,     -- RFC822 Message-ID
    content_hash TEXT UNIQUE NOT NULL,   -- SHA-256 (prevents duplicates)

    -- Thread relationships
    thread_id TEXT NOT NULL,             -- Assigned thread identifier
    parent_id INTEGER,                   -- FK to emails.id
    in_reply_to TEXT,                    -- RFC822 In-Reply-To header
    references TEXT,                     -- RFC822 References (space-separated)

    -- Headers
    from_address TEXT NOT NULL,
    from_name TEXT,
    to_address TEXT,
    cc TEXT,                             -- JSON array
    bcc TEXT,                            -- JSON array
    reply_to TEXT,
    subject TEXT,
    date TEXT NOT NULL,                  -- ISO format

    -- Content (full storage)
    body_text TEXT,                      -- Plain text body
    body_html TEXT,                      -- HTML body (if present)
    body_clean TEXT,                     -- After content cleaning
    new_content TEXT,                    -- Current level (quotes removed)
    recent_quote TEXT,                   -- Most recent quoted reply
    all_quotes TEXT,                     -- JSON array of all quotes

    -- Email metadata
    headers TEXT,                        -- JSON: all headers
    mime_type TEXT,
    size INTEGER,                        -- Bytes

    -- Mailing list headers
    list_id TEXT,
    list_post TEXT,

    -- Processing metadata
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    workflow_name TEXT,                  -- Which workflow handled this
    processing_status TEXT DEFAULT 'pending',  -- 'pending', 'processed', 'skipped', 'error'

    FOREIGN KEY (parent_id) REFERENCES emails(id) ON DELETE SET NULL
);

-- Indexes
CREATE INDEX idx_message_id ON emails(message_id);
CREATE INDEX idx_content_hash ON emails(content_hash);
CREATE INDEX idx_thread_id ON emails(thread_id);
CREATE INDEX idx_parent_id ON emails(parent_id);
CREATE INDEX idx_from_address ON emails(from_address);
CREATE INDEX idx_date ON emails(date);
CREATE INDEX idx_workflow ON emails(workflow_name);
CREATE INDEX idx_processing_status ON emails(processing_status);


-- Thread relationships (bidirectional)
CREATE TABLE thread_links (
    parent_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,
    link_type TEXT DEFAULT 'reply',      -- 'reply', 'reference', 'related'

    PRIMARY KEY (parent_id, child_id),
    FOREIGN KEY (parent_id) REFERENCES emails(id) ON DELETE CASCADE,
    FOREIGN KEY (child_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE INDEX idx_thread_parent ON thread_links(parent_id);
CREATE INDEX idx_thread_child ON thread_links(child_id);


-- Attachments (metadata + extracted text, NOT file bytes)
CREATE TABLE attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL,

    -- File metadata
    filename TEXT NOT NULL,
    original_filename TEXT,              -- Before sanitization
    content_type TEXT,
    size INTEGER,
    content_hash TEXT,                   -- SHA-256 for deduplication

    -- Extracted content for search
    text_content TEXT,                   -- Extracted from PDF/Office docs
    extraction_status TEXT,              -- 'success', 'failed', 'pending'

    -- Classification hints
    is_pdf BOOLEAN,
    is_image BOOLEAN,
    is_document BOOLEAN,

    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE INDEX idx_attachment_email ON attachments(email_id);
CREATE INDEX idx_attachment_hash ON attachments(content_hash);


-- Full-text search (FTS5)
CREATE VIRTUAL TABLE email_search USING fts5(
    message_id UNINDEXED,
    from_address,
    from_name,
    to_address,
    subject,
    body_clean,
    new_content,
    attachment_text,
    content='emails',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER emails_ai AFTER INSERT ON emails BEGIN
    INSERT INTO email_search(rowid, message_id, from_address, from_name,
                            to_address, subject, body_clean, new_content)
    VALUES (new.id, new.message_id, new.from_address, new.from_name,
            new.to_address, new.subject, new.body_clean, new.new_content);
END;

CREATE TRIGGER emails_ad AFTER DELETE ON emails BEGIN
    DELETE FROM email_search WHERE rowid = old.id;
END;

CREATE TRIGGER emails_au AFTER UPDATE ON emails BEGIN
    UPDATE email_search SET
        from_address = new.from_address,
        from_name = new.from_name,
        to_address = new.to_address,
        subject = new.subject,
        body_clean = new.body_clean,
        new_content = new.new_content
    WHERE rowid = new.id;
END;
```

---

## Layer Interactions

### Complete Email Processing Flow

```
1. Email Arrives (stdin/Mutt/Gmail)
   │
   ▼
2. Email Storage Layer
   ├─ Extract full email with all headers
   ├─ Clean content (BOM, CRLF, control chars)
   ├─ Extract quotes (3 levels: full/recent/new)
   ├─ Extract sender from quotes
   ├─ Extract attachment metadata + text content
   ├─ Build thread relationships (In-Reply-To, References)
   ├─ Store in emails.db
   └─ Return: Email object with thread context
   │
   ▼
3. Classification Layer
   ├─ Query Email Storage Layer for thread history
   ├─ Build enriched context:
   │  - Email metadata (from, subject, date)
   │  - Clean content (quotes removed)
   │  - Thread context (previous emails in conversation)
   │  - Attachment text content (searchable)
   ├─ Run classification (similarity + LLM)
   ├─ User selects workflow
   └─ Return: workflow_name, confidence
   │
   ▼
4. Workflow Execution
   ├─ Extract entity from workflow (jro-expense → jro)
   ├─ Get attachment bytes from email (in memory)
   ├─ Call archive-protocol:
   │  └─ writer.write_document(
   │       source="mail",
   │       workflow="jro-expense",
   │       content=pdf_bytes,
   │       origin_metadata={"mail": {...email data...}}
   │     )
   ├─ Archive-protocol saves:
   │  - PDF to ~/Archive/entities/jro/workflows/jro-expense/2025/
   │  - Metadata JSON to ~/Archive/entities/jro/metadata/workflows/...
   └─ Return: document paths
   │
   ▼
5. Update Email Storage Layer
   └─ Mark email as processed:
      emails.workflow_name = "jro-expense"
      emails.processing_status = "processed"
      emails.processed_at = NOW()
```

### Key Interface Contracts

```python
# 1. Email Storage Layer → Classification Layer
class EmailStore:
    def get_email(self, message_id: str) -> Email:
        """Get email with all extracted fields"""

    def get_thread(self, thread_id: str) -> List[Email]:
        """Get all emails in conversation, ordered chronologically"""

    def search_emails(self, query: str, **filters) -> List[Email]:
        """Full-text search across emails"""

    def mark_processed(self, message_id: str, workflow: str) -> None:
        """Mark email as processed by workflow"""

# 2. Classification Layer → Document Storage Layer
from archive_protocol import RepositoryWriter

writer = RepositoryWriter(base_path="~/Archive", entity="jro")
result = writer.write_document(
    source="mail",
    workflow="jro-expense",
    content=pdf_bytes,
    filename="invoice.pdf",
    document_type=DocumentType.RECEIPT,
    origin_metadata={
        "mail": {
            "message_id": email.message_id,
            "from": email.from_address,
            "subject": email.subject,
            "thread_id": email.thread_id,
            "has_attachments": len(email.attachments) > 0
        }
    }
)

# 3. Document → Email lookup
from archive_protocol import MetadataReader

reader = MetadataReader(base_path="~/Archive")
doc_metadata = reader.load_metadata(metadata_path)
message_id = doc_metadata["origin"]["mail"]["message_id"]

email = email_store.get_email(message_id)
thread = email_store.get_thread(email.thread_id)
```

### Enhanced Classification with Thread Context

```python
# Before (current mailflow):
classification = hybrid_classifier.classify(
    email_data=email_data,  # Single email only
    workflows=workflows,
    criteria_instances=criteria
)

# After (with Email Storage Layer):
email = email_store.get_email(message_id)
thread = email_store.get_thread(email.thread_id)

classification = hybrid_classifier.classify(
    email_data=email.to_dict(),
    thread_context={
        "emails": [e.to_dict() for e in thread],
        "participants": set(e.from_address for e in thread),
        "subject_thread": thread[0].subject if thread else email.subject,
        "conversation_length": len(thread)
    },
    workflows=workflows,
    criteria_instances=criteria
)

# LLM gets richer context:
prompt = f"""
Classify this email:
From: {email.from_address}
Subject: {email.subject}
Content: {email.new_content}  # Quotes removed!

Previous conversation (thread of {len(thread)} emails):
{format_thread_history(thread)}

Available workflows: {workflows}
"""
```

---

## Implementation Phases

### Phase 1: Core Email Storage (Week 1)

**Goals:**
- Port quote extraction (3 algorithms)
- Port content cleaning pipeline
- Create email_store.py with database schema
- Enhanced email_extractor.py with all headers
- Basic thread reconstruction (In-Reply-To parsing)

**Deliverables:**
- `src/mailflow/email_storage/quote_extraction.py` (~200 LOC)
- `src/mailflow/email_storage/content_cleaning.py` (~100 LOC)
- `src/mailflow/email_storage/email_store.py` (~400 LOC)
- Enhanced `src/mailflow/email_extractor.py`
- Tests: `tests/email_storage/test_*.py`

**Source Files from Contextual:**
- `contextual/src/contextual/email_utils.py:45-180` (quote extraction)
- `contextual/src/contextual/email_utils.py:15-40` (content cleaning)
- `contextual/src/contextual/message_store.py` (database operations)

**Test Data:**
- `contextual/tests/fixtures/email_quotes/`
- `contextual/tests/fixtures/email_encoding/`

**Success Criteria:**
- All quote extraction tests passing
- Content cleaning handles BOM, CRLF, control chars
- Emails stored with full content in database
- Deduplication working (message-id + content hash)

---

### Phase 2: Advanced Threading (Week 1-2)

**Goals:**
- Complete thread_builder.py (References header, thread IDs)
- Bidirectional linking (parent-child)
- Sender extraction from quotes
- Thread navigation methods

**Deliverables:**
- `src/mailflow/email_storage/thread_builder.py` (~400 LOC)
- `src/mailflow/email_storage/sender_extraction.py` (~150 LOC)
- Enhanced email_store.py with thread queries
- Tests: `tests/email_storage/test_thread_*.py`

**Source Files from Contextual:**
- `contextual/src/contextual/message_store.py:120-450` (threading)
- `contextual/src/contextual/email_utils.py:185-240` (sender extraction)

**Test Data:**
- `contextual/tests/fixtures/email_threads/`

**Success Criteria:**
- Thread reconstruction from In-Reply-To/References
- Bidirectional navigation (parent → children, child → parent)
- Thread IDs automatically assigned
- Sender extraction from multiple quote formats

---

### Phase 3: Document Ingestion (Week 2)

**Goals:**
- Port document_ingest.py
- PDF text extraction (PyPDF2/pdfplumber)
- Office docs (python-docx, openpyxl)
- Store in attachments.text_content
- Update FTS5 to include attachment text

**Deliverables:**
- `src/mailflow/email_storage/document_ingest.py` (~500 LOC)
- Updated email_store.py with attachment text indexing
- Tests: `tests/email_storage/test_document_ingest.py`

**Source Files from Contextual:**
- `contextual/services/documents/ingest.py`

**New Dependencies:**
```toml
dependencies = [
    "pypdf2>=3.0.0",
    "python-docx>=1.1.0",
    "openpyxl>=3.1.0",
]
```

**Success Criteria:**
- Extract text from PDF attachments
- Extract text from DOCX/XLSX attachments
- FTS search finds text inside attachments
- Graceful handling of corrupted files

---

### Phase 4: Archive-Protocol Integration (Week 2-3)

**Goals:**
- Update workflow.py to use RepositoryWriter
- Link emails.message_id to archive-protocol metadata
- Remove old pdf_metadata.db references
- Update all workflow actions

**Deliverables:**
- Updated `src/mailflow/workflow.py`
- Updated `src/mailflow/attachment_handler.py`
- Updated `src/mailflow/pdf_converter.py`
- Migration guide (if needed)

**Changes:**
```python
# Before:
def save_pdf(email_data, directory, ...):
    output_path = directory / filename
    save_email_as_pdf(message, output_path, ...)
    metadata_store.store_pdf_metadata(...)

# After:
def save_pdf(email_data, workflow_name, ...):
    entity = workflow_name.split('-')[0]
    writer = RepositoryWriter(base_path="~/Archive", entity=entity)
    pdf_bytes = convert_email_to_pdf_bytes(message, ...)
    result = writer.write_document(
        source="mail",
        workflow=workflow_name,
        content=pdf_bytes,
        origin_metadata={"mail": {...}}
    )
```

**Success Criteria:**
- Documents saved to archive-protocol structure
- Metadata JSON includes email message_id
- No duplicate metadata storage
- All workflows updated (save_pdf, save_attachment, save_email_as_pdf)

---

### Phase 5: Classification Enhancement (Week 3)

**Goals:**
- Update HybridClassifier to use thread context
- Enhance LLM prompts with conversation history
- Use clean content (quotes removed) for classification
- Use attachment text for better matching

**Deliverables:**
- Updated `src/mailflow/hybrid_classifier.py`
- Updated `src/mailflow/llm_classifier.py`
- Updated `src/mailflow/similarity.py`
- Tests: `tests/test_classification_with_threads.py`

**Changes:**
```python
# Enhanced similarity scoring
features = {
    "from_domain": email.from_domain,
    "subject_words": extract_words(email.subject),
    "body_words": extract_words(email.new_content),  # NEW: quotes removed
    "thread_participants": [e.from_address for e in thread],  # NEW
    "attachment_text": " ".join(a.text_content for a in attachments),  # NEW
    "has_pdf": any(a.is_pdf for a in attachments),
}
```

**Success Criteria:**
- Classification uses clean content (no quoted replies)
- LLM receives thread context in prompt
- Attachment text content used in similarity scoring
- Better classification accuracy on reply emails

---

### Phase 6: Reply Drafting (Week 3-4)

**Goals:**
- Port reply drafting module
- Use thread context + entity context
- Optional feature (can be enabled/disabled)

**Deliverables:**
- `src/mailflow/reply_drafting.py` (~600 LOC)
- CLI command: `mailflow draft-reply <message-id>`
- Configuration option to enable/disable
- Tests: `tests/test_reply_drafting.py`

**Source Files from Contextual:**
- `contextual/src/contextual/reply_drafting.py`

**Success Criteria:**
- Draft replies using full thread context
- Configurable tone/style preferences
- Optional feature (disabled by default)
- Integration with email store for thread lookup

---

## Testing Strategy

### Test Organization

```
tests/
├── email_storage/
│   ├── test_quote_extraction.py      # 3-level quote algorithms
│   ├── test_content_cleaning.py      # BOM, CRLF, control chars
│   ├── test_email_store.py           # Database operations
│   ├── test_thread_builder.py        # Thread reconstruction
│   ├── test_sender_extraction.py     # Quote attribution
│   └── test_document_ingest.py       # PDF/Office text extraction
│
├── integration/
│   ├── test_email_to_storage.py      # Email → database flow
│   ├── test_storage_to_classification.py  # Thread context usage
│   ├── test_classification_to_archive.py  # Workflow execution
│   └── test_end_to_end.py            # Complete email processing
│
└── fixtures/
    ├── email_quotes/                 # From Contextual
    ├── email_threads/                # From Contextual
    ├── email_encoding/               # From Contextual
    └── attachments/                  # PDF/Office test files
```

### Test Data from Contextual

Copy test fixtures:
```bash
cp -r /Users/juanre/prj/contextual/tests/fixtures/email_quotes tests/fixtures/
cp -r /Users/juanre/prj/contextual/tests/fixtures/email_threads tests/fixtures/
cp -r /Users/juanre/prj/contextual/tests/fixtures/email_encoding tests/fixtures/
```

### Test-Driven Development (TDD)

For each phase:
1. **Write tests first** (based on Contextual's test suite)
2. **Implement feature** (port from Contextual)
3. **Run tests** → verify functionality
4. **Code review** → ensure quality
5. **Update progress document**

### Example Test Coverage

```python
# tests/email_storage/test_quote_extraction.py
def test_get_current_level_content_removes_all_quotes():
    """Test that all quoted content is removed"""
    email_body = """
    This is my response.

    > You asked a question.
    >
    >> Someone else said this.
    """
    result = get_current_level_content(email_body)
    assert result.strip() == "This is my response."


def test_get_most_recent_quote_extracts_latest():
    """Test extraction of most recent quoted reply"""
    email_body = """
    My response.

    > Recent quote here.

    >> Older quote here.
    """
    result = get_most_recent_quote(email_body)
    assert "Recent quote" in result
    assert "Older quote" not in result


def test_get_fullthread_quotes_all_levels():
    """Test extraction of all quotes at all levels"""
    email_body = """
    New content.
    > Level 1
    >> Level 2
    >>> Level 3
    """
    result = get_fullthread_quotes(email_body)
    assert len(result) == 3
    assert "Level 1" in result[0]
    assert "Level 2" in result[1]
    assert "Level 3" in result[2]
```

---

## Agent Workflow

### Per-Phase Agent Usage

For each implementation phase:

1. **Launch test-writer agent**
   ```python
   Task(
       subagent_type="test-writer",
       description="Write tests for quote extraction",
       prompt="""
       Write comprehensive tests for quote extraction module.
       Port test cases from Contextual: contextual/tests/test_email_utils.py:200-350
       Test fixtures available in: tests/fixtures/email_quotes/

       Test coverage:
       - get_current_level_content() - remove all quotes
       - get_most_recent_quote() - extract latest quote
       - get_fullthread_quotes() - extract all levels
       - Edge cases: nested quotes, malformed attribution, mixed formats
       """
   )
   ```

2. **Launch implementation agent**
   ```python
   Task(
       subagent_type="general-purpose",
       description="Implement quote extraction",
       prompt="""
       Port quote extraction from Contextual to Mailflow.
       Source: contextual/src/contextual/email_utils.py:45-180
       Destination: src/mailflow/email_storage/quote_extraction.py

       Requirements:
       - All three functions: get_current_level_content, get_most_recent_quote, get_fullthread_quotes
       - Support Mutt, Outlook, Gmail quote formats
       - Pass all tests in tests/email_storage/test_quote_extraction.py
       """
   )
   ```

3. **Verify tests pass**
   ```bash
   pytest tests/email_storage/test_quote_extraction.py -v
   ```

4. **Launch code-reviewer agent**
   ```python
   Task(
       subagent_type="code-reviewer",
       description="Review quote extraction",
       prompt="""
       Review the quote extraction implementation.
       Check:
       - Code quality and maintainability
       - Test coverage (should be >90%)
       - Edge case handling
       - Documentation completeness
       - Security considerations
       """
   )
   ```

5. **Update progress document**
   - Mark phase complete in `MAILFLOW_VS_CONTEXTUAL_COMPARISON.md`
   - Commit changes with descriptive message

6. **Move to next phase**

---

## Progress Tracking

### Update Comparison Document

After each phase, update `MAILFLOW_VS_CONTEXTUAL_COMPARISON.md`:

```markdown
## Implementation Progress

### Phase 1: Core Email Storage ✅
**Status**: Complete
**Date**: 2025-10-24

- [✅] Quote extraction ported
  - File: `src/mailflow/email_storage/quote_extraction.py`
  - Tests: `tests/email_storage/test_quote_extraction.py` (15 tests, 95% coverage)
  - Source: `contextual/src/contextual/email_utils.py:45-180`

- [✅] Content cleaning ported
  - File: `src/mailflow/email_storage/content_cleaning.py`
  - Tests: `tests/email_storage/test_content_cleaning.py` (12 tests, 90% coverage)
  - Source: `contextual/src/contextual/email_utils.py:15-40`

- [✅] Email store created
  - File: `src/mailflow/email_storage/email_store.py`
  - Tests: `tests/email_storage/test_email_store.py` (25 tests, 88% coverage)
  - Database: `~/.local/share/mailflow/emails.db`

- [✅] Email extractor enhanced
  - File: `src/mailflow/email_extractor.py` (updated)
  - Added headers: in-reply-to, references, cc, bcc, reply-to
  - Integrated quote extraction and content cleaning

**Code Review**: ✅ Approved
**Integration Tests**: ✅ All passing

---

### Phase 2: Advanced Threading 🚧
**Status**: In Progress
**Started**: 2025-10-25

- [🚧] Thread builder implementation
- [ ] Bidirectional linking
- [ ] Sender extraction from quotes
- [ ] Thread navigation methods
```

---

## Code Migration Reference

### Key Files to Port from Contextual

| Feature | Contextual Source | Mailflow Destination | LOC | Complexity |
|---------|------------------|---------------------|-----|------------|
| Quote Extraction | `email_utils.py:45-180` | `quote_extraction.py` | ~200 | Low |
| Content Cleaning | `email_utils.py:15-40` | `content_cleaning.py` | ~100 | Low |
| Email Store | `message_store.py:30-450` | `email_store.py` | ~400 | Medium |
| Thread Builder | `message_store.py:120-300` | `thread_builder.py` | ~400 | Medium |
| Sender Extraction | `email_utils.py:185-240` | `sender_extraction.py` | ~150 | Low |
| Document Ingestion | `services/documents/ingest.py` | `document_ingest.py` | ~500 | High |
| Reply Drafting | `reply_drafting.py` | `reply_drafting.py` | ~600 | High |

### Adaptation Notes

**What to preserve exactly:**
- Quote extraction algorithms (proven, well-tested)
- Content cleaning pipeline (handles real-world edge cases)
- Thread reconstruction logic (In-Reply-To/References parsing)
- Sender extraction patterns (multiple email client formats)

**What to adapt:**
- Database operations → Use SQLite (not Contextual's format)
- File paths → Use Mailflow's config system
- Logging → Use Mailflow's logger
- Error handling → Match Mailflow's patterns

**What to skip:**
- Org-mode formatting (Mailflow uses archive-protocol)
- Mutt keybindings (Mailflow supports multiple sources)
- Task system (different architecture)

---

## Success Criteria

### Feature Parity Checklist

**Email Extraction:**
- [✅] RFC822 parsing (already done)
- [ ] All headers extracted (in-reply-to, references, cc, bcc, reply-to)
- [ ] Quote extraction (3 levels)
- [ ] Content cleaning (BOM, CRLF, control chars)
- [ ] Sender extraction from quotes

**Thread/Conversation:**
- [ ] Thread reconstruction from In-Reply-To/References
- [ ] Thread ID assignment
- [ ] Parent-child relationships
- [ ] Bidirectional navigation
- [ ] Out-of-order delivery handling

**Attachment Processing:**
- [✅] Binary extraction (already done)
- [ ] PDF text extraction
- [ ] Office document text extraction
- [ ] FTS indexing of attachment content

**Storage:**
- [ ] Full email storage (not just previews)
- [ ] Deduplication (message-id + content hash)
- [ ] FTS5 search
- [ ] Archive-protocol integration

**Classification Enhancement:**
- [ ] Thread context in classification
- [ ] Clean content (quotes removed)
- [ ] Attachment text in similarity scoring
- [ ] Enhanced LLM prompts

**Optional Features:**
- [ ] Reply drafting (optional, can be disabled)

### Quality Gates

Each phase must pass:
- ✅ All unit tests passing (>90% coverage)
- ✅ Integration tests passing
- ✅ Code review approved
- ✅ Documentation updated
- ✅ No regressions in existing functionality

---

## Risk Mitigation

### Identified Risks

**1. Database Schema Changes**
- **Risk**: Breaking changes to existing databases
- **Mitigation**: New `emails.db` separate from existing DBs; migration scripts if needed

**2. Performance Impact**
- **Risk**: Storing full emails increases database size
- **Mitigation**: Test with large email corpus; add cleanup tools if needed

**3. Archive-Protocol Integration**
- **Risk**: Changes to workflow execution might break existing users
- **Mitigation**: Incremental rollout; config flag to enable new features

**4. Test Data Quality**
- **Risk**: Contextual's test fixtures might not cover all edge cases
- **Mitigation**: Add real-world test cases from actual Mailflow usage

### Rollback Plan

If major issues arise:
1. Keep old code paths working (don't delete immediately)
2. Config flag to disable new features: `email_storage.enabled = false`
3. Database rollback: Delete `emails.db`, fallback to old behavior
4. Git branch protection: All changes via PR with reviews

---

## Timeline Estimate

### Optimistic (3-4 weeks)
- Week 1: Phases 1-2 (Core storage + threading)
- Week 2: Phases 3-4 (Document ingestion + archive-protocol)
- Week 3: Phase 5 (Classification enhancement)
- Week 4: Phase 6 (Reply drafting) + polish

### Realistic (5-6 weeks)
- Weeks 1-2: Phases 1-2 with thorough testing
- Weeks 3-4: Phases 3-4 with integration testing
- Week 5: Phase 5 with real-world validation
- Week 6: Phase 6 + documentation + edge cases

### Conservative (7-8 weeks)
- Add 1-2 weeks buffer for:
  - Unexpected edge cases
  - Performance optimization
  - User testing and feedback
  - Documentation and migration guides

---

## Conclusion

This design achieves complete feature parity with Contextual's production-grade email processing while:
- ✅ Preserving Mailflow's superior classification/routing
- ✅ Using layered architecture for maintainability
- ✅ Leveraging archive-protocol for document storage
- ✅ Incremental implementation with quality gates
- ✅ Comprehensive testing at each phase

The implementation will be tracked in the comparison document and executed using specialized agents for each phase, ensuring quality and systematic progress.

**Next Steps:**
1. Set up git worktree for isolated development
2. Begin Phase 1: Core Email Storage
3. Port quote extraction and content cleaning
4. Build foundation for subsequent phases
