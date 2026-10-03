"""Synthetic checks for the standalone invoice experiment."""

import base64
import json

import fitz
import httpx
import pytest

from experimentc.extract_invoice import SCHEMA, chat, main


def test_chat_sends_image_and_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["messages"][0]["images"] == [base64.b64encode(b"png").decode()]
        assert payload["stream"] is False
        assert payload["format"] == SCHEMA
        return httpx.Response(200, json={"done": True, "message": {"content": "{}"}})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler)) as client:
        assert chat(client, "test", "OCR:", b"png", SCHEMA)["done"]


@pytest.mark.parametrize("result", [
    {"done": True, "done_reason": "length", "message": {"content": "partial"}},
    {"done": True, "message": {"content": ""}},
])
def test_chat_rejects_incomplete_or_empty_output(result: dict) -> None:
    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=result)
    )) as client:
        with pytest.raises(ValueError):
            chat(client, "test", "OCR:")


def test_cli_pdf_to_invoice(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((50, 50), "Synthetic invoice")
        document.save(pdf)
    invoice = {key: None for key in SCHEMA["required"]}
    invoice["line_items"] = []
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision"]})
        content = json.dumps(invoice) if "format" in payload else "Synthetic invoice"
        return httpx.Response(200, json={"done": True, "message": {"content": content}})

    original_client = httpx.Client
    monkeypatch.setattr("experimentc.extract_invoice.httpx.Client", lambda **kwargs:
                        original_client(**kwargs, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr("sys.argv", ["extract_invoice.py", str(pdf), "--output", str(tmp_path / "out")])
    main()
    assert json.loads((tmp_path / "out" / "invoice.json").read_text()) == invoice
    assert "images" in calls[1]["messages"][0]
    assert "images" not in calls[2]["messages"][0]
    assert (tmp_path / "out" / "ocr.md").exists()
