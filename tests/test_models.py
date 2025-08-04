import pytest
from datetime import datetime
import json

from pmail.models import CriteriaInstance, WorkflowDefinition, DataStore


class TestCriteriaInstance:
    def test_criteria_instance_creation(self):
        now = datetime.now()
        instance = CriteriaInstance(
            email_id="test123",
            workflow_name="archive",
            timestamp=now,
            email_features={"from_domain": "example.com"},
            user_confirmed=True,
            confidence_score=0.85
        )
        
        assert instance.email_id == "test123"
        assert instance.workflow_name == "archive"
        assert instance.timestamp == now
        assert instance.email_features["from_domain"] == "example.com"
        assert instance.user_confirmed is True
        assert instance.confidence_score == 0.85
    
    def test_criteria_instance_serialization(self):
        now = datetime.now()
        instance = CriteriaInstance(
            email_id="test123",
            workflow_name="archive",
            timestamp=now,
            email_features={"from_domain": "example.com"}
        )
        
        # Convert to dict
        data = instance.to_dict()
        assert data["email_id"] == "test123"
        assert data["workflow_name"] == "archive"
        assert data["timestamp"] == now.isoformat()
        
        # Convert back from dict
        instance2 = CriteriaInstance.from_dict(data)
        assert instance2.email_id == instance.email_id
        assert instance2.workflow_name == instance.workflow_name
        assert instance2.timestamp == instance.timestamp


class TestWorkflowDefinition:
    def test_workflow_creation(self):
        workflow = WorkflowDefinition(
            name="save-invoices",
            description="Save invoice PDFs",
            action_type="save_attachment",
            action_params={"directory": "~/invoices", "pattern": "*.pdf"}
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
            action_type="flag",
            action_params={"flag": "important"}
        )
        
        # Convert to dict
        data = workflow.to_dict()
        assert data["name"] == "test-workflow"
        assert data["action_type"] == "flag"
        
        # Convert back from dict
        workflow2 = WorkflowDefinition.from_dict(data)
        assert workflow2.name == workflow.name
        assert workflow2.action_type == workflow.action_type


class TestDataStore:
    def test_datastore_initialization(self, test_config):
        store = DataStore(test_config)
        
        # Should have default workflows
        assert len(store.workflows) > 0
        assert "archive" in store.workflows
        assert "needs-reply" in store.workflows
        
        # Should start with no criteria instances
        assert len(store.criteria_instances) == 0
    
    def test_add_criteria_instance(self, test_config):
        store = DataStore(test_config)
        
        instance = CriteriaInstance(
            email_id="test123",
            workflow_name="archive",
            timestamp=datetime.now(),
            email_features={"from_domain": "example.com"}
        )
        
        store.add_criteria_instance(instance)
        
        # Check it was added
        assert len(store.criteria_instances) == 1
        assert store.criteria_instances[0].email_id == "test123"
        
        # Check it was saved to file
        criteria_file = test_config.get_criteria_instances_file()
        assert criteria_file.exists()
        
        # Create new store and check it loads
        store2 = DataStore(test_config)
        assert len(store2.criteria_instances) == 1
        assert store2.criteria_instances[0].email_id == "test123"
    
    def test_add_workflow(self, test_config):
        store = DataStore(test_config)
        
        workflow = WorkflowDefinition(
            name="custom-workflow",
            description="Custom test workflow",
            action_type="flag",
            action_params={"flag": "custom"}
        )
        
        store.add_workflow(workflow)
        
        # Check it was added
        assert "custom-workflow" in store.workflows
        assert store.workflows["custom-workflow"].description == "Custom test workflow"
        
        # Check persistence
        store2 = DataStore(test_config)
        assert "custom-workflow" in store2.workflows
    
    def test_get_criteria_for_workflow(self, test_config):
        store = DataStore(test_config)
        
        # Add some criteria instances
        for i in range(3):
            instance = CriteriaInstance(
                email_id=f"test{i}",
                workflow_name="archive" if i < 2 else "needs-reply",
                timestamp=datetime.now(),
                email_features={}
            )
            store.add_criteria_instance(instance)
        
        # Get criteria for archive workflow
        archive_criteria = store.get_criteria_for_workflow("archive")
        assert len(archive_criteria) == 2
        
        # Get criteria for needs-reply workflow
        reply_criteria = store.get_criteria_for_workflow("needs-reply")
        assert len(reply_criteria) == 1