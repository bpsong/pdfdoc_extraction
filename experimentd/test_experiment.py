"""Synthetic tests for local-only extraction, citations and accuracy scoring."""

from __future__ import annotations

from copy import deepcopy
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from typing import Any

import fitz
import pytest
from pydantic import ValidationError

from experimentd import extract_invoice as extraction
from experimentd.evaluate import evaluate, location_matches, score_sample, value_matches
from experimentd.render_overlays import render_sample
from experimentd import run_benchmark as benchmark


def synthetic_invoice() -> dict[str, Any]:
    def field(value: str | None) -> dict[str, Any]:
        return {"value": value, "source_ids": ["p1_e0"] if value is not None else []}
    return {**{n: field("Example") for n in extraction.HEADER_FIELDS},
            "line_items": [{"description": field("Example product"), "unit_of_measure": field(None),
                            "quantity": field("2"), "unit_price": field("12.62"), "line_total": field("25.25")}]}


def synthetic_reference() -> dict[str, Any]:
    invoice = synthetic_invoice()
    def field(value: dict[str, Any]) -> dict[str, Any]:
        return {"value": value["value"], "regions": [{"page": 1, "bbox_normalized": [0, 0, .5, .5]}]
                if value["value"] is not None else []}
    invoice["invoice_total"]["value"] = "25.25"
    return {"id": "synthetic", "group": "example", "pdf": "input.pdf", "pages": "1",
            "fields": {n: field(invoice[n]) for n in extraction.HEADER_FIELDS},
            "line_items": [{n: field(row[n]) for n in extraction.ITEM_FIELDS} for row in invoice["line_items"]]}


ELEMENTS = [{"id": "p1_e0", "page": 1, "text": "Example", "bbox": [10, 10, 20, 20]}]
PARSED = {"pages": [{"page": 1, "width": 100, "height": 100}], "elements": ELEMENTS}


@pytest.mark.parametrize("host", ["https://localhost:11434", "http://example.com", "http://192.168.0.1",
                                  "http://127.0.0.1@remote.invalid", "http://localhost/path", "http://localhost?x=1"])
def test_remote_hosts_rejected(host: str) -> None:
    with pytest.raises(ValueError):
        extraction.validate_host(host)


