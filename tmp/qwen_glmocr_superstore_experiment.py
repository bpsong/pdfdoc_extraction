"""Throwaway GLM-OCR-to-Qwen Superstore header and line-item experiment."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import ollama
import pymupdf
from glmocr import GlmOcr, __version__ as glmocr_version


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "sample stock invoices from internet"
DEFAULT_CHECKPOINT = ROOT / "tmp" / "qwen_glmocr_superstore_checkpoint.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "qwen_glmocr_superstore_results.json"
OCR_MODEL = "glm-ocr:latest"
RESOLVER_MODEL = "qwen3.5:9b-q4_K_M"
OLLAMA_HOST = "http://127.0.0.1:11434"
EXPERIMENT_VERSION = 7

HEADER_FIELDS = {
    "row_id": "Invoice number printed after the INVOICE heading and # symbol.",
    "order_date": "Date printed beside Date. Preserve the printed month format.",
    "ship_mode": "Shipping service printed beside Ship Mode.",
    "customer_name": "Customer name printed in the Bill To block.",
    "ship_to_address": (
        "Complete address printed in the Ship To block, joined into one line "
        "without omitting postal code, city, state or region, or country."
    ),
    "order_id": "Exact identifier printed after Order ID in the Terms section.",
    "invoice_subtotal": "Numeric amount printed beside Subtotal, before discount and shipping.",
    "discount_percent": (
        "Numeric percentage inside the Discount label, not the discount currency "
        "amount. Return empty when no Discount row is printed."
    ),
    "shipping_fee": "Numeric currency amount printed beside Shipping.",
    "total_amount_payable": "Final numeric amount printed beside Total or Balance Due.",
}

LINE_ITEM_FIELDS = {
    "product_name": "Product name from the first text line in the Item column.",
    "sub_category": "First comma-separated classification below the product name.",
    "category": "Second comma-separated classification below the product name.",
    "product_id": "Third comma-separated identifier below the product name.",
    "quantity": "Numeric value in the Quantity column.",
    "unit_cost": "Numeric value in the Rate column, without currency symbols or commas.",
    "subtotal": "Numeric value in the Amount column, without currency symbols or commas.",
}

NUMERIC_HEADERS = {
    "invoice_subtotal",
    "discount_percent",
    "shipping_fee",
    "total_amount_payable",
}
REQUIRED_HEADERS = set(HEADER_FIELDS) - {"discount_percent"}

GROUND_TRUTH: dict[str, dict[str, Any]] = {
    "invoice_Aaron Bergman_36258.pdf": {
        "headers": {
            "row_id": "36258",
            "order_date": "Mar 06 2012",
            "ship_mode": "First Class",
            "customer_name": "Aaron Bergman",
            "ship_to_address": "98103, Seattle, Washington, United States",
            "order_id": "CA-2012-AB10015140-40974",
            "invoice_subtotal": 48.71,
            "discount_percent": 20.0,
            "shipping_fee": 11.13,
            "total_amount_payable": 50.10,
        },
        "line_items": [
            {
                "product_name": "Global Push Button Manager's Chair, Indigo",
                "sub_category": "Chairs",
                "category": "Furniture",
                "product_id": "FUR-CH-4421",
                "quantity": 1.0,
                "unit_cost": 48.71,
                "subtotal": 48.71,
            }
        ],
    },
    "invoice_Aaron Bergman_36259.pdf": {
        "headers": {
            "row_id": "36259",
            "order_date": "Mar 06 2012",
            "ship_mode": "First Class",
            "customer_name": "Aaron Bergman",
            "ship_to_address": "98103, Seattle, Washington, United States",
            "order_id": "CA-2012-AB10015140-40974",
            "invoice_subtotal": 53.82,
            "discount_percent": None,
            "shipping_fee": 4.29,
            "total_amount_payable": 58.11,
        },
        "line_items": [
            {
                "product_name": "Newell 330",
                "sub_category": "Art",
                "category": "Office Supplies",
                "product_id": "OFF-AR-5309",
                "quantity": 3.0,
                "unit_cost": 17.94,
                "subtotal": 53.82,
            }
        ],
    },
    "invoice_Steven Ward_9240.pdf": {
        "headers": {
            "row_id": "9240",
            "order_date": "Dec 07 2012",
            "ship_mode": "Standard Class",
            "customer_name": "Steven Ward",
            "ship_to_address": "Matagalpa, Matagalpa, Nicaragua",
            "order_id": "MX-2012-SW2075593-41250",
            "invoice_subtotal": 9106.0,
            "discount_percent": None,
            "shipping_fee": 78.5,
            "total_amount_payable": 9184.5,
        },
        "line_items": [
            {
                "product_name": "Nokia Signal Booster, VoIP",
                "sub_category": "Phones",
                "category": "Technology",
                "product_id": "TEC-PH-5352",
                "quantity": 10.0,
                "unit_cost": 910.6,
                "subtotal": 9106.0,
            }
        ],
    },
    "invoice_Tamara Chand_41648.pdf": {
        "headers": {
            "row_id": "41648",
            "order_date": "Jun 07 2012",
            "ship_mode": "Same Day",
            "customer_name": "Tamara Chand",
            "ship_to_address": "Baku, Baki, Azerbaijan",
            "order_id": "AJ-2012-TC109809-41067",
            "invoice_subtotal": 454.71,
            "discount_percent": None,
            "shipping_fee": 147.24,
            "total_amount_payable": 601.95,
        },
        "line_items": [
            {
                "product_name": "Hon Executive Leather Armchair, Adjustable",
                "sub_category": "Chairs",
                "category": "Furniture",
                "product_id": "FUR-CH-4654",
                "quantity": 1.0,
                "unit_cost": 454.71,
                "subtotal": 454.71,
            }
        ],
    },
}


def parse_args() -> argparse.Namespace:
    """Parse experiment arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolver-model", default=RESOLVER_MODEL)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser.parse_args()


