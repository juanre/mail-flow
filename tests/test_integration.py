"""
Integration test simulating the complete user workflow
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mailflow.config import Config
from mailflow.email_extractor import EmailExtractor
from mailflow.models import DataStore, WorkflowDefinition
from mailflow.ui import WorkflowSelector


class TestIntegration:
    """Test the complete integration of all components"""

    @pytest.fixture
    def sample_emails(self):
        """Load sample emails from res directory"""
        res_dir = Path(__file__).parent / "res"
        emails = {}

        for email_file in res_dir.glob("*.eml"):
            with open(email_file, "r", encoding="utf-8", errors="ignore") as f:
                emails[email_file.stem] = f.read()

        return emails

    async def test_complete_workflow_new_user(self, temp_config_dir, sample_emails):
        """Test complete workflow for a new user with no history"""
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()
        ui = WorkflowSelector(config, data_store, interactive=True)

        # Process first email (no history, should show default workflows)
        if "amazon_invoice" in sample_emails:
            email_data = extractor.extract(sample_emails["amazon_invoice"])

            # Mock user input to create new workflow
            # select_workflow now uses builtins.input, _create_new_workflow uses LineInput
            with patch("builtins.input", return_value="new"):
                with patch("mailflow.linein.LineInput.ask") as mock_ask:
                    # LineInput is used in _create_new_workflow
                    mock_ask.side_effect = [
                        "save-invoices",  # Workflow name
                        "Save invoice attachments",  # Description
                        "no",  # Use a workflow template? No
                        "save_attachment",  # Action type
                        "~/invoices",  # Directory
                        "*.pdf",  # Pattern
                    ]

                    selected = await ui.select_workflow(email_data)
                    assert selected == "save-invoices"

            # Verify workflow was created
            assert "save-invoices" in data_store.workflows

    async def test_workflow_selection(self, temp_config_dir, sample_emails):
        """Test workflow selection from existing workflows"""
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()

        # Create workflows
        workflows = {
            "save-invoices": WorkflowDefinition(
                name="save-invoices",
                description="Save invoice PDFs",
                action_type="save_attachment",
                action_params={"directory": "~/invoices", "pattern": "*.pdf"},
            ),
            "save-errors": WorkflowDefinition(
                name="save-errors",
                description="Save error emails as PDF",
                action_type="save_email_as_pdf",
                action_params={"directory": "~/errors"},
            ),
            "create-todos": WorkflowDefinition(
                name="create-todos",
                description="Create todo items from emails",
                action_type="create_todo",
                action_params={"todo_file": "~/todos.txt"},
            ),
        }

        for workflow in workflows.values():
            data_store.add_workflow(workflow)

        ui = WorkflowSelector(config, data_store, interactive=True)

        if "cloudflare_invoice" in sample_emails:
            email_data = extractor.extract(sample_emails["cloudflare_invoice"])

            # Mock user selecting first workflow
            with patch("builtins.input", return_value="1"):
                selected = await ui.select_workflow(email_data)

            # Should have selected something
            assert selected is not None
            assert selected in data_store.workflows

    async def test_workflow_execution(self, temp_config_dir, sample_emails):
        """Test that workflows can be executed"""
        from mailflow.process import process

        # Mock the workflow execution
        with patch("mailflow.workflow.save_attachment") as mock_save:
            # select_workflow now uses builtins.input; 's' is skip
            with patch("builtins.input", return_value="s"):
                if "amazon_invoice" in sample_emails:
                    # Run the process
                    await process(sample_emails["amazon_invoice"])

                    # Should not execute any workflow when skipped
                    mock_save.assert_not_called()
