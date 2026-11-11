"""Provider-neutral business reports for pinned gate and review snapshots."""

from __future__ import annotations

from collections import Counter
import hashlib
from typing import Any, Mapping

from modules.db.connection import json_dumps
from modules.services.business_validation import evaluate_business_rules
from modules.services.business_validation_schema import require_business_rule_capability


def snapshot_hash(value: Any) -> str:
    """Fingerprint JSON state without exposing values in audit summaries."""
    return hashlib.sha256(json_dumps(value).encode("utf-8")).hexdigest()


def build_business_report(
    values: Mapping[str, Any], schema: Mapping[str, Any], *,
    schema_version_id: str, schema_hash: str, format_version: int,
    document_id: str, extraction_result_id: str | None,
    review_revision: str | None = None, source_artifact_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Evaluate current values with pinned rules; evaluator failures block release."""
    if "business_validation" not in schema:
        return None
    require_business_rule_capability(schema, format_version)
    if not schema_version_id:
        raise ValueError("Business rules require an exact published review form.")
    try:
        result = evaluate_business_rules(values, schema["business_validation"]).to_dict()
        result["evaluation_status"] = "error" if any(
            check["status"] == "error" for check in result["checks"]
        ) else "completed"
    except (ValueError, TypeError, RuntimeError):
        # Do not surface exception text, which may contain document values.
        result = {
            "format_version": 1, "evaluation_status": "error",
            "has_blocking_findings": True, "requires_review": True,
            "checks": [{"rule_id": "evaluator", "validator": "evaluator",
                        "status": "error", "code": "evaluator_unavailable",
                        "severity": "blocking", "require_review": True,
                        "message": "Business validation could not be completed.", "field_paths": []}],
        }
    return {
        **result, "schema_version_id": schema_version_id, "schema_hash": schema_hash,
        "schema_format_version": format_version, "document_id": document_id,
        "extraction_result_id": extraction_result_id,
        "source_artifact_ids": source_artifact_ids or [],
        "review_revision": review_revision, "values_revision": snapshot_hash(values),
    }


def business_report_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Select audit-safe rule identities and outcome counts, excluding amounts/messages."""
    checks = report.get("checks", [])
    return {
        "schema_version_id": report.get("schema_version_id"),
        "schema_hash": report.get("schema_hash"),
        "values_revision": report.get("values_revision"),
        "counts": dict(Counter(check["status"] for check in checks)),
        "rules": sorted({check["rule_id"] for check in checks}),
        "validators": sorted({check["validator"] for check in checks}),
        "has_blocking_findings": report.get("has_blocking_findings"),
    }


def business_review_reasons(report: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Map business findings to gate reasons without putting values in reasons."""
    reasons = []
    highlights: set[str] = set()
    for check in report.get("checks", []):
        if check["status"] in {"passed", "skipped"}:
            continue
        if not (check["require_review"] or check["severity"] == "blocking" or check["status"] == "error"):
            continue
        fields = sorted({
            path.split("/")[1].replace("~1", "/").replace("~0", "~")
            for path in check["field_paths"] if path.startswith("/")
        })
        highlights.update(fields)
        reasons.append({"reason": "business_validation", "rule_id": check["rule_id"],
                        "validator": check["validator"], "code": check["code"],
                        "status": check["status"], "field_keys": fields})
    return reasons, sorted(highlights)