def sdk_overrides() -> dict[str, Any]:
    """Configure the official self-hosted SDK for bounded local OCR calls."""
    return {
        "pipeline.ocr_api.api_path": "/api/generate",
        "pipeline.ocr_api.api_mode": "ollama_generate",
        "pipeline.ocr_api.request_timeout": 300,
        "pipeline.ocr_api.connection_pool_size": 4,
        "pipeline.max_workers": 1,
        "pipeline.page_loader.pdf_dpi": 200,
        "pipeline.page_loader.max_tokens": 512,
        "logging.level": "INFO",
    }


def create_sdk_parser() -> GlmOcr:
    """Create the official SDK parser against the local Ollama GLM model."""
    return GlmOcr(
        mode="selfhosted",
        model=OCR_MODEL,
        ocr_api_host="127.0.0.1",
        ocr_api_port=11434,
        layout_device="cpu",
        _dotted=sdk_overrides(),
    )


def clean_region_content(content: str) -> str:
    """Remove repeated SDK formatting while preserving visible OCR text."""
    text = unicodedata.normalize("NFKC", html.unescape(content))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</t[dh]\s*>", " | ", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.replace("```markdown", "").replace("```", "")
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = re.sub(r"\s+", " ", line).strip().strip("| ")
        if (
            not line
            or line == "---"
            or line.casefold().startswith(("答:", "markdown:"))
            or line.casefold() in seen
        ):
            continue
        seen.add(line.casefold())
        lines.append(line)
    return "\n".join(lines)


