# Metadata Storage Design for PDF Workflows

## Overview
Store comprehensive metadata for every PDF saved, enabling full-text search and tracking of email origins.

## Directory Structure
```
~/receipts/
├── receipts.db                    # SQLite database
├── 2024/
│   ├── 2024-01-15-amazon-invoice.pdf
│   ├── 2024-01-20-utility-bill.pdf
│   └── 2024-02-03-receipt.pdf
└── 2025/
    ├── 2025-01-08-invoice.pdf
    └── ...
```

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS pdf_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- File information
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    file_hash TEXT,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Email metadata
    email_message_id TEXT NOT NULL,
    email_from TEXT,
    email_to TEXT,
    email_subject TEXT,
    email_date TEXT,
    
    -- Email content
    email_body_text TEXT,      -- Plain text version
    email_body_html TEXT,      -- Original HTML
    email_headers TEXT,        -- JSON of all headers
    
    -- PDF metadata
    pdf_type TEXT,             -- 'attachment' or 'converted'
    pdf_original_filename TEXT, -- For attachments
    pdf_page_count INTEGER,
    pdf_text_content TEXT,     -- Extracted text from PDF
    
    -- Workflow information
    workflow_name TEXT,
    confidence_score REAL,
    
    -- Searchable content
    search_content TEXT,       -- Combined searchable text
    
    -- Mutt/Emacs integration
    mutt_folder TEXT,          -- e.g., "~/Mail/INBOX"
    original_email_path TEXT,  -- Full path to .eml file if available
    
    UNIQUE(email_message_id, filename)
);

-- Full-text search index
CREATE VIRTUAL TABLE IF NOT EXISTS pdf_search 
USING fts5(filename, email_subject, email_from, search_content, content=pdf_metadata);

-- Quick lookups
CREATE INDEX idx_email_date ON pdf_metadata(email_date);
CREATE INDEX idx_saved_at ON pdf_metadata(saved_at);
CREATE INDEX idx_workflow ON pdf_metadata(workflow_name);
```

## Implementation Plan

### 1. Update save_pdf Function
```python
def save_pdf(message: Dict[str, Any], directory: str, 
             filename_template: str = "{date}_{from}_{subject}",
             store_metadata: bool = True):
    """Save PDF with full metadata tracking"""
    
    # Create year-based path
    email_date = parse_email_date(message.get("date"))
    year_dir = Path(directory) / str(email_date.year)
    year_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with date prefix
    date_prefix = email_date.strftime("%Y-%m-%d")
    filename = f"{date_prefix}-{generate_filename(message, filename_template)}"
    
    # Save PDF (existing logic)
    pdf_path = save_pdf_file(message, year_dir, filename)
    
    # Store metadata
    if store_metadata:
        store_pdf_metadata(directory, pdf_path, message, workflow_name)
    
    return pdf_path
```

### 2. Metadata Storage Module
```python
# src/pmail/metadata_store.py
import sqlite3
from pathlib import Path
import hashlib
from typing import Dict, Any, Optional

class MetadataStore:
    def __init__(self, base_directory: str):
        self.base_dir = Path(base_directory)
        self.db_path = self.base_dir / f"{self.base_dir.name}.db"
        self._init_database()
    
    def store_pdf_metadata(self, pdf_path: Path, email_data: Dict[str, Any], 
                          workflow_name: str, pdf_text: Optional[str] = None):
        """Store comprehensive metadata for a saved PDF"""
        
        # Extract text from PDF if not provided
        if pdf_text is None and pdf_path.exists():
            pdf_text = extract_pdf_text(pdf_path)
        
        # Convert email body to plain text
        body_text = extract_text_from_html(email_data.get("body", ""))
        
        # Build searchable content
        search_content = " ".join([
            email_data.get("subject", ""),
            email_data.get("from", ""),
            body_text,
            pdf_text or ""
        ])
        
        # Store in database
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO pdf_metadata (
                    filename, filepath, email_message_id, email_from, 
                    email_to, email_subject, email_date, email_body_text,
                    email_body_html, pdf_text_content, workflow_name,
                    search_content, pdf_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (...))
```

### 3. PDF Text Extraction
```python
def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF for searching"""
    try:
        import pypdf2  # or pdfplumber
        with open(pdf_path, 'rb') as file:
            reader = pypdf2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
        return text
    except Exception as e:
        logger.warning(f"Could not extract PDF text: {e}")
        return ""
```

### 4. Search Interface
```python
def search_pdfs(directory: str, query: str) -> List[Dict[str, Any]]:
    """Search across all PDFs in a directory"""
    store = MetadataStore(directory)
    
    results = store.search(query)
    
    for result in results:
        print(f"{result['filename']} - {result['email_subject']}")
        print(f"  From: {result['email_from']} on {result['email_date']}")
        print(f"  Score: {result['relevance_score']}")
```

### 5. Mutt/Emacs Integration
```python
# Store the message-id for linking back
metadata["mutt_message_url"] = f"mutt://message-id/{email_data['message_id']}"
metadata["emacs_link"] = f"[[mutt:msgid:{email_data['message_id']}][Email]]"
```

## Benefits

1. **Full-Text Search**: Find any PDF by content, sender, subject, or date
2. **Context Preservation**: Know exactly which email generated each PDF
3. **Deduplication**: Check if we already saved this email
4. **Analytics**: Track patterns, volumes, senders over time
5. **Integration**: Jump back to original email from PDF reference

## Example Usage

```bash
# After implementing, users could:
pmail-search ~/receipts "amazon invoice 2024"
pmail-search ~/bills "utility january"

# Or from Python:
from pmail.metadata_store import search_pdfs
results = search_pdfs("~/receipts", "tax deductible")
```

## Migration Strategy

1. Make metadata storage optional initially
2. Add `--rebuild-metadata` command to scan existing PDFs
3. Extract dates from existing filenames where possible
4. Gradually build up metadata for new saves

## Future Enhancements

1. OCR support for scanned PDFs
2. Duplicate detection before saving
3. Export to CSV/JSON for analysis
4. Web interface for searching
5. Automatic categorization based on content