"""Test processed emails tracking and deduplication"""

import hashlib
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from mailflow.config import Config


@pytest.fixture
def temp_config():
    """Create temporary config for testing"""
    temp_dir = tempfile.mkdtemp()
    return Config(config_dir=temp_dir)


@pytest.fixture
def sample_email_content():
    """Sample email content for testing"""
    return """From: test@example.com
To: user@test.com
Subject: Test Email
Message-ID: <test123@example.com>

This is the email body content.
"""


@pytest.fixture
def sample_email_no_message_id():
    """Sample email without Message-ID"""
    return """From: test@example.com
To: user@test.com
Subject: Test Email

This is the email body content.
"""


class TestProcessedEmailsTracker:
    """Test the processed emails tracker"""

    def test_imports_tracker(self):
        """Test that we can import the tracker module"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        assert ProcessedEmailsTracker is not None

    def test_tracker_initialization(self, temp_config):
        """Test tracker creates database and schema"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        # Should create database file
        db_path = temp_config.config_dir / "processed_emails.db"
        assert db_path.exists()

    def test_tracker_schema_creation(self, temp_config):
        """Test that tracker creates correct database schema"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        # Check that table exists
        with tracker.get_connection() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_emails'"
            )
            assert result.fetchone() is not None

    def test_mark_as_processed_with_message_id(self, temp_config, sample_email_content):
        """Test marking email as processed using message-id"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        message_id = "<test123@example.com>"
        workflow_name = "test-workflow"

        tracker.mark_as_processed(
            email_content=sample_email_content,
            message_id=message_id,
            workflow_name=workflow_name,
        )

        # Verify it was recorded
        assert tracker.is_processed(sample_email_content, message_id)

    def test_mark_as_processed_without_message_id(self, temp_config, sample_email_no_message_id):
        """Test marking email as processed without message-id (uses content hash)"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        workflow_name = "test-workflow"

        tracker.mark_as_processed(
            email_content=sample_email_no_message_id, message_id=None, workflow_name=workflow_name
        )

        # Should be detected as processed by content hash
        assert tracker.is_processed(sample_email_no_message_id, None)

    def test_is_processed_with_message_id(self, temp_config, sample_email_content):
        """Test checking if email is processed using message-id"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        message_id = "<test123@example.com>"

        # Not processed yet
        assert not tracker.is_processed(sample_email_content, message_id)

        # Mark as processed
        tracker.mark_as_processed(sample_email_content, message_id, "workflow1")

        # Should be detected
        assert tracker.is_processed(sample_email_content, message_id)

    def test_is_processed_with_content_hash_only(self, temp_config, sample_email_no_message_id):
        """Test checking if email is processed using content hash when no message-id"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        # Not processed yet
        assert not tracker.is_processed(sample_email_no_message_id, None)

        # Mark as processed
        tracker.mark_as_processed(sample_email_no_message_id, None, "workflow1")

        # Should be detected by content hash
        assert tracker.is_processed(sample_email_no_message_id, None)

    def test_duplicate_message_id_same_content(self, temp_config, sample_email_content):
        """Test that same message-id is detected as duplicate"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        message_id = "<test123@example.com>"

        # Process once
        tracker.mark_as_processed(sample_email_content, message_id, "workflow1")

        # Try to process again with same message-id
        assert tracker.is_processed(sample_email_content, message_id)

    def test_duplicate_content_different_message_id(self, temp_config, sample_email_content):
        """Test that identical content with different message-id is detected"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        # Process with first message-id
        tracker.mark_as_processed(sample_email_content, "<msg1@test.com>", "workflow1")

        # Same content, different message-id - should detect by content hash
        assert tracker.is_processed(sample_email_content, "<msg2@test.com>")

    def test_get_statistics(self, temp_config, sample_email_content):
        """Test getting tracker statistics"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        # Process a few emails
        tracker.mark_as_processed(sample_email_content, "<msg1@test.com>", "workflow1")
        tracker.mark_as_processed(sample_email_content + "\nExtra", "<msg2@test.com>", "workflow2")

        stats = tracker.get_statistics()

        assert stats["total_processed"] == 2
        assert "workflow1" in stats["by_workflow"]
        assert "workflow2" in stats["by_workflow"]

    def test_force_reprocess(self, temp_config, sample_email_content):
        """Test that we can get info about processed email for force reprocessing"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        message_id = "<test123@example.com>"
        tracker.mark_as_processed(sample_email_content, message_id, "workflow1")

        # Get info about the processed email
        info = tracker.get_processed_info(sample_email_content, message_id)

        assert info is not None
        assert info["workflow_name"] == "workflow1"
        assert "processed_at" in info

    def test_content_hash_calculation(self, temp_config):
        """Test that content hash is deterministic"""
        from mailflow.processed_emails_tracker import ProcessedEmailsTracker

        tracker = ProcessedEmailsTracker(temp_config)

        content1 = "Test email content"
        content2 = "Test email content"
        content3 = "Different content"

        hash1 = tracker._calculate_content_hash(content1)
        hash2 = tracker._calculate_content_hash(content2)
        hash3 = tracker._calculate_content_hash(content3)

        # Same content should have same hash
        assert hash1 == hash2

        # Different content should have different hash
        assert hash1 != hash3

        # Hash should be hex string
        assert len(hash1) == 32  # MD5 produces 32 hex chars
