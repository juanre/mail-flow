# ABOUTME: Tests that non-interactive UI accepts archivist label even when candidates are empty.

from unittest.mock import AsyncMock, patch

import pytest

from mailflow.config import Config
from mailflow.models import DataStore, WorkflowDefinition
from mailflow.ui import WorkflowSelector


@pytest.mark.asyncio
async def test_noninteractive_accepts_label_without_candidates(temp_config_dir):
    config = Config(config_dir=temp_config_dir)
    data_store = DataStore(config)
    data_store.add_workflow(
        WorkflowDefinition(
            name="tsm-expense",
            kind="document",
            criteria={"summary": "TheStarMaps expenses"},
            handling={
                "archive": {"target": "document", "entity": "tsm", "doctype": "expense"},
                "index": {"llmemory": True},
            },
        )
    )

    selector = WorkflowSelector(config, data_store, interactive=False)

    email = {
        "from": "billing@example.com",
        "to": "acct@example.com",
        "subject": "Invoice attached",
        "body": "Please see attached invoice.",
        "attachments": [],
        "date": "2025-01-05",
        "message_id": "<test@example.com>",
    }

    with patch(
        "mailflow.archivist_integration.classify_with_archivist",
        new=AsyncMock(
            return_value={
                "label": "tsm-expense",
                "confidence": 0.92,
                "rankings": [],  # LLM-only decisions may have no candidates
            }
        ),
    ):
        selected = await selector.select_workflow(email)

    assert selected == "tsm-expense"
