"""Run a resumable 40-PDF comparison of two local vision extraction paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import ollama
import pymupdf


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experimenta" / "results" / "batch_40_comparison"
FTS_SOURCE = ROOT / "fts_test_files" / "fts_data"
SUPERSTORE_SOURCE = ROOT / "sample stock invoices from internet"
GLM_PROMPT = """\
Transcribe every visible character from this single PDF page.
Preserve headings, labels, values, reading order, and line breaks.
For tables, write one row per line and separate visible cells with ` | `.
Do not summarize, interpret, correct, classify, or omit repeated text.
Return only the transcription text, without a JSON wrapper.
"""
ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "item_description": {"type": ["string", "null"]},
        "unit_of_measure": {"type": ["string", "null"]},
        "quantity": {"type": ["number", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "amount": {"type": ["number", "null"]},
    },
    "required": [
        "item_description",
        "unit_of_measure",
        "quantity",
        "unit_price",
        "amount",
    ],
    "additionalProperties": False,
}
PAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "page_number": {"type": "integer", "minimum": 1},
        "document_role": {
            "type": "string",
            "enum": [
                "tax_invoice",
                "invoice",
                "delivery_order",
                "purchase_order",
                "other",
            ],
        },
        "visible_title": {"type": ["string", "null"]},
        "supplier_name": {"type": ["string", "null"]},
        "customer_name": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "purchase_order_number": {"type": ["string", "null"]},
        "fts_project_number": {"type": ["string", "null"]},
        "invoice_date": {"type": ["string", "null"]},
        "bill_to": {"type": ["string", "null"]},
        "ship_to": {"type": ["string", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "line_items": {"type": "array", "items": ITEM_SCHEMA},
        "observations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "page_number",
        "document_role",
        "visible_title",
        "supplier_name",
        "customer_name",
        "invoice_number",
        "purchase_order_number",
        "fts_project_number",
        "invoice_date",
        "bill_to",
        "ship_to",
        "total_amount",
        "line_items",
        "observations",
    ],
    "additionalProperties": False,
}
FINAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "purchase_order_number": {"type": ["string", "null"]},
        "invoice_date": {"type": ["string", "null"]},
        "bill_to": {"type": ["string", "null"]},
        "ship_to": {"type": ["string", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "line_items": {"type": "array", "items": ITEM_SCHEMA},
        "selected_invoice_pages": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
        },
        "assessment": {"type": "string"},
    },
    "required": [
        "supplier_name",
        "invoice_number",
        "purchase_order_number",
        "invoice_date",
        "bill_to",
        "ship_to",
        "total_amount",
        "line_items",
        "selected_invoice_pages",
        "assessment",
    ],
    "additionalProperties": False,
}

T = TypeVar("T")


def parse_args() -> argparse.Namespace:
    """Parse reproducible batch options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--fts-count", type=int, default=10)
    parser.add_argument("--superstore-count", type=int, default=30)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--glm-model", default="glm-ocr:latest")
    parser.add_argument("--qwen-model", default="qwen3.5:9b-q4_K_M")
    parser.add_argument("--dpi", type=int, default=216)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--num-predict", type=int, default=3072)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--stage",
        choices=["all", "glm", "glm_qwen", "qwen_only"],
        default="all",
    )
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    """Write deterministic UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    """Hash one source file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_slug(name: str) -> str:
    """Return a stable filesystem-safe document key."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_.")


def page_count(path: Path) -> int:
    """Read a PDF page count."""
    with pymupdf.open(path) as document:
        return document.page_count


def create_or_load_manifest(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Freeze the seeded sample on first run and reuse it thereafter."""
    manifest_path = args.output_dir / "sample_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        documents = manifest.get("documents")
        if not isinstance(documents, list):
            raise ValueError(f"Invalid manifest: {manifest_path}")
        return documents

    fts = sorted(FTS_SOURCE.glob("*.pdf"), key=lambda path: path.name.lower())
    superstore = sorted(
        (
            path
            for path in SUPERSTORE_SOURCE.glob("invoice_*.pdf")
            if not path.name.startswith("random_merged_")
        ),
        key=lambda path: path.name.lower(),
    )
    if len(fts) < args.fts_count or len(superstore) < args.superstore_count:
        raise ValueError("Source pools do not contain enough eligible PDFs")
    rng = random.Random(args.seed)
    selected = [
        *(('fts', path) for path in rng.sample(fts, args.fts_count)),
        *(('superstore', path) for path in rng.sample(superstore, args.superstore_count)),
    ]
    documents: list[dict[str, Any]] = []
    for index, (kind, path) in enumerate(selected, start=1):
        resolved = path.resolve()
        documents.append(
            {
                "index": index,
                "kind": kind,
                "source_pdf": str(resolved),
                "source_name": resolved.name,
                "source_sha256": sha256(resolved),
                "page_count": page_count(resolved),
                "document_key": f"{index:02d}_{kind}_{safe_slug(resolved.stem)}",
            }
        )
    write_json(
        manifest_path,
        {
            "seed": args.seed,
            "fts_source": str(FTS_SOURCE.resolve()),
            "superstore_source": str(SUPERSTORE_SOURCE.resolve()),
            "fts_eligible_count": len(fts),
            "superstore_eligible_count": len(superstore),
            "documents": documents,
        },
    )
    return documents


