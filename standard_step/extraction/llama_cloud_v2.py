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

    metadata: Dict[str, Any] = _to_plain_dict(getattr(job, "extract_metadata", None))
    try:
        detailed_job = client.extract.get(
            job.id,
            expand=["extract_metadata"],
            **request_scope,
        )
        metadata = _to_plain_dict(getattr(detailed_job, "extract_metadata", None)) or metadata
    except Exception as exc:  # pragma: no cover - metadata is best-effort.
        if logger:
            logger.warning("Failed to fetch LlamaCloud extraction metadata for %s: %s", job.id, exc)

    return LlamaCloudExtractionResult(
        data=getattr(job, "extract_result", {}) or {},
        extraction_metadata=metadata,
        job_id=job.id,
        status=job.status,
    )


def preflight_extract_v2_access(
    *,
    api_key: str,
    configuration_id: Optional[str] = None,
    project_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> None:
    """Validate LlamaCloud Extract credentials/configuration without extracting a file."""
    client = LlamaCloud(api_key=api_key)
    request_scope = _optional_scope(
        project_id=project_id,
        organization_id=organization_id,
    )
    try:
        if configuration_id:
            client.configurations.retrieve(configuration_id, **request_scope)
        else:
            client.projects.list(organization_id=organization_id)
    except Exception as exc:
        raise TaskError(humanize_extract_error(exc, configuration_id=configuration_id)) from exc


def humanize_extract_error(error: Any, *, configuration_id: Optional[str] = None) -> str:
    """Return an operator-friendly LlamaCloud Extract error message."""
    text = str(error)
    lowered = text.lower()
    if "invalid api key" in lowered or "401" in lowered:
        return (
            "LlamaCloud Extract authentication failed. Check the Extract task API key "
            "and LlamaCloud region, then re-ingest the source PDF."
        )
    if "configuration" in lowered and ("not found" in lowered or "404" in lowered):
        config_part = f" '{configuration_id}'" if configuration_id else ""
        return (
            f"LlamaCloud Extract configuration{config_part} was not found. "
            "Check the Extract task configuration_id, then re-ingest the source PDF."
        )
    if "cancelled" in lowered:
        return "LlamaCloud Extract job was cancelled before completion."
    if "timeout" in lowered or "timed out" in lowered:
        return "LlamaCloud Extract job timed out before completion."
    return f"LlamaCloud Extract failed: {text}"


def is_non_retryable_extract_error(error: Any) -> bool:
    """Return True for auth/config errors that should fail without retry loops."""
    text = str(error).lower()
    return (
        "invalid api key" in text
        or "401" in text
        or ("configuration" in text and ("not found" in text or "404" in text))
    )


def _to_plain_dict(value: Any) -> Dict[str, Any]:
    """Convert SDK metadata models into plain dictionaries for persistence."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "dict"):
        dumped = value.dict(exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return {}


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
        _extend_named_metadata(candidates, field_metadata, names)
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
    """Extract numeric confidence, preserving NULL when confidence is absent.

    For complex fields, LlamaCloud may return no top-level confidence while
    still returning confidence for nested object or array children. In that
    case the aggregate field confidence is the minimum nested confidence.
    """
    values: list[float] = []
    for candidate in metadata_candidates(metadata, field_key, alias):
        direct = _direct_numeric_confidence(candidate)
        if direct is not None:
            values.append(direct)

        nested = _nested_confidence_details(candidate)
        values.extend(
            float(item["confidence"])
            for item in nested.values()
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
        )
    if values:
        return min(values)
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


def extract_confidence_details(metadata: Dict[str, Any], field_key: str, alias: str) -> Dict[str, Any]:
    """Return structured confidence details for nested field display.

    The persisted top-level ``confidence`` column remains the review-gate source
    of truth. This detail payload is stored in ``source_json`` so the review UI
    can display object/array confidence without a schema migration.
    """
    nested_confidences: dict[str, dict[str, Any]] = {}
    aggregate_values: list[float] = []
    for candidate in metadata_candidates(metadata, field_key, alias):
        direct = _direct_numeric_confidence(candidate)
        if direct is not None:
            aggregate_values.append(direct)
        nested_confidences.update(_nested_confidence_details(candidate))

    aggregate_values.extend(
        float(item["confidence"])
        for item in nested_confidences.values()
        if isinstance(item.get("confidence"), (int, float))
    )
    details: Dict[str, Any] = {
        "aggregation": "minimum_nested_confidence",
    }
    if aggregate_values:
        details["confidence"] = min(aggregate_values)
        details["confidence_band"] = confidence_band(min(aggregate_values))
    if nested_confidences:
        details["nested_confidences"] = nested_confidences
    return details


def extract_field_source(metadata: Dict[str, Any], field_key: str, alias: str) -> Dict[str, Any]:
    """Extract field citation/source metadata when present."""
    source: Dict[str, Any] = {}
    for candidate in metadata_candidates(metadata, field_key, alias):
        if isinstance(candidate, dict):
            provider_source = candidate.get("source") or candidate.get("citation") or candidate.get("citations")
            if provider_source is not None:
                source["provider_source"] = provider_source
                break
    confidence_details = extract_confidence_details(metadata, field_key, alias)
    if confidence_details.get("nested_confidences"):
        source["confidence_details"] = confidence_details
    return source


def confidence_band(confidence: Any) -> str:
    """Map numeric confidence values to stable UI/review bands."""
    if confidence is None:
        return "missing"
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "missing"
    if value >= 0.9:
        return "high"
    if value >= 0.7:
        return "medium"
    return "low"


def _extend_named_metadata(candidates: list[Any], container: Dict[str, Any], names: set[str]) -> None:
    for key in names:
        if key in container:
            candidates.append(container[key])


def _direct_numeric_confidence(candidate: Any) -> float | None:
    raw_value = candidate
    if isinstance(candidate, dict):
        for key in ("confidence", "confidence_score", "score", "confidence_value"):
            if key in candidate:
                raw_value = candidate[key]
                break
        else:
            return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str):
        try:
            return float(raw_value)
        except ValueError:
            return None
    return None


def _nested_confidence_details(value: Any, prefix: str = "") -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for index, item in enumerate(value):
            details.update(_nested_confidence_details(item, _join_path(prefix, str(index))))
        return details

    if not isinstance(value, dict):
        return details

    direct = _direct_numeric_confidence(value)
    if direct is not None and prefix:
        item: dict[str, Any] = {
            "confidence": direct,
            "confidence_band": confidence_band(direct),
        }
        label = _direct_confidence_label(value)
        if label:
            item["confidence_label"] = label
        source = value.get("source") or value.get("citation") or value.get("citations")
        if source is not None:
            item["source"] = {"provider_source": source}
        details[prefix] = item
        return details

    metadata_keys = {
        "confidence",
        "confidence_score",
        "score",
        "confidence_value",
        "confidence_label",
        "label",
        "confidence_level",
        "level",
        "parsing_confidence",
        "extraction_confidence",
        "source",
        "citation",
        "citations",
        "bounding_boxes",
        "matching_text",
        "page",
        "page_dimensions",
        "row_metadata",
        "page_metadata",
    }
    for key, nested in value.items():
        if key in metadata_keys:
            continue
        details.update(_nested_confidence_details(nested, _join_path(prefix, str(key))))
    return details


def _direct_confidence_label(candidate: dict[str, Any]) -> str | None:
    for key in ("confidence_label", "label", "confidence_level", "level"):
        value = candidate.get(key)
        if isinstance(value, str):
            return value
    return None


def _join_path(prefix: str, part: str) -> str:
    return f"{prefix}.{part}" if prefix else part
