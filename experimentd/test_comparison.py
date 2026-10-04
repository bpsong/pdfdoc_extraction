"""Synthetic tests for production adapter reuse and fair paired scoring."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import fitz
import pytest

from experimentd import compare_methods as comparison
from experimentd import glm_comparison as glm
from experimentd import trace_glm_stages as tracing
from experimentd.extract_invoice import HEADER_FIELDS, ITEM_FIELDS, MODEL, save_json
from experimentd.test_experiment import synthetic_reference


@pytest.mark.parametrize("selection,expected", [(None, [1, 2, 3]), ("2", [2]), ("1-2,3", [1, 2, 3]), ("3,1", [1, 3])])
def test_page_selection_preserves_original_order(selection: str | None, expected: list[int]) -> None:
    assert glm.select_pages(selection, 3) == expected


@pytest.mark.parametrize("selection", ["0", "4", "2-1", "1-2-3", ""])
def test_invalid_page_selection_rejected(selection: str) -> None:
    with pytest.raises(ValueError):
        glm.select_pages(selection, 3)


def test_normalization_does_not_invent_word_boxes() -> None:
    data = {**{name: "Example" for name in HEADER_FIELDS},
            "line_items": [{"description": "Example product", "unit_of_measure": None,
                            "quantity": "2", "unit_price": "12.62", "line_total": "25.25"}]}
    result = glm.canonical_invoice(data, {name: [1] for name in [*HEADER_FIELDS, "line_items"]}, [2])
    assert result["invoice_number"]["page_numbers"] == [2]
    assert result["invoice_number"]["boxes"] == []
    assert result["invoice_number"]["grounding_status"] == "page_evidence_only"
    assert result["line_items"][0]["unit_of_measure"]["value"] is None
    assert result["line_items"][0]["printed_minus_computed"] == "0.01"


def test_transport_retains_production_schema_prompt_and_encodes_images() -> None:
    original = {"model": MODEL, "messages": [{"role": "user", "content": "synthetic prompt", "images": [b"synthetic image"]}],
                "format": {"type": "object"}, "options": {"num_ctx": 18000}, "think": False}
    payload = glm.RecordingLocalClient.encode_payload(original)
    assert payload["messages"][0]["images"] == ["c3ludGhldGljIGltYWdl"]
    assert payload["messages"][0]["content"] == original["messages"][0]["content"]
    assert payload["format"] == original["format"]
    assert original["messages"][0]["images"] == [b"synthetic image"]
    assert payload["options"] == {"num_ctx": 18000, "seed": 42}


def test_transport_rejects_remote_endpoints(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        glm.RecordingLocalClient("http://remote.invalid", tmp_path, 5)


def test_recording_client_unloads_only_its_previous_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def local(host: str, route: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append((route, payload))
        return {"done": True, "response": "{}"}
    monkeypatch.setattr(glm, "local_request", local)
    client = glm.RecordingLocalClient("http://localhost:11434", tmp_path, 5, MODEL)
    client.generate(model=glm.GLM_MODEL, prompt="synthetic", format={})
    assert calls[0] == ("/api/generate", {"model": MODEL, "keep_alive": 0})
    assert len(client.calls) == 1
    assert (tmp_path / "calls/01/request.json").exists()
    assert (tmp_path / "calls/01/response.json").exists()


def test_production_adapter_integration_on_selected_synthetic_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        document.new_page(width=100, height=100).insert_text((10, 20), "Unrelated")
        document.new_page(width=200, height=300).insert_text((10, 20), "Example invoice")
        document.save(pdf)
    data = {"customer_name": "Example Buyer", "supplier_name": "Example Seller",
            "invoice_date": "2026-01-02", "invoice_number": "INV-1", "invoice_total": 10.0,
            "line_items": [{"description": "Example product", "unit_of_measure": None,
                            "quantity": 2.0, "unit_price": 5.0, "line_total": 10.0}]}
    seen = []
    scalar_index = 0
    def local(host: str, route: str, payload: dict[str, Any] | None = None, timeout: float = 600) -> dict[str, Any]:
        nonlocal scalar_index
        if route == "/api/tags":
            return {"models": [{"name": name, "digest": "synthetic"} for name in [MODEL, glm.GLM_MODEL]]}
        if payload.get("keep_alive") == 0:
            return {"done": True}
        seen.append((route, payload))
        assert "reference_method" not in json.dumps(payload)
        if route == "/api/generate":
            properties = payload["format"]["properties"]
            content = {key: data[key] for key in properties}
            return {"done": True, "done_reason": "stop", "response": json.dumps(content)}
        if scalar_index < len(HEADER_FIELDS):
            value = data[HEADER_FIELDS[scalar_index]]
        else:
            value = data["line_items"]
        scalar_index += 1
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps({"value": value, "page_numbers": [1]})}}
    monkeypatch.setattr(glm, "local_request", local)
    result = glm.extract_glm(pdf, tmp_path / "output", "2")
    assert len(seen) == 8  # actual production header/table + six Qwen resolvers
    assert result["customer_name"]["value"] == "Example Buyer"
    assert result["invoice_number"]["page_numbers"] == [2]
    assert len(result["line_items"]) == 1
    assert result["line_items"][0]["computed_line_total"] == "10.00"
    assert comparison.read_json(tmp_path / "output/run.json")["bbox_available"] is False
    assert comparison.read_json(tmp_path / "output/parsed.json")["pages"][0]["page"] == 2
    assert all(payload["think"] is False for route, payload in seen if route == "/api/chat")


def test_selected_page_renderer_obeys_production_dimension_limit(tmp_path: Path) -> None:
    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        document.new_page(width=100, height=100)
        document.new_page(width=200, height=300)
        document.save(pdf)
    adapter = glm.SelectedPageAdapter([2], ollama_host="http://localhost:11434", model=glm.GLM_MODEL, dpi=216)
    images = adapter.render_pdf(str(pdf), max_dimension=256)
    assert len(images) == 1
    pixmap = fitz.Pixmap(images[0])
    assert pixmap.height == 256 and pixmap.width in (170, 171)


def test_glm_unavailable_box_metrics_are_null_and_failures_count(tmp_path: Path) -> None:
    report = comparison.score_method([synthetic_reference()], tmp_path, "glm_task")
    assert report["overall"]["overall_accuracy"] == {"correct": 0, "total": 10, "percent": 0.0}
    assert report["overall"]["location_accuracy"] is None
    assert report["overall"]["value_and_location_accuracy"] is None
    assert report["failures"] == ["synthetic"]


def test_extra_rows_penalize_score_without_inflating_paired_wins(tmp_path: Path) -> None:
    reference = synthetic_reference()
    values = {name: reference["fields"][name]["value"] for name in HEADER_FIELDS}
    values["line_items"] = [{name: row[name]["value"] for name in ITEM_FIELDS} for row in reference["line_items"]]
    values["line_items"].append(deepcopy(values["line_items"][0]))
    invoice = glm.canonical_invoice(values, {}, [1])
    directory = tmp_path / "glm_task/synthetic"
    save_json(directory / "invoice.json", invoice)
    save_json(directory / "parsed.json", {"pages": [{"page": 1, "width": 100, "height": 100}]})
    save_json(directory / "run.json", {"elapsed_seconds": 1, "total_load_seconds": 0,
                                      "total_inference_excluding_load_seconds": 1, "model_calls": [{}]})
    report = comparison.score_method([reference], tmp_path, "glm_task")
    assert report["overall"]["overall_accuracy"]["total"] == 15
    assert report["overall"]["overall_accuracy"]["correct"] == 10
    paired = comparison.paired_results(report, report)
    assert paired["counts"]["both_correct"] == 10
    assert sum(paired["counts"].values()) == 10


def test_missing_cache_artifacts_require_rerun(tmp_path: Path) -> None:
    save_json(tmp_path / "invoice.json", {})
    save_json(tmp_path / "run.json", {})
    assert not comparison.cache_matches("glm_task", synthetic_reference(), tmp_path / "input.pdf", tmp_path, {})


def test_report_has_same_references_and_no_zero_box_score_for_glm(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    save_json(manifest, {"samples": [synthetic_reference()]})
    report = comparison.write_report(manifest, tmp_path / "output")
    assert report["methods"]["glm_task"]["overall"]["location_accuracy"] is None
    assert sum(report["paired"]["counts"].values()) == 10
    assert (tmp_path / "output/comparison.json").exists()
    assert (tmp_path / "output/SUMMARY.md").exists()


def test_task_configuration_uses_numeric_types_for_numeric_columns() -> None:
    fields = glm.configured_fields()
    assert fields["invoice_total"]["type"] == "float"
    rows = fields["line_items"]["item_fields"]
    assert rows["unit_of_measure"]["type"] == "Optional[str]"
    assert all(rows[name]["type"] == "Optional[float]" for name in ("quantity", "unit_price", "line_total"))


def recorded_stage_fixture(directory: Path) -> dict[str, Any]:
    """Write synthetic call records without using any actual invoice content."""
    reference = synthetic_reference()
    for i, name in enumerate(HEADER_FIELDS, 1):
        save_json(directory / f"calls/{i:02d}/request.json", {"messages": [{"content":
                  "Configured field: " + json.dumps({"key": name})}]})
        save_json(directory / f"calls/{i:02d}/response.json", {"done": True, "done_reason": "stop",
                  "message": {"content": json.dumps({"value": reference["fields"][name]["value"], "page_numbers": [1]})}})
    rows = [{name: row[name]["value"] for name in ITEM_FIELDS} for row in reference["line_items"]]
    save_json(directory / "calls/06/request.json", {"messages": [{"content": "This is ordered evidence chunk 1 of 1."}]})
    save_json(directory / "calls/06/response.json", {"done": True, "done_reason": "stop",
              "message": {"content": json.dumps({"value": rows, "page_numbers": [1]})}})
    save_json(directory / "run.json", {"selected_pages": [2]})
    return reference


def test_stage_reconstruction_uses_raw_calls_and_original_page_mapping(tmp_path: Path) -> None:
    recorded_stage_fixture(tmp_path)
    invoice = tracing.recorded_qwen_invoice(tmp_path)
    assert invoice["invoice_number"]["value"] == "Example"
    assert invoice["invoice_number"]["page_numbers"] == [2]
    assert invoice["line_items"][0]["unit_of_measure"]["value"] is None
    assert invoice["line_items"][0]["computed_line_total"] == "25.24"


def test_stage_diagnostic_identifies_postprocessing_regression(tmp_path: Path) -> None:
    directory = tmp_path / "glm_task/synthetic"
    reference = recorded_stage_fixture(directory)
    invoice = tracing.recorded_qwen_invoice(directory)
    invoice["line_items"][0]["unit_of_measure"]["value"] = "PCS"
    save_json(directory / "invoice.json", invoice)
    save_json(directory / "parsed.json", {"pages": []})
    manifest = tmp_path / "manifest.json"
    save_json(manifest, {"samples": [reference]})
    report = tracing.trace(manifest, tmp_path)
    assert report["raw_qwen_overall"]["overall_accuracy"]["correct"] == 10
    assert report["final_task_overall"]["overall_accuracy"]["correct"] == 9
    assert report["postprocessing_changes"] == {"correct_to_wrong": 1, "wrong_to_correct": 0}


def test_stage_reconstruction_ignores_truncated_retry(tmp_path: Path) -> None:
    recorded_stage_fixture(tmp_path)
    save_json(tmp_path / "calls/07/request.json", {"messages": [{"content": 'Configured field: {"key":"invoice_number"}'}]})
    save_json(tmp_path / "calls/07/response.json", {"done": True, "done_reason": "length", "message": {"content": "{"}})
    assert tracing.recorded_qwen_invoice(tmp_path)["invoice_number"]["value"] == "Example"