def response_text(response: Any, attribute: str) -> str:
    """Read response text from an Ollama object or mapping."""
    value = getattr(response, attribute, None)
    if value is None and isinstance(response, dict):
        value = response.get(attribute)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Ollama response has no non-empty {attribute}")
    return value.strip()


def message_text(response: Any) -> str:
    """Read assistant content from an Ollama chat response."""
    message = getattr(response, "message", None)
    if message is None and isinstance(response, dict):
        message = response.get("message")
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama response has no assistant content")
    return content.strip()


def retry(label: str, attempts: int, operation: Callable[[], T]) -> T:
    """Retry transient local-model failures with bounded backoff."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (json.JSONDecodeError, RuntimeError, ConnectionError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = min(5 * attempt, 15)
            print(
                f"{label}: attempt {attempt}/{attempts} failed; retry in {delay}s: {exc}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"{label} failed after {attempts} attempts") from last_error


def verify_models(client: ollama.Client, models: list[str]) -> None:
    """Fail before the long run if a required model is unavailable."""
    response = client.list()
    entries = getattr(response, "models", None)
    if entries is None and isinstance(response, dict):
        entries = response.get("models", [])
    installed = {
        str(entry.get("model", ""))
        if isinstance(entry, dict)
        else str(getattr(entry, "model", ""))
        for entry in entries or []
    }
    missing = [model for model in models if model not in installed]
    if missing:
        raise RuntimeError(f"Required Ollama models are missing: {missing}")


def ensure_rendered(document: dict[str, Any], output: Path, dpi: int) -> list[Path]:
    """Render pages once and return stable PNG paths."""
    pages_dir = output / document["document_key"] / "pages"
    expected = int(document["page_count"])
    existing = [pages_dir / f"page_{index:02d}.png" for index in range(1, expected + 1)]
    if all(path.is_file() for path in existing):
        return existing
    pages_dir.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(document["source_pdf"]) as pdf:
        scale = dpi / 72.0
        for index, page in enumerate(pdf, start=1):
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            (pages_dir / f"page_{index:02d}.png").write_bytes(
                pixmap.tobytes("png")
            )
    return existing


def call_glm(client: ollama.Client, model: str, image: bytes) -> tuple[str, float]:
    """Transcribe one rendered page with GLM-OCR."""
    started = time.perf_counter()
    response = client.generate(
        model=model,
        prompt=GLM_PROMPT,
        images=[image],
        stream=False,
        options={"temperature": 0, "num_ctx": 16384, "num_predict": 8192},
    )
    text = response_text(response, "response")
    return text, time.perf_counter() - started


def evidence_preamble(page_number: int, glm_text: str | None) -> str:
    """Describe the evidence available to Qwen for one page."""
    if glm_text is None:
        return """\
