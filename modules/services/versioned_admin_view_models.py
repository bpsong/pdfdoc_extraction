"""Deterministic UI state helpers for versioned administration pages."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def lifecycle_actions(
    status: str, *, has_published_version: bool
) -> dict[str, bool]:
    """Return lifecycle action availability for a template."""
    return {
        "can_activate": status == "inactive" and has_published_version,
        "can_deactivate": status == "active",
        "can_archive": status == "inactive",
        "can_edit": status != "archived",
        "can_publish": status != "archived",
    }


def version_label(version: Mapping[str, Any], *, kind: str) -> str:
    """Return an exact, human-readable pipeline/schema version label."""
    if kind not in {"pipeline", "schema"}:
        raise ValueError("Version label kind must be pipeline or schema.")
    if kind == "schema":
        prefix = version.get("schema_key") or version.get("template_name")
    else:
        prefix = version.get("template_key") or version.get("name")
    number = version.get("version_number") or "—"
    hash_suffix = (
        f" · {str(version['content_hash'])[:10]}"
        if version.get("content_hash")
        else ""
    )
    return f"{prefix or 'Template'} · v{number}{hash_suffix}"


def schema_selector_options(
    versions: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return stable exact-version options without choosing one implicitly."""
    return [
        {
            "value": str(version["id"]),
            "label": version_label(version, kind="schema"),
            "content_hash": version.get("content_hash"),
            "version_number": version.get("version_number"),
        }
        for version in versions
    ]


def group_findings(
    findings: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group validation findings by severity without changing order."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        item = dict(finding)
        grouped.setdefault(str(item.get("severity") or "error"), []).append(item)
    return grouped


def revision_conflict_view(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Return explicit stale-writer state without selecting a replacement."""
    return {
        "message": str(detail.get("message") or "The draft changed on the server."),
        "current": detail.get("current"),
        "reload_required": detail.get("current") is not None,
        "overwrite_allowed": False,
    }
