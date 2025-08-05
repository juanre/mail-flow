from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
from pathlib import Path
import logging

from pmail.utils import atomic_json_write, safe_json_load, file_lock
from pmail.exceptions import DataError, ValidationError
from pmail.security import validate_path, MAX_ATTACHMENT_COUNT

logger = logging.getLogger(__name__)


@dataclass
class CriteriaInstance:
    """A concrete example of an email that was classified to a workflow"""

    email_id: str
    workflow_name: str
    timestamp: datetime
    email_features: Dict[str, Any]
    user_confirmed: bool = True
    confidence_score: Optional[float] = None

    def __post_init__(self):
        """Validate after initialization"""
        if not self.email_id:
            raise ValidationError("email_id cannot be empty")
        if not self.workflow_name:
            raise ValidationError("workflow_name cannot be empty")
        if not isinstance(self.email_features, dict):
            raise ValidationError("email_features must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "email_id": self.email_id,
            "workflow_name": self.workflow_name,
            "timestamp": self.timestamp.isoformat(),
            "email_features": self.email_features,
            "user_confirmed": self.user_confirmed,
            "confidence_score": self.confidence_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CriteriaInstance":
        try:
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
            return cls(**data)
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid criteria instance data: {e}")


@dataclass
class WorkflowDefinition:
    """Definition of a workflow"""

    name: str
    description: str
    action_type: str  # e.g., "save_attachment", "flag", "copy_to_folder"
    action_params: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    # Valid action types
    VALID_ACTION_TYPES = {
        "save_attachment",
        "create_todo",
        "save_email_as_pdf",
        "save_pdf",
        "custom",
    }

    def __post_init__(self):
        """Validate after initialization"""
        if not self.name:
            raise ValidationError("Workflow name cannot be empty")
        if not self.action_type:
            raise ValidationError("Action type cannot be empty")
        if self.action_type not in self.VALID_ACTION_TYPES:
            raise ValidationError(
                f"Invalid action type: {self.action_type}. "
                f"Must be one of: {', '.join(self.VALID_ACTION_TYPES)}"
            )

        # Validate action parameters based on type
        self._validate_action_params()

    def _validate_action_params(self):
        """Validate action parameters based on action type"""
        if self.action_type == "save_attachment":
            if "directory" not in self.action_params:
                raise ValidationError("save_attachment requires 'directory' parameter")
            # Validate directory path
            try:
                validate_path(self.action_params["directory"])
            except Exception as e:
                raise ValidationError(f"Invalid directory path: {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowDefinition":
        try:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            return cls(**data)
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid workflow data: {e}")


class DataStore:
    """Handles persistence of workflows and criteria instances"""

    # Limits to prevent unbounded growth
    MAX_CRITERIA_INSTANCES = 10000
    MAX_WORKFLOWS = 100

    def __init__(self, config):
        self.config = config
        self.workflows_file = config.get_workflows_file()
        self.criteria_file = config.get_criteria_instances_file()
        self._load_data()

    def _load_data(self):
        """Load data with error handling"""
        # Load workflows
        try:
            workflows_data = safe_json_load(self.workflows_file, default={})
            self.workflows = {}
            for name, data in workflows_data.items():
                try:
                    self.workflows[name] = WorkflowDefinition.from_dict(data)
                except ValidationError as e:
                    logger.error(f"Skipping invalid workflow '{name}': {e}")
        except Exception as e:
            logger.error(f"Failed to load workflows: {e}")
            self.workflows = {}

        # Add default workflows if empty
        if not self.workflows:
            self.workflows = self._default_workflows()
            try:
                self.save_workflows()
            except Exception as e:
                logger.error(f"Failed to save default workflows: {e}")

        # Load criteria instances
        try:
            criteria_data = safe_json_load(self.criteria_file, default=[])
            self.criteria_instances = []
            for data in criteria_data:
                try:
                    self.criteria_instances.append(CriteriaInstance.from_dict(data))
                except ValidationError as e:
                    logger.error(f"Skipping invalid criteria instance: {e}")
        except Exception as e:
            logger.error(f"Failed to load criteria instances: {e}")
            self.criteria_instances = []

    def _default_workflows(self) -> Dict[str, WorkflowDefinition]:
        """Provide minimal default workflows - use 'pmail init' for full set"""
        defaults = {}

        try:
            # Just create one basic workflow so the system works out of the box
            defaults["create-todo"] = WorkflowDefinition(
                name="create-todo",
                description="Create a todo item from email",
                action_type="create_todo",
                action_params={"todo_file": "~/todos.txt"},
            )
        except ValidationError as e:
            logger.error(f"Failed to create default workflow: {e}")

        return defaults

    def save_workflows(self):
        """Save workflows with atomic write and locking"""
        if len(self.workflows) > self.MAX_WORKFLOWS:
            raise DataError(
                f"Too many workflows: {len(self.workflows)} (max: {self.MAX_WORKFLOWS})",
                recovery_hint="Remove unused workflows",
            )

        with file_lock(self.workflows_file):
            # Backup before save
            try:
                self.config.backup_file(self.workflows_file)
            except Exception as e:
                logger.warning(f"Failed to backup workflows: {e}")

            # Prepare data
            workflows_data = {}
            for name, workflow in self.workflows.items():
                try:
                    workflows_data[name] = workflow.to_dict()
                except Exception as e:
                    logger.error(f"Failed to serialize workflow '{name}': {e}")

            # Atomic write
            atomic_json_write(self.workflows_file, workflows_data)
            logger.info(f"Saved {len(workflows_data)} workflows")

    def save_criteria(self):
        """Save criteria instances with atomic write and locking"""
        if len(self.criteria_instances) > self.MAX_CRITERIA_INSTANCES:
            # Trim oldest instances
            logger.warning(
                f"Trimming criteria instances from {len(self.criteria_instances)} "
                f"to {self.MAX_CRITERIA_INSTANCES}"
            )
            self.criteria_instances = sorted(
                self.criteria_instances, key=lambda x: x.timestamp, reverse=True
            )[: self.MAX_CRITERIA_INSTANCES]

        with file_lock(self.criteria_file):
            # Backup before save
            try:
                self.config.backup_file(self.criteria_file)
            except Exception as e:
                logger.warning(f"Failed to backup criteria: {e}")

            # Prepare data
            criteria_data = []
            for instance in self.criteria_instances:
                try:
                    criteria_data.append(instance.to_dict())
                except Exception as e:
                    logger.error(f"Failed to serialize criteria instance: {e}")

            # Atomic write
            atomic_json_write(self.criteria_file, criteria_data)
            logger.info(f"Saved {len(criteria_data)} criteria instances")

    def add_criteria_instance(self, instance: CriteriaInstance):
        """Add criteria instance with validation"""
        if not isinstance(instance, CriteriaInstance):
            raise ValidationError("Invalid criteria instance type")

        self.criteria_instances.append(instance)
        self.save_criteria()

    def add_workflow(self, workflow: WorkflowDefinition):
        """Add workflow with validation"""
        if not isinstance(workflow, WorkflowDefinition):
            raise ValidationError("Invalid workflow type")

        if len(self.workflows) >= self.MAX_WORKFLOWS:
            raise DataError(
                f"Maximum number of workflows ({self.MAX_WORKFLOWS}) reached",
                recovery_hint="Remove unused workflows before adding new ones",
            )

        self.workflows[workflow.name] = workflow
        self.save_workflows()

    def get_criteria_for_workflow(self, workflow_name: str) -> List[CriteriaInstance]:
        """Get criteria instances for a specific workflow"""
        return [ci for ci in self.criteria_instances if ci.workflow_name == workflow_name]

    def get_recent_criteria(self, limit: int = 100) -> List[CriteriaInstance]:
        """Get the most recent criteria instances"""
        limit = min(limit, len(self.criteria_instances))
        sorted_criteria = sorted(self.criteria_instances, key=lambda x: x.timestamp, reverse=True)
        return sorted_criteria[:limit]
