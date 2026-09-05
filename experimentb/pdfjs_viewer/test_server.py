"""Focused checks for the standalone citation viewer server."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import urlopen

from experimentb.pdfjs_viewer.server import ViewerHandler, ViewerServer, resolve_path


def test_default_experiment_input_path(tmp_path: Path) -> None:
    """An omitted CLI input resolves to the supplied local default."""
    default = tmp_path / "sample.pdf"
    assert resolve_path("", default) == default.resolve()


def test_data_endpoint_exposes_sample_metadata(tmp_path: Path) -> None:
    """The server exposes the extracted fields and the PDF route."""
    pdf_path = tmp_path / "sample_invoice.pdf"
    json_path = tmp_path / "extraction.json"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    json_path.write_text(json.dumps({"data": {"supplier_name": "Synthetic Supplier"}}), encoding="utf-8")
    server = ViewerServer(("127.0.0.1", 0), ViewerHandler, pdf_path, json_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/data"
        with urlopen(url) as response:
            payload = json.load(response)
        assert payload["pdf_url"] == "/api/pdf"
        assert payload["source_filename"] == "sample_invoice.pdf"
        assert payload["data"] == {"supplier_name": "Synthetic Supplier"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
