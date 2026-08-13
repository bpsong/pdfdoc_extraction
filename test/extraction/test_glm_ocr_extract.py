"""Tests for the configured local GLM-OCR extraction task."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from modules.db.connection import connect, json_loads
from modules.db.migrations import initialize_database
from modules.db.repositories import ExtractionRepository, TaskRunRepository
from modules.exceptions import TaskError
from modules.services.batch_service import BatchService
from standard_step.extraction.glm_ocr_adapter import (
    GlmOcrAdapterFinding,
    GlmOcrAdapterResult,
    GlmOcrCallRecord,
    GlmOcrConflict,
    GlmOcrModelNotFoundError,
    GlmOcrPdfError,
    GlmOcrResponseError,
    GlmOcrTimeoutError,
    GlmOcrUnavailableError,
)
from standard_step.extraction.glm_ocr_extract import GlmOcrExtractTask
from standard_step.extraction.structured_fields import FieldNormalizationFinding
from standard_step.storage.store_metadata_as_json import StoreMetadataAsJson
from test.helpers_sqlite import TempConfig


def _fields() -> dict:
    return {
        "invoice_number": {"alias": "Invoice number", "type": "str"},
        "summary": {
            "alias": "Summary",
            "type": "Dict[str, Any]",
            "object_fields": {
                "currency": {"alias": "Currency", "type": "str"},
                "tax": {"alias": "Tax", "type": "Optional[float]"},
            },
        },
        "items": {
            "alias": "Items",
            "type": "List[Any]",
            "is_table": True,
            "item_fields": {
                "description": {"alias": "Description", "type": "str"},
                "quantity": {"alias": "Quantity", "type": "int"},
            },
        },
        "optional_note": {"alias": "Optional note", "type": "Optional[str]"},
    }


def _params(**overrides) -> dict:
    params = {
        "ollama_host": "http://127.0.0.1:11434",
        "model": "glm-ocr:latest",
        "document_instructions": "Read the invoice labels.",
        "prompt_style": "detailed",
        "dpi": 216,
        "num_ctx": 8192,
        "num_predict": 2048,
        "timeout_seconds": 300,
        "fields": _fields(),
    }
    params.update(overrides)
    return params


def _persisted_context(tmp_path) -> tuple[TempConfig, dict, str]:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    config = TempConfig(tmp_path / "app.sqlite3", {})
    initialize_database(config)
    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename=pdf_path.name,
        )
        task_run = TaskRunRepository(conn).create_started(
            batch_id=created["batch"]["id"],
            document_id=created["document"]["id"],
            task_key="glm_extract",
            task_index=0,
            module_name="standard_step.extraction.glm_ocr_extract",
            class_name="GlmOcrExtractTask",
        )
    context = {
        "id": created["document"]["id"],
        "batch_id": created["batch"]["id"],
        "document_id": created["document"]["id"],
        "task_run_id": task_run["id"],
        "current_task_key": "glm_extract",
        "current_task_index": 0,
        "pipeline_template_id": "template-1",
        "pipeline_version_id": "version-1",
        "file_path": str(pdf_path),
        "data": {"existing": "preserved"},
        "metadata": {"existing": {"kept": True}},
        "review_flags": ["legacy_flag"],
    }
    return config, context, created["document"]["id"]


def _adapter_result() -> GlmOcrAdapterResult:
    return GlmOcrAdapterResult(
        data={
            "invoice_number": "INV-7",
            "summary": {"currency": "SGD", "tax": None},
            "items": [{"description": "Paper", "quantity": 2}],
        },
        page_count=2,
        field_pages={
            "invoice_number": [1],
            "summary": [1, 2],
            "items": [2],
            "optional_note": [],
        },
        calls=[
            GlmOcrCallRecord(
                page_number=1,
                call_type="scalar_object",
                duration_seconds=1.23456789,
                completion_reason="stop",
                prompt_hash="prompt-hash",
                schema_hash="schema-hash",
            )
        ],
        findings=[
            GlmOcrAdapterFinding(
                path="optional_note",
                code="schema_type",
                message="Structured response did not satisfy the configured type constraint",
                page_number=2,
                call_type="scalar_object",
            )
        ],
        normalization_findings=[
            FieldNormalizationFinding(
                path="items.0.quantity",
                code="invalid_integer",
                message="Value could not be converted to an integer",
            )
        ],
        conflicts=[
            GlmOcrConflict(
                path="summary.currency",
                retained_page=1,
                conflicting_page=2,
            )
        ],
    )


def test_task_success_preserves_context_merges_flags_and_persists_safe_rows(
    tmp_path, monkeypatch
) -> None:
    config, context, document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params())
    fake_adapter = SimpleNamespace(extract=lambda *args, **kwargs: _adapter_result())
    monkeypatch.setattr(task, "_build_adapter", lambda: fake_adapter)

    task.on_start(context)
    returned = task.run(context)

    assert returned is context
    assert context["data"] == {
        "existing": "preserved",
        "invoice_number": "INV-7",
        "summary": {"currency": "SGD", "tax": None},
        "items": [{"description": "Paper", "quantity": 2}],
        "optional_note": None,
    }
    assert context["pipeline_template_id"] == "template-1"
    assert context["pipeline_version_id"] == "version-1"
    assert context["metadata"]["existing"] == {"kept": True}
    glm_metadata = context["metadata"]["glm_ocr"]
    assert glm_metadata["provider"] == "glm_ocr_ollama"
    assert glm_metadata["host_classification"] == "loopback"
    assert glm_metadata["calls"][0]["prompt_hash"] == "prompt-hash"
    assert "Read the invoice labels" not in str(glm_metadata)
    assert context["review_flags"][0] == "legacy_flag"
    assert context["review_flags"][1] == {
        "flag": "glm_ocr_unscored",
        "reason": "unscored_extraction",
        "field_keys": list(_fields()),
    }

    with connect(config) as conn:
        repository = ExtractionRepository(conn)
        result = repository.get_latest_result(document_id)
        rows = {item["field_key"]: item for item in repository.get_fields(document_id)}
        artifact_count = conn.execute(
            "SELECT COUNT(*) FROM document_files WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]

    assert result is not None and result["provider"] == "glm_ocr_ollama"
    assert result["provider_job_id"] is None
    assert context["extraction_result_id"] == result["id"]
    assert json_loads(result["data_json"])["optional_note"] is None
    assert set(rows) == set(_fields())
    assert json_loads(rows["items"]["final_value_json"]) == [
        {"description": "Paper", "quantity": 2}
    ]
    assert rows["optional_note"]["confidence"] is None
    assert rows["optional_note"]["confidence_label"] is None
    assert json_loads(rows["optional_note"]["extracted_value_json"]) is None
    assert json_loads(rows["optional_note"]["final_value_json"]) is None
    assert rows["optional_note"]["requires_review"] == 0
    assert rows["optional_note"]["review_status"] == "not_required"
    optional_source = json_loads(rows["optional_note"]["source_json"])
    assert optional_source["pages"] == []
    assert optional_source["validation_findings"][0]["code"] == "schema_type"
    assert "INV-7" not in rows["optional_note"]["source_json"]
    persisted_metadata = json_loads(result["metadata_json"])
    for runtime_parameter in (
        "ollama_host",
        "document_instructions",
        "dpi",
        "num_ctx",
        "num_predict",
        "timeout_seconds",
        "fields",
        "api_key",
    ):
        assert runtime_parameter not in persisted_metadata
        assert runtime_parameter not in context
    assert "Read the invoice labels" not in result["metadata_json"]
    assert artifact_count == 1  # The ingestion source only; extraction creates none.


def test_task_passes_compact_prompt_style_to_adapter(tmp_path, monkeypatch) -> None:
    config, context, _document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params(prompt_style="compact"))
    calls: list[dict[str, Any]] = []

    def extract(*args: Any, **kwargs: Any) -> GlmOcrAdapterResult:
        calls.append(kwargs)
        return _adapter_result()

    monkeypatch.setattr(task, "_build_adapter", lambda: SimpleNamespace(extract=extract))

    task.on_start(context)
    task.run(context)

    assert calls[0]["prompt_style"] == "compact"


def test_task_builds_document_resolver_from_versioned_parameters(
    tmp_path,
) -> None:
    config, context, _document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(
        config,
        **_params(
            resolution_mode="document",
            resolver_model="qwen3.5:9b-q4_K_M",
            resolver_max_dimension=1024,
            resolver_num_ctx=8192,
            resolver_num_predict=1536,
            resolver_max_attempts=3,
        ),
    )

    task.on_start(context)
    adapter = task._build_adapter()

    assert adapter.resolution_mode == "document"
    assert adapter.resolver_model == "qwen3.5:9b-q4_K_M"
    assert adapter.resolver_max_dimension == 1024
    assert adapter.resolver_num_ctx == 8192
    assert adapter.resolver_num_predict == 1536
    assert adapter.resolver_max_attempts == 3


def test_document_resolution_metadata_excludes_prompts_values_and_runtime_limits(
    tmp_path,
    monkeypatch,
) -> None:
    config, context, _document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(
        config,
        **_params(
            resolution_mode="document",
            resolver_model="qwen3.5:9b-q4_K_M",
            resolver_num_ctx=8192,
            resolver_num_predict=1536,
            resolver_max_attempts=2,
        ),
    )
    monkeypatch.setattr(
        task,
        "_build_adapter",
        lambda: SimpleNamespace(extract=lambda *args, **kwargs: _adapter_result()),
    )

    task.on_start(context)
    task.run(context)

    metadata = context["metadata"]["glm_ocr"]
    assert metadata["resolution_mode"] == "document"
    assert metadata["resolver_model"] == "qwen3.5:9b-q4_K_M"
    assert metadata["call_strategy"] == (
        "per_page_evidence_then_bounded_field_resolution"
    )
    serialized = str(metadata)
    for excluded in (
        "resolver_num_ctx",
        "resolver_num_predict",
        "resolver_max_attempts",
        "resolver_max_dimension",
        "Read the invoice labels",
        "INV-7",
        "Paper",
    ):
        assert excluded not in serialized


def test_task_keeps_legacy_page_merge_when_resolution_params_are_absent(
    tmp_path,
) -> None:
    config, context, _document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params())

    task.on_start(context)
    adapter = task._build_adapter()

    assert adapter.resolution_mode == "page_merge"
    assert adapter.resolver_model == ""


def test_task_rejects_unknown_prompt_style(tmp_path) -> None:
    config, context, _document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params(prompt_style="raw"))

    with pytest.raises(TaskError, match="prompt_style is invalid"):
        task.on_start(context)


def test_task_rejects_verbatim_prompt_without_instructions(tmp_path) -> None:
    config, context, _document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(
        config,
        **_params(prompt_style="verbatim", document_instructions=""),
    )

    with pytest.raises(TaskError, match="requires document instructions"):
        task.on_start(context)


def test_task_dict_flags_are_extended_without_overwriting_existing_entries(
    tmp_path, monkeypatch
) -> None:
    config, context, _ = _persisted_context(tmp_path)
    context["review_flags"] = {"legacy": True}
    task = GlmOcrExtractTask(config, **_params())
    monkeypatch.setattr(
        task,
        "_build_adapter",
        lambda: SimpleNamespace(extract=lambda *args, **kwargs: _adapter_result()),
    )

    task.on_start(context)
    task.run(context)

    assert context["review_flags"]["legacy"] is True
    assert context["review_flags"]["glm_ocr_unscored"] == {
        "reason": "unscored_extraction",
        "field_keys": list(_fields()),
    }


def test_task_without_review_gate_leaves_persisted_review_state_clear(
    tmp_path, monkeypatch
) -> None:
    config, context, document_id = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params())
    monkeypatch.setattr(
        task,
        "_build_adapter",
        lambda: SimpleNamespace(extract=lambda *args, **kwargs: _adapter_result()),
    )

    task.on_start(context)
    returned = task.run(context)

    with connect(config) as conn:
        rows = ExtractionRepository(conn).get_fields(document_id)
    assert returned["data"]["invoice_number"] == "INV-7"
    assert "pipeline_state" not in returned
    assert "review_required" not in returned
    assert all(row["requires_review"] == 0 for row in rows)
    assert all(row["review_status"] == "not_required" for row in rows)


def test_gate_free_glm_context_continues_directly_to_storage(
    tmp_path, monkeypatch
) -> None:
    config, context, document_id = _persisted_context(tmp_path)
    extract_task = GlmOcrExtractTask(config, **_params())
    monkeypatch.setattr(
        extract_task,
        "_build_adapter",
        lambda: SimpleNamespace(extract=lambda *args, **kwargs: _adapter_result()),
    )
    extract_task.on_start(context)
    extract_task.run(context)

    storage_task = StoreMetadataAsJson(
        config,
        data_dir=str(tmp_path / "output"),
        filename="{invoice_number}.json",
        extraction={"fields": _fields()},
    )
    storage_task.on_start(context)
    stored = storage_task.run(context)

    assert stored["output_path"].endswith("INV-7.json")
    assert (tmp_path / "output" / "INV-7.json").is_file()
    with connect(config) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM review_items WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM document_files WHERE document_id = ? "
            "AND file_type = 'export_json'",
            (document_id,),
        ).fetchone()[0] == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ollama_host": "ftp://localhost:11434"}, "HTTP"),
        ({"ollama_host": "http://user:pass@localhost:11434"}, "credentials"),
        ({"ollama_host": "http://localhost:11434/api"}, "base URL"),
        ({"model": ""}, "model"),
        ({"dpi": 0}, "dpi"),
        ({"num_ctx": True}, "num_ctx"),
        ({"num_predict": -1}, "num_predict"),
        ({"resolution_mode": "unknown"}, "resolution_mode"),
        (
            {"resolution_mode": "document", "resolver_model": ""},
            "resolver_model",
        ),
        ({"resolver_num_ctx": 0}, "resolver_num_ctx"),
        ({"resolver_max_dimension": 128}, "resolver_max_dimension"),
        ({"resolver_num_predict": False}, "resolver_num_predict"),
        ({"resolver_max_attempts": 6}, "resolver_max_attempts"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"api_key": "not-used"}, "LlamaCloud-only"),
        (
            {
                "fields": {
                    "first": _fields()["items"],
                    "second": {**_fields()["items"], "alias": "Other"},
                }
            },
            "field configuration",
        ),
    ],
)
def test_task_validation_rejects_invalid_provider_configuration(
    tmp_path, overrides, message
) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    config = TempConfig(tmp_path / "app.sqlite3", {})
    context: dict[str, Any] = {
        "file_path": str(pdf_path),
        "current_task_key": "glm_extract",
    }
    task = GlmOcrExtractTask(config, **_params(**overrides))

    with pytest.raises(TaskError, match=message):
        task.on_start(context)
    assert context["error_step"] == "glm_extract"
    assert context["fatal_failure"]["provider"] == "glm_ocr_ollama"


def test_task_validation_rejects_missing_file_and_field_limit(tmp_path) -> None:
    config = TempConfig(tmp_path / "app.sqlite3", {})
    task = GlmOcrExtractTask(config, **_params())
    with pytest.raises(TaskError, match="source PDF"):
        task.on_start({"file_path": str(tmp_path / "missing.pdf")})

    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    too_many = {
        f"field_{index}": {"alias": f"Field {index}", "type": "str"}
        for index in range(101)
    }
    task = GlmOcrExtractTask(config, **_params(fields=too_many))
    with pytest.raises(TaskError, match="at most 100"):
        task.on_start({"file_path": str(pdf_path)})


@pytest.mark.parametrize(
    ("provider_error", "failure_type", "message"),
    [
        (GlmOcrUnavailableError("secret host"), "glm_ocr_unavailable", "unavailable"),
        (GlmOcrModelNotFoundError("secret model"), "glm_ocr_model_missing", "not installed"),
        (GlmOcrTimeoutError("secret timeout"), "glm_ocr_timeout", "timed out"),
        (GlmOcrPdfError("secret pdf"), "glm_ocr_pdf_error", "source PDF"),
        (GlmOcrResponseError("secret raw response"), "glm_ocr_protocol_error", "structured response"),
    ],
)
def test_expected_provider_failures_are_redacted_and_registered(
    tmp_path, monkeypatch, provider_error, failure_type, message
) -> None:
    config, context, _ = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params())

    def fail(*args, **kwargs):
        raise provider_error

    monkeypatch.setattr(
        task,
        "_build_adapter",
        lambda: SimpleNamespace(extract=fail),
    )
    task.on_start(context)

    with pytest.raises(TaskError, match=message):
        task.run(context)
    assert context["error_step"] == "glm_extract"
    assert context["fatal_failure"]["failure_type"] == failure_type
    assert "secret" not in str(context["fatal_failure"])
    assert "secret" not in str(context["error"])


def test_unexpected_failure_does_not_expose_exception_text(tmp_path, monkeypatch) -> None:
    config, context, _ = _persisted_context(tmp_path)
    task = GlmOcrExtractTask(config, **_params())

    def fail(*args, **kwargs):
        raise RuntimeError("raw prompt and extracted customer value")

    monkeypatch.setattr(
        task,
        "_build_adapter",
        lambda: SimpleNamespace(extract=fail),
    )
    task.on_start(context)

    with pytest.raises(TaskError, match="Unexpected GLM-OCR"):
        task.run(context)
    assert "customer value" not in str(context["fatal_failure"])
    assert context["fatal_failure"]["failure_type"] == "glm_ocr_unexpected_error"
