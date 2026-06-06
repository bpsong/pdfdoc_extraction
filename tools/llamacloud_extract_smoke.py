"""Manual smoke and workflow fit check for LlamaCloud Extract v2.

This script is intentionally not part of the automated test suite. Use it after
configuring LlamaCloud UI access to verify that the SDK can upload and extract a
known local document, then check whether the returned JSON fits the configured
workflow field keys, optional aliases, and types.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ConfigDict, Field, ValidationError, create_model
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from standard_step.extraction.extract_pdf import _parse_field_type
from standard_step.extraction.llama_cloud_v2 import run_extract_v2_job


def main() -> int:
    """Run a one-file LlamaCloud Extract v2 smoke check."""
    parser = argparse.ArgumentParser(description="Run a manual LlamaCloud Extract v2 smoke check.")
    parser.add_argument(
        "--config",
        default="dev_config.yaml",
        help="Path to YAML config. Defaults to dev_config.yaml.",
    )
    parser.add_argument(
        "--task",
        default="extract_document_data",
        help="Extraction task name in the YAML config.",
    )
    parser.add_argument(
        "--file",
        default="sample_invoice.pdf",
        help="PDF file to extract. Defaults to sample_invoice.pdf.",
    )
    parser.add_argument(
        "--configuration-id",
        default=None,
        help="Override saved LlamaCloud Extract v2 configuration ID.",
    )
    parser.add_argument(
        "--output-dir",
        default="test/data/llamacloud_smoke",
        help="Directory for raw JSON, normalized JSON, and fit report.",
    )
    parser.add_argument(
        "--raw-json",
        default=None,
        help="Skip cloud call and validate an existing raw extract_result JSON file.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    file_path = Path(args.file)
    output_dir = Path(args.output_dir)

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    task_params = _task_params(config, args.task)

    if args.raw_json:
        raw_data = json.loads(Path(args.raw_json).read_text(encoding="utf-8"))
    else:
        api_key = os.getenv("LLAMA_CLOUD_API_KEY") or task_params.get("api_key")
        if not api_key:
            raise SystemExit("Missing LlamaCloud API key. Set LLAMA_CLOUD_API_KEY or task params api_key.")

        if not file_path.exists():
            raise SystemExit(f"File not found: {file_path}")

        result = run_extract_v2_job(
            api_key=api_key,
            file_path=str(file_path),
            fields=task_params.get("fields", {}),
            configuration_id=args.configuration_id or task_params.get("configuration_id"),
            tier=task_params.get("tier", "agentic"),
            parse_tier=task_params.get("parse_tier"),
            extraction_target=task_params.get("extraction_target", "per_doc"),
            cite_sources=task_params.get("cite_sources"),
            project_id=task_params.get("project_id"),
            organization_id=task_params.get("organization_id"),
            poll_interval_seconds=float(task_params.get("poll_interval_seconds", 2.0)),
            timeout_seconds=float(task_params.get("timeout_seconds", 1800.0)),
        )
        raw_data = result.data

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw_extract_result.json"
    normalized_path = output_dir / "workflow_normalized_data.json"
    report_path = output_dir / "workflow_fit_report.json"

    fit_report = check_workflow_fit(raw_data, task_params.get("fields", {}))
    _write_json(raw_path, raw_data)
    _write_json(normalized_path, fit_report["normalized_data"])
    _write_json(report_path, fit_report)

    print("LlamaCloud Extract v2 smoke check complete.")
    print(f"Raw extract JSON: {raw_path}")
    print(f"Workflow-normalized JSON: {normalized_path}")
    print(f"Fit report: {report_path}")

    if fit_report["fits_workflow"]:
        print("Workflow fit: PASS")
        print(json.dumps(fit_report["normalized_data"], indent=2, ensure_ascii=False))
        return 0

    print("Workflow fit: FAIL")
    print(json.dumps(fit_report, indent=2, ensure_ascii=False))
    return 1


def check_workflow_fit(raw_data: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, Any]:
    """Validate raw LlamaCloud JSON against configured workflow fields.

    Args:
        raw_data: Raw ``extract_result`` dictionary returned by LlamaCloud.
        fields: Extraction fields mapping from config.

    Returns:
        Report with missing workflow fields, extra raw keys, validation errors, and
        normalized data keyed by workflow field names.
    """
    if not isinstance(raw_data, dict):
        return {
            "fits_workflow": False,
            "missing_fields": [],
            "extra_keys": [],
            "extra_aliases": [],
            "key_matches": {},
            "validation_errors": ["Raw extract result is not a JSON object."],
            "normalized_data": {},
        }

    accepted_keys = set()
    missing_fields = []
    key_matches = {}

    for field_name, field_config in fields.items():
        if not isinstance(field_config, dict):
            continue

        alias = field_config.get("alias", field_name)
        accepted_keys.add(field_name)
        accepted_keys.add(alias)

        if alias in raw_data:
            key_matches[field_name] = {"matched_key": alias, "matched_by": "alias"}
        elif field_name in raw_data:
            key_matches[field_name] = {"matched_key": field_name, "matched_by": "field_name"}
        else:
            missing_fields.append(
                {
                    "field": field_name,
                    "alias": alias,
                    "accepted_keys": [field_name, alias],
                }
            )

    extra_keys = sorted(key for key in raw_data if key not in accepted_keys)

    processed_data = _preprocess_lists(raw_data, fields)
    validation_errors: List[str] = []
    normalized_data: Dict[str, Any] = {}

    try:
        dynamic_model = _build_dynamic_model(fields)
        normalized_data = dynamic_model(**processed_data).model_dump()
    except ValidationError as exc:
        validation_errors = [
            f"{'.'.join(str(part) for part in error.get('loc', []))}: {error.get('msg')}"
            for error in exc.errors()
        ]

    return {
        "fits_workflow": not missing_fields and not validation_errors,
        "missing_fields": missing_fields,
        "extra_keys": extra_keys,
        # Backwards-compatible report key for previously saved smoke reports.
        "extra_aliases": extra_keys,
        "key_matches": key_matches,
        "validation_errors": validation_errors,
        "normalized_data": normalized_data,
    }


def _preprocess_lists(raw_data: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, Any]:
    processed_data = raw_data.copy()
    for field_name, field_config in fields.items():
        if not isinstance(field_config, dict):
            continue

        alias = field_config.get("alias")
        source_key = alias if alias in processed_data else None
        if source_key is None and field_name in processed_data:
            source_key = field_name
        if source_key and isinstance(processed_data[source_key], list):
            field_type = field_config.get("type", "")
            if "List[str]" in field_type or "Optional[List[str]]" in field_type:
                processed_data[source_key] = [item for item in processed_data[source_key] if item is not None]
    return processed_data


def _build_dynamic_model(fields: Dict[str, Any]):
    model_fields = {}
    for field_name, field_config in fields.items():
        if not isinstance(field_config, dict):
            continue

        field_type_str = field_config.get("type", "Any")
        field_type = _parse_field_type(field_type_str)
        alias = field_config.get("alias", field_name)
        model_fields[field_name] = (field_type, Field(alias=alias))

    return create_model(
        "WorkflowFitModel",
        __config__=ConfigDict(populate_by_name=True, extra="ignore"),
        **model_fields,
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _task_params(config: Dict[str, Any], task_name: str) -> Dict[str, Any]:
    tasks = config.get("tasks", {})
    if not isinstance(tasks, dict) or task_name not in tasks:
        raise SystemExit(f"Task not found in config: {task_name}")

    params = tasks[task_name].get("params", {})
    if not isinstance(params, dict):
        raise SystemExit(f"Task params must be a mapping: {task_name}")
    return params


if __name__ == "__main__":
    raise SystemExit(main())
