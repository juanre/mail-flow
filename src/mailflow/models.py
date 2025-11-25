# ABOUTME: Data models for workflows, criteria instances, and execution history
# ABOUTME: Provides dataclasses with validation for workflow definitions and tracking
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mailflow.exceptions import DataError, ValidationError
from mailflow.security import validate_path
from mailflow.utils import atomic_json_write, file_lock, safe_json_load

logger = logging.getLogger(__name__)


@dataclass
class CriteriaInstance:
    """A concrete example of an email that was classified to a workflow"""

    email_id: str
    workflow_name: str
    timestamp: datetime
    email_features: dict[str, Any]
    user_confirmed: bool = True
    confidence_score: float | None = None

    def __post_init__(self):
        """Validate after initialization"""
        if not self.email_id:
            raise ValidationError("email_id cannot be empty")
        if not self.workflow_name:
            raise ValidationError("workflow_name cannot be empty")
        if not isinstance(self.email_features, dict):
            raise ValidationError("email_features must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "email_id": self.email_id,
            "workflow_name": self.workflow_name,
            "timestamp": self.timestamp.isoformat(),
            "email_features": self.email_features,
            "user_confirmed": self.user_confirmed,
            "confidence_score": self.confidence_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CriteriaInstance":
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
    action_params: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    # Valid action types
    VALID_ACTION_TYPES = {
        "save_attachment",
        "create_todo",
        "save_email_as_pdf",
        "save_pdf",
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
        # archive-protocol handles all path management
        # No directory validation needed
        pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinition":
        try:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            return cls(**data)
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid workflow data: {e}")


class DataStore:
    """Handles persistence of workflows and criteria instances"""

    # Workflow limit to prevent misconfiguration
    MAX_WORKFLOWS = 100

    # Storage milestone thresholds for criteria instances
    # No hard limit - training data diversity is valuable regardless of age
    CRITERIA_MILESTONES = [50000, 100000, 150000, 200000, 250000]

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

    def _default_workflows(self) -> dict[str, WorkflowDefinition]:
        """Return empty dict - users should run 'mailflow init' to set up workflows.

        No default workflows are created automatically. Users must run 'mailflow init'
        to create workflows tailored to their needs (entities and document types).
        """
        return {}

    def save_workflows(self):
        """Save workflows with atomic write and locking"""
        if len(self.workflows) > self.MAX_WORKFLOWS:
            raise DataError(
                f"Too many workflows: {len(self.workflows)} (max: {self.MAX_WORKFLOWS})",
                recovery_hint="Remove unused workflows",
            )

        with file_lock(self.workflows_file):
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
        """Save criteria instances without arbitrary limits.

        Training data is valuable - old examples are as important as new ones
        for maintaining classification diversity. Storage is cheap (~2KB per instance),
        so we don't delete training data arbitrarily.

        Warnings are issued at storage milestones to keep user informed.
        """
        instance_count = len(self.criteria_instances)

        # Warn at milestones (50k, 100k, 150k, etc.) but don't delete
        for milestone in self.CRITERIA_MILESTONES:
            if instance_count == milestone:
                storage_mb = (instance_count * 2048) / (1024 * 1024)  # Rough estimate
                logger.warning(
                    f"Criteria instances reached {instance_count:,} entries (~{storage_mb:.1f}MB). "
                    f"Consider reviewing if storage becomes an issue."
                )
                break

        with file_lock(self.criteria_file):
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

    def get_criteria_for_workflow(self, workflow_name: str) -> list[CriteriaInstance]:
        """Get criteria instances for a specific workflow"""
        return [ci for ci in self.criteria_instances if ci.workflow_name == workflow_name]

    def get_recent_criteria(self, limit: int = 100) -> list[CriteriaInstance]:
        """Get the most recent criteria instances"""
        limit = min(limit, len(self.criteria_instances))
        sorted_criteria = sorted(self.criteria_instances, key=lambda x: x.timestamp, reverse=True)
        return sorted_criteria[:limit]

    def record_skip(self, email_id: str, features: dict) -> None:
        """Record a skip decision for classifier training (negative example).

        Args:
            email_id: The message ID of the skipped email
            features: Email features dict for training
        """
        instance = CriteriaInstance(
            email_id=email_id,
            workflow_name="_skip",
            timestamp=datetime.now(),
            email_features=features,
            user_confirmed=True,
        )
        self.add_criteria_instance(instance)