Use only the supplied page image. No OCR transcription is available. Inspect
the complete image carefully, including small text and table columns.
"""
    return f"""\
Use BOTH the supplied page image and the GLM-OCR transcription below. The image
is authoritative for page title, spatial relationships, and table columns. The
transcription helps with small text but may contain OCR errors.

GLM-OCR transcription for page {page_number}:
---
{glm_text}
---
"""


def page_prompt(kind: str, page_number: int, glm_text: str | None) -> str:
    """Build document-profile guidance while keeping evidence paths equal."""
    evidence = evidence_preamble(page_number, glm_text)
    if kind == "fts":
        guidance = """\
FUJI TRADING (S) PTE LTD is the customer, never the supplier. An FTS project
number has the pattern S followed by digits, such as S268588; store it only as
fts_project_number, never as invoice_number. Extract values only when visible.

Populate line_items only from a page explicitly titled Tax Invoice or Invoice.
Ignore item tables on delivery orders, purchase orders, quotations, packing
lists, and duplicate invoice copies. Extract item_description,
unit_of_measure, and quantity. Set unit_price and amount to null unless they are
explicit on that invoice row. A unit_of_measure must be a textual unit such as
EA, PCS, SET, KG, or M; never use a price, code, SKU, tax code, or identifier.
Set invoice_date, bill_to, and ship_to to null for this FTS profile.
"""
    else:
        guidance = """\
This is a SuperStore invoice. SuperStore is the supplier. Extract invoice_number
from the value beside the # symbol and invoice_date from Date. bill_to must be
only the person name under Bill To, without any address. ship_to must contain
the complete address under Ship To across all visible lines, preserving its
content in one string. Extract Total, not Balance Due or Subtotal.

For every invoice table row, extract the product name as item_description plus
its Quantity, Rate as unit_price, and Amount. The category/product-code line
under a product is supporting detail, not a separate item. Set unit_of_measure
to null because this invoice has no unit-of-measure column. Set
purchase_order_number and fts_project_number to null.
"""
    return f"""\
You are examining page {page_number} of a business document. Classify the page
from its visible title and return only values visibly supported on this page.
{evidence}
{guidance}
Preserve identifiers and descriptions exactly. Convert quantities and money to
JSON numbers. Do not guess missing values. Return JSON matching the schema.
"""


def call_qwen_page(
    client: ollama.Client,
    model: str,
    kind: str,
    page_number: int,
    image: bytes,
    glm_text: str | None,
    num_ctx: int,
    num_predict: int,
) -> tuple[dict[str, Any], float]:
    """Extract page evidence with non-thinking Qwen vision."""
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": page_prompt(kind, page_number, glm_text),
                "images": [image],
            }
        ],
        format=PAGE_SCHEMA,
        stream=False,
        think=False,
        options={
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    )
    parsed = json.loads(message_text(response))
    if parsed.get("page_number") != page_number:
        observations = parsed.get("observations")
        if not isinstance(observations, list):
            observations = []
            parsed["observations"] = observations
        observations.insert(
            0,
            f"Runner corrected page_number to supplied page {page_number}.",
        )
        parsed["page_number"] = page_number
    return parsed, time.perf_counter() - started


def final_prompt(kind: str, pages: list[dict[str, Any]]) -> str:
    """Build profile-specific document reconciliation guidance."""
    if kind == "fts":
        guidance = """\
Use explicitly titled Tax Invoice or Invoice pages as authoritative for
supplier_name, invoice_number, total_amount, and line_items. Use purchase-order
or supporting pages only to fill purchase_order_number. FUJI TRADING (S) PTE
LTD is the customer and cannot be supplier_name. Never use an S-digits FTS
project number as invoice_number. Return line items only from the selected
invoice page; do not combine purchase-order or delivery-order rows. Keep
invoice_date, bill_to, and ship_to null.
"""
    else:
        guidance = """\
