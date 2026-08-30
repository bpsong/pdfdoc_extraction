"""Compare GLM-OCR text with page-aware Qwen vision extraction."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import ollama
import pymupdf


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = (
    REPOSITORY_ROOT
    / "fts_test_files"
    / "fts_data"
    / "S268588 1781061.pdf"
)
DEFAULT_OUTPUT_DIR = (
    REPOSITORY_ROOT / "experimenta" / "results" / "S268588_1781061"
)

GLM_TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}

ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "item_description": {"type": ["string", "null"]},
        "unit_of_measure": {"type": ["string", "null"]},
        "quantity": {"type": ["number", "null"]},
    },
    "required": ["item_description", "unit_of_measure", "quantity"],
    "additionalProperties": False,
}

PAGE_RESULT_SCHEMA: dict[str, Any] = {
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
        "invoice_or_delivery_order_number": {"type": ["string", "null"]},
        "purchase_order_number": {"type": ["string", "null"]},
        "fts_project_number": {"type": ["string", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "invoice_items": {
            "type": "array",
            "items": ITEM_SCHEMA,
        },
        "observations": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "page_number",
        "document_role",
        "visible_title",
        "supplier_name",
        "customer_name",
        "invoice_or_delivery_order_number",
        "purchase_order_number",
        "fts_project_number",
        "total_amount",
        "invoice_items",
        "observations",
    ],
    "additionalProperties": False,
}

FINAL_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": ["string", "null"]},
        "invoice_or_delivery_order_number": {"type": ["string", "null"]},
        "purchase_order_number": {"type": ["string", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "invoice_items": {
            "type": "array",
            "items": ITEM_SCHEMA,
        },
        "selected_invoice_pages": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
        },
        "assessment": {"type": "string"},
    },
    "required": [
        "supplier_name",
        "invoice_or_delivery_order_number",
        "purchase_order_number",
        "total_amount",
        "invoice_items",
        "selected_invoice_pages",
        "assessment",
    ],
    "additionalProperties": False,
}

GLM_TEXT_PROMPT = """\
Transcribe every visible character from this single PDF page.
Preserve headings, labels, values, reading order, and line breaks.
For tables, write one row per line and separate visible cells with ` | `.
Do not summarize, interpret, correct, classify, or omit repeated text.
Return JSON matching the supplied schema.
"""


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options for a reproducible local run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--glm-model", default="glm-ocr:latest")
    parser.add_argument("--qwen-model", default="qwen3.5:9b-q4_K_M")
    parser.add_argument("--dpi", type=int, default=216)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument(
        "--qwen-num-predict",
        type=int,
        default=None,
        help=(
            "Qwen generation budget. Defaults to 22000 with --think and 3072 "
            "without it."
        ),
    )
    parser.add_argument(
        "--qwen-num-ctx",
        type=int,
        default=None,
        help=(
            "Qwen context window. Defaults to 32768 with --think and 16384 "
            "without it."
        ),
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="Enable Qwen thinking mode for both vision and reconciliation calls.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed page artifacts already present in output-dir.",
    )
    parser.add_argument(
        "--qwen-only",
        action="store_true",
        help="Skip GLM-OCR and extract each page from its image alone.",
    )
    return parser.parse_args()


def render_pdf(pdf_path: Path, pages_dir: Path, dpi: int) -> list[bytes]:
    """Render each PDF page to PNG and retain the exact bytes sent to models."""
    if dpi <= 0:
        raise ValueError("dpi must be greater than zero")
    pages_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(pdf_path)
    try:
        if document.page_count < 1:
            raise ValueError("PDF has no pages")
        images: list[bytes] = []
        scale = dpi / 72.0
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            image_bytes = pixmap.tobytes("png")
            page_path = pages_dir / f"page_{page_index + 1:02d}.png"
            page_path.write_bytes(image_bytes)
            images.append(image_bytes)
        return images
    finally:
        document.close()


def response_text(response: Any, attribute: str) -> str:
    """Read a text value from Ollama SDK objects or mapping responses."""
    value = getattr(response, attribute, None)
    if value is None and isinstance(response, dict):
        value = response.get(attribute)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Ollama response did not contain non-empty {attribute}")
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
        raise RuntimeError("Ollama chat response did not contain assistant content")
    return content.strip()


def write_json(path: Path, value: Any) -> None:
    """Write stable, readable UTF-8 JSON."""
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def call_glm_text(
    client: ollama.Client,
    model: str,
    image_bytes: bytes,
) -> tuple[str, float]:
    """Return one page's layout-preserving GLM-OCR transcription."""
    started = time.perf_counter()
    response = client.generate(
        model=model,
        prompt=GLM_TEXT_PROMPT,
        images=[image_bytes],
        format=GLM_TEXT_SCHEMA,
        stream=False,
        options={
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": 4096,
        },
    )
    parsed = json.loads(response_text(response, "response"))
    text = parsed.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("GLM-OCR returned an empty page transcription")
    return text.strip(), time.perf_counter() - started


