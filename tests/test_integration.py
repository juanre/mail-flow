"""
Integration test simulating the complete user workflow
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
                        "no",  # Use a workflow template? No
                        "acme",  # Entity
                        "invoice",  # Document type
                        "acme-invoice",  # Workflow name
                        "Save invoice attachments",  # Summary
                    ]

                    selected = await ui.select_workflow(email_data)
                    assert selected == "acme-invoice"

            # Verify workflow was created
            assert "acme-invoice" in data_store.workflows

    async def test_workflow_selection(self, temp_config_dir, sample_emails):
        """Test workflow selection from existing workflows"""
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)
        extractor = EmailExtractor()

        # Create workflows
        workflows = {
            "save-invoices": WorkflowDefinition(
                name="save-invoices",
                kind="document",
                criteria={"summary": "Save invoice PDFs"},
                handling={
                    "archive": {"target": "document", "entity": "acme", "doctype": "invoice"},
                    "index": {"llmemory": True},
                },
            ),
            "save-errors": WorkflowDefinition(
                name="save-errors",
                kind="document",
                criteria={"summary": "Save error emails as PDF"},
                handling={
                    "archive": {"target": "document", "entity": "acme", "doctype": "errors"},
                    "index": {"llmemory": True},
                },
            ),
            "create-todos": WorkflowDefinition(
                name="create-todos",
                kind="document",
                criteria={"summary": "Create todo items from emails"},
                handling={
                    "archive": {"target": "document", "entity": "acme", "doctype": "todos"},
                    "index": {"llmemory": True},
                },
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

        config = Config(config_dir=temp_config_dir)

        # Mock the workflow execution
        with patch("mailflow.process.Workflows") as mock_workflows:
            mock_action = MagicMock()
            mock_workflows.get.return_value = mock_action
            # select_workflow now uses builtins.input; 's' is skip
            with patch("builtins.input", return_value="s"):
                if "amazon_invoice" in sample_emails:
                    # Run the process
                    await process(sample_emails["amazon_invoice"], config=config)

                    # Should not execute any workflow when skipped
                    mock_action.assert_not_called()
