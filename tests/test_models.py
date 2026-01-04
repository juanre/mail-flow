from mailflow.models import DataStore, WorkflowDefinition


class TestWorkflowDefinition:
    def test_workflow_creation(self):
        workflow = WorkflowDefinition(
            name="save-invoices",
            kind="document",
            criteria={"summary": "Save invoice PDFs"},
            constraints={"requires_evidence": ["invoice"]},
            handling={
                "archive": {"target": "document", "entity": "acme", "doctype": "invoice"},
                "index": {"llmemory": False},
            },
            postprocessors=["pdf-ocr"],
        )

        assert workflow.name == "save-invoices"
        assert workflow.kind == "document"
        assert workflow.criteria["summary"] == "Save invoice PDFs"
        assert workflow.archive_entity == "acme"
        assert workflow.archive_doctype == "invoice"
        assert workflow.index_llmemory is False

    def test_workflow_serialization(self):
        workflow = WorkflowDefinition(
            name="test-workflow",
            kind="document",
            criteria={"summary": "Test"},
            handling={
                "archive": {"target": "document", "entity": "demo", "doctype": "pdfs"},
                "index": {"llmemory": True},
            },
        )

        # Convert to dict
        data = workflow.to_dict()
        assert data["name"] == "test-workflow"
        assert data["handling"]["archive"]["doctype"] == "pdfs"

        # Convert back from dict
        workflow2 = WorkflowDefinition.from_dict(data)
        assert workflow2.name == workflow.name
        assert workflow2.handling == workflow.handling

    def test_workflow_classifier_appendix_round_trip(self):
        workflow = WorkflowDefinition(
            name="tsm-expense",
            kind="document",
            criteria={"summary": "Expense receipts"},
            handling={
                "archive": {"target": "document", "entity": "tsm", "doctype": "expense"},
                "index": {"llmemory": True},
            },
            classifier={"appendix": "Expense workflow policy (TheStarMaps):\n- Example\n"},
        )

        data = workflow.to_dict()
        assert data["classifier"]["appendix"].startswith("Expense workflow policy")

        workflow2 = WorkflowDefinition.from_dict(data)
        assert workflow2.classifier is not None
        assert workflow2.classifier["appendix"].startswith("Expense workflow policy")


class TestDataStore:
    def test_datastore_initialization(self, test_config):
        store = DataStore(test_config)

        # DataStore should start empty (users run 'init' to create workflows)
        assert len(store.workflows) == 0

    def test_add_workflow(self, test_config):
        store = DataStore(test_config)

        workflow = WorkflowDefinition(
            name="custom-workflow",
            kind="document",
            criteria={"summary": "Custom test workflow"},
            handling={
                "archive": {"target": "document", "entity": "acme", "doctype": "docs"},
                "index": {"llmemory": True},
            },
        )

        store.add_workflow(workflow)

        # Check it was added
        assert "custom-workflow" in store.workflows
        assert store.workflows["custom-workflow"].criteria["summary"] == "Custom test workflow"

        # Check persistence
        store2 = DataStore(test_config)
        assert "custom-workflow" in store2.workflows