def parse_pdf(parser: GlmOcr, pdf_path: Path) -> dict[str, Any]:
    """Parse one PDF and retain compact page-aware layout evidence."""
    started = time.perf_counter()
    result = parser.parse(str(pdf_path), save_layout_visualization=False, preserve_order=True)
    if not isinstance(result.json_result, list):
        raise TypeError("SDK json_result must contain a list of pages")
    pages: list[dict[str, Any]] = []
    for page_number, raw_regions in enumerate(result.json_result, start=1):
        if not isinstance(raw_regions, list):
            raise TypeError(f"SDK page {page_number} has no region list")
        blocks: list[str] = []
        seen: set[str] = set()
        for fallback_index, region in enumerate(raw_regions):
            if not isinstance(region, dict):
                continue
            content = region.get("content")
            if not isinstance(content, str):
                continue
            cleaned = clean_region_content(content)
            identity = re.sub(r"\s+", " ", cleaned).casefold()
            if not cleaned or identity in seen:
                continue
            seen.add(identity)
            label = str(region.get("native_label") or region.get("label") or "text")
            index = int(region.get("index", fallback_index)) + 1
            blocks.append(f"[REGION {index}: {label}]\n{cleaned}")
        pages.append({"page": page_number, "text": "\n\n".join(blocks)})
    return {
        "pages": pages,
        "region_count": sum(page["text"].count("[REGION ") for page in pages),
        "char_count": sum(len(page["text"]) for page in pages),
        "seconds": round(time.perf_counter() - started, 3),
    }


def load_checkpoint(path: Path) -> dict[str, Any]:
    """Load a resumable checkpoint when present."""
    if not path.exists():
        return {"version": EXPERIMENT_VERSION, "parses": {}, "results": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Checkpoint must be a JSON object")
    payload.setdefault("parses", {})
    if payload.get("version") != EXPERIMENT_VERSION:
        payload["version"] = EXPERIMENT_VERSION
        payload["results"] = {}
    else:
        payload.setdefault("results", {})
    return payload


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    """Persist resumable experiment state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def page_evidence(pages: list[dict[str, Any]]) -> str:
    """Format compact OCR pages for Qwen."""
    return "\n\n".join(
        f"===== PAGE {page['page']} =====\n{compact_evidence_text(str(page['text']))}"
        for page in pages
    )


def compact_evidence_text(text: str) -> str:
    """Collapse Unicode, truncated alternatives, and repeated OCR table rows."""
    normalized = unicodedata.normalize("NFKC", text)
    candidates: list[str] = []
    for raw_line in normalized.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line.casefold().startswith(("答:", "markdown:")):
            continue
        line = re.sub(r"\$\s+", "$", line)
        line = re.sub(r"\s*,\s*", ", ", line)
        line = re.sub(r",\s+(?=\d{3}\b)", ",", line)
        candidates.append(line)

    def identity(line: str) -> str:
        value = line.casefold()
        value = re.sub(r"\s+", "", value)
        value = value.replace("$", "")
        return value

    unique: list[str] = []
    identities: list[str] = []
    for line in candidates:
        key = identity(line)
        if key in identities:
            continue
        identities.append(key)
        unique.append(line)

    kept: list[str] = []
    for index, line in enumerate(unique):
        key = identities[index]
        is_truncated = any(
            other.startswith(key)
            and len(other) > len(key)
            and not line.startswith("[REGION ")
            for other_index, other in enumerate(identities)
            if other_index != index
        )
        if not is_truncated:
            kept.append(line)
    return "\n".join(kept)


def evidence_schema(max_page: int) -> dict[str, Any]:
    """Return reusable exact-quote evidence schema."""
    return {
        "type": "array",
        "maxItems": 3,
        "items": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "minimum": 1, "maximum": max_page},
                "quote": {"type": "string", "maxLength": 240},
            },
            "required": ["page", "quote"],
            "additionalProperties": False,
        },
    }


def header_schema(max_page: int, field_key: str) -> dict[str, Any]:
    """Return one focused header structured-output schema."""
    return {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": HEADER_FIELDS[field_key],
            },
            "evidence": evidence_schema(max_page),
        },
        "required": ["value", "evidence"],
        "additionalProperties": False,
    }


def line_items_schema(max_page: int) -> dict[str, Any]:
    """Return a schema for every complete visible invoice table row."""
    properties: dict[str, Any] = {}
    for field_key, description in LINE_ITEM_FIELDS.items():
        properties[field_key] = {
            "type": "number" if field_key in {"quantity", "unit_cost", "subtotal"} else "string",
            "description": description,
        }
    return {
        "type": "object",
        "properties": {
            "line_items": {
                "type": "array",
                "description": "Every complete visible row in the invoice Item table, in order.",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(LINE_ITEM_FIELDS),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["line_items"],
        "additionalProperties": False,
    }


def chat_json(
    client: ollama.Client,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    num_ctx: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call Qwen with deterministic structured output."""
    started = time.perf_counter()
    errors: list[str] = []
    for attempt in range(2):
        attempt_prompt = prompt
        if attempt:
            attempt_prompt += (
                "\n\nRETRY: Return only the complete JSON required by the schema. "
                "Keep every string concise and do not add explanations."
            )
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": attempt_prompt}],
            format=schema,
            think=False,
            stream=False,
            options={"temperature": 0, "num_ctx": num_ctx, "num_predict": 1024},
            keep_alive="10m",
        )
        try:
            decoded = json.loads(response.message.content or "")
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if not isinstance(decoded, dict):
            errors.append("response was not a JSON object")
            continue
        return decoded, {
            "seconds": round(time.perf_counter() - started, 3),
            "attempts": attempt + 1,
            "done_reason": response.done_reason,
            "prompt_eval_count": response.prompt_eval_count,
            "eval_count": response.eval_count,
            "prior_errors": errors,
        }
    raise ValueError(f"Qwen did not return valid JSON after two attempts: {errors}")


