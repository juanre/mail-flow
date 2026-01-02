from datetime import datetime

from mailflow.models import DataStore, WorkflowDefinition


class TestWorkflowDefinition:
    def test_workflow_creation(self):
        workflow = WorkflowDefinition(
            name="save-invoices",
            description="Save invoice PDFs",
            action_type="save_attachment",
            action_params={"directory": "~/invoices", "pattern": "*.pdf"},
        )

        assert workflow.name == "save-invoices"
        assert workflow.description == "Save invoice PDFs"
        assert workflow.action_type == "save_attachment"
        assert workflow.action_params["directory"] == "~/invoices"
        assert workflow.action_params["pattern"] == "*.pdf"

    def test_workflow_serialization(self):
        workflow = WorkflowDefinition(
            name="test-workflow",
            description="Test",
            action_type="save_pdf",
            action_params={"directory": "~/pdfs"},
        )

        # Convert to dict
        data = workflow.to_dict()
        assert data["name"] == "test-workflow"
        assert data["action_type"] == "save_pdf"

        # Convert back from dict
        workflow2 = WorkflowDefinition.from_dict(data)
        assert workflow2.name == workflow.name
        assert workflow2.action_type == workflow.action_type


class TestDataStore:
    def test_datastore_initialization(self, test_config):
        store = DataStore(test_config)

        # DataStore should start empty (users run 'init' to create workflows)
        assert len(store.workflows) == 0

    def test_add_workflow(self, test_config):
        store = DataStore(test_config)

        workflow = WorkflowDefinition(
            name="custom-workflow",
            description="Custom test workflow",
            action_type="create_todo",
            action_params={"todo_file": "~/todos.txt"},
        )

        store.add_workflow(workflow)

        # Check it was added
        assert "custom-workflow" in store.workflows
        assert store.workflows["custom-workflow"].description == "Custom test workflow"

        # Check persistence
        store2 = DataStore(test_config)
        assert "custom-workflow" in store2.workflows
