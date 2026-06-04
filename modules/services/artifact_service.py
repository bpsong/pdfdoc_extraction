"""Helpers for registering durable document artifacts in SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.config_manager import ConfigManager
from modules.db.connection import connect
from modules.db.repositories import DocumentRepository


def register_document_artifact(
    config_manager: ConfigManager,
    context: dict[str, Any],
    *,
    file_type: str,
    file_path: str | Path,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Register a durable file output for the current SQLite document.

    The helper is intentionally best-effort for standard steps: a missing
    ``document_id`` means the task is running in legacy/direct mode, while a
    database error should not hide the primary file-operation result.
    """
    document_id = context.get("document_id") or context.get("id")
    if not document_id:
        return None

    resolved_path = str(Path(str(file_path)).resolve())
    try:
        with connect(config_manager) as conn:
            documents = DocumentRepository(conn)
            if documents.get(str(document_id)) is None:
                return None
            existing = documents.find_file(
                document_id=str(document_id),
                file_type=file_type,
                file_path=resolved_path,
            )
            if existing:
                return existing
            return documents.add_file(
                document_id=str(document_id),
                file_type=file_type,
                file_path=resolved_path,
                metadata=metadata,
            )
    except Exception:
        return None