def normalize_text(value: str) -> str:
    """Normalize whitespace and case for scoring."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def parse_number(value: Any) -> float | None:
    """Parse one currency or percentage scalar."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().replace(",", "").replace("$", "").replace("%", "")
    return float(cleaned) if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned) else None


def header_value_is_complete(field_key: str, value: Any) -> bool:
    """Reject empty or visibly truncated required header candidates."""
    if field_key in NUMERIC_HEADERS:
        return parse_number(value) is not None
    if not isinstance(value, str) or not value.strip():
        return False
    if field_key == "order_date":
        return bool(re.search(r"\b\d{4}\b", value))
    if field_key == "ship_to_address":
        return value.count(",") >= 2
    if field_key == "ship_mode":
        return "," not in value and "\n" not in value and len(value.split()) <= 5
    return True


def recovered_header_is_credible(field_key: str, value: Any, evidence: str) -> bool:
    """Reject a missing header recovery copied from an unrelated OCR region."""
    if not header_value_is_complete(field_key, value):
        return False
    if field_key == "ship_mode" and "ship mode" not in normalize_text(evidence):
        candidate = normalize_text(str(value))
        if candidate and candidate in normalize_text(evidence):
            return False
    return True


def render_first_page(pdf_path: Path) -> bytes:
    """Render a PDF first page for missing-header GLM image recovery."""
    with pymupdf.open(pdf_path) as document:
        pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        return pixmap.tobytes("png")


def recover_header_from_image(
    client: ollama.Client,
    pdf_path: Path,
    field_key: str,
) -> tuple[Any, dict[str, Any]]:
    """Recover one required header absent from SDK text using GLM vision."""
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "type": ["string", "null"],
                "description": HEADER_FIELDS[field_key],
            }
        },
        "required": ["value"],
        "additionalProperties": False,
    }
    prompt = f"""Inspect this invoice page and extract only one header field.
Field: {field_key}
Definition: {HEADER_FIELDS[field_key]}
Return the exact visible value. Do not use the filename. Return null only when
the page does not visibly contain the field. For ship_mode, read only the value
beside the Ship Mode label in the right-hand invoice summary; never return text
from the Ship To address."""
    started = time.perf_counter()
    response = client.generate(
        model=OCR_MODEL,
        prompt=prompt,
        images=[render_first_page(pdf_path)],
        format=schema,
        stream=False,
        options={"temperature": 0, "num_ctx": 8192, "num_predict": 256},
    )
    decoded = json.loads(response.response or "")
    value = decoded.get("value") if isinstance(decoded, dict) else None
    return value, {"seconds": round(time.perf_counter() - started, 3), "raw": decoded}


