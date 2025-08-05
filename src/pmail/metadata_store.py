"""
Metadata storage for PDF workflows using SQLite.
Tracks email origins, content, and enables full-text search.
"""

import sqlite3
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from contextlib import contextmanager

from pmail.exceptions import DataError
from pmail.security import sanitize_filename

logger = logging.getLogger(__name__)


# Document type constants
class DocumentType:
    INVOICE = "invoice"
    RECEIPT = "receipt"
    STATEMENT = "statement"
    TAX = "tax"
    CONTRACT = "contract"
    REPORT = "report"
    UNKNOWN = "unknown"


# Document category constants
class DocumentCategory:
    PURCHASE = "purchase"
    EXPENSE = "expense"
    FINANCIAL = "financial"
    GOVERNMENT = "government"
    LEGAL = "legal"
    BUSINESS = "business"
    PERSONAL = "personal"
    UNCATEGORIZED = "uncategorized"


class MetadataStore:
    """Store and search metadata for saved PDFs."""

    def __init__(self, base_directory: str):
        self.base_dir = Path(base_directory).expanduser()
        self.db_path = self.base_dir / f"{self.base_dir.name}.db"
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with schema."""
        with self.get_connection() as conn:
            # Main metadata table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pdf_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    -- File information
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    file_hash TEXT,
                    file_size INTEGER,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Email metadata
                    email_message_id TEXT NOT NULL,
                    email_from TEXT,
                    email_to TEXT,
                    email_subject TEXT,
                    email_date TEXT,
                    
                    -- Email content
                    email_body_text TEXT,
                    email_body_html TEXT,
                    email_headers TEXT,  -- JSON
                    
                    -- PDF metadata
                    pdf_type TEXT,  -- 'attachment' or 'converted'
                    pdf_original_filename TEXT,
                    pdf_page_count INTEGER,
                    pdf_text_content TEXT,
                    
                    -- Workflow information
                    workflow_name TEXT,
                    confidence_score REAL,
                    
                    -- Document classification
                    document_type TEXT,  -- 'invoice', 'receipt', 'tax', 'statement', etc.
                    document_category TEXT,  -- broader category
                    
                    -- Extracted document information (JSON)
                    document_info TEXT,  -- JSON with extracted fields
                    
                    -- Search content
                    search_content TEXT,
                    
                    -- Integration
                    mutt_folder TEXT,
                    original_email_path TEXT,
                    
                    UNIQUE(email_message_id, filename)
                )
            """
            )

            # Full-text search
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS pdf_search 
                USING fts5(
                    filename, 
                    email_subject, 
                    email_from, 
                    search_content, 
                    content=pdf_metadata
                )
            """
            )

            # Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email_date ON pdf_metadata(email_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_at ON pdf_metadata(saved_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow ON pdf_metadata(workflow_name)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_message_id ON pdf_metadata(email_message_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_type ON pdf_metadata(document_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_category ON pdf_metadata(document_category)"
            )

            conn.commit()

    @contextmanager
    def get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise DataError(f"Database operation failed: {e}")
        finally:
            if conn:
                conn.close()

    def store_pdf_metadata(
        self,
        pdf_path: Path,
        email_data: Dict[str, Any],
        workflow_name: str,
        pdf_type: str = "attachment",
        pdf_text: Optional[str] = None,
        confidence_score: Optional[float] = None,
        document_type: str = DocumentType.UNKNOWN,
        document_category: str = DocumentCategory.UNCATEGORIZED,
        document_info: Optional[Dict[str, Any]] = None,
    ):
        """Store comprehensive metadata for a saved PDF."""
        try:
            # Calculate file hash
            file_hash = self._calculate_file_hash(pdf_path)

            # Extract plain text from email body
            body_text = self._extract_text_from_body(email_data.get("body", ""))

            # Build searchable content
            search_content = " ".join(
                filter(
                    None,
                    [
                        email_data.get("subject", ""),
                        email_data.get("from", ""),
                        body_text,
                        pdf_text or "",
                    ],
                )
            )

            # Prepare data
            metadata = {
                "filename": pdf_path.name,
                "filepath": str(pdf_path.relative_to(self.base_dir)),
                "file_hash": file_hash,
                "file_size": pdf_path.stat().st_size,
                "email_message_id": email_data.get("message_id", ""),
                "email_from": email_data.get("from", ""),
                "email_to": email_data.get("to", ""),
                "email_subject": email_data.get("subject", ""),
                "email_date": email_data.get("date", ""),
                "email_body_text": body_text,
                "email_body_html": email_data.get("body", ""),
                "email_headers": json.dumps(email_data.get("headers", {})),
                "pdf_type": pdf_type,
                "pdf_original_filename": email_data.get("original_filename"),
                "pdf_text_content": pdf_text,
                "workflow_name": workflow_name,
                "confidence_score": confidence_score,
                "search_content": search_content,
                "document_type": document_type,
                "document_category": document_category,
                "document_info": json.dumps(document_info) if document_info else None,
            }

            # Store in database
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pdf_metadata (
                        filename, filepath, file_hash, file_size,
                        email_message_id, email_from, email_to, 
                        email_subject, email_date, email_body_text,
                        email_body_html, email_headers, pdf_type,
                        pdf_original_filename, pdf_text_content,
                        workflow_name, confidence_score, search_content,
                        document_type, document_category, document_info
                    ) VALUES (
                        :filename, :filepath, :file_hash, :file_size,
                        :email_message_id, :email_from, :email_to,
                        :email_subject, :email_date, :email_body_text,
                        :email_body_html, :email_headers, :pdf_type,
                        :pdf_original_filename, :pdf_text_content,
                        :workflow_name, :confidence_score, :search_content,
                        :document_type, :document_category, :document_info
                    )
                """,
                    metadata,
                )

                # Update FTS index
                conn.execute(
                    """
                    INSERT INTO pdf_search (
                        filename, email_subject, email_from, search_content
                    ) VALUES (?, ?, ?, ?)
                """,
                    (
                        metadata["filename"],
                        metadata["email_subject"],
                        metadata["email_from"],
                        metadata["search_content"],
                    ),
                )

                conn.commit()
                logger.info(f"Stored metadata for {pdf_path.name}")

        except Exception as e:
            logger.error(f"Failed to store metadata: {e}")
            raise DataError(f"Failed to store PDF metadata: {e}")

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search PDFs using full-text search."""
        try:
            with self.get_connection() as conn:
                # Use FTS5 for search
                results = conn.execute(
                    """
                    SELECT 
                        m.*,
                        rank
                    FROM pdf_search s
                    JOIN pdf_metadata m ON m.id = s.rowid
                    WHERE pdf_search MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """,
                    (query, limit),
                )

                return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def search_by_type(self, document_type: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search PDFs by document type."""
        try:
            with self.get_connection() as conn:
                results = conn.execute(
                    """
                    SELECT * FROM pdf_metadata 
                    WHERE document_type = ?
                    ORDER BY saved_at DESC
                    LIMIT ?
                """,
                    (document_type, limit),
                )

                return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Search by type failed: {e}")
            return []

    def get_by_message_id(self, message_id: str) -> List[Dict[str, Any]]:
        """Get all PDFs associated with an email message ID."""
        try:
            with self.get_connection() as conn:
                results = conn.execute(
                    """
                    SELECT * FROM pdf_metadata 
                    WHERE email_message_id = ?
                    ORDER BY saved_at DESC
                """,
                    (message_id,),
                )

                return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Lookup failed: {e}")
            return []

    def check_duplicate(self, message_id: str, filename: str) -> bool:
        """Check if we already saved this PDF."""
        try:
            with self.get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT COUNT(*) as count FROM pdf_metadata 
                    WHERE email_message_id = ? AND filename = ?
                """,
                    (message_id, filename),
                )

                return result.fetchone()["count"] > 0

        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get storage statistics."""
        try:
            with self.get_connection() as conn:
                stats = {}

                # Total PDFs
                result = conn.execute("SELECT COUNT(*) as count FROM pdf_metadata")
                stats["total_pdfs"] = result.fetchone()["count"]

                # By PDF type
                result = conn.execute(
                    """
                    SELECT pdf_type, COUNT(*) as count 
                    FROM pdf_metadata 
                    GROUP BY pdf_type
                """
                )
                stats["by_pdf_type"] = {row["pdf_type"]: row["count"] for row in result}

                # By document type
                result = conn.execute(
                    """
                    SELECT document_type, COUNT(*) as count 
                    FROM pdf_metadata 
                    WHERE document_type IS NOT NULL
                    GROUP BY document_type
                    ORDER BY count DESC
                """
                )
                stats["by_document_type"] = {row["document_type"]: row["count"] for row in result}

                # By document category
                result = conn.execute(
                    """
                    SELECT document_category, COUNT(*) as count 
                    FROM pdf_metadata 
                    WHERE document_category IS NOT NULL
                    GROUP BY document_category
                    ORDER BY count DESC
                """
                )
                stats["by_category"] = {row["document_category"]: row["count"] for row in result}

                # By workflow
                result = conn.execute(
                    """
                    SELECT workflow_name, COUNT(*) as count 
                    FROM pdf_metadata 
                    GROUP BY workflow_name
                    ORDER BY count DESC
                    LIMIT 10
                """
                )
                stats["by_workflow"] = {row["workflow_name"]: row["count"] for row in result}

                # By year
                result = conn.execute(
                    """
                    SELECT 
                        strftime('%Y', email_date) as year,
                        COUNT(*) as count 
                    FROM pdf_metadata 
                    WHERE email_date IS NOT NULL
                    GROUP BY year
                    ORDER BY year DESC
                """
                )
                stats["by_year"] = {row["year"]: row["count"] for row in result}

                # Total size
                result = conn.execute("SELECT SUM(file_size) as total_size FROM pdf_metadata")
                total_bytes = result.fetchone()["total_size"] or 0
                stats["total_size_mb"] = round(total_bytes / (1024 * 1024), 2)

                return stats

        except Exception as e:
            logger.error(f"Statistics query failed: {e}")
            return {}

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _extract_text_from_body(self, body: str) -> str:
        """Extract plain text from email body (HTML or plain)."""
        if not body:
            return ""

        # Check if it's HTML
        if "<html" in body.lower() or "<body" in body.lower():
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(body, "html.parser")
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                # Get text
                text = soup.get_text()
                # Break into lines and remove leading/trailing space
                lines = (line.strip() for line in text.splitlines())
                # Break multi-headlines into a line each
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                # Drop blank lines
                text = " ".join(chunk for chunk in chunks if chunk)
                return text
            except Exception as e:
                logger.warning(f"Failed to extract text from HTML: {e}")
                return body

        return body

    def update_document_classification(
        self,
        message_id: str,
        filename: str,
        document_type: Optional[str] = None,
        document_category: Optional[str] = None,
    ):
        """Update document classification for a saved PDF."""
        with self.get_connection() as conn:
            updates = []
            params = {"message_id": message_id, "filename": filename}

            if document_type is not None:
                updates.append("document_type = :document_type")
                params["document_type"] = document_type

            if document_category is not None:
                updates.append("document_category = :document_category")
                params["document_category"] = document_category

            if updates:
                query = f"""
                    UPDATE pdf_metadata 
                    SET {", ".join(updates)}
                    WHERE email_message_id = :message_id AND filename = :filename
                """
                conn.execute(query, params)
                conn.commit()

    def update_document_info(self, message_id: str, filename: str, document_info: Dict[str, Any]):
        """Update extracted document information for a saved PDF.

        Example document_info:
        {
            "amount": 99.99,
            "currency": "USD",
            "vendor": "Amazon",
            "invoice_number": "INV-12345",
            "invoice_date": "2024-01-15",
            "due_date": "2024-02-15",
            "items": [...],
            "tax_amount": 8.99
        }
        """
        with self.get_connection() as conn:
            # Get existing document info
            cursor = conn.execute(
                """
                SELECT document_info 
                FROM pdf_metadata 
                WHERE email_message_id = ? AND filename = ?
            """,
                (message_id, filename),
            )

            row = cursor.fetchone()
            if row:
                existing_info = {}
                if row["document_info"]:
                    try:
                        existing_info = json.loads(row["document_info"])
                    except json.JSONDecodeError:
                        pass

                # Merge with new info
                existing_info.update(document_info)

                # Update database
                conn.execute(
                    """
                    UPDATE pdf_metadata 
                    SET document_info = ?
                    WHERE email_message_id = ? AND filename = ?
                """,
                    (json.dumps(existing_info), message_id, filename),
                )

                conn.commit()

    def get_document_info(self, message_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Get document info for a specific PDF."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT document_type, document_category, document_info
                FROM pdf_metadata
                WHERE email_message_id = ? AND filename = ?
            """,
                (message_id, filename),
            )

            row = cursor.fetchone()
            if row:
                result = {
                    "document_type": row["document_type"],
                    "document_category": row["document_category"],
                    "info": {},
                }

                if row["document_info"]:
                    try:
                        result["info"] = json.loads(row["document_info"])
                    except json.JSONDecodeError:
                        pass

                return result
            return None

    @staticmethod
    def suggest_document_classification(email_data: Dict[str, Any]) -> Tuple[str, str]:
        """Suggest document type and category based on email content.

        Returns:
            Tuple of (document_type, document_category)
        """
        # Get text content for analysis
        subject = email_data.get("subject", "").lower()
        from_addr = email_data.get("from", "").lower()
        body = email_data.get("body", "").lower()

        # Combine all text for matching
        text = f"{subject} {from_addr} {body}"

        # Invoice indicators
        if any(word in text for word in ["invoice", "bill", "payment due", "amount due"]):
            return DocumentType.INVOICE, DocumentCategory.PURCHASE

        # Receipt indicators
        if any(
            word in text
            for word in [
                "receipt",
                "purchase confirmation",
                "order confirmation",
                "thank you for your order",
            ]
        ):
            return DocumentType.RECEIPT, DocumentCategory.PURCHASE

        # Financial statement indicators
        if any(
            word in text
            for word in ["statement", "account summary", "balance", "transaction history"]
        ):
            return DocumentType.STATEMENT, DocumentCategory.FINANCIAL

        # Tax document indicators
        if any(word in text for word in ["tax", "1099", "w-2", "w2", "irs", "return"]):
            return DocumentType.TAX, DocumentCategory.GOVERNMENT

        # Contract indicators
        if any(word in text for word in ["contract", "agreement", "terms", "lease"]):
            return DocumentType.CONTRACT, DocumentCategory.LEGAL

        # Report indicators
        if any(word in text for word in ["report", "analysis", "summary", "findings"]):
            return DocumentType.REPORT, DocumentCategory.BUSINESS

        # Default
        return DocumentType.UNKNOWN, DocumentCategory.UNCATEGORIZED
