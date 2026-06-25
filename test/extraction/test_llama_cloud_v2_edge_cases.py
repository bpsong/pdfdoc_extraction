from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.exceptions import TaskError
from standard_step.extraction import llama_cloud_v2 as llama


def test_build_configuration_and_schema_type_variants():
    fields = {
        "ignored": "invalid",
        "tags": {"type": "List[Optional[str]]", "description": "Tags"},
        "attributes": {"type": "Dict[str, Any]"},
        "amount": {"type": "Decimal"},
        "unknown": {"type": "Custom"},
        "table": {
            "type": "List[Any]",
            "is_table": True,
            "item_fields": {
                "ignored": "invalid",
                "note": {"type": "Optional[str]", "description": "Note"},
            },
        },
    }

    configuration = llama.build_extraction_configuration(
        fields,
        parse_tier="cost_effective",
        cite_sources=False,
        confidence_scores=None,
    )

    assert configuration["parse_tier"] == "cost_effective"
    assert configuration["cite_sources"] is False
    assert "confidence_scores" not in configuration
    assert configuration["data_schema"]["properties"]["tags"]["items"]["type"] == "string"
    assert configuration["data_schema"]["properties"]["attributes"]["type"] == "object"
    assert "required" not in configuration["data_schema"]["properties"]["table"]["items"]


def test_run_extract_job_uses_inline_configuration_and_saved_configuration(monkeypatch):
    completed = SimpleNamespace(
        id="job-1",
        status="COMPLETED",
        extract_result={"value": 1},
        extract_metadata={"summary": True},
    )
    detailed = SimpleNamespace(extract_metadata={"details": True})
    client = SimpleNamespace(
        files=SimpleNamespace(create=Mock(return_value=SimpleNamespace(id="file-1"))),
        extract=SimpleNamespace(
            run=Mock(return_value=completed),
            get=Mock(return_value=detailed),
        ),
    )
    cloud = Mock(return_value=client)
    monkeypatch.setattr(llama, "LlamaCloud", cloud)

    result = llama.run_extract_v2_job(
        api_key="key",
        file_path="invoice.pdf",
        fields={"value": {"type": "int"}},
        project_id="project",
        organization_id="organization",
        poll_interval_seconds=0.1,
        timeout_seconds=2,
    )

    assert result.data == {"value": 1}
    assert result.extraction_metadata == {"details": True}
    kwargs = client.extract.run.call_args.kwargs
    assert "configuration" in kwargs
    assert kwargs["project_id"] == "project"
    assert kwargs["organization_id"] == "organization"

    client.extract.run.reset_mock()
    llama.run_extract_v2_job(
        api_key="key",
        file_path="invoice.pdf",
        fields={},
        configuration_id="config-1",
    )
    assert client.extract.run.call_args.kwargs["configuration_id"] == "config-1"


def test_run_extract_job_rejects_non_completed_status(monkeypatch):
    job = SimpleNamespace(
        id="job-2",
        status="FAILED",
        error_message=None,
        error="provider failure",
    )
    client = SimpleNamespace(
        files=SimpleNamespace(create=Mock(return_value=SimpleNamespace(id="file-1"))),
        extract=SimpleNamespace(run=Mock(return_value=job)),
    )
    monkeypatch.setattr(llama, "LlamaCloud", Mock(return_value=client))

    with pytest.raises(TaskError, match="provider failure"):
        llama.run_extract_v2_job(
            api_key="key",
            file_path="invoice.pdf",
            fields={},
        )


@pytest.mark.parametrize("configuration_id", ["config-1", None])
def test_preflight_success_and_failure(monkeypatch, configuration_id):
    client = SimpleNamespace(
        configurations=SimpleNamespace(retrieve=Mock()),
        projects=SimpleNamespace(list=Mock()),
    )
    monkeypatch.setattr(llama, "LlamaCloud", Mock(return_value=client))

    llama.preflight_extract_v2_access(
        api_key="key",
        configuration_id=configuration_id,
        organization_id="org",
    )

    failing_client = SimpleNamespace(
        configurations=SimpleNamespace(
            retrieve=Mock(side_effect=RuntimeError("401 invalid API key"))
        ),
        projects=SimpleNamespace(
            list=Mock(side_effect=RuntimeError("timeout"))
        ),
    )
    monkeypatch.setattr(llama, "LlamaCloud", Mock(return_value=failing_client))
    with pytest.raises(TaskError):
        llama.preflight_extract_v2_access(
            api_key="key",
            configuration_id=configuration_id,
        )


@pytest.mark.parametrize(
    ("error", "configuration_id", "expected"),
    [
        ("401 invalid API key", None, "authentication failed"),
        ("configuration not found 404", "cfg", "'cfg' was not found"),
        ("job cancelled", None, "cancelled"),
        ("request timed out", None, "timed out"),
        ("other provider error", None, "other provider error"),
    ],
)
def test_humanize_extract_error_variants(error, configuration_id, expected):
    assert expected in llama.humanize_extract_error(
        error,
        configuration_id=configuration_id,
    )


def test_non_retryable_error_classification():
    assert llama.is_non_retryable_extract_error("401 invalid api key") is True
    assert llama.is_non_retryable_extract_error("configuration not found") is True
    assert llama.is_non_retryable_extract_error("temporary timeout") is False


def test_plain_dict_conversion_variants():
    class LegacyModel:
        def dict(self, *, exclude_none):
            return {"legacy": True}

    class InvalidModel:
        def model_dump(self, **kwargs):
            return ["not", "a", "dict"]

    assert llama._to_plain_dict(None) == {}
    assert llama._to_plain_dict({"value": 1}) == {"value": 1}
    assert llama._to_plain_dict(LegacyModel()) == {"legacy": True}
    assert llama._to_plain_dict(InvalidModel()) == {}
    assert llama._to_plain_dict(object()) == {}
    assert llama._optional_scope(project_id=None, organization_id=None) == {}


def test_metadata_candidates_labels_sources_and_confidence_bands():
    metadata = {
        "document_metadata": {"supplier": "medium"},
        "fields": [
            {"field_key": "supplier", "confidence": "0.82", "label": "medium"},
            "invalid",
        ],
        "confidences": {
            "Supplier": {
                "confidence_value": 0.91,
                "citation": {"page": 1},
            }
        },
    }

    candidates = llama.metadata_candidates(metadata, "supplier", "Supplier")

    assert "medium" in candidates
    assert llama.extract_numeric_confidence(metadata, "supplier", "Supplier") == 0.82
    assert llama.extract_confidence_label(metadata, "supplier", "Supplier") == "medium"
    assert llama.extract_field_source(metadata, "supplier", "Supplier") == {
        "provider_source": {"page": 1}
    }
    assert llama.confidence_band(None) == "missing"
    assert llama.confidence_band("invalid") == "missing"
    assert llama.confidence_band(0.95) == "high"
    assert llama.confidence_band(0.75) == "medium"
    assert llama.confidence_band(0.2) == "low"


def test_nested_confidence_details_include_labels_and_skip_metadata_keys():
    value = {
        "row": {
            "amount": {
                "score": "0.66",
                "confidence_level": "low",
                "source": "page-1",
            },
            "page": 1,
        }
    }

    details = llama._nested_confidence_details(value)

    assert details["row.amount"]["confidence"] == 0.66
    assert details["row.amount"]["confidence_label"] == "low"
    assert details["row.amount"]["source"] == {"provider_source": "page-1"}
    assert llama._nested_confidence_details("scalar") == {}
    assert llama._join_path("row", "amount") == "row.amount"
    assert llama._join_path("", "amount") == "amount"