def recover_header_from_qwen_image(
    client: ollama.Client,
    model: str,
    pdf_path: Path,
    field_key: str,
) -> tuple[Any, dict[str, Any]]:
    """Use resolver vision when the OCR model cannot recover a required header."""
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "description": HEADER_FIELDS[field_key]}},
        "required": ["value"],
        "additionalProperties": False,
    }
    prompt = f"""Inspect this invoice image and extract only one header field.
Field: {field_key}
Definition: {HEADER_FIELDS[field_key]}
Return only the exact visible field value. For ship_mode, use only the value
beside Ship Mode in the right-hand summary below Date, never Ship To text."""
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [render_first_page(pdf_path)],
            }
        ],
        format=schema,
        think=False,
        stream=False,
        options={"temperature": 0, "num_ctx": 8192, "num_predict": 256},
        keep_alive="10m",
    )
    decoded = json.loads(response.message.content or "")
    value = decoded.get("value") if isinstance(decoded, dict) else None
    return value, {"seconds": round(time.perf_counter() - started, 3), "raw": decoded}


def clean_recovered_header(field_key: str, value: Any) -> Any:
    """Remove a repeated field label from a GLM image-recovery scalar."""
    if not isinstance(value, str):
        return value
    labels = {
        "row_id": r"^(?:invoice\s*)?#\s*",
        "order_date": r"^date\s*:\s*",
        "ship_mode": r"^ship\s*mode\s*:\s*",
        "customer_name": r"^bill\s*to\s*:\s*",
        "ship_to_address": r"^ship\s*to\s*:\s*",
        "order_id": r"^order\s*id\s*:\s*",
        "invoice_subtotal": r"^subtotal\s*:\s*",
        "shipping_fee": r"^shipping\s*:\s*",
        "total_amount_payable": r"^(?:total|balance\s*due)\s*:\s*",
    }
    pattern = labels.get(field_key)
    return re.sub(pattern, "", value, flags=re.IGNORECASE).strip() if pattern else value.strip()


