# ABOUTME: Tracks processed emails to prevent reprocessing duplicates
# ABOUTME: Uses message-id (primary) and content hash (fallback) for deduplication

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ProcessedEmailsTracker:
    """
    Track processed emails to prevent duplicate processing.

    Uses hybrid approach:
    - Primary: message-id for fast lookup
    - Fallback: content hash for emails without message-id

    Database location: config_dir/processed_emails.db
    (typically ~/.config/mailflow/processed_emails.db)
    """

    def __init__(self, config):
        """
        Initialize tracker with config.

        Args:
            config: Config object
        """
        self.config = config
        self.db_path = config.config_dir / "processed_emails.db"
        self._init_database()

    def _init_database(self):
        """Create database and schema if not exists"""
        with self.get_connection() as conn:
            # Processed emails table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_hash TEXT NOT NULL,
                    message_id TEXT,
                    workflow_name TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(email_hash)
                )
                """
            )

            # Indexes for fast lookup
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_hash ON processed_emails(email_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_message_id ON processed_emails(message_id)"
            )

            conn.commit()
            logger.debug("Processed emails database initialized")

    @contextmanager
    def get_connection(self):
        """Get database connection with proper transaction management."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                    logger.debug("Rolled back database transaction due to error")
                except Exception:
                    pass
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    logger.warning("Failed to close database connection")

    def _calculate_content_hash(self, email_content: str) -> str:
        """
        Calculate SHA-256 hash of email content.

        Args:
            email_content: Raw email content

        Returns:
            64-character hex string (SHA-256 hash)
        """
        return hashlib.sha256(email_content.encode("utf-8")).hexdigest()

    def mark_as_processed(
        self, email_content: str, message_id: str | None, workflow_name: str
    ) -> None:
        """
        Mark email as processed.

        Args:
            email_content: Raw email content
            message_id: Email message-id (can be None)
            workflow_name: Name of workflow that processed this email
        """
        content_hash = self._calculate_content_hash(email_content)

        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO processed_emails
                    (email_hash, message_id, workflow_name, processed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content_hash, message_id, workflow_name, datetime.now().isoformat()),
                )
                conn.commit()
                logger.debug(f"Marked email as processed: {message_id or content_hash[:8]}")
        except Exception as e:
            logger.error(f"Failed to mark email as processed: {e}")
            raise

    def is_processed(self, email_content: str, message_id: str | None) -> bool:
        """
        Check if email has been processed.

        Uses hybrid approach:
        1. If message_id provided, check by message_id first (fast)
        2. Fall back to content hash check

        Args:
            email_content: Raw email content
            message_id: Email message-id (can be None)

        Returns:
            True if email has been processed before
        """
        content_hash = self._calculate_content_hash(email_content)

        try:
            with self.get_connection() as conn:
                # First try message-id lookup if available
                if message_id:
                    result = conn.execute(
                        "SELECT COUNT(*) as count FROM processed_emails WHERE message_id = ?",
                        (message_id,),
                    )
                    if result.fetchone()["count"] > 0:
                        return True

                # Fall back to content hash lookup
                result = conn.execute(
                    "SELECT COUNT(*) as count FROM processed_emails WHERE email_hash = ?",
                    (content_hash,),
                )
                return result.fetchone()["count"] > 0

        except Exception as e:
            logger.error(f"Failed to check if processed: {e}")
            return False

    def get_processed_info(
        self, email_content: str, message_id: str | None
    ) -> dict[str, Any] | None:
        """
        Get information about a processed email.

        Args:
            email_content: Raw email content
            message_id: Email message-id (can be None)

        Returns:
            Dict with workflow_name, processed_at, etc. or None if not processed
        """
        content_hash = self._calculate_content_hash(email_content)

        try:
            with self.get_connection() as conn:
                # Try message-id first if available
                if message_id:
                    result = conn.execute(
                        """
                        SELECT workflow_name, processed_at, message_id, email_hash
                        FROM processed_emails
                        WHERE message_id = ?
                        ORDER BY processed_at DESC
                        LIMIT 1
                        """,
                        (message_id,),
                    )
                    row = result.fetchone()
                    if row:
                        return dict(row)

                # Fall back to content hash
                result = conn.execute(
                    """
                    SELECT workflow_name, processed_at, message_id, email_hash
                    FROM processed_emails
                    WHERE email_hash = ?
                    ORDER BY processed_at DESC
                    LIMIT 1
                    """,
                    (content_hash,),
                )
                row = result.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get processed info: {e}")
            return None

    def get_statistics(self) -> dict[str, Any]:
        """
        Get statistics about processed emails.

        Returns:
            Dict with total_processed, by_workflow counts, etc.
        """
        try:
            with self.get_connection() as conn:
                # Total processed
                result = conn.execute("SELECT COUNT(*) as count FROM processed_emails")
                total = result.fetchone()["count"]

                # By workflow
                result = conn.execute(
                    """
                    SELECT workflow_name, COUNT(*) as count
                    FROM processed_emails
                    GROUP BY workflow_name
                    """
                )
                by_workflow = {row["workflow_name"]: row["count"] for row in result.fetchall()}

                return {"total_processed": total, "by_workflow": by_workflow}

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"total_processed": 0, "by_workflow": {}}
