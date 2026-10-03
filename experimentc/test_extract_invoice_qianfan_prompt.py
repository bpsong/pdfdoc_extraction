"""Verify prompt extraction and timing using synthetic documents."""

import argparse
import importlib.util
import json
from pathlib import Path

import fitz
import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "qianfan_prompt", Path(__file__).with_name("extract_invoice_qianfan_prompt.py")
)
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def test_custom_prompt_is_sent_without_schema() -> None:
    request = script.build_request(b"image", "Extract QTY", "model", 500)
    assert request["messages"][0]["content"] == "Extract QTY"
    assert request["messages"][0]["images"] == ["aW1hZ2U="]
    assert "format" not in request
    assert request["think"] is False


@pytest.mark.parametrize("truncated", [False, True])
def test_pdf_outputs_and_incomplete_response(tmp_path, monkeypatch, truncated) -> None:
    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((50, 50), "Invoice QTY 1")
        document.save(pdf)

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision"]})
        payload = json.loads(request.content)
        assert "format" not in payload
        assert payload["messages"][0]["images"]
        return httpx.Response(200, json={
            "done": True, "done_reason": "length" if truncated else "stop",
            "total_duration": 5_000_000_000, "load_duration": 1_000_000_000,
            "message": {"content": "| QTY |\n| 1 |"},
        })

    original = httpx.Client
    monkeypatch.setattr(script.httpx, "Client", lambda **kwargs:
                        original(**kwargs, transport=httpx.MockTransport(handler)))
    output = tmp_path / "output"
    args = argparse.Namespace(pdf=pdf, output=output, dpi=72, timeout=10,
                              max_tokens=500, host="http://localhost", model="test",
                              prompt=script.DEFAULT_PROMPT)
    if truncated:
        with pytest.raises(ValueError, match="incomplete"):
            script.run(args)
        assert (output / "page_001_response.json").exists()
        assert not (output / "extraction.md").exists()
    else:
        script.run(args)
        assert "| 1 |" in (output / "extraction.md").read_text()
        timing = json.loads((output / "run.json").read_text())
        assert timing["inference_excluding_load_seconds"] == 4
