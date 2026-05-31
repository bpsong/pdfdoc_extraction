from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from modules.services.config_validation_service import ConfigValidationService
from test.helpers_sqlite import TempConfig


BCRYPT_HASH = "$2b$12$eImiTXuWVxfM37uY4JANj.QlsWu1PErG3e1hYzWdG2ZHB5QoLGj7W"


def _base_config(tmp_path: Path) -> dict[str, Any]:
    upload_dir = tmp_path / "uploads"
    watch_dir = tmp_path / "watch"
    schema_dir = tmp_path / "schemas"
    upload_dir.mkdir(exist_ok=True)
    watch_dir.mkdir(exist_ok=True)
    schema_dir.mkdir(exist_ok=True)
    return {
        "web": {
            "upload_dir": str(upload_dir),
            "secret_key": "test-secret",
        },
        "watch_folder": {
            "dir": str(watch_dir),
            "processing_dir": str(tmp_path / "processing"),
        },
        "authentication": {
            "username": "admin",
            "password_hash": BCRYPT_HASH,
        },
        "schema": {"directories": [str(schema_dir)]},
        "tasks": {
            "extract": {
                "module": "custom_step.extraction.fake_extract",
                "class": "FakeExtractTask",
                "params": {
                    "api_key": "llx-test-key",
                    "fields": {
                        "invoice_number": {
                            "alias": "Invoice number",
                            "type": "str",
                        }
                    },
                },
                "on_error": "stop",
            }
        },
        "pipeline": ["extract"],
    }


def _service(tmp_path: Path, values: dict[str, Any] | None = None) -> ConfigValidationService:
    config = TempConfig(tmp_path / "app.sqlite3", values or _base_config(tmp_path))
    return ConfigValidationService(config)


def _codes(result: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in result["findings"]}


def test_validate_payload_accepts_valid_config(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.validate_payload({"config": _base_config(tmp_path)})

    assert result["valid"] is True
    assert result["summary"]["errors"] == 0
    assert result["normalized"]["pipeline"] == ["extract"]


def test_validate_payload_reports_review_gate_param_errors(tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    config["tasks"]["review"] = {
        "module": "standard_step.review.review_gate",
        "class": "ReviewGateTask",
        "params": {"confidence_threshold": 1.5, "resume_policy": "restart"},
        "on_error": "stop",
    }
    config["pipeline"] = ["extract", "review"]
    service = _service(tmp_path, config)

    result = service.validate_payload({"config": config})

    assert result["valid"] is False
    assert "review-gate-invalid-confidence-threshold" in _codes(result)
    assert "review-gate-invalid-resume-policy" in _codes(result)


def test_validate_pipeline_reports_split_param_and_fanout_warnings(tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    config["tasks"]["split"] = {
        "module": "standard_step.split.llamacloud_split",
        "class": "LlamaCloudSplitTask",
        "params": {"enabled": True, "allow_uncategorized": "drop"},
        "on_error": "stop",
    }
    config["pipeline"] = ["extract", "split"]
    service = _service(tmp_path, config)

    result = service.validate_pipeline({"config": config})

    assert result["valid"] is False
    assert "split-missing-categories-or-configuration" in _codes(result)
    assert "split-invalid-allow-uncategorized" in _codes(result)
    assert "split-final-pipeline-step" in _codes(result)


def test_validate_payload_accepts_yaml_payload(tmp_path: Path) -> None:
    service = _service(tmp_path)
    config = _base_config(tmp_path)

    result = service.validate_payload({"yaml": yaml.safe_dump(config)})

    assert result["valid"] is True
    assert result["source"] == "payload"


def test_validate_all_schemas_reports_invalid_schema_files(tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    schema_dir = Path(config["schema"]["directories"][0])
    (schema_dir / "invoice.yaml").write_text(
        yaml.safe_dump({"fields": {"invoice_number": {"type": "string"}}}),
        encoding="utf-8",
    )
    (schema_dir / "bad.yaml").write_text(
        yaml.safe_dump({"fields": {"amount": {"type": "money"}}}),
        encoding="utf-8",
    )
    service = _service(tmp_path, config)

    result = service.validate_all_schemas()

    assert result["valid"] is False
    assert result["findings"] == [
        {
            "severity": "error",
            "path": "schemas.bad.yaml.amount.type",
            "message": "Unsupported field type: money.",
            "code": "schema-invalid",
            "details": {},
        }
    ]
