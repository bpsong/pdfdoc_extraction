"""Serve the PDF.js bounding-box review experiment."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


EXPERIMENT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = EXPERIMENT_DIR.parents[1]
PUBLIC_DIR = EXPERIMENT_DIR / "public"
DEFAULT_PDF = REPOSITORY_ROOT / "sample_invoice.pdf"
DEFAULT_JSON = EXPERIMENT_DIR.parent / "llama-extract-sample_invoice.json"


def resolve_path(value: str, default: Path) -> Path:
    """Resolve a CLI path from the current directory, falling back to a default."""
    if not value:
        return default.resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


class ViewerServer(ThreadingHTTPServer):
    """HTTP server carrying the two experiment input paths."""

    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler_class: type[SimpleHTTPRequestHandler], pdf_path: Path, json_path: Path) -> None:
        super().__init__(address, handler_class)
        self.pdf_path = pdf_path
        self.json_path = json_path


class ViewerHandler(SimpleHTTPRequestHandler):
    """Serve the viewer UI, its JSON data, and the source PDF."""

    server: ViewerServer

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        route = urlparse(self.path).path
        if route == "/api/data":
            self._send_json()
            return
        if route == "/api/pdf":
            self._send_pdf()
            return
        if route == "/":
            self.path = "/index.html"
        super().do_GET()

    def _send_json(self) -> None:
        try:
            payload = json.loads(self.server.json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.send_error(500, f"Unable to read extraction JSON: {exc}")
            return

        payload["pdf_url"] = "/api/pdf"
        payload["source_filename"] = self.server.pdf_path.name
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_pdf(self) -> None:
        pdf_path = self.server.pdf_path
        if not pdf_path.is_file():
            self.send_error(404, "PDF file not found")
            return

        try:
            size = pdf_path.stat().st_size
            with pdf_path.open("rb") as source:
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f'inline; filename="{pdf_path.name}"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.copyfile(source, self.wfile)
        except OSError as exc:
            self.send_error(500, f"Unable to read PDF: {exc}")

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[viewer] {self.address_string()} - {format_string % args}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    """Parse standalone server options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind")
    parser.add_argument("--pdf", default="", help="PDF path; defaults to the repository sample invoice")
    parser.add_argument("--json", dest="json_path", default="", help="LlamaCloud JSON path; defaults to experimentb output")
    return parser.parse_args()


def main() -> None:
    """Start the local experiment server."""
    args = parse_args()
    pdf_path = resolve_path(args.pdf, DEFAULT_PDF)
    json_path = resolve_path(args.json_path, DEFAULT_JSON)
    missing = [str(path) for path in (pdf_path, json_path) if not path.is_file()]
    if missing:
        raise SystemExit(f"Input file(s) not found: {', '.join(missing)}")

    server = ViewerServer((args.host, args.port), ViewerHandler, pdf_path, json_path)
    print(f"PDF.js citation viewer: http://{args.host}:{args.port}/")
    print(f"PDF: {pdf_path}")
    print(f"JSON: {json_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping viewer server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
