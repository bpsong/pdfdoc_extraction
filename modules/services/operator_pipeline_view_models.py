"""Deterministic operator UI state for exact pipeline selection."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence


def reconcile_selection(
    selected_version_id: str | None,
    available_versions: Iterable[Mapping[str, Any]],
) -> str | None:
    """Keep a selection only while the exact version remains available."""
    available_ids = {
        str(version["pipeline_version_id"]) for version in available_versions
    }
    return (
        selected_version_id
        if selected_version_id and selected_version_id in available_ids
        else None
    )


def can_start_processing(
    files: Sequence[Mapping[str, Any]],
    *,
    selected_version_id: str | None,
    uploading: bool,
) -> bool:
    """Return whether upload prerequisites are fully satisfied."""
    return bool(
        not uploading
        and selected_version_id
        and files
        and all(not file.get("error") for file in files)
    )


def multipart_selection_fields(
    selected_version_id: str, filenames: Sequence[str]
) -> list[tuple[str, str]]:
    """Return the scalar multipart contract for one whole batch."""
    if not selected_version_id:
        raise ValueError("A pipeline version must be selected.")
    return [("pipeline_version_id", selected_version_id), *[
        ("files", filename) for filename in filenames
    ]]


def pinned_pipeline_label(identity: Mapping[str, Any]) -> str:
    """Return an honest exact-version or migration-derived label."""
    if identity.get("historical"):
        return "Historical migrated pipeline"
    return (
        f"{identity.get('name') or identity.get('template_key') or 'Pipeline'} "
        f"({identity.get('template_key')}, version {identity.get('version_number')})"
    )
