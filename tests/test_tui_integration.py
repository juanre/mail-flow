# ABOUTME: Integration tests for TUI workflow selection.
"""Integration tests for TUI workflow selection."""

from unittest.mock import patch

import pytest

from mailflow.config import Config
from mailflow.models import DataStore
from mailflow.ui import WorkflowSelector


class TestWorkflowSelectorTUI:
    async def test_displays_email_info(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)

        selector = WorkflowSelector(config, data_store, interactive=True)

        email = {
            "from": "billing@test.com",
            "to": "user@example.com",
            "subject": "Invoice #123",
            "body": "Please find attached",
            "attachments": [{"filename": "invoice.pdf", "size": 1024}],
            "date": "2025-01-01",
            "message_id": "<test@example.com>",
            "features": {"from_domain": "test.com"},
        }

        # Mock input to return 'skip'
        with patch('builtins.input', return_value='s'):
            result = await selector.select_workflow(email)

        # Should return None for skip
        assert result is None

    async def test_number_selection_returns_workflow(self, temp_config_dir):
        config = Config(config_dir=temp_config_dir)
        data_store = DataStore(config)

        # Add some workflows
        from mailflow.models import WorkflowDefinition
        data_store.add_workflow(WorkflowDefinition(
            name="gsk-invoice",
            kind="document",
            criteria={"summary": "GreaterSkies invoices"},
            handling={
                "archive": {"target": "document", "entity": "gsk", "doctype": "invoice"},
                "index": {"llmemory": True},
            },
        ))

        selector = WorkflowSelector(config, data_store, interactive=True)

        email = {
            "from": "billing@test.com",
            "to": "user@example.com",
            "subject": "Invoice #123",
            "body": "Please find attached",
            "attachments": [],
            "date": "2025-01-01",
            "message_id": "<test@example.com>",
            "features": {"from_domain": "test.com"},
        }

        # Mock input to return '1' (select first workflow)
        with patch('builtins.input', return_value='1'):
            result = await selector.select_workflow(email)

        assert result == "gsk-invoice"
