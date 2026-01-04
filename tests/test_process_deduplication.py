"""Test email deduplication in process.py"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mailflow.config import Config
from mailflow.process import process


@pytest.fixture
def temp_config():
    """Create temporary config for testing"""
    temp_dir = tempfile.mkdtemp()
    workflows_file = Path(temp_dir) / "workflows.json"
    workflows_file.write_text('{"schema_version": 1, "workflows": []}')
    return Config(config_dir=temp_dir)


@pytest.fixture
def sample_email():
    """Sample email with Message-ID"""
    return """From: test@example.com
To: user@test.com
Subject: Test Email
Message-ID: <test123@example.com>

This is the email body content.
"""


class TestProcessDeduplication:
    """Test deduplication in the process function"""

    async def test_process_tracks_processed_emails(self, temp_config, sample_email):
        """Test that successfully processed emails are tracked"""
        # Create a workflow first
        from mailflow.models import DataStore, WorkflowDefinition

        data_store = DataStore(temp_config)
        workflow = WorkflowDefinition(
            name="test-workflow",
            kind="document",
            criteria={"summary": "Test workflow"},
            handling={
                "archive": {"target": "document", "entity": "acme", "doctype": "docs"},
                "index": {"llmemory": True},
            },
        )
        data_store.add_workflow(workflow)

        # Mock the UI to select a workflow (async mock) and mock workflow execution
        with patch("mailflow.ui.WorkflowSelector.select_workflow", new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "test-workflow"

            with patch("mailflow.process.Workflows") as mock_workflows:
                mock_action = MagicMock()
                mock_workflows.get.return_value = mock_action

                # Process the email
                await process(sample_email, config=temp_config)

                # Verify the email was tracked
                from mailflow.processed_emails_tracker import ProcessedEmailsTracker

                tracker = ProcessedEmailsTracker(temp_config)
                assert tracker.is_processed(sample_email, "<test123@example.com>")

    async def test_process_skips_duplicate_emails(self, temp_config, sample_email):
        """Test that duplicate emails are skipped"""
        # Create a workflow first
        from mailflow.models import DataStore, WorkflowDefinition

        data_store = DataStore(temp_config)
        workflow = WorkflowDefinition(
            name="test-workflow",
            kind="document",
            criteria={"summary": "Test workflow"},
            handling={
                "archive": {"target": "document", "entity": "acme", "doctype": "docs"},
                "index": {"llmemory": True},
            },
        )
        data_store.add_workflow(workflow)

        # First, process the email successfully
        with patch("mailflow.ui.WorkflowSelector.select_workflow", new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "test-workflow"

            with patch("mailflow.process.Workflows") as mock_workflows:
                mock_action = MagicMock()
                mock_workflows.get.return_value = mock_action

                # Process the email once
                await process(sample_email, config=temp_config)
                first_call_count = mock_action.call_count

                # Try to process again (should be skipped)
                await process(sample_email, config=temp_config)

                # Action should not have been called again
                assert mock_action.call_count == first_call_count

    async def test_process_force_reprocesses_emails(self, temp_config, sample_email):
        """Test that force flag allows reprocessing"""
        # Create a workflow first
        from mailflow.models import DataStore, WorkflowDefinition

        data_store = DataStore(temp_config)
        workflow = WorkflowDefinition(
            name="test-workflow",
            kind="document",
            criteria={"summary": "Test workflow"},
            handling={
                "archive": {"target": "document", "entity": "acme", "doctype": "docs"},
                "index": {"llmemory": True},
            },
        )
        data_store.add_workflow(workflow)

        # First, process the email
        with patch("mailflow.ui.WorkflowSelector.select_workflow", new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "test-workflow"

            with patch("mailflow.process.Workflows") as mock_workflows:
                mock_action = MagicMock()
                mock_workflows.get.return_value = mock_action

                # Track how many times select_workflow was called
                # If the email is skipped, select_workflow won't be called on second pass
                await process(sample_email, config=temp_config)
                first_call_count = mock_select.call_count

                # Process again WITHOUT force - should skip (select_workflow not called)
                await process(sample_email, config=temp_config, force=False)
                assert mock_select.call_count == first_call_count  # No new call

                # Process again WITH force - should process (select_workflow called)
                await process(sample_email, config=temp_config, force=True)
                assert mock_select.call_count == first_call_count + 1  # New call made

    async def test_process_does_not_track_skipped_workflows(self, temp_config, sample_email):
        """Test that emails are not tracked when user skips workflow selection"""
        # Mock UI to return None (user skipped)
        with patch("mailflow.ui.WorkflowSelector.select_workflow", new_callable=AsyncMock) as mock_select:
            mock_select.return_value = None

            # Process the email
            await process(sample_email, config=temp_config)

            # Verify the email was NOT tracked
            from mailflow.processed_emails_tracker import ProcessedEmailsTracker

            tracker = ProcessedEmailsTracker(temp_config)
            assert not tracker.is_processed(sample_email, "<test123@example.com>")