@pytest.mark.parametrize("host", ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434/"])
def test_loopback_hosts_accepted(host: str) -> None:
    assert extraction.validate_host(host) == host.rstrip("/")


def test_schema_rejects_wrong_types_and_extra_keys() -> None:
    invoice = synthetic_invoice()
    invoice["invoice_total"]["value"] = 25.25
    with pytest.raises(ValidationError):
        extraction.Invoice.model_validate(invoice)
    invoice = synthetic_invoice()
    invoice["invented"] = "unexpected"
    with pytest.raises(ValidationError):
        extraction.Invoice.model_validate(invoice)


def test_citations_preserve_word_boxes_and_union_per_page() -> None:
    elements = ELEMENTS + [{"id": "p1_e1", "page": 1, "text": "product", "bbox": [30, 15, 50, 25]},
                           {"id": "p2_e2", "page": 2, "text": "continued", "bbox": [5, 5, 10, 10]}]
    result = extraction.resolve_field({"value": "Example product continued", "source_ids": ["p1_e0", "p1_e1", "p2_e2"]},
                                      {e["id"]: e for e in elements})
    assert result["bounding_boxes"] == [{"page": 1, "bbox": [10, 10, 50, 25]}, {"page": 2, "bbox": [5, 5, 10, 10]}]
    assert len(result["boxes"]) == 3


@pytest.mark.parametrize("field", [{"value": "Example", "source_ids": ["bad"]},
                                   {"value": "Example", "source_ids": []},
                                   {"value": None, "source_ids": ["p1_e0"]}])
def test_invalid_citations_are_flagged_without_repair(field: dict[str, Any]) -> None:
    result = extraction.resolve_field(field, {e["id"]: e for e in ELEMENTS})
    assert result["grounding_status"] == "invalid_citation"


def test_printed_total_is_preserved_when_multiplication_differs() -> None:
    result = extraction.resolve_invoice(synthetic_invoice(), ELEMENTS)
    row = result["line_items"][0]
    assert row["line_total"]["value"] == "25.25"
    assert row["computed_line_total"] == "25.24"
    assert row["printed_minus_computed"] == "0.01"
    assert row["unit_of_measure"]["grounding_status"] == "absent"


def test_negative_discount_arithmetic_and_nonfinite_numbers() -> None:
    invoice = synthetic_invoice()
    row = invoice["line_items"][0]
    row["quantity"]["value"] = "1"
    row["unit_price"]["value"] = "-18.36"
    row["line_total"]["value"] = "-18.36"
    result = extraction.resolve_invoice(invoice, ELEMENTS)
    assert result["line_items"][0]["computed_line_total"] == "-18.36"
    assert extraction.decimal_value("NaN") is None
    assert not value_matches("invoice_total", "NaN", "NaN")


def test_scoring_uses_exact_decimals_and_layout_normalized_text() -> None:
    assert value_matches("customer_name", "EXAMPLE, Buyer", "Example Buyer")
    assert value_matches("quantity", "12", "12.00")
    assert not value_matches("line_total", "25.25", "25.24")
    assert not value_matches("description", "Example product code", "Example product")
    assert not value_matches("unit_of_measure", None, "PCS")


def test_missing_and_extra_rows_count_as_errors() -> None:
    reference = synthetic_reference()
    result = extraction.resolve_invoice(synthetic_invoice(), ELEMENTS)
    result["invoice_total"]["value"] = "25.25"
    result["line_items"].append(deepcopy(result["line_items"][0]))
    score = score_sample(reference, result, PARSED)
    assert len(score["checks"]) == 15
    assert all(not c["correct"] for c in score["checks"] if c["field"].startswith("extra"))
    result["line_items"] = []
    score = score_sample(reference, result, PARSED)
    assert score["expected_rows"] == 1 and score["actual_rows"] == 0
    assert sum(c["correct"] for c in score["checks"]) == 5  # missing rows get no null-cell credit


def test_location_rejects_wrong_page_region_and_invalid_bounds() -> None:
    field = extraction.resolve_field({"value": "Example", "source_ids": ["p1_e0"]}, {e["id"]: e for e in ELEMENTS})
    regions = [{"page": 1, "bbox_normalized": [0, 0, .5, .5]}]
    pages = {1: PARSED["pages"][0]}
    assert location_matches(field, regions, pages)
    assert not location_matches(field, [{"page": 2, "bbox_normalized": [0, 0, .5, .5]}], pages)
    assert not location_matches(field, [{"page": 1, "bbox_normalized": [.6, .6, 1, 1]}], pages)
    field["boxes"][0]["bbox"] = [10, 10, 101, 20]
    assert not location_matches(field, regions, pages)


def test_failed_samples_remain_in_report_denominator(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    extraction.save_json(manifest, {"samples": [synthetic_reference()]})
    report = evaluate(manifest, tmp_path / "results")
    assert report["failures"] == ["synthetic"]
    assert report["overall"]["overall_accuracy"] == {"correct": 0, "total": 10, "percent": 0.0}


def test_extraction_saves_schema_valid_grounded_json_without_sending_truth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"synthetic placeholder")
    parsed = {**PARSED, "source_sha256": "synthetic", "liteparse_version": "2.15.1", "parse_seconds": .1}
    monkeypatch.setattr(extraction, "parse_pdf", lambda *args: parsed)
    calls = []
    def local(host: str, route: str, payload: dict[str, Any] | None = None, timeout: float = 600) -> dict[str, Any]:
        calls.append((host, route, payload))
        if route == "/api/tags":
            return {"models": [{"name": extraction.MODEL, "digest": "synthetic", "details": {}}]}
        assert "reference_method" not in json.dumps(payload)
        assert payload["format"] == extraction.Invoice.model_json_schema()
        assert payload["think"] is False and payload["stream"] is False
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(synthetic_invoice())}}
    monkeypatch.setattr(extraction, "local_request", local)
    result = extraction.extract(pdf, tmp_path / "results")
    assert result["line_items"][0]["computed_line_total"] == "25.24"
    assert [route for _, route, _ in calls] == ["/api/tags", "/api/chat"]
    assert (tmp_path / "results" / "ollama_response.json").exists()
    assert (tmp_path / "results" / "run.json").exists()