def extract_headers(
    client: ollama.Client,
    model: str,
    pages: list[dict[str, Any]],
    num_ctx: int,
    pdf_path: Path,
) -> dict[str, Any]:
    """Resolve every header independently to avoid schema-field competition."""
    evidence = page_evidence(pages)
    values: dict[str, Any] = {}
    raw: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    max_page = max(int(page["page"]) for page in pages)
    for field_key, description in HEADER_FIELDS.items():
        prompt = f"""Extract only the configured invoice header field from OCR evidence.
Field: {field_key}
Definition: {description}

Return value as printed, except numeric currency and percentage values must use
digits and a decimal point without currency symbols, percent signs, or commas.
When OCR contains both a complete and truncated alternative, choose the complete
value. Dates must include the visible four-digit year. Ship To text may share an
OCR region with Bill To: exclude the Bill To label and customer name, then join
all address lines in reading order. A mixed line such as
"Customer Name 98103, City," contains the start of Ship To after the customer.
Return an empty value and empty evidence only when the field is not printed.
Each evidence quote must be an exact contiguous OCR quote from its claimed page.
Do not use the filename or infer values from other documents.

OCR EVIDENCE
{evidence}"""
        attempts: list[dict[str, Any]] = []
        decoded: dict[str, Any] = {}
        value: Any = None
        for attempt in range(2):
            attempt_prompt = prompt
            if attempt:
                attempt_prompt += (
                    "\n\nRECHECK: The prior value was empty or incomplete. Review all "
                    "OCR regions, prefer complete alternatives, and apply the field "
                    "definition before returning empty."
                )
            decoded, field_metrics = chat_json(
                client, model, attempt_prompt, header_schema(max_page, field_key), num_ctx
            )
            attempts.append(field_metrics)
            value = decoded.get("value")
            if field_key == "discount_percent" or header_value_is_complete(field_key, value):
                break
        recovery = None
        needs_image = field_key in REQUIRED_HEADERS and not recovered_header_is_credible(
            field_key, value, evidence
        )
        compare_multiline = field_key == "ship_to_address"
        if needs_image or compare_multiline:
            recovery_attempts: list[dict[str, Any]] = []
            recovered: Any = None
            for _ in range(2):
                recovered, recovery_attempt = recover_header_from_image(
                    client, pdf_path, field_key
                )
                recovered = clean_recovered_header(field_key, recovered)
                customer_name = values.get("customer_name")
                if (
                    field_key == "ship_to_address"
                    and isinstance(recovered, str)
                    and isinstance(customer_name, str)
                    and normalize_text(recovered).startswith(normalize_text(customer_name))
                ):
                    recovered = recovered[len(customer_name) :].strip(" ,\r\n")
                recovery_attempts.append(recovery_attempt)
                if recovered_header_is_credible(field_key, recovered, evidence):
                    break
            qwen_recovery = None
            if needs_image and not recovered_header_is_credible(
                field_key, recovered, evidence
            ):
                recovered, qwen_recovery = recover_header_from_qwen_image(
                    client, model, pdf_path, field_key
                )
                recovered = clean_recovered_header(field_key, recovered)
            recovery = {
                "glm_attempts": recovery_attempts,
                "qwen_attempt": qwen_recovery,
                "selected": recovered,
            }
            if recovered_header_is_credible(field_key, recovered, evidence) and (needs_image or (
                isinstance(recovered, str)
                and len(normalize_text(recovered)) > len(normalize_text(str(value or "")))
            )):
                value = recovered
        values[field_key] = parse_number(value) if field_key in NUMERIC_HEADERS else (
            value.strip() if isinstance(value, str) and value.strip() else None
        )
        raw[field_key] = decoded
        metrics[field_key] = {"text_attempts": attempts, "image_recovery": recovery}
    return {"values": values, "raw": raw, "metrics": metrics}


def extract_line_items(
    client: ollama.Client,
    model: str,
    pages: list[dict[str, Any]],
    num_ctx: int,
) -> dict[str, Any]:
    """Extract the complete Item table into an ordered object array."""
    evidence = page_evidence(pages)
    prompt = f"""Extract every complete row from the invoice Item table.

The Item column uses two visual lines per row:
- first line: product_name
- second line: sub_category, category, product_id
The remaining columns are Quantity, Rate, and Amount. Map Rate to unit_cost and
Amount to subtotal. Currency values must be JSON numbers without symbols or
commas. Do not treat Subtotal, Discount, Shipping, or Total summary rows as line
items. The full product_name is the entire product line immediately before the
classification line; do not drop trailing numbers or words. The classification
line contains exactly sub_category, category, and product_id in that order;
split it at its two commas. OCR may repeat alternative transcriptions of the
same physical row. Output a row only once when product ID, quantity, rate, and
amount identify the same row. When OCR joins the product and classification
lines, use the product-ID suffix and classification words to restore the seven
configured cells without losing product-name words. Preserve table order and
do not merge genuinely different rows. Return only the configured row values
with no explanations.

OCR EVIDENCE
{evidence}"""
    decoded, metrics = chat_json(
        client,
        model,
        prompt,
        line_items_schema(max(int(page["page"]) for page in pages)),
        num_ctx,
    )
    items = decoded.get("line_items")
    if not isinstance(items, list):
        raise TypeError("Qwen line_items must be an array")
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append({field_key: item.get(field_key) for field_key in LINE_ITEM_FIELDS})
    repaired, repairs = repair_line_items_from_ocr(normalized, pages)
    return {
        "values": repaired,
        "resolver_values": normalized,
        "repairs": repairs,
        "raw": decoded,
        "metrics": metrics,
    }


