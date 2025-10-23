"""Test email deduplication in process.py"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mailflow.config import Config
from mailflow.process import process


@pytest.fixture
def temp_config():
    """Create temporary config for testing"""
    temp_dir = tempfile.mkdtemp()
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

    def test_process_tracks_processed_emails(self, temp_config, sample_email):
        """Test that successfully processed emails are tracked"""
        # Create a workflow first
        from mailflow.models import DataStore, WorkflowDefinition

        data_store = DataStore(temp_config)
        workflow = WorkflowDefinition(
            name="test-workflow",
            description="Test workflow",
            action_type="save_pdf",
            action_params={"directory": "~/test"},
        )
        data_store.add_workflow(workflow)

        # Mock the UI to select a workflow
        with patch("mailflow.ui.WorkflowSelector.select_workflow") as mock_select:
            mock_select.return_value = "test-workflow"

            # Process the email (workflow will actually execute)
            process(sample_email, config=temp_config)

            # Verify the email was tracked
            from mailflow.processed_emails_tracker import ProcessedEmailsTracker

            tracker = ProcessedEmailsTracker(temp_config)
            assert tracker.is_processed(sample_email, "<test123@example.com>")

    def test_process_skips_duplicate_emails(self, temp_config, sample_email):
        """Test that duplicate emails are skipped"""
        # Create a workflow first
        from mailflow.models import DataStore, WorkflowDefinition

        data_store = DataStore(temp_config)
        workflow = WorkflowDefinition(
            name="test-workflow",
            description="Test workflow",
            action_type="save_pdf",
            action_params={"directory": "~/test"},
        )
        data_store.add_workflow(workflow)

        # First, process the email successfully
        with patch("mailflow.ui.WorkflowSelector.select_workflow") as mock_select:
            mock_select.return_value = "test-workflow"

            with patch("mailflow.workflow.Workflows") as mock_workflows:
                mock_action = MagicMock()
                mock_workflows.__getitem__.return_value = mock_action

                # Process the email once
                process(sample_email, config=temp_config)
                first_call_count = mock_action.call_count

                # Try to process again (should be skipped)
                process(sample_email, config=temp_config)

                # Action should not have been called again
                assert mock_action.call_count == first_call_count

    def test_process_force_reprocesses_emails(self, temp_config, sample_email):
        """Test that force flag allows reprocessing"""
        # Create a workflow first
        from mailflow.models import DataStore, WorkflowDefinition

        data_store = DataStore(temp_config)
        workflow = WorkflowDefinition(
            name="test-workflow",
            description="Test workflow",
            action_type="save_pdf",
            action_params={"directory": "~/test"},
        )
        data_store.add_workflow(workflow)

        # First, process the email
        with patch("mailflow.ui.WorkflowSelector.select_workflow") as mock_select:
            mock_select.return_value = "test-workflow"

            # Track how many times select_workflow was called
            # If the email is skipped, select_workflow won't be called on second pass
            process(sample_email, config=temp_config)
            first_call_count = mock_select.call_count

            # Process again WITHOUT force - should skip (select_workflow not called)
            process(sample_email, config=temp_config, force=False)
            assert mock_select.call_count == first_call_count  # No new call

            # Process again WITH force - should process (select_workflow called)
            process(sample_email, config=temp_config, force=True)
            assert mock_select.call_count == first_call_count + 1  # New call made

    def test_process_does_not_track_skipped_workflows(self, temp_config, sample_email):
        """Test that emails are not tracked when user skips workflow selection"""
        # Mock UI to return None (user skipped)
        with patch("mailflow.ui.WorkflowSelector.select_workflow") as mock_select:
            mock_select.return_value = None

            # Process the email
            process(sample_email, config=temp_config)

            # Verify the email was NOT tracked
            from mailflow.processed_emails_tracker import ProcessedEmailsTracker

            tracker = ProcessedEmailsTracker(temp_config)
            assert not tracker.is_processed(sample_email, "<test123@example.com>")
