"""Helpers for running LlamaCloud Extract v2 jobs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from llama_cloud import LlamaCloud

from modules.exceptions import TaskError


@dataclass
class LlamaCloudExtractionResult:
    """Normalized Extract v2 result used by extraction tasks."""

    data: Dict[str, Any]
    extraction_metadata: Dict[str, Any]
    job_id: str
    status: str


def build_extraction_configuration(
    fields: Dict[str, Any],
    *,
    tier: str = "agentic",
    parse_tier: Optional[str] = None,
    extraction_target: str = "per_doc",
    cite_sources: Optional[bool] = None,
    confidence_scores: Optional[bool] = True,
) -> Dict[str, Any]:
    """Build an inline Extract v2 configuration from task field settings.

    Args:
        fields: Field mapping from task configuration.
        tier: Extract tier to use.
        parse_tier: Optional parse tier to use before extraction.
        extraction_target: Extract target, usually ``per_doc``.
        cite_sources: Whether to request citation metadata.
        confidence_scores: Whether to request field confidence metadata.

    Returns:
        Inline configuration dictionary accepted by ``client.extract.run``.
    """
    configuration: Dict[str, Any] = {
        "data_schema": build_data_schema(fields),
        "extraction_target": extraction_target,
        "tier": tier,
    }

    if parse_tier:
        configuration["parse_tier"] = parse_tier
    if cite_sources is not None:
        configuration["cite_sources"] = cite_sources
    if confidence_scores is not None:
        configuration["confidence_scores"] = confidence_scores

    return configuration


def build_data_schema(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Build a JSON schema from extraction fields using workflow field keys."""
    properties: Dict[str, Any] = {}

    for field_key, field_config in fields.items():
        if not isinstance(field_config, dict):
            continue

        if field_config.get("is_table", False):
            properties[field_key] = _build_table_schema(field_config)
        else:
            properties[field_key] = _schema_for_type(field_config.get("type", "str"))

        description = field_config.get("description") or field_config.get("alias")
        if description:
            properties[field_key]["description"] = description

    return {
        "type": "object",
        "properties": properties,
    }


def run_extract_v2_job(
    *,
    api_key: str,
    file_path: str,
    fields: Dict[str, Any],
    configuration_id: Optional[str] = None,
    tier: str = "agentic",
    parse_tier: Optional[str] = None,
    extraction_target: str = "per_doc",
    cite_sources: Optional[bool] = None,
    confidence_scores: Optional[bool] = True,
    project_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    poll_interval_seconds: float = 2.0,
    timeout_seconds: float = 1800.0,
    logger: Optional[logging.Logger] = None,
) -> LlamaCloudExtractionResult:
    """Upload a file, run an Extract v2 job, and return normalized output.

    This follows the LlamaCloud UI's generated Python snippet: upload the file,
    then call ``client.extract.run(...)`` with either a saved
    ``configuration_id`` or an inline ``configuration``. The SDK handles polling
    and returns the completed job.
    """
    client = LlamaCloud(api_key=api_key)

    request_scope = _optional_scope(
        project_id=project_id,
        organization_id=organization_id,
    )
    file_obj = client.files.create(
        file=file_path,
        purpose="extract",
        **request_scope,
    )

    extract_kwargs: Dict[str, Any] = {
        "file_input": file_obj.id,
        **request_scope,
    }
    if configuration_id:
        extract_kwargs["configuration_id"] = configuration_id
    else:
        extract_kwargs["configuration"] = build_extraction_configuration(
            fields,
            tier=tier,
            parse_tier=parse_tier,
            extraction_target=extraction_target,
            cite_sources=cite_sources,
            confidence_scores=confidence_scores,
        )

    job = client.extract.run(
        **extract_kwargs,
        polling_interval=poll_interval_seconds,
        polling_timeout=timeout_seconds,
    )

    if job.status != "COMPLETED":
        error_message = getattr(job, "error_message", None) or getattr(job, "error", None)
        raise TaskError(f"LlamaCloud extraction job {job.id} ended with status {job.status}: {error_message}")

    metadata: Dict[str, Any] = {}
    try:
        detailed_job = client.extract.get(
            job.id,
            expand=["extract_metadata"],
            **request_scope,
        )
        metadata = getattr(detailed_job, "extract_metadata", {}) or {}
    except Exception as exc:  # pragma: no cover - metadata is best-effort.
        if logger:
            logger.warning("Failed to fetch LlamaCloud extraction metadata for %s: %s", job.id, exc)

    return LlamaCloudExtractionResult(
        data=getattr(job, "extract_result", {}) or {},
        extraction_metadata=metadata,
        job_id=job.id,
        status=job.status,
    )