def page_prompt(page_number: int, glm_text: str | None) -> str:
    """Build the multimodal prompt for a single page."""
    if glm_text:
        evidence_instructions = """\
Use BOTH the supplied page image and the GLM-OCR transcription below.
The image is authoritative for page title, spatial relationships, and table
columns. The transcription helps with small text but may contain OCR errors.
"""
        evidence = f"""\
GLM-OCR transcription for page {page_number}:
---
{glm_text}
---
"""
    else:
        evidence_instructions = """\
Use only the supplied page image. No OCR transcription is available.
Inspect the complete image carefully, including small text and table columns.
"""
        evidence = ""
    return f"""\
You are examining page {page_number} of a multi-page business document.
{evidence_instructions}

Classify this page from its visible title. Extract only values visibly supported
on this page. FUJI TRADING (S) PTE LTD is the customer, never the supplier.
An FTS project number has the pattern S followed by digits, such as S268588; it
is not a supplier invoice or delivery-order number. Record it separately.

Populate invoice_items only when this page is explicitly titled Tax Invoice or
Invoice. Ignore tables on delivery orders, purchase orders, quotations, packing
lists, and duplicate invoice copies. A unit_of_measure must be explicit textual
unit information such as EA, PCS, SET, KG, or M. Never use a price, amount,
product code, SKU, tax code, TIN, or other identifier as unit_of_measure. Use
null when the invoice table has no explicit unit-of-measure column or value.

Preserve identifiers and descriptions exactly. Convert quantities and totals to
JSON numbers without inventing decimal places. Return JSON matching the schema.

{evidence}
"""


def call_qwen_page(
    client: ollama.Client,
    model: str,
    page_number: int,
    image_bytes: bytes,
    glm_text: str | None,
    think: bool,
    num_ctx: int,
    num_predict: int,
) -> tuple[dict[str, Any], float]:
    """Extract structured page evidence using Qwen image and text input."""
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": page_prompt(page_number, glm_text),
                "images": [image_bytes],
            }
        ],
        format=PAGE_RESULT_SCHEMA,
        stream=False,
        think=think,
        options={
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    )
    parsed = json.loads(message_text(response))
    returned_page_number = parsed.get("page_number")
    if returned_page_number != page_number:
        observations = parsed.get("observations")
        if not isinstance(observations, list):
            observations = []
            parsed["observations"] = observations
        observations.insert(
            0,
            (
                "Runner correction: Qwen returned page_number="
                f"{returned_page_number}; the supplied image is page {page_number}."
            ),
        )
        parsed["page_number"] = page_number
    return parsed, time.perf_counter() - started


def final_prompt(page_results: list[dict[str, Any]]) -> str:
    """Build a document reconciliation prompt from grounded page evidence."""
    evidence = json.dumps(page_results, indent=2, ensure_ascii=False)
    return f"""\
Reconcile the structured page evidence below into one invoice result.

Use explicitly titled Tax Invoice or Invoice pages as authoritative for supplier,
invoice number, total amount, and invoice_items. Use purchase-order or supporting
pages only to fill the purchase_order_number when necessary. Never use an FTS
project number matching S followed by digits as the invoice or delivery-order
number. FUJI TRADING (S) PTE LTD is the customer and cannot be supplier_name.

Return invoice items only from the selected invoice page. Do not combine or
deduplicate rows from delivery orders or purchase orders. A unit_of_measure must
be explicit textual unit information; otherwise return null. Preserve exact
descriptions and identifiers. Do not guess missing values. Return JSON matching
the supplied schema.

Page evidence:
{evidence}
"""


def call_qwen_final(
    client: ollama.Client,
    model: str,
    page_results: list[dict[str, Any]],
    think: bool,
    num_ctx: int,
    num_predict: int,
) -> tuple[dict[str, Any], float]:
    """Produce one document-level result from Qwen's page evidence."""
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": final_prompt(page_results)}],
        format=FINAL_RESULT_SCHEMA,
        stream=False,
        think=think,
        options={
            "temperature": 0,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    )
    parsed = json.loads(message_text(response))
    return parsed, time.perf_counter() - started


def verify_models(client: ollama.Client, required_models: list[str]) -> None:
    """Fail early when an expected Ollama model is not installed."""
    response = client.list()
    models = getattr(response, "models", None)
    if models is None and isinstance(response, dict):
        models = response.get("models", [])
    installed = {
        str(getattr(model, "model", None) or model.get("model"))
        if isinstance(model, dict)
        else str(getattr(model, "model", ""))
        for model in models or []
    }
    missing = [model for model in required_models if model not in installed]
    if missing:
        raise RuntimeError(f"Required Ollama models are missing: {missing}")


