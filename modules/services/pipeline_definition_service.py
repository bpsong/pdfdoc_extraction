"""Exact-version runtime definition loading for pinned document execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import sqlite3
from typing import Any, Mapping

from modules.config_protocol import ConfigProvider
from modules.db.repositories import BatchRepository, DocumentRepository
from modules.services.pipeline_template_service import PipelineTemplateService
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.task_registry_service import ApprovedTaskRegistry, TaskApprovalError
from modules.services.versioned_config_contracts import (
    PIPELINE_DEFINITION_SCHEMA_VERSION,
    RuntimeResolvedDefinition,
    resolve_secret_references,
)


class PipelineDefinitionError(RuntimeError):
    """Raised when a pinned executable definition cannot be safely loaded."""


@dataclass(frozen=True, slots=True)
class ExecutablePipeline:
    """Non-serializable runtime definition with immutable attribution."""

    template_id: str
    template_key: str
    version_id: str
    version_number: int
    content_hash: str
    definition: RuntimeResolvedDefinition
    display_snapshot: dict[str, Any]

    @property
    def pipeline(self) -> list[str]:
        value = self.definition.get("pipeline", [])
        return list(value) if isinstance(value, list) else []

    @property
    def tasks(self) -> Mapping[str, Any]:
        value = self.definition.get("tasks", {})
        return value if isinstance(value, Mapping) else {}


class PipelineDefinitionService:
    """Load and verify one exact immutable pipeline for runtime execution."""

    def __init__(self, conn: sqlite3.Connection, config: ConfigProvider) -> None:
        self.conn = conn
        self.config = config

    def load_version(self, version_id: str) -> ExecutablePipeline:
        """Load an exact version, schemas, secrets, and task approvals."""
        try:
            pipelines = PipelineTemplateService(self.conn)
            version = pipelines.load_version(version_id)
            if int(version["schema_version"]) != PIPELINE_DEFINITION_SCHEMA_VERSION:
                raise PipelineDefinitionError(
                    "Pinned pipeline uses an unsupported definition format."
                )
            template = pipelines.templates.get(str(version["template_id"]))
            if template is None:
                raise PipelineDefinitionError("Pinned pipeline template is missing.")

            definition = deepcopy(version["definition"])
            self._inject_review_schemas(definition, version["schema_dependencies"])
            self._verify_task_approvals(definition)
            raw_secrets = self.config.get("pipeline_secrets", {}) or {}
            secrets = raw_secrets if isinstance(raw_secrets, Mapping) else {}
            resolved = resolve_secret_references(definition, secrets)
            return ExecutablePipeline(
                template_id=str(template["id"]),
                template_key=str(template["template_key"]),
                version_id=str(version["id"]),
                version_number=int(version["version_number"]),
                content_hash=str(version["content_hash"]),
                definition=resolved,
                display_snapshot=dict(version["display_snapshot"]),
            )
        except PipelineDefinitionError:
            raise
        except (KeyError, ValueError, RuntimeError, TaskApprovalError) as exc:
            raise PipelineDefinitionError(
                "Pinned pipeline definition is unavailable or invalid."
            ) from exc

    def load_for_document(self, document_id: str) -> ExecutablePipeline:
        """Load the document assignment and reject batch/document disagreement."""
        documents = DocumentRepository(self.conn)
        document = documents.get(document_id)
        if document is None:
            raise PipelineDefinitionError("Document does not exist.")
        version_id = document.get("pipeline_version_id")
        template_id = document.get("pipeline_template_id")
        if not version_id or not template_id:
            raise PipelineDefinitionError("Document has no pinned pipeline assignment.")
        batch = BatchRepository(self.conn).get(str(document["batch_id"]))
        if batch is None:
            raise PipelineDefinitionError("Document batch does not exist.")
        if (
            batch.get("pipeline_version_id") != version_id
            or batch.get("pipeline_template_id") != template_id
        ):
            raise PipelineDefinitionError(
                "Document and batch pipeline assignments disagree."
            )
        executable = self.load_version(str(version_id))
        if executable.template_id != str(template_id):
            raise PipelineDefinitionError(
                "Pinned pipeline version does not belong to the assigned template."
            )
        return executable

    def _inject_review_schemas(
        self,
        definition: dict[str, Any],
        dependencies: Mapping[str, str],
    ) -> None:
        tasks = definition.get("tasks")
        if not isinstance(tasks, dict):
            raise PipelineDefinitionError("Pinned pipeline tasks are malformed.")
        schemas = ReviewSchemaVersionService(self.conn)
        for task_key, schema_version_id in dependencies.items():
            task = tasks.get(task_key)
            if not isinstance(task, dict):
                raise PipelineDefinitionError(
                    "Pinned review dependency refers to an unknown task."
                )
            params = task.setdefault("params", {})
            if not isinstance(params, dict):
                raise PipelineDefinitionError("Pinned review task parameters are malformed.")
            if params.get("schema_version_id") != schema_version_id:
                raise PipelineDefinitionError(
                    "Pinned review dependency identity does not match task JSON."
                )
            schema_version = schemas.load_version(schema_version_id)
            params["_review_schema"] = deepcopy(schema_version["schema"])
            params["_review_schema_hash"] = schema_version["content_hash"]

    def _verify_task_approvals(self, definition: Mapping[str, Any]) -> None:
        tasks = definition.get("tasks")
        pipeline = definition.get("pipeline")
        if not isinstance(tasks, Mapping) or not isinstance(pipeline, list):
            raise PipelineDefinitionError("Pinned pipeline structure is malformed.")
        registry = ApprovedTaskRegistry(self.config)
        for task_key in pipeline:
            task = tasks.get(task_key)
            if not isinstance(task, Mapping):
                raise PipelineDefinitionError(
                    f"Pinned pipeline task is missing: {task_key}"
                )
            module_name = str(task.get("module") or "")
            class_name = str(task.get("class") or "")
            registry.assert_approved(module_name, class_name)
