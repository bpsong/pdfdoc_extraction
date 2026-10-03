"""Check image-bearing extraction requests without running Ollama."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "qianfan_experiment", Path(__file__).with_name("extract_invoice_qianfan.py")
)
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def test_json_request_uses_vision_schema_and_disables_thinking() -> None:
    request = script.build_request(b"image", "json", "test-model", 500)
    assert request["messages"][0]["images"] == ["aW1hZ2U="]
    assert request["format"] == script.SCHEMA
    assert request["think"] is False
    assert request["options"]["num_predict"] == 500
    assert "line_items" in request["format"]["required"]


def test_markdown_request_does_not_constrain_json() -> None:
    request = script.build_request(b"image", "markdown", "test-model", 500)
    assert "format" not in request
    assert request["messages"][0]["content"] == "OCR the image and output in Markdown."


def test_timing_summary_excludes_load() -> None:
    timing = script.timing_summary({"total_duration": 10_000_000_000,
                                   "load_duration": 2_000_000_000,
                                   "prompt_eval_duration": 5_000_000_000,
                                   "eval_duration": 3_000_000_000}, 2)
    assert timing["excluding_load_seconds"] == 8
    assert timing["prompt_seconds"] == 5
    assert timing["generation_seconds"] == 3
    assert timing["page"] == 2


def test_multi_page_results_stay_separate(tmp_path, monkeypatch) -> None:
    import argparse
    import json
    import fitz
    import httpx

    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        for _ in range(2):
            document.new_page().insert_text((50, 50), "Synthetic invoice")
        document.save(pdf)
    invoice = {key: None for key in script.SCHEMA["required"]}
    invoice["line_items"] = []

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision"]})
        return httpx.Response(200, json={"done": True, "total_duration": 2_000_000_000,
                                        "message": {"content": json.dumps(invoice)}})

    original = httpx.Client
    monkeypatch.setattr(script.httpx, "Client", lambda **kwargs:
                        original(**kwargs, transport=httpx.MockTransport(handler)))
    output = tmp_path / "output"
    script.run(argparse.Namespace(pdf=pdf, output=output, dpi=72, timeout=10,
                                 max_tokens=1000, host="http://localhost", model="test", mode="json"))
    assert [page["page"] for page in json.loads((output / "page_invoices.json").read_text())] == [1, 2]
    assert not (output / "invoice.json").exists()
    assert json.loads((output / "run.json").read_text())["inference_excluding_load_seconds"] == 4
