# ABOUTME: Data models for workflows and execution history
# ABOUTME: Provides dataclasses with validation for workflow definitions
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from mailflow.exceptions import DataError, ValidationError
from mailflow.utils import atomic_json_write, file_lock, safe_json_load

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDefinition:
    """Definition of a workflow"""

    name: str
    description: str
    # Connector-local action used to produce canonical archived output.
    # If missing in workflows.json (SOT), mailflow defaults to save_pdf.
    action_type: str = "save_pdf"
    action_params: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
        """Parse workflow entries from workflows.json.

        Supports both:
        - SOT format entries (minimal): {name, description, postprocessors?}
        - Legacy mailflow entries: {name, description, action_type, action_params, created_at}
        """
        try:
            parsed: dict[str, Any] = dict(data)

            if not parsed.get("action_type"):
                parsed["action_type"] = "save_pdf"
            if parsed.get("action_params") is None:
                parsed["action_params"] = {}

            created_at_raw = parsed.get("created_at")
            if created_at_raw:
                dt = datetime.fromisoformat(created_at_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed["created_at"] = dt
            else:
                parsed["created_at"] = datetime.now(timezone.utc)

            # Ignore non-mailflow keys (e.g. postprocessors, tags)
            allowed_keys = {"name", "description", "action_type", "action_params", "created_at"}
            parsed = {k: v for k, v in parsed.items() if k in allowed_keys}

            return cls(**parsed)
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid workflow data: {e}")


class DataStore:
    """Handles persistence of workflows"""

    # Workflow limit to prevent misconfiguration
    MAX_WORKFLOWS = 100

    def __init__(self, config):
        self.config = config
        self.workflows_file = config.get_workflows_file()
        self._load_data()

    def _load_data(self):
        """Load data with error handling"""
        # Load workflows
        try:
            workflows_data = safe_json_load(self.workflows_file, default={})
            self.workflows = {}
            migrated = False

            # SOT format: {"workflows": [ {name, description, ...}, ... ]}
            if isinstance(workflows_data, dict) and isinstance(workflows_data.get("workflows"), list):
                for entry in workflows_data["workflows"]:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    if not name:
                        continue
                    try:
                        self.workflows[name] = WorkflowDefinition.from_dict(entry)
                    except ValidationError as e:
                        logger.error(f"Skipping invalid workflow '{name}': {e}")

            # Legacy format: { "<name>": {...workflow...}, ... }
            elif isinstance(workflows_data, dict):
                for name, data in workflows_data.items():
                    if not isinstance(data, dict):
                        continue
                    try:
                        self.workflows[name] = WorkflowDefinition.from_dict(data)
                    except ValidationError as e:
                        logger.error(f"Skipping invalid workflow '{name}': {e}")
                migrated = bool(self.workflows)

            if migrated:
                logger.warning(
                    "Detected legacy workflows.json format at %s; migrating to SOT format",
                    self.workflows_file,
                )
                try:
                    self.save_workflows()
                except Exception as e:
                    logger.error(f"Failed to migrate workflows.json: {e}")
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
            # Prepare SOT-shaped data
            entries: list[dict[str, Any]] = []
            for name, workflow in self.workflows.items():
                try:
                    entries.append(workflow.to_dict())
                except Exception as e:
                    logger.error(f"Failed to serialize workflow '{name}': {e}")

            # Atomic write
            atomic_json_write(self.workflows_file, {"workflows": entries})
            logger.info(f"Saved {len(entries)} workflows")

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
