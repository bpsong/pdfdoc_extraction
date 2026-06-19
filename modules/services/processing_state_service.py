"""Processing-state aggregation for dynamic pipeline UI."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, TypeGuard

from modules.db.connection import json_loads
from modules.db.repositories import BatchRepository, DocumentRepository, TaskRunRepository


SNAPSHOT_METADATA_KEY = "pipeline_snapshot"
SNAPSHOT_VERSION = 1
PAUSED_DOCUMENT_STATUSES = {"review_required", "in_review"}
TERMINAL_DOCUMENT_STATUSES = {"completed", "completed_with_errors", "failed", "cancelled", "review_completed"}
FAILED_DOCUMENT_STATUSES = {"failed", "cancelled"}


def build_pipeline_snapshot(config_manager: Any, *, source: str = "active_config") -> dict[str, Any]:
    """Build a safe display snapshot from the active configured pipeline.

    Args:
        config_manager: Configuration provider supporting ``get`` and/or ``get_all``.
        source: Human-readable source marker for diagnostics.

    Returns:
        A JSON-serializable snapshot that intentionally omits task params.
    """
    pipeline = _config_value(config_manager, "pipeline", [])
    tasks = _config_value(config_manager, "tasks", {})
    if not isinstance(pipeline, list):
        pipeline = []
    if not isinstance(tasks, dict):
        tasks = {}

    steps: list[dict[str, Any]] = []
    for index, task_key in enumerate(pipeline):
        if not isinstance(task_key, str) or not task_key.strip():
            continue
        key = task_key.strip()
        raw_task_cfg = tasks.get(key)
        task_cfg: dict[str, Any] = raw_task_cfg if isinstance(raw_task_cfg, dict) else {}
        module_name = str(task_cfg.get("module") or "")
        class_name = str(task_cfg.get("class") or "")
        label = str(task_cfg.get("label") or _label_for(class_name or key))
        steps.append(
            {
                "key": key,
                "label": label,
                "module": module_name,
                "class": class_name,
                "category": classify_pipeline_step(module_name, class_name, key),
                "position": len(steps),
                "on_error": task_cfg.get("on_error"),
            }
        )

    content_basis = "|".join(
        f"{step['position']}:{step['key']}:{step['module']}:{step['class']}:{step['on_error'] or ''}"
        for step in steps
    )
    return {
        "version": SNAPSHOT_VERSION,
        "source": source,
        "content_hash": hashlib.sha256(content_basis.encode("utf-8")).hexdigest(),
        "step_count": len(steps),
        "steps": steps,
    }


def classify_pipeline_step(module_name: str, class_name: str, task_key: str = "") -> str:
    """Return a display-only category for a configured pipeline step."""
    module_lower = module_name.lower()
    class_lower = class_name.lower()
    key_lower = task_key.lower()
    combined = f"{module_lower}.{class_lower}.{key_lower}"
    if ".split" in module_lower or "split" in combined:
        return "split"
    if ".extraction" in module_lower or "extract" in combined:
        return "extract"
    if ".review" in module_lower or "review" in combined:
        return "review"
    if ".storage" in module_lower or "store" in combined or "metadata" in combined:
        return "storage"
    if ".rules" in module_lower or "rule" in combined or "reference" in combined:
        return "rules"
    if ".archiver" in module_lower or "archive" in combined:
        return "archive"
    if ".housekeeping" in module_lower or "cleanup" in combined:
        return "housekeeping"
    if ".context" in module_lower or "context" in combined or "nanoid" in combined:
        return "context"
    return "custom"


def snapshot_from_batch(batch: dict[str, Any], config_manager: Any) -> dict[str, Any]:
    """Return the persisted batch snapshot or a safe active-config fallback."""
    metadata = json_loads(batch.get("metadata_json"), {})
    if isinstance(metadata, dict):
        snapshot = metadata.get(SNAPSHOT_METADATA_KEY)
        if _valid_snapshot(snapshot):
            return snapshot
    fallback = build_pipeline_snapshot(config_manager, source="active_config_fallback")
    fallback["fallback"] = True
    return fallback


class ProcessingStateService:
    """Build API payloads for dynamic processing overview pages."""

    def __init__(self, config_manager: Any, conn: sqlite3.Connection) -> None:
        """Initialize the service."""
        self.config_manager = config_manager
        self.conn = conn
        self.batches = BatchRepository(conn)
        self.documents = DocumentRepository(conn)
        self.task_runs = TaskRunRepository(conn)

    def get_batch_state(self, batch_id: str) -> dict[str, Any] | None:
        """Return processing state for one batch."""
        batch = self.batches.get(batch_id)
        if batch is None:
            return None
        return self._state_for_batch(batch)

    def list_active_state(self, *, limit: int = 10) -> dict[str, Any]:
        """Return processing state for recent batches."""
        batches = self.batches.list(limit=limit, offset=0)
        states = [self._state_for_batch(batch) for batch in batches]
        return {"batches": states, "pipeline_groups": _pipeline_groups(states), "limit": limit}

    def _state_for_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        """Build one batch state payload."""
        snapshot = snapshot_from_batch(batch, self.config_manager)
        documents = self.documents.list_by_batch(str(batch["id"]))
        runs_by_document = {
            str(document["id"]): self.task_runs.list_by_document(str(document["id"])) for document in documents
        }
        children_by_parent = _children_by_parent(documents)
        split_position = _first_split_position(snapshot)
        document_payloads = [
            self._document_payload(document, snapshot, runs_by_document[str(document["id"])], children_by_parent, split_position)
            for document in documents
        ]
        aggregate_steps = self._aggregate_steps(snapshot, document_payloads)
        return {
            "batch": _batch_payload(batch),
            "pipeline_snapshot": snapshot,
            "aggregate_step_states": aggregate_steps,
            "documents": document_payloads,
            "task_runs_by_document": runs_by_document,
            "progress_percent": _aggregate_progress(document_payloads, batch),
        }

    def _document_payload(
        self,
        document: dict[str, Any],
        snapshot: dict[str, Any],
        task_runs: list[dict[str, Any]],
        children_by_parent: dict[str, list[dict[str, Any]]],
        split_position: int | None,
    ) -> dict[str, Any]:
        """Build one document's dynamic step-state payload."""
        step_states = []
        for step in snapshot.get("steps", []):
            applicable = _step_applies_to_document(document, step, children_by_parent, split_position)
            state = _document_step_state(document, step, task_runs, applicable)
            step_states.append({**step, "state": state, "applicable": applicable})

        current_step = _current_step(step_states, document)
        last_completed = _last_completed_step(step_states)
        progress = _document_progress(document, step_states)
        return {
            **document,
            "metadata": json_loads(document.get("metadata_json"), {}),
            "task_states": step_states,
            "task_runs": task_runs,
            "current_step": current_step,
            "last_completed_step": last_completed,
            "progress_percent": progress,
        }

    @staticmethod
    def _aggregate_steps(snapshot: dict[str, Any], document_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aggregate document states for each configured pipeline step."""
        aggregate = []
        for step in snapshot.get("steps", []):
            states = []
            for document in document_payloads:
                match = next((item for item in document.get("task_states", []) if item.get("key") == step.get("key")), None)
                if match:
                    states.append(str(match.get("state") or "pending"))
            counts = {state: states.count(state) for state in ("pending", "running", "completed", "paused", "failed", "skipped")}
            aggregate_step = {**step, "state": _aggregate_state(states), "counts": counts}
            detail = _aggregate_step_detail(step, document_payloads, states)
            if detail:
                aggregate_step["detail"] = detail
            aggregate.append(aggregate_step)
        return aggregate


def _config_value(config_manager: Any, key: str, default: Any) -> Any:
    """Read config from nested ``get_all`` data or dot-path ``get`` providers."""
    config = config_manager.get_all() if hasattr(config_manager, "get_all") else {}
    if isinstance(config, dict) and key in config:
        return config[key]
    if hasattr(config_manager, "get"):
        return config_manager.get(key, default)
    return default


def _valid_snapshot(value: Any) -> TypeGuard[dict[str, Any]]:
    """Return True when a metadata value looks like a pipeline snapshot."""
    return (
        isinstance(value, dict)
        and value.get("version") == SNAPSHOT_VERSION
        and isinstance(value.get("steps"), list)
        and all(isinstance(step, dict) and step.get("key") for step in value["steps"])
    )


def _label_for(value: str) -> str:
    """Build a readable label from a class or task key."""
    text = value or "Task"
    for suffix in ("Task", "V2"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    chars = []
    for index, char in enumerate(text.replace("_", " ")):
        if index and char.isupper() and chars[-1] != " ":
            chars.append(" ")
        chars.append(char)
    return " ".join("".join(chars).split()).title()


def _batch_payload(batch: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-friendly batch payload with parsed metadata."""
    return {**batch, "metadata": json_loads(batch.get("metadata_json"), {})}


def _children_by_parent(documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group child documents by parent id."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        parent_id = document.get("parent_document_id")
        if parent_id:
            grouped.setdefault(str(parent_id), []).append(document)
    return grouped


def _first_split_position(snapshot: dict[str, Any]) -> int | None:
    """Return the first configured split step position, if any."""
    for step in snapshot.get("steps", []):
        if step.get("category") == "split":
            return int(step.get("position") or 0)
    return None


def _step_applies_to_document(
    document: dict[str, Any],
    step: dict[str, Any],
    children_by_parent: dict[str, list[dict[str, Any]]],
    split_position: int | None,
) -> bool:
    """Return whether a configured step applies to a root or split child document."""
    if split_position is None:
        return True
    position = int(step.get("position") or 0)
    is_child = bool(document.get("parent_document_id"))
    has_children = bool(children_by_parent.get(str(document.get("id"))))
    if is_child:
        return position > split_position
    if has_children:
        return position <= split_position
    return True


def _document_step_state(
    document: dict[str, Any],
    step: dict[str, Any],
    task_runs: list[dict[str, Any]],
    applicable: bool,
) -> str:
    """Return one document's state for one configured step."""
    if not applicable:
        return "skipped"
    key = str(step.get("key") or "")
    runs = [run for run in task_runs if run.get("task_key") == key]
    statuses = [str(run.get("status") or "").lower() for run in runs]
    if "failed" in statuses:
        return "failed"
    document_status = str(document.get("status") or "").lower()
    current_key = str(document.get("current_task_key") or "")
    current_index = int(document.get("current_task_index") or 0)
    step_position = int(step.get("position") or 0)
    if "paused" in statuses:
        if _has_completed_downstream(task_runs, step_position) or (
            document_status in TERMINAL_DOCUMENT_STATUSES and current_index > step_position
        ):
            return "completed"
        return "paused"
    if "running" in statuses:
        return "running"
    if "completed" in statuses:
        return "completed"

    if document_status in FAILED_DOCUMENT_STATUSES and (current_key == key or current_index == step_position):
        return "failed"
    if document_status in PAUSED_DOCUMENT_STATUSES and current_key == key:
        return "paused"
    if current_key == key and document_status not in TERMINAL_DOCUMENT_STATUSES:
        return "running"
    if current_index > step_position and document_status not in {"queued", "received"}:
        return "completed"
    if document_status in {"completed", "review_completed"}:
        return "completed"
    return "pending"


def _has_completed_downstream(task_runs: list[dict[str, Any]], step_position: int) -> bool:
    """Return True when a later step completed after this step paused."""
    return any(
        int(run.get("task_index") or 0) > step_position
        and str(run.get("status") or "").lower() == "completed"
        for run in task_runs
    )


def _aggregate_step_detail(
    step: dict[str, Any],
    document_payloads: list[dict[str, Any]],
    states: list[str],
) -> str | None:
    """Return an outcome-specific aggregate detail for special step types."""
    if step.get("category") != "review":
        return None
    relevant = [state for state in states if state != "skipped"]
    if not relevant or any(state != "completed" for state in relevant):
        return None
    review_runs = []
    step_key = step.get("key")
    for document in document_payloads:
        for run in document.get("task_runs") or []:
            if run.get("task_key") == step_key:
                review_runs.append(run)
    if not review_runs:
        return None
    if all(_review_gate_was_skipped(run) for run in review_runs):
        return "skipped"
    return None


def _review_gate_was_skipped(task_run: dict[str, Any]) -> bool:
    """Return True when a completed review gate passed without human review."""
    if str(task_run.get("status") or "").lower() != "completed":
        return False
    output = json_loads(task_run.get("output_json"), {})
    return (
        output.get("review_required") is False
        or output.get("review_gate_status") == "passed"
        or (output.get("pipeline_state") is None and output.get("review_item_id") is None)
    )


def _aggregate_state(states: list[str]) -> str:
    """Return a display state from document-level step states."""
    relevant = [state for state in states if state != "skipped"]
    if not states:
        return "pending"
    if not relevant:
        return "skipped"
    if "failed" in relevant:
        return "failed"
    if "paused" in relevant:
        return "paused"
    if "running" in relevant:
        return "running"
    if relevant and all(state == "completed" for state in relevant):
        return "completed"
    if "completed" in relevant and "pending" in relevant:
        return "running"
    return "pending"


def _current_step(step_states: list[dict[str, Any]], document: dict[str, Any]) -> dict[str, Any] | None:
    """Return the current display step for a document."""
    active = next((step for step in step_states if step.get("state") in {"running", "paused", "failed"}), None)
    if active:
        return active
    current_key = str(document.get("current_task_key") or "")
    if current_key:
        return next((step for step in step_states if step.get("key") == current_key), None)
    return next((step for step in step_states if step.get("state") == "pending" and step.get("applicable")), None)


def _last_completed_step(step_states: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the last completed configured step."""
    completed = [step for step in step_states if step.get("state") == "completed"]
    return completed[-1] if completed else None


def _document_progress(document: dict[str, Any], step_states: list[dict[str, Any]]) -> int:
    """Calculate deterministic progress from configured step states."""
    status = str(document.get("status") or "").lower()
    if status in TERMINAL_DOCUMENT_STATUSES:
        return 100
    applicable = [step for step in step_states if step.get("applicable")]
    if not applicable:
        return 100 if status in {"completed", "review_completed"} else 10
    total_units = 1 + len(applicable)
    completed_units = 1.0
    for step in applicable:
        state = step.get("state")
        if state == "completed":
            completed_units += 1.0
        elif state in {"running", "paused"}:
            completed_units += 0.5
        elif state == "failed":
            completed_units += 1.0
    return min(100, max(0, round((completed_units / total_units) * 100)))


def _aggregate_progress(document_payloads: list[dict[str, Any]], batch: dict[str, Any]) -> int:
    """Return aggregate progress for a batch state payload."""
    if document_payloads:
        return round(sum(int(document.get("progress_percent") or 0) for document in document_payloads) / len(document_payloads))
    total = int(batch.get("total_documents") or 0)
    completed = int(batch.get("completed_documents") or 0)
    failed = int(batch.get("failed_documents") or 0)
    return round(((completed + failed) / total) * 100) if total else 0


def _pipeline_groups(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group recent batch states by pipeline snapshot hash."""
    groups: dict[str, dict[str, Any]] = {}
    for state in states:
        snapshot = state.get("pipeline_snapshot") or {}
        content_hash = str(snapshot.get("content_hash") or "unknown")
        group = groups.setdefault(
            content_hash,
            {
                "content_hash": content_hash,
                "pipeline_snapshot": snapshot,
                "batch_ids": [],
                "batch_count": 0,
                "document_count": 0,
            },
        )
        batch = state.get("batch") or {}
        if batch.get("id"):
            group["batch_ids"].append(batch["id"])
        group["batch_count"] += 1
        group["document_count"] += len(state.get("documents") or [])
    return list(groups.values())
