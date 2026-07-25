"""SQLite-backed watch-folder binding lifecycle and Windows path policy."""

from __future__ import annotations

import ntpath
from pathlib import Path
import sqlite3
from typing import Any

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction
from modules.db.repositories import AuditRepository, WatchFolderBindingRepository
from modules.services.ingestion_assignment_service import (
    IngestionAssignmentError,
    IngestionAssignmentService,
)
from modules.services.pipeline_definition_service import PipelineDefinitionService


class IngressBindingConflictError(ValueError):
    """Raised when a watch binding violates path or lifecycle policy."""


class IngressBindingService:
    """Manage exact-version watch folders and reject overlapping claims."""

    def __init__(self, conn: sqlite3.Connection, config: ConfigProvider) -> None:
        self.conn = conn
        self.config = config
        self.bindings = WatchFolderBindingRepository(conn)
        self.audit = AuditRepository(conn)

    def normalize_path(self, raw_path: str) -> tuple[str, str]:
        """Return display and case-insensitive Windows-normalized absolute paths."""
        if not str(raw_path or "").strip():
            raise IngressBindingConflictError("Watch folder path is required.")
        path = Path(str(raw_path).strip()).expanduser()
        if not path.is_absolute():
            config_path = getattr(self.config, "_config_path", None)
            base = Path(config_path).parent if config_path else Path.cwd()
            path = base / path
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise IngressBindingConflictError(
                "Watch folder does not exist or is inaccessible."
            ) from exc
        if not resolved.is_dir():
            raise IngressBindingConflictError("Watch folder path is not a directory.")
        try:
            next(resolved.iterdir(), None)
        except OSError as exc:
            raise IngressBindingConflictError(
                "Watch folder is inaccessible."
            ) from exc
        display = ntpath.normpath(str(resolved))
        drive, tail = ntpath.splitdrive(display)
        if drive and tail in {"\\", "/"}:
            raise IngressBindingConflictError("A drive root cannot be watched.")
        normalized = ntpath.normcase(display).rstrip("\\/")
        return display, normalized

    def list(self) -> list[dict[str, Any]]:
        """Return bindings with safe version and accessibility summaries."""
        result: list[dict[str, Any]] = []
        for binding in self.bindings.list():
            result.append(self._payload(binding))
        return result

    def create(
        self,
        *,
        folder_path: str,
        pipeline_version_id: str,
        enabled: bool,
        user: str | None,
    ) -> dict[str, Any]:
        display, normalized = self.normalize_path(folder_path)
        summary = self._validate_version(pipeline_version_id, enabled=enabled)
        self._reject_path_conflict(normalized)
        with immediate_transaction(self.conn):
            self._reject_path_conflict(normalized)
            binding = self.bindings.create(
                folder_path=display,
                normalized_path=normalized,
                pipeline_template_id=summary["pipeline_template_id"],
                pipeline_version_id=pipeline_version_id,
                enabled=enabled,
                user=user,
            )
            self._audit("watch_binding.created", binding, user=user)
        return self._payload(binding)

    def update(
        self,
        binding_id: str,
        *,
        folder_path: str | None = None,
        pipeline_version_id: str | None = None,
        enabled: bool | None = None,
        user: str | None,
    ) -> dict[str, Any]:
        current = self.bindings.get(binding_id)
        if current is None:
            raise KeyError(f"Unknown watch-folder binding: {binding_id}")
        display, normalized = self.normalize_path(
            folder_path or str(current["folder_path"])
        )
        target_version = pipeline_version_id or str(current["pipeline_version_id"])
        target_enabled = bool(current["enabled"]) if enabled is None else enabled
        summary = self._validate_version(target_version, enabled=target_enabled)
        self._reject_path_conflict(normalized, exclude_id=binding_id)
        with immediate_transaction(self.conn):
            self._reject_path_conflict(normalized, exclude_id=binding_id)
            updated = self.bindings.update(
                binding_id,
                folder_path=display,
                normalized_path=normalized,
                pipeline_template_id=summary["pipeline_template_id"],
                pipeline_version_id=target_version,
                enabled=target_enabled,
                user=user,
            )
            self._audit("watch_binding.updated", updated, user=user)
        return self._payload(updated)

    def delete(self, binding_id: str, *, user: str | None) -> None:
        current = self.bindings.get(binding_id)
        if current is None:
            raise KeyError(f"Unknown watch-folder binding: {binding_id}")
        if self.bindings.is_referenced(binding_id):
            raise IngressBindingConflictError(
                "A binding referenced by an ingestion batch cannot be deleted."
            )
        with immediate_transaction(self.conn):
            if self.bindings.is_referenced(binding_id):
                raise IngressBindingConflictError(
                    "A binding referenced by an ingestion batch cannot be deleted."
                )
            self._audit("watch_binding.deleted", current, user=user)
            if not self.bindings.delete(binding_id):
                raise KeyError(f"Unknown watch-folder binding: {binding_id}")

    def _validate_version(
        self, version_id: str, *, enabled: bool
    ) -> dict[str, Any]:
        try:
            if enabled:
                return IngestionAssignmentService(
                    self.conn, self.config
                ).resolve_selection(version_id, role="system")
            executable = PipelineDefinitionService(
                self.conn, self.config
            ).load_version(version_id)
            return {
                "pipeline_template_id": executable.template_id,
                "pipeline_version_id": executable.version_id,
            }
        except (IngestionAssignmentError, RuntimeError, KeyError) as exc:
            raise IngressBindingConflictError(
                "Selected pipeline version is not eligible for this binding."
            ) from exc

    def _reject_path_conflict(
        self, normalized_path: str, *, exclude_id: str | None = None
    ) -> None:
        for binding in self.bindings.list():
            if exclude_id and binding["id"] == exclude_id:
                continue
            other = str(binding["normalized_path"])
            try:
                common = ntpath.commonpath([normalized_path, other])
            except ValueError:
                continue
            if common in {normalized_path, other}:
                raise IngressBindingConflictError(
                    "Watch folder duplicates or nests another binding."
                )

    def _audit(
        self, event_type: str, binding: dict[str, Any], *, user: str | None
    ) -> None:
        self.audit.append_uncommitted(
            event_type=event_type,
            event={
                "binding_id": binding["id"],
                "normalized_path": binding["normalized_path"],
                "pipeline_template_id": binding["pipeline_template_id"],
                "pipeline_version_id": binding["pipeline_version_id"],
                "enabled": bool(binding["enabled"]),
            },
            user=user,
        )

    def _payload(self, binding: dict[str, Any]) -> dict[str, Any]:
        version = self.conn.execute(
            """
            SELECT v.version_number, v.content_hash, t.template_key, t.name,
                   t.status AS template_status
            FROM pipeline_versions v
            JOIN pipeline_templates t ON t.id = v.template_id
            WHERE v.id = ?
            """,
            (binding["pipeline_version_id"],),
        ).fetchone()
        accessible = Path(str(binding["folder_path"])).is_dir()
        findings: list[dict[str, str]] = []
        if not accessible:
            findings.append(
                {
                    "code": "watch-folder-inaccessible",
                    "severity": "error",
                    "message": "The configured watch folder is not accessible.",
                }
            )
        if version is None:
            findings.append(
                {
                    "code": "pipeline-version-missing",
                    "severity": "error",
                    "message": "The assigned pipeline version is unavailable.",
                }
            )
        elif bool(binding["enabled"]) and version["template_status"] != "active":
            findings.append(
                {
                    "code": "pipeline-template-inactive",
                    "severity": "error",
                    "message": "The assigned pipeline template is not active.",
                }
            )
        return {
            **binding,
            "enabled": bool(binding["enabled"]),
            "accessible": accessible,
            "pipeline": dict(version) if version else None,
            "validation_findings": findings,
        }
