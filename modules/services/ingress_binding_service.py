"""SQLite-backed watch-folder binding lifecycle and Windows path policy."""

from __future__ import annotations

import ntpath
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from typing import Any

from modules.config_protocol import ConfigProvider
from modules.db.connection import immediate_transaction, utc_now
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

    def management_list(self) -> list[dict[str, Any]]:
        """Add publication, monitoring, and lifecycle summaries for administrators."""
        result = self.list()
        for item in result:
            latest = self.bindings.latest_version(item["pipeline_template_id"])
            health = self.bindings.health(item["id"])
            state = item["state"]
            last_scan = health.get("last_scan_at")
            stale = not last_scan or (datetime.now(timezone.utc) - datetime.fromisoformat(last_scan)).total_seconds() > max(30, float(self.config.get("watch_folder.polling_interval", 5)) * 3)
            item.update(
                latest_version=latest,
                update_available=bool(latest and latest["id"] != item["pipeline_version_id"]),
                health=health,
                health_status=state if state != "enabled" else (
                    "unhealthy" if item["validation_findings"] or health.get("issue") else "stale" if stale else "healthy"
                ),
                can_delete=not self.bindings.is_referenced(item["id"]),
            )
        return result

    def check_access(self, folder_path: str) -> dict[str, Any]:
        """Check existence and directory listing without moving or creating files."""
        try:
            display, _ = self.normalize_path(folder_path)
            return {"ok": True, "folder_path": display, "message": "Folder exists and can be listed. File move/delete permissions were not tested.", "checked_at": utc_now()}
        except IngressBindingConflictError as exc:
            return {"ok": False, "message": str(exc), "checked_at": utc_now()}

    def create(
        self,
        *,
        folder_path: str,
        pipeline_version_id: str | None,
        enabled: bool,
        user: str | None,
    ) -> dict[str, Any]:
        display, normalized = self.normalize_path(folder_path)
        summary = self._validate_version(pipeline_version_id, enabled=enabled) if pipeline_version_id or enabled else {"pipeline_template_id": None}
        pipeline_version_id = pipeline_version_id or None
        self._reject_path_conflict(normalized)
        with immediate_transaction(self.conn):
            self._reject_path_conflict(normalized)
            if pipeline_version_id or enabled:
                summary = self._validate_version(pipeline_version_id, enabled=enabled)
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
        action: str | None = None,
        expected_revision: int | None = None,
        user: str | None,
    ) -> dict[str, Any]:
        current = self.bindings.get(binding_id)
        if current is None:
            raise KeyError(f"Unknown watch-folder binding: {binding_id}")
        if current.get("retired_at"):
            raise IngressBindingConflictError("Retired bindings cannot be edited.")
        if action not in {None, "pause", "resume", "unbind", "retire"}:
            raise IngressBindingConflictError("Unknown binding action.")
        if action in {"pause", "unbind", "retire"}:
            enabled = False
        elif action == "resume":
            enabled = True
        display, normalized = str(current["folder_path"]), str(current["normalized_path"])
        if folder_path is not None or enabled is True:
            display, normalized = self.normalize_path(folder_path if folder_path is not None else display)
        target_version = pipeline_version_id if pipeline_version_id is not None else current["pipeline_version_id"]
        target_enabled = bool(current["enabled"]) if enabled is None else enabled
        summary = {"pipeline_template_id": current["pipeline_template_id"]}
        if pipeline_version_id is not None or target_enabled:
            summary = self._validate_version(target_version, enabled=target_enabled)
        if action == "unbind":
            target_version = None
            summary = {"pipeline_template_id": None}
        self._reject_path_conflict(normalized, exclude_id=binding_id)
        with immediate_transaction(self.conn):
            fresh = self.bindings.get(binding_id)
            if fresh is None:
                raise KeyError(f"Unknown watch-folder binding: {binding_id}")
            revision = current.get("revision", 1) if expected_revision is None else expected_revision
            if fresh.get("revision", 1) != revision:
                raise IngressBindingConflictError("This binding changed. Refresh before saving.")
            if action != "unbind" and (pipeline_version_id is not None or target_enabled):
                summary = self._validate_version(target_version, enabled=target_enabled)
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
            self.bindings.set_lifecycle(binding_id, retired_at=utc_now() if action == "retire" else None)
            updated = self.bindings.get(binding_id)
            self._audit(f"watch_binding.{action or 'updated'}", updated, user=user, previous=current)
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
        self, version_id: str | None, *, enabled: bool
    ) -> dict[str, Any]:
        try:
            if not version_id:
                raise IngressBindingConflictError("A published pipeline version is required.")
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
        except IngestionAssignmentError as exc:
            if str(exc) == "Selected pipeline template is not active.":
                raise IngressBindingConflictError(
                    "The pipeline template must be active before a watch-folder "
                    "binding can be enabled. Publish a version and activate the "
                    "template first."
                ) from exc
            raise IngressBindingConflictError(
                "Selected pipeline version is not eligible for this binding."
            ) from exc
        except (RuntimeError, KeyError) as exc:
            raise IngressBindingConflictError(
                "Selected pipeline version is not eligible for this binding."
            ) from exc

    def _reject_path_conflict(
        self, normalized_path: str, *, exclude_id: str | None = None
    ) -> None:
        for binding in self.bindings.list():
            if binding.get("retired_at"):
                continue
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
        self, event_type: str, binding: dict[str, Any], *, user: str | None,
        previous: dict[str, Any] | None = None,
    ) -> None:
        self.audit.append_uncommitted(
            event_type=event_type,
            event={
                "binding_id": binding["id"],
                "normalized_path": binding["normalized_path"],
                "pipeline_template_id": binding["pipeline_template_id"],
                "pipeline_version_id": binding["pipeline_version_id"],
                "enabled": bool(binding["enabled"]),
                "previous": previous,
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
        if version is None and binding["pipeline_version_id"]:
            findings.append(
                {
                    "code": "pipeline-version-missing",
                    "severity": "error",
                    "message": "The assigned pipeline version is unavailable.",
                }
            )
        elif version is not None and bool(binding["enabled"]) and version["template_status"] != "active":
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
            "state": "retired" if binding.get("retired_at") else (
                "enabled" if binding["enabled"] else "paused" if binding["pipeline_version_id"] else "unbound"
            ),
        }