Reconcile the SuperStore invoice pages. SuperStore is supplier_name. bill_to is
only the person name without address. ship_to is the full multiline address in
one string. Use Total, not Balance Due or Subtotal. Return each invoice product
row once with description, quantity, unit_price, and amount; category/code text
is not a separate row. Keep purchase_order_number null.
"""
    evidence = json.dumps(pages, indent=2, ensure_ascii=False)
    return f"""\
Reconcile the structured page evidence into one invoice result.
{guidance}
Preserve exact identifiers and descriptions. Do not guess missing values.
Return JSON matching the supplied schema.

Page evidence:
{evidence}
"""


def call_qwen_final(
    client: ollama.Client,
    model: str,
    kind: str,
    pages: list[dict[str, Any]],
    num_ctx: int,
    num_predict: int,
) -> tuple[dict[str, Any], float]:
    """Reconcile page evidence with non-thinking Qwen."""
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": final_prompt(kind, pages)}],
        format=FINAL_SCHEMA,
        stream=False,
        think=False,
        options={
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    )
    return json.loads(message_text(response)), time.perf_counter() - started


def run_glm_stage(
    client: ollama.Client,
    args: argparse.Namespace,
    documents: list[dict[str, Any]],
) -> None:
    """Produce reusable GLM page text for the selected corpus."""
    total_pages = sum(int(document["page_count"]) for document in documents)
    progress = 0
    for document in documents:
        page_paths = ensure_rendered(document, args.output_dir, args.dpi)
        glm_dir = args.output_dir / document["document_key"] / "glm_ocr_text"
        glm_dir.mkdir(parents=True, exist_ok=True)
        for page_number, page_path in enumerate(page_paths, start=1):
            progress += 1
            text_path = glm_dir / f"page_{page_number:02d}.txt"
            timing_path = glm_dir / f"page_{page_number:02d}_timing.json"
            if text_path.is_file() and text_path.read_text(encoding="utf-8").strip():
                print(f"GLM {progress}/{total_pages}: reuse {document['source_name']} p{page_number}", flush=True)
                continue
            print(f"GLM {progress}/{total_pages}: {document['source_name']} p{page_number}", flush=True)
            text, seconds = retry(
                f"GLM {document['source_name']} p{page_number}",
                args.retries,
                lambda p=page_path: call_glm(client, args.glm_model, p.read_bytes()),
            )
            text_path.write_text(text + "\n", encoding="utf-8")
            write_json(timing_path, {"seconds": round(seconds, 3)})


def run_qwen_method(
    client: ollama.Client,
    args: argparse.Namespace,
    documents: list[dict[str, Any]],
    method: str,
) -> None:
    """Run one Qwen evidence path over the complete frozen corpus."""
    use_glm = method == "glm_qwen"
    total = len(documents)
    for position, document in enumerate(documents, start=1):
        doc_dir = args.output_dir / document["document_key"]
        method_dir = doc_dir / method
        final_path = method_dir / "final_result.json"
        if final_path.is_file():
            print(f"{method} {position}/{total}: reuse {document['source_name']}", flush=True)
            continue
        method_dir.mkdir(parents=True, exist_ok=True)
        page_paths = ensure_rendered(document, args.output_dir, args.dpi)
        page_results: list[dict[str, Any]] = []
        timings: list[dict[str, Any]] = []
        for page_number, page_path in enumerate(page_paths, start=1):
            result_path = method_dir / f"page_{page_number:02d}.json"
            timing_path = method_dir / f"page_{page_number:02d}_timing.json"
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                page_results.append(result)
                timings.append(
                    json.loads(timing_path.read_text(encoding="utf-8"))
                    if timing_path.is_file()
                    else {"page_number": page_number, "seconds": 0.0, "reused": True}
                )
                continue
            glm_text = None
            if use_glm:
                glm_path = doc_dir / "glm_ocr_text" / f"page_{page_number:02d}.txt"
                glm_text = glm_path.read_text(encoding="utf-8").strip()
            print(
                f"{method} {position}/{total}: {document['source_name']} p{page_number}/{len(page_paths)}",
                flush=True,
            )
            result, seconds = retry(
                f"{method} {document['source_name']} p{page_number}",
                args.retries,
                lambda p=page_path, n=page_number, text=glm_text: call_qwen_page(
                    client,
                    args.qwen_model,
                    document["kind"],
                    n,
                    p.read_bytes(),
                    text,
                    args.num_ctx,
                    args.num_predict,
                ),
            )
            write_json(result_path, result)
            timing = {"page_number": page_number, "seconds": round(seconds, 3)}
            write_json(timing_path, timing)
            page_results.append(result)
            timings.append(timing)
        print(f"{method} {position}/{total}: reconcile {document['source_name']}", flush=True)
        final, final_seconds = retry(
            f"{method} reconcile {document['source_name']}",
            args.retries,
            lambda: call_qwen_final(
                client,
                args.qwen_model,
                document["kind"],
                page_results,
                args.num_ctx,
                args.num_predict,
            ),
        )
        write_json(final_path, final)
        timings.append(
            {"stage": "document_reconciliation", "seconds": round(final_seconds, 3)}
        )
        write_json(
            method_dir / "run_summary.json",
            {
                "method": method,
                "qwen_think": False,
                "qwen_model": args.qwen_model,
                "glm_model": args.glm_model if use_glm else None,
                "num_ctx": args.num_ctx,
                "num_predict": args.num_predict,
                "dpi": args.dpi,
                "timings": timings,
            },
        )


def write_progress(output: Path, documents: list[dict[str, Any]]) -> None:
    """Summarize durable stage completion after any run."""
    rows = []
    for document in documents:
        doc_dir = output / document["document_key"]
        pages = int(document["page_count"])
        rows.append(
            {
                "document_key": document["document_key"],
                "source_name": document["source_name"],
                "kind": document["kind"],
                "page_count": pages,
                "glm_pages_complete": sum(
                    (doc_dir / "glm_ocr_text" / f"page_{index:02d}.txt").is_file()
                    for index in range(1, pages + 1)
                ),
                "glm_qwen_complete": (doc_dir / "glm_qwen" / "final_result.json").is_file(),
                "qwen_only_complete": (doc_dir / "qwen_only" / "final_result.json").is_file(),
            }
        )
    write_json(
        output / "progress.json",
        {
            "documents": rows,
            "totals": {
                "documents": len(rows),
                "pages": sum(row["page_count"] for row in rows),
                "glm_pages_complete": sum(row["glm_pages_complete"] for row in rows),
                "glm_qwen_complete": sum(row["glm_qwen_complete"] for row in rows),
                "qwen_only_complete": sum(row["qwen_only_complete"] for row in rows),
            },
        },
    )


def main() -> int:
    """Run selected stages and preserve enough state for safe resumption."""
    args = parse_args()
    args.output_dir = args.output_dir.resolve()
    if args.dpi <= 0 or args.num_ctx <= args.num_predict or args.retries < 1:
        raise ValueError("Invalid DPI, context/generation budget, or retry count")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    documents = create_or_load_manifest(args)
    client = ollama.Client(host=args.ollama_host, timeout=args.timeout_seconds)
    needed = [args.qwen_model]
    if args.stage in {"all", "glm", "glm_qwen"}:
        needed.insert(0, args.glm_model)
    verify_models(client, needed)
    try:
        if args.stage in {"all", "glm"}:
            run_glm_stage(client, args, documents)
        if args.stage in {"all", "glm_qwen"}:
            run_qwen_method(client, args, documents, "glm_qwen")
        if args.stage in {"all", "qwen_only"}:
            run_qwen_method(client, args, documents, "qwen_only")
    finally:
        write_progress(args.output_dir, documents)
    print(f"Batch stage complete: {args.stage}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