def _optional_scope(
    *,
    project_id: Optional[str],
    organization_id: Optional[str],
) -> Dict[str, Any]:
    scope: Dict[str, Any] = {}
    if project_id:
        scope["project_id"] = project_id
    if organization_id:
        scope["organization_id"] = organization_id
    return scope


def _build_table_schema(field_config: Dict[str, Any]) -> Dict[str, Any]:
    item_properties: Dict[str, Any] = {}

    for item_key, item_config in field_config.get("item_fields", {}).items():
        if not isinstance(item_config, dict):
            continue
        item_properties[item_key] = _schema_for_type(item_config.get("type", "str"))
        description = item_config.get("description") or item_config.get("alias")
        if description:
            item_properties[item_key]["description"] = description

    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": item_properties,
        },
    }


def _schema_for_type(type_str: str) -> Dict[str, Any]:
    clean_type = _unwrap_optional(type_str.strip())

    if clean_type.startswith("List[") and clean_type.endswith("]"):
        inner_type = clean_type[5:-1].strip()
        return {
            "type": "array",
            "items": _schema_for_type(inner_type),
        }

    if clean_type.startswith("Dict[") or clean_type == "dict":
        return {"type": "object"}

    type_mapping = {
        "str": "string",
        "float": "number",
        "Decimal": "number",
        "int": "integer",
        "bool": "boolean",
        "Any": "string",
    }
    return {"type": type_mapping.get(clean_type, "string")}


def _unwrap_optional(type_str: str) -> str:
    clean_type = type_str
    while clean_type.startswith("Optional[") and clean_type.endswith("]"):
        clean_type = clean_type[9:-1].strip()
    return clean_type


def metadata_candidates(metadata: Dict[str, Any], field_key: str, alias: str) -> list[Any]:
    """Return likely metadata objects for a field from supported provider shapes."""
    candidates: list[Any] = []
    names = {field_key, alias}

    field_metadata = metadata.get("field_metadata")
    if isinstance(field_metadata, dict):
        document_metadata = field_metadata.get("document_metadata")
        if isinstance(document_metadata, dict):
            _extend_named_metadata(candidates, document_metadata, names)

    document_metadata = metadata.get("document_metadata")
    if isinstance(document_metadata, dict):
        _extend_named_metadata(candidates, document_metadata, names)

    for container_key in ("fields", "field_metadata", "field_confidences", "confidence", "confidences"):
        container = metadata.get(container_key)
        if isinstance(container, dict):
            _extend_named_metadata(candidates, container, names)
        elif isinstance(container, list):
            for item in container:
                if not isinstance(item, dict):
                    continue
                if item.get("field_key") == field_key or item.get("name") in names or item.get("field_name") in names:
                    candidates.append(item)
    return candidates


def extract_numeric_confidence(metadata: Dict[str, Any], field_key: str, alias: str) -> float | None:
    """Extract numeric confidence, preserving NULL when confidence is absent."""
    for candidate in metadata_candidates(metadata, field_key, alias):
        raw_value = candidate
        if isinstance(candidate, dict):
            for key in ("confidence", "confidence_score", "score", "confidence_value"):
                if key in candidate:
                    raw_value = candidate[key]
                    break
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        if isinstance(raw_value, str):
            try:
                return float(raw_value)
            except ValueError:
                continue
    return None


def extract_confidence_label(metadata: Dict[str, Any], field_key: str, alias: str) -> str | None:
    """Extract a textual confidence label when provider metadata includes one."""
    for candidate in metadata_candidates(metadata, field_key, alias):
        if isinstance(candidate, dict):
            for key in ("confidence_label", "label", "confidence_level", "level"):
                value = candidate.get(key)
                if isinstance(value, str):
                    return value
        elif isinstance(candidate, str):
            return candidate
    return None


def extract_field_source(metadata: Dict[str, Any], field_key: str, alias: str) -> Dict[str, Any]:
    """Extract field citation/source metadata when present."""
    for candidate in metadata_candidates(metadata, field_key, alias):
        if isinstance(candidate, dict):
            source = candidate.get("source") or candidate.get("citation") or candidate.get("citations")
            if source is not None:
                return {"provider_source": source}
    return {}


def _extend_named_metadata(candidates: list[Any], container: Dict[str, Any], names: set[str]) -> None:
    for key in names:
        if key in container:
            candidates.append(container[key])
