from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
from pathlib import Path


@dataclass
class CriteriaInstance:
    """A concrete example of an email that was classified to a workflow"""
    email_id: str
    workflow_name: str
    timestamp: datetime
    email_features: Dict[str, Any]
    user_confirmed: bool = True
    confidence_score: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "email_id": self.email_id,
            "workflow_name": self.workflow_name,
            "timestamp": self.timestamp.isoformat(),
            "email_features": self.email_features,
            "user_confirmed": self.user_confirmed,
            "confidence_score": self.confidence_score
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CriteriaInstance':
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class WorkflowDefinition:
    """Definition of a workflow"""
    name: str
    description: str
    action_type: str  # e.g., "save_attachment", "flag", "copy_to_folder"
    action_params: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowDefinition':
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


class DataStore:
    """Handles persistence of workflows and criteria instances"""
    
    def __init__(self, config):
        self.config = config
        self.workflows_file = config.get_workflows_file()
        self.criteria_file = config.get_criteria_instances_file()
        self._load_data()
    
    def _load_data(self):
        # Load workflows
        if self.workflows_file.exists():
            with open(self.workflows_file, 'r') as f:
                workflows_data = json.load(f)
                self.workflows = {
                    name: WorkflowDefinition.from_dict(data)
                    for name, data in workflows_data.items()
                }
        else:
            self.workflows = self._default_workflows()
            self.save_workflows()
        
        # Load criteria instances
        if self.criteria_file.exists():
            with open(self.criteria_file, 'r') as f:
                criteria_data = json.load(f)
                self.criteria_instances = [
                    CriteriaInstance.from_dict(data) for data in criteria_data
                ]
        else:
            self.criteria_instances = []
            self.save_criteria()
    
    def _default_workflows(self) -> Dict[str, WorkflowDefinition]:
        """Provide some default workflows"""
        return {
            "archive": WorkflowDefinition(
                name="archive",
                description="Archive the email",
                action_type="flag",
                action_params={"flag": "archived"}
            ),
            "needs-reply": WorkflowDefinition(
                name="needs-reply",
                description="Mark email as needing reply",
                action_type="flag",
                action_params={"flag": "important"}
            ),
            "save-attachments": WorkflowDefinition(
                name="save-attachments",
                description="Save all attachments",
                action_type="save_attachment",
                action_params={"directory": "~/Downloads/email-attachments"}
            )
        }
    
    def save_workflows(self):
        self.config.backup_file(self.workflows_file)
        workflows_data = {
            name: workflow.to_dict()
            for name, workflow in self.workflows.items()
        }
        with open(self.workflows_file, 'w') as f:
            json.dump(workflows_data, f, indent=2)
    
    def save_criteria(self):
        self.config.backup_file(self.criteria_file)
        criteria_data = [
            instance.to_dict() for instance in self.criteria_instances
        ]
        with open(self.criteria_file, 'w') as f:
            json.dump(criteria_data, f, indent=2)
    
    def add_criteria_instance(self, instance: CriteriaInstance):
        self.criteria_instances.append(instance)
        self.save_criteria()
    
    def add_workflow(self, workflow: WorkflowDefinition):
        self.workflows[workflow.name] = workflow
        self.save_workflows()
    
    def get_criteria_for_workflow(self, workflow_name: str) -> List[CriteriaInstance]:
        return [
            ci for ci in self.criteria_instances
            if ci.workflow_name == workflow_name
        ]
    
    def get_recent_criteria(self, limit: int = 100) -> List[CriteriaInstance]:
        """Get the most recent criteria instances"""
        sorted_criteria = sorted(
            self.criteria_instances,
            key=lambda x: x.timestamp,
            reverse=True
        )
        return sorted_criteria[:limit]