def test_truncated_response_keeps_raw_output_and_has_no_success_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"synthetic")
    monkeypatch.setattr(extraction, "parse_pdf", lambda *args: {**PARSED, "source_sha256": "synthetic", "liteparse_version": "2.15.1", "parse_seconds": .1})
    def local(host: str, route: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if route == "/api/tags":
            return {"models": [{"name": extraction.MODEL, "digest": "synthetic", "details": {}}]}
        return {"done": True, "done_reason": "length", "message": {"content": "{"}}
    monkeypatch.setattr(extraction, "local_request", local)
    with pytest.raises(ValueError, match="incomplete"):
        extraction.extract(pdf, tmp_path / "results")
    assert (tmp_path / "results" / "ollama_response.json").exists()
    assert not (tmp_path / "results" / "invoice.json").exists()


def test_real_liteparse_and_overlay_on_synthetic_pdf(tmp_path: Path) -> None:
    pytest.importorskip("liteparse")
    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        page = document.new_page(width=200, height=200)
        page.insert_text((20, 30), "Example Seller INVOICE")
        document.save(pdf)
    original = pdf.read_bytes()
    parsed = extraction.parse_pdf(pdf, "1", dpi=150)
    assert "Example" in parsed["pages"][0]["text"]
    assert all(e["page"] == 1 for e in parsed["elements"])
    invoice = synthetic_invoice()
    first_id = parsed["elements"][0]["id"]
    for field in invoice.values():
        if isinstance(field, dict):
            field["source_ids"] = [first_id]
    for row in invoice["line_items"]:
        for field in row.values():
            field["source_ids"] = [first_id] if field["value"] is not None else []
    extraction.save_json(tmp_path / "invoice.json", extraction.resolve_invoice(invoice, parsed["elements"]))
    images = render_sample(pdf, tmp_path)
    assert len(images) == 1 and images[0].exists()
    assert pdf.read_bytes() == original


def test_local_http_ignores_proxies_and_blocks_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"received": data["synthetic"]}).encode())

        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", "http://remote.invalid/document-upload")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            pass

    monkeypatch.setenv("HTTP_PROXY", "http://remote.invalid:9999")
    monkeypatch.setenv("http_proxy", "http://remote.invalid:9999")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_port}"
    try:
        assert extraction.local_request(host, "/api/chat", {"synthetic": "example"}, timeout=5) == {"received": "example"}
        with pytest.raises(ValueError, match="Redirects"):
            extraction.local_request(host, "/redirect", timeout=5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("old_digest,expected_calls", [("current", 0), ("outdated", 1)])
def test_resume_checks_actual_model_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           old_digest: str, expected_calls: int) -> None:
    manifest = tmp_path / "experimentd" / "samples.local.json"
    extraction.save_json(manifest, {"samples": [synthetic_reference()]})
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"synthetic")
    output = tmp_path / "results"
    directory = output / "synthetic"
    metadata = {"source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "model": extraction.MODEL, "model_digest": old_digest, "pages": "1",
                "liteparse_version": "synthetic", "dpi": 300,
                "prompt_sha256": hashlib.sha256(extraction.PROMPT.encode()).hexdigest(),
                "options": {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": 4096},
                "elapsed_seconds": 1}
    extraction.save_json(directory / "run.json", metadata)
    extraction.save_json(directory / "invoice.json", {})
    monkeypatch.setattr(benchmark, "version", lambda name: "synthetic")
    monkeypatch.setattr(benchmark, "local_request", lambda *args, **kwargs:
                        {"models": [{"name": extraction.MODEL, "digest": "current"}]})
    calls = []
    def fake_extract(*args: Any) -> dict[str, Any]:
        calls.append(args)
        extraction.save_json(directory / "run.json", {**metadata, "model_digest": "current"})
        extraction.save_json(directory / "invoice.json", {})
        return {}
    monkeypatch.setattr(benchmark, "extract", fake_extract)
    monkeypatch.setattr(benchmark, "evaluate", lambda *args: {"groups": {}, "failures": []})
    benchmark.run(argparse.Namespace(manifest=manifest, output=output, host="http://localhost:11434",
                                     model=extraction.MODEL, resume=True, dpi=300, timeout=5))
    assert len(calls) == expected_calls