def main() -> int:
    """Run the complete experiment and retain all non-secret evidence."""
    args = parse_arguments()
    pdf_path = args.pdf.resolve()
    output_dir = args.output_dir.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    qwen_num_predict = args.qwen_num_predict
    if qwen_num_predict is None:
        qwen_num_predict = 22000 if args.think else 3072
    if qwen_num_predict <= 0:
        raise ValueError("qwen-num-predict must be greater than zero")
    qwen_num_ctx = args.qwen_num_ctx
    if qwen_num_ctx is None:
        qwen_num_ctx = 32768 if args.think else 16384
    if qwen_num_ctx <= qwen_num_predict:
        raise ValueError("qwen-num-ctx must be greater than qwen-num-predict")

    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    glm_dir = output_dir / "glm_ocr_text"
    qwen_dir = output_dir / "qwen_page_results"
    if not args.qwen_only:
        glm_dir.mkdir(parents=True, exist_ok=True)
    qwen_dir.mkdir(parents=True, exist_ok=True)

    client = ollama.Client(host=args.ollama_host, timeout=args.timeout_seconds)
    required_models = [args.qwen_model]
    if not args.qwen_only:
        required_models.insert(0, args.glm_model)
    verify_models(client, required_models)
    images = render_pdf(pdf_path, pages_dir, args.dpi)

    glm_texts: list[str] = []
    page_results: list[dict[str, Any]] = []
    call_timings: list[dict[str, Any]] = []
    for page_number, image_bytes in enumerate(images, start=1):
        glm_path = glm_dir / f"page_{page_number:02d}.txt"
        qwen_path = qwen_dir / f"page_{page_number:02d}.json"
        if args.qwen_only:
            print(
                f"Page {page_number}/{len(images)}: GLM-OCR skipped",
                flush=True,
            )
            glm_text = None
            glm_seconds = 0.0
            glm_stage = "glm_ocr_skipped"
        elif args.resume and glm_path.is_file():
            print(
                f"Page {page_number}/{len(images)}: reuse GLM-OCR transcription",
                flush=True,
            )
            glm_text = glm_path.read_text(encoding="utf-8").strip()
            if not glm_text:
                raise RuntimeError(f"Existing GLM-OCR text is empty: {glm_path}")
            glm_seconds = 0.0
            glm_stage = "glm_ocr_text_reused"
        else:
            print(
                f"Page {page_number}/{len(images)}: GLM-OCR transcription",
                flush=True,
            )
            glm_text, glm_seconds = call_glm_text(
                client,
                args.glm_model,
                image_bytes,
            )
            glm_path.write_text(glm_text + "\n", encoding="utf-8")
            glm_stage = "glm_ocr_text"
        if glm_text is not None:
            glm_texts.append(glm_text)
        call_timings.append(
            {
                "page_number": page_number,
                "stage": glm_stage,
                "seconds": round(glm_seconds, 3),
            }
        )

        if args.resume and qwen_path.is_file():
            print(
                f"Page {page_number}/{len(images)}: reuse Qwen vision result",
                flush=True,
            )
            page_result = json.loads(qwen_path.read_text(encoding="utf-8"))
            qwen_seconds = 0.0
            qwen_stage = "qwen_page_vision_reused"
        else:
            print(
                f"Page {page_number}/{len(images)}: Qwen vision extraction",
                flush=True,
            )
            page_result, qwen_seconds = call_qwen_page(
                client,
                args.qwen_model,
                page_number,
                image_bytes,
                glm_text,
                args.think,
                qwen_num_ctx,
                qwen_num_predict,
            )
            write_json(qwen_path, page_result)
            qwen_stage = "qwen_page_vision"
        page_results.append(page_result)
        call_timings.append(
            {
                "page_number": page_number,
                "stage": qwen_stage,
                "seconds": round(qwen_seconds, 3),
            }
        )

    if not args.qwen_only:
        combined_text = "\n\n".join(
            f"===== PAGE {index} =====\n{text}"
            for index, text in enumerate(glm_texts, start=1)
        )
        (output_dir / "glm_ocr_all_pages.txt").write_text(
            combined_text + "\n",
            encoding="utf-8",
        )
    write_json(output_dir / "qwen_all_page_results.json", page_results)

    print("Document reconciliation: Qwen", flush=True)
    final_result, final_seconds = call_qwen_final(
        client,
        args.qwen_model,
        page_results,
        args.think,
        qwen_num_ctx,
        qwen_num_predict,
    )
    write_json(output_dir / "final_result.json", final_result)
    call_timings.append(
        {
            "page_number": None,
            "stage": "qwen_document_reconciliation",
            "seconds": round(final_seconds, 3),
        }
    )

    run_summary = {
        "source_pdf": str(pdf_path),
        "source_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "page_count": len(images),
        "experiment_mode": "qwen_vision_only" if args.qwen_only else "glm_text_and_qwen_vision",
        "glm_model": None if args.qwen_only else args.glm_model,
        "qwen_model": args.qwen_model,
        "qwen_think": args.think,
        "qwen_num_ctx": qwen_num_ctx,
        "qwen_num_predict": qwen_num_predict,
        "dpi": args.dpi,
        "calls": call_timings,
    }
    write_json(output_dir / "run_summary.json", run_summary)
    print(f"Experiment complete: {output_dir}", flush=True)
    print(json.dumps(final_result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
