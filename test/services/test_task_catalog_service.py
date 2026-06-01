from __future__ import annotations

from pathlib import Path

from modules.services.task_catalog_service import TaskCatalogService
from test.helpers_sqlite import TempConfig


def test_task_catalog_discovers_standard_tasks_and_configured_metadata(tmp_path: Path) -> None:
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["split_documents", "extract_document_data", "review_gate", "store_json"],
            "tasks": {
                "split_documents": {
                    "module": "standard_step.split.llamacloud_split",
                    "class": "LlamaCloudSplitTask",
                    "params": {"enabled": True, "api_key": "secret-key"},
                    "on_error": "stop",
                },
                "extract_document_data": {
                    "module": "standard_step.extraction.extract_pdf_v2",
                    "class": "ExtractPdfV2Task",
                    "params": {"api_key": "llx-secret", "fields": {"supplier": {"type": "str"}}},
                    "on_error": "stop",
                },
                "review_gate": {
                    "module": "standard_step.review.review_gate",
                    "class": "ReviewGateTask",
                    "params": {"confidence_threshold": 0.8},
                    "on_error": "stop",
                },
                "store_json": {
                    "module": "standard_step.storage.store_metadata_as_json_v2",
                    "class": "StoreMetadataAsJsonV2",
                    "params": {"data_dir": "data", "filename": "{supplier}"},
                    "on_error": "continue",
                },
            },
        },
    )

    catalog = TaskCatalogService(config).catalog()
    tasks = {task["id"]: task for task in catalog["tasks"]}

    extract = tasks["standard_step.extraction.extract_pdf_v2.ExtractPdfV2Task"]
    split = tasks["standard_step.split.llamacloud_split.LlamaCloudSplitTask"]
    review = tasks["standard_step.review.review_gate.ReviewGateTask"]

    assert catalog["summary"]["configured"] >= 4
    assert extract["import_status"] == "ok"
    assert extract["is_configured"] is True
    assert extract["configured_keys"] == ["extract_document_data"]
    assert extract["configured_params"]["extract_document_data"]["api_key"] == "***REDACTED***"
    assert split["pipeline_positions"] == [0]
    assert "split_children" in split["expected_outputs"]
    assert "review_item_id" in review["expected_outputs"]


def test_task_catalog_reports_configured_import_failure(tmp_path: Path) -> None:
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {
            "pipeline": ["missing"],
            "tasks": {
                "missing": {
                    "module": "missing_package.missing_module",
                    "class": "MissingTask",
                    "params": {},
                }
            },
        },
    )

    catalog = TaskCatalogService(config).catalog()
    missing = next(task for task in catalog["tasks"] if task["class_name"] == "MissingTask")

    assert missing["is_configured"] is True
    assert missing["import_status"] == "failed"
    assert "No module named" in missing["import_error"]
    assert catalog["summary"]["failed"] >= 1
