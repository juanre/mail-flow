# ABOUTME: Data models for workflows and execution history
# ABOUTME: Provides dataclasses with validation for workflow definitions
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mailflow.exceptions import DataError, ValidationError
from mailflow.utils import atomic_json_write, file_lock

logger = logging.getLogger(__name__)

WORKFLOWS_SCHEMA_VERSION = 1


def _validate_str_list(value: Any, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValidationError(
            f"Invalid '{field_name}': must be a list of non-empty strings"
        )


@dataclass
class WorkflowDefinition:
    """Definition of a workflow (vNext schema)."""

    name: str
    kind: str
    criteria: dict[str, Any]
    handling: dict[str, Any]
    constraints: dict[str, Any] | None = None
    postprocessors: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate after initialization."""
        if not isinstance(self.name, str) or not self.name:
            raise ValidationError("Workflow name cannot be empty")
        if not isinstance(self.kind, str) or not self.kind:
            raise ValidationError("Workflow kind cannot be empty")
        if not isinstance(self.criteria, dict):
            raise ValidationError("Workflow criteria must be an object")
        summary = self.criteria.get("summary")
        if not isinstance(summary, str) or not summary:
            raise ValidationError("Workflow criteria.summary is required")

        _validate_str_list(self.criteria.get("must_include"), "criteria.must_include")
        _validate_str_list(self.criteria.get("must_exclude"), "criteria.must_exclude")
        _validate_str_list(self.criteria.get("topics"), "criteria.topics")

        if self.constraints is not None and not isinstance(self.constraints, dict):
            raise ValidationError("Workflow constraints must be an object if provided")
        if isinstance(self.constraints, dict):
            _validate_str_list(
                self.constraints.get("requires_evidence"),
                "constraints.requires_evidence",
            )
            _validate_str_list(
                self.constraints.get("evidence_sources"),
                "constraints.evidence_sources",
            )

        if not isinstance(self.handling, dict) or not self.handling:
            raise ValidationError("Workflow handling is required")

        unsupported = set(self.handling.keys()) - {"archive", "index"}
        if unsupported:
            raise ValidationError(
                f"Unsupported handling keys for mailflow: {', '.join(sorted(unsupported))}"
            )

        archive = self.handling.get("archive")
        if not isinstance(archive, dict):
            raise ValidationError("Workflow handling.archive is required for mailflow")
        target = archive.get("target")
        if target != "document":
            raise ValidationError(
                f"Unsupported archive target for mailflow: {target!r} (expected 'document')"
            )
        entity = archive.get("entity")
        doctype = archive.get("doctype")
        if not isinstance(entity, str) or not entity:
            raise ValidationError("Workflow handling.archive.entity is required")
        if not isinstance(doctype, str) or not doctype:
            raise ValidationError("Workflow handling.archive.doctype is required")

        index = self.handling.get("index")
        if index is not None:
            if not isinstance(index, dict):
                raise ValidationError("Workflow handling.index must be an object if provided")
            llmemory = index.get("llmemory")
            if llmemory is not None and not isinstance(llmemory, bool):
                raise ValidationError("Workflow handling.index.llmemory must be boolean if provided")

    @property
    def archive_entity(self) -> str:
        return self.handling["archive"]["entity"]

    @property
    def archive_doctype(self) -> str:
        return self.handling["archive"]["doctype"]

    @property
    def index_llmemory(self) -> bool:
        index = self.handling.get("index") or {}
        llmemory = index.get("llmemory")
        return True if llmemory is None else bool(llmemory)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "kind": self.kind,
            "criteria": self.criteria,
            "handling": self.handling,
        }
        if self.constraints:
            data["constraints"] = self.constraints
        if self.postprocessors:
            data["postprocessors"] = self.postprocessors
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinition":
        """Parse workflow entries from workflows.json (vNext)."""
        if not isinstance(data, dict):
            raise ValidationError("Workflow entry must be an object")
        try:
            return cls(
                name=data.get("name"),
                kind=data.get("kind"),
                criteria=data.get("criteria"),
                constraints=data.get("constraints"),
                handling=data.get("handling"),
                postprocessors=data.get("postprocessors") or [],
            )
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

    def _load_data(self) -> None:
        """Load workflows with strict schema validation."""
        if not self.workflows_file.exists():
            raise DataError(
                f"Workflows file not found: {self.workflows_file}",
                recovery_hint="Create workflows.json with 'mailflow init'",
            )

        try:
            with open(self.workflows_file) as f:
                workflows_data = json.load(f)
        except json.JSONDecodeError as e:
            raise DataError(
                f"Invalid JSON in workflows file: {self.workflows_file}",
                recovery_hint=str(e),
            )
        except OSError as e:
            raise DataError(
                f"Failed to read workflows file: {self.workflows_file}",
                recovery_hint=str(e),
            )

        if not isinstance(workflows_data, dict):
            raise DataError("workflows.json must be a JSON object")

        schema_version = workflows_data.get("schema_version")
        if schema_version != WORKFLOWS_SCHEMA_VERSION:
            raise DataError(
                f"Unsupported workflows.json schema_version: {schema_version}",
                recovery_hint=f"Expected schema_version={WORKFLOWS_SCHEMA_VERSION}",
            )

        workflows_list = workflows_data.get("workflows")
        if not isinstance(workflows_list, list):
            raise DataError("workflows.json must include a 'workflows' list")

        self.workflows = {}
        for idx, entry in enumerate(workflows_list):
            try:
                workflow = WorkflowDefinition.from_dict(entry)
            except ValidationError as e:
                raise DataError(
                    f"Invalid workflow entry at index {idx}: {e}",
                    recovery_hint="Fix the entry or remove it",
                )
            if workflow.name in self.workflows:
                raise DataError(
                    f"Duplicate workflow name: {workflow.name}",
                    recovery_hint="Workflow names must be unique",
                )
            self.workflows[workflow.name] = workflow

    def save_workflows(self) -> None:
        """Save workflows with atomic write and locking."""
        if len(self.workflows) > self.MAX_WORKFLOWS:
            raise DataError(
                f"Too many workflows: {len(self.workflows)} (max: {self.MAX_WORKFLOWS})",
                recovery_hint="Remove unused workflows",
            )

        with file_lock(self.workflows_file):
            entries = [workflow.to_dict() for workflow in self.workflows.values()]
            atomic_json_write(
                self.workflows_file,
                {"schema_version": WORKFLOWS_SCHEMA_VERSION, "workflows": entries},
            )
            logger.info(f"Saved {len(entries)} workflows")

    def add_workflow(self, workflow: WorkflowDefinition) -> None:
        """Add workflow with validation."""
        if not isinstance(workflow, WorkflowDefinition):
            raise ValidationError("Invalid workflow type")

        if len(self.workflows) >= self.MAX_WORKFLOWS:
            raise DataError(
                f"Maximum number of workflows ({self.MAX_WORKFLOWS}) reached",
                recovery_hint="Remove unused workflows before adding new ones",
            )

        if workflow.name in self.workflows:
            raise ValidationError(f"Workflow '{workflow.name}' already exists")

        self.workflows[workflow.name] = workflow
        self.save_workflows()