def repair_line_items_from_ocr(
    items: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Ground standard two-line item cells in exact OCR classification rows."""
    repaired = [dict(item) for item in items]
    repairs: list[dict[str, Any]] = []
    lines = page_evidence(pages).splitlines()
    used_line_indexes: set[int] = set()
    for row_index, item in enumerate(repaired):
        product_id = item.get("product_id")
        if not isinstance(product_id, str) or not product_id.strip():
            continue
        for line_index, line in enumerate(lines):
            if line_index in used_line_indexes or "|" not in line:
                continue
            if normalize_text(product_id) not in normalize_text(line):
                continue
            classification = line.split("|", 1)[0].strip()
            parts = [part.strip() for part in classification.split(",")]
            if len(parts) != 3 or normalize_text(parts[2]) != normalize_text(product_id):
                continue
            previous_index = line_index - 1
            while previous_index >= 0 and (
                not lines[previous_index].strip()
                or lines[previous_index].startswith("[REGION ")
            ):
                previous_index -= 1
            if previous_index < 0:
                continue
            product_name = lines[previous_index].strip()
            if "|" in product_name or product_name.startswith("====="):
                continue
            before = {
                key: item.get(key)
                for key in ("product_name", "sub_category", "category", "product_id")
            }
            item.update(
                {
                    "product_name": product_name,
                    "sub_category": parts[0],
                    "category": parts[1],
                    "product_id": parts[2],
                }
            )
            after = {
                key: item.get(key)
                for key in ("product_name", "sub_category", "category", "product_id")
            }
            used_line_indexes.add(line_index)
            if before != after:
                repairs.append(
                    {
                        "row": row_index,
                        "page_evidence_line": line,
                        "before": before,
                        "after": after,
                    }
                )
            break
    return repaired, repairs


def value_matches(actual: Any, expected: Any) -> bool:
    """Compare numeric and textual business values."""
    if expected is None:
        return actual is None
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and abs(float(actual) - float(expected)) < 0.005
    return isinstance(actual, str) and normalize_text(actual) == normalize_text(str(expected))


def score_result(result: dict[str, Any], expected: dict[str, Any]) -> None:
    """Attach header, row, and individual line-item cell scores."""
    header_values = result["headers"]["values"]
    header_matches = {
        key: value_matches(header_values.get(key), value)
        for key, value in expected["headers"].items()
    }
    actual_items = result["line_items"]["values"]
    expected_items = expected["line_items"]
    cell_matches: list[dict[str, bool]] = []
    for row_index, expected_item in enumerate(expected_items):
        actual_item = actual_items[row_index] if row_index < len(actual_items) else {}
        cell_matches.append(
            {
                key: value_matches(actual_item.get(key), value)
                for key, value in expected_item.items()
            }
        )
    result["header_matches"] = header_matches
    result["line_item_count_match"] = len(actual_items) == len(expected_items)
    result["line_item_cell_matches"] = cell_matches
    result["document_exact"] = (
        all(header_matches.values())
        and result["line_item_count_match"]
        and all(all(row.values()) for row in cell_matches)
    )


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate header and line-item accuracy separately."""
    header_total = len(results) * len(HEADER_FIELDS)
    line_item_cells_total = sum(
        len(row)
        for result in results
        for row in result["line_item_cell_matches"]
    )
    qwen_text_seconds = sum(
        sum(
            sum(attempt["seconds"] for attempt in metric["text_attempts"])
            for metric in result["headers"]["metrics"].values()
        )
        + result["line_items"]["metrics"]["seconds"]
        for result in results
    )
    glm_image_seconds = sum(
        sum(
            sum(
                attempt["seconds"]
                for attempt in metric["image_recovery"]["glm_attempts"]
            )
            if metric["image_recovery"] is not None
            else 0
            for metric in result["headers"]["metrics"].values()
        )
        for result in results
    )
    qwen_image_seconds = sum(
        sum(
            metric["image_recovery"]["qwen_attempt"]["seconds"]
            if metric["image_recovery"] is not None
            and metric["image_recovery"]["qwen_attempt"] is not None
            else 0
            for metric in result["headers"]["metrics"].values()
        )
        for result in results
    )
    return {
        "documents": len(results),
        "documents_exact": sum(result["document_exact"] for result in results),
        "header_fields_correct": sum(
            sum(result["header_matches"].values()) for result in results
        ),
        "header_fields_total": header_total,
        "line_item_counts_correct": sum(result["line_item_count_match"] for result in results),
        "line_item_cells_correct": sum(
            sum(row.values())
            for result in results
            for row in result["line_item_cell_matches"]
        ),
        "line_item_cells_total": line_item_cells_total,
        "sdk_parse_seconds": round(sum(result["parse"]["seconds"] for result in results), 3),
        "qwen_text_seconds": round(qwen_text_seconds, 3),
        "glm_image_recovery_seconds": round(glm_image_seconds, 3),
        "qwen_image_recovery_seconds": round(qwen_image_seconds, 3),
        "resolution_seconds": round(
            qwen_text_seconds + glm_image_seconds + qwen_image_seconds,
            3,
        ),
    }


def main() -> int:
    """Run the resumable four-document Superstore experiment."""
    args = parse_args()
    checkpoint = load_checkpoint(args.checkpoint)
    parses = checkpoint["parses"]
    completed = checkpoint["results"]

    missing = [filename for filename in GROUND_TRUTH if filename not in parses]
    if missing:
        with create_sdk_parser() as parser:
            for index, filename in enumerate(missing, start=1):
                print(f"[OCR {index}/{len(missing)}] {filename}", flush=True)
                parsed = parse_pdf(parser, PDF_DIR / filename)
                parses[filename] = parsed
                save_checkpoint(args.checkpoint, checkpoint)
                print(
                    f"  {parsed['region_count']} regions, {parsed['char_count']} chars, "
                    f"{parsed['seconds']}s",
                    flush=True,
                )

    client = ollama.Client(host=OLLAMA_HOST, timeout=args.timeout)
    for index, (filename, expected) in enumerate(GROUND_TRUTH.items(), start=1):
        if filename in completed:
            print(f"[Qwen {index}/4] {filename}: cached", flush=True)
            continue
        print(f"[Qwen {index}/4] {filename}", flush=True)
        parsed = parses[filename]
        pages = parsed["pages"]
        headers = extract_headers(
            client,
            args.resolver_model,
            pages,
            args.num_ctx,
            PDF_DIR / filename,
        )
        line_items = extract_line_items(client, args.resolver_model, pages, args.num_ctx)
        result = {
            "pdf": filename,
            "expected": expected,
            "parse": parsed,
            "headers": headers,
            "line_items": line_items,
        }
        score_result(result, expected)
        completed[filename] = result
        save_checkpoint(args.checkpoint, checkpoint)
        print(
            json.dumps(
                {
                    "headers": headers["values"],
                    "line_items": line_items["values"],
                    "header_matches": result["header_matches"],
                    "line_item_cell_matches": result["line_item_cell_matches"],
                    "document_exact": result["document_exact"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )

    ordered_results = [completed[filename] for filename in GROUND_TRUTH]
    summary = build_summary(ordered_results)
    payload = {
        "experiment": {
            "version": EXPERIMENT_VERSION,
            "pipeline": "official GLM-OCR SDK parse -> Qwen header and table resolver",
            "glmocr_sdk_version": glmocr_version,
            "ocr_model": OCR_MODEL,
            "resolver_model": args.resolver_model,
            "resolver_thinking": False,
            "resolver_temperature": 0,
            "production_code_changed": False,
            "expected_values_used_in_prompts": False,
        },
        "summary": summary,
        "results": ordered_results,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(args.output)}, indent=2), flush=True)
    return 0 if summary["documents_exact"] == len(ordered_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
