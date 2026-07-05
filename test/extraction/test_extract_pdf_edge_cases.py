from pathlib import Path
import random
import time
from typing import Any
from unittest.mock import Mock

import pytest

from modules.exceptions import TaskError
from standard_step.extraction.extract_pdf import ExtractPdfTask


class Config:
    def __init__(self, params):
        self.params = params

    def get(self, key, default=None):
        if key == "tasks.extract_document_data.params":
            return self.params
        return default


def _task(tmp_path: Path, params=None) -> ExtractPdfTask:
    values = params if params is not None else {
        "api_key": "key",
        "fields": {"value": {"alias": "Value", "type": "str"}},
    }
    task = ExtractPdfTask(config_manager=Config(values), **values)
    task.on_start({"id": "doc"})
    return task


def test_on_start_uses_injected_params_without_fixed_config_lookup():
    class NoLookupConfig:
        def get(self, key, default=None):
            raise AssertionError(f"Unexpected task-specific config lookup: {key}")

    task = ExtractPdfTask(
        config_manager=NoLookupConfig(),
        api_key="injected-key",
        fields={"value": {"alias": "Value", "type": "str"}},
    )

    task.on_start({"id": "doc", "current_task_key": "alternate_extract"})

    assert task.api_key == "injected-key"
    assert task.fields == {"value": {"alias": "Value", "type": "str"}}


def test_require_api_key_and_required_field_validation(tmp_path):
    missing_key = _task(tmp_path, {"fields": {"value": {"type": "str"}}})
    with pytest.raises(TaskError, match="API key"):
        missing_key._require_api_key()
    with pytest.raises(TaskError, match="API key"):
        missing_key.validate_required_fields({"file_path": str(tmp_path / "missing.pdf")})

    missing_fields = _task(tmp_path, {"api_key": "key", "fields": {}})
    with pytest.raises(TaskError, match="Fields configuration"):
        missing_fields.validate_required_fields({"file_path": str(tmp_path / "missing.pdf")})

    valid = _task(tmp_path)
    with pytest.raises(TaskError, match="File does not exist"):
        valid.validate_required_fields({"file_path": str(tmp_path / "missing.pdf")})


def test_extract_retry_handles_non_retryable_last_attempt_and_zero_attempts(
    tmp_path,
    monkeypatch,
):
    task = _task(tmp_path)
    runner = Mock(side_effect=RuntimeError("401 invalid API key"))
    monkeypatch.setattr(
        "standard_step.extraction.extract_pdf.run_extract_v2_job",
        runner,
    )
    with pytest.raises(TaskError, match="authentication failed"):
        task._extract_with_retry("file.pdf")
    assert runner.call_count == 1

    runner = Mock(side_effect=RuntimeError("temporary timeout"))
    monkeypatch.setattr(
        "standard_step.extraction.extract_pdf.run_extract_v2_job",
        runner,
    )
    monkeypatch.setattr(time, "sleep", Mock())
    monkeypatch.setattr(random, "uniform", lambda *args: 0)
    with pytest.raises(TaskError, match="timed out"):
        task._extract_with_retry("file.pdf", max_retries=2)
    assert runner.call_count == 2

    with pytest.raises(TaskError, match="after 0 attempts"):
        task._extract_with_retry("file.pdf", max_retries=0)


def test_run_wraps_unexpected_validation_error(tmp_path, monkeypatch):
    task = _task(tmp_path)
    monkeypatch.setattr(
        task,
        "validate_required_fields",
        Mock(side_effect=RuntimeError("unexpected secret")),
    )
    context: dict[str, Any] = {"file_path": "file.pdf"}

    with pytest.raises(TaskError, match="Unexpected error"):
        task.run(context)

    assert context["fatal_failure"]["failure_type"] == "extract_unexpected_error"
    assert context["error_step"] == "ExtractPdfTask"


def test_process_data_and_value_parser_edge_cases(tmp_path):
    task = _task(tmp_path)
    task.fields = {}
    assert task._process_fields({}, None, None) == {}

    assert task._get_extracted_value({"value": 1}, "value", "Value") == (True, 1)
    assert task._process_value(None, "Optional[str]") is None
    assert task._process_value(None, "str") is None
    assert task._process_value("bad", "float") == "bad"
    assert task._process_value("value", "Unknown") == "value"
    assert task._process_value("not-list", "List[str]") == "not-list"
    assert task._process_value([1], "List[str") == [1]
    assert task._process_value("not-dict", "Dict[str, int]") == "not-dict"
    assert task._process_value({"a": 1}, "Dict[str, int") == {"a": 1}
    assert task._process_value({"a": 1}, "Dict[str]") == {"a": 1}
    assert task._process_value("value", "Tuple[str]") == "value"
    assert task._process_value(
        [None, "1", "2"],
        "Optional[List[int]]",
    ) == [1, 2]
    assert task._process_value(
        {"1": "2"},
        "Dict[int, float]",
    ) == {1: 2.0}


def test_table_processing_skips_invalid_and_empty_items(tmp_path):
    task = _task(tmp_path)
    field_config = {
        "item_fields": {
            "quantity": {"alias": "Quantity", "type": "int"},
        }
    }

    assert task._process_table_field(
        {"Items": "not-a-list"},
        "items",
        "Items",
        field_config,
    ) == []
    assert task._process_table_field(
        {"Items": ["invalid", {}, {"Other": 1}, {"Quantity": "2"}]},
        "items",
        "Items",
        field_config,
    ) == [{"quantity": 2}]


def test_structured_object_processing_normalizes_child_keys_and_types(tmp_path):
    task = _task(tmp_path)
    field_config = {
        "type": "Dict[str, Any]",
        "object_fields": {
            "customer_name": {"alias": "Customer name", "type": "str"},
            "invoice_count": {"alias": "Invoice count", "type": "int"},
            "total_amount": {"alias": "Total amount", "type": "float"},
            "approved": {"alias": "Approved", "type": "bool"},
            "notes": {"alias": "Notes", "type": "Optional[str]"},
        },
    }

    result = task._process_scalar_field(
        {
            "Customer name": "Acme Ltd",
            "Invoice count": "3",
            "Total amount": "1250.75",
            "Approved": "yes",
            "Notes": None,
            "Ignored": "value",
        },
        field_config,
    )

    assert result == {
        "customer_name": "Acme Ltd",
        "invoice_count": 3,
        "total_amount": 1250.75,
        "approved": True,
        "notes": None,
    }


def test_metadata_candidate_wrapper_and_table_lookup(tmp_path):
    task = _task(
        tmp_path,
        {
            "api_key": "key",
            "fields": {
                "items": {
                    "alias": "Items",
                    "type": "List[Any]",
                    "is_table": True,
                    "item_fields": {},
                }
            },
        },
    )

    table = task._find_table_field_config()
    assert table and table["key"] == "items" and table["alias"] == "Items"
    assert task._metadata_candidates(
        {"fields": {"items": {"confidence": 0.5}}},
        "items",
        "Items",
    )
