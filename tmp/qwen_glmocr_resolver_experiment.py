"""Throwaway GLM-OCR-to-Qwen document evidence resolver experiment.

The official GLM-OCR SDK parse is intentionally loaded from the completed
four-document checkpoint. This isolates semantic resolution quality from OCR
latency and avoids parsing the same customer PDFs again.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import time
from pathlib import Path
from typing import Any

import ollama


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT = ROOT / "tmp" / "glmocr_sdk_test_a_b_checkpoint.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "qwen_glmocr_resolver_results.json"
DEFAULT_MODEL = "qwen3.5:9b-q4_K_M"
OLLAMA_HOST = "http://127.0.0.1:11434"

FIELD_KEYS = (
    "supplier_name",
    "invoice_or_delivery_order_number",
    "purchase_order_number",
    "total_amount",
)

FIELD_DESCRIPTIONS = {
    "supplier_name": (
        "Legal name of the supplier that issued the invoice or delivery order. "
        "The bill-to, buyer, customer, ship-to party, and receiving stamp are "
        "not the supplier."
    ),
    "invoice_or_delivery_order_number": (
        "Exact supplier invoice number or delivery-order number printed beside "
        "a label such as Invoice No, Tax Invoice No, Delivery Order, DO No, or "
        "D/O No. It is not a PO, project, marking, or reference number."
    ),
    "purchase_order_number": (
        "Exact buyer purchase-order identifier printed beside Purchase Order, "
        "PO No, P/O No, or Your PO."
    ),
    "total_amount": (
        "Final payable document total including tax. Prefer an invoice total; "
        "otherwise use the delivery-order final total or purchase-order total. "
        "Do not select a subtotal, tax amount, or individual line amount."
    ),
}

SYSTEM_PROMPT = """You resolve structured fields from page-aware OCR evidence.

Use only the supplied OCR text. Do not use the filename or outside knowledge.
Return the requested configured field using the required JSON schema.

Evidence rules:
- Copy each evidence quote exactly and contiguously from one numbered page.
- Use at most three short quotes per field. Set value to an empty string and
  evidence to an empty list when the field is not supported.
- Do not invent, silently correct, or combine identifiers.
- Treat the supplied page-role hints as document-structure evidence. Prefer
  supplier invoice evidence over supplier delivery-order evidence, and prefer
  either supplier document over an attached buyer purchase order.
- The supplier is the company issuing the supplier invoice or delivery order,
  not a bill-to, buyer, customer, ship-to party, or receiving-stamp company.
- In this FTS packet, FUJI TRADING (S) PTE LTD and FUJI TRADING (SINGAPORE) PTE
  LTD are the buyer/customer and must not be selected as supplier.
- FTS project or marking numbers use SXXXXXX style: S followed by six digits.
  Such a value is never the supplier invoice or delivery-order number.
- For total_amount, return digits with a decimal point and no currency symbol.
  Always use the supplier invoice total when a supplier invoice is present,
  even when an attached buyer purchase order has its own TOTAL. If the invoice
  prints an amount in words but omits the numeric final total, derive it from
  explicitly labelled invoice components such as subtotal plus GST. Cite every
  component and put only the short arithmetic equation in derivation.
- For the other fields, preserve the identifier or company wording as printed
  and leave derivation empty.
"""


def parse_args() -> argparse.Namespace:
    """Parse experiment command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser.parse_args()


def clean_region_content(content: str) -> str:
    """Remove SDK formatting repetition while retaining OCR reading order."""
    text = html.unescape(content)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</t[dh]\s*>", " | ", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)

    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.replace("```markdown", "").replace("```", "")
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        line = line.strip("| ")
        if not line or line == "---":
            continue
        identity = line.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        lines.append(line)
    return "\n".join(lines)


def compact_pages(raw_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build deduplicated, page-aware evidence from SDK layout regions."""
    compacted: list[dict[str, Any]] = []
    for fallback_page, raw_page in enumerate(raw_pages, start=1):
        page_number = int(raw_page.get("page") or fallback_page)
        regions = raw_page.get("regions")
        if not isinstance(regions, list):
            raise TypeError(f"Page {page_number} has no SDK region list")

        blocks: list[str] = []
        seen_blocks: set[str] = set()
        for fallback_index, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            content = region.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            cleaned = clean_region_content(content)
            if not cleaned:
                continue
            identity = re.sub(r"\s+", " ", cleaned).casefold()
            if identity in seen_blocks:
                continue
            seen_blocks.add(identity)
            region_index = int(region.get("index", fallback_index)) + 1
            label = str(region.get("native_label") or region.get("label") or "text")
            blocks.append(f"[REGION {region_index}: {label}]\n{cleaned}")

        body = "\n\n".join(blocks)
        compacted.append(
            {
                "page": page_number,
                "role_hint": infer_page_role(body),
                "text": body,
                "region_count": len(blocks),
                "char_count": len(body),
            }
        )
    return compacted


def infer_page_role(text: str) -> str:
    """Infer a broad invoice-packet page role from explicit document headings."""
    normalized = normalize_text(text)
    if "tax invoice" in normalized:
        return "supplier_invoice"
    if "** purchase order **" in normalized or "suppler code" in normalized:
        return "buyer_purchase_order"
    if "purchase order" in normalized and "supplier code" in normalized:
        return "buyer_purchase_order"
    if "delivery order" in normalized or re.search(r"\bd/?o no\b", normalized):
        return "supplier_delivery_order"
    return "unknown"


def single_field_response_schema(max_page: int, field_key: str) -> dict[str, Any]:
    """Return a focused non-null schema for one configured field."""
    evidence_item = {
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "minimum": 1,
                "maximum": max_page,
                "description": "One-based page containing the exact quote.",
            },
            "quote": {
                "type": "string",
                "maxLength": 200,
                "description": (
                    "One short complete OCR line copied exactly from that page. "
                    "Do not join separate regions or add markdown formatting."
                ),
            },
        },
        "required": ["page", "quote"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": (
                    f"{FIELD_DESCRIPTIONS[field_key]} Use an empty string only "
                    "when the evidence does not support a value."
                ),
            },
            "evidence": {
                "type": "array",
                "items": evidence_item,
                "maxItems": 3,
            },
            "derivation": {
                "type": "string",
                "description": (
                    "Arithmetic equation only for a derived total; otherwise "
                    "an empty string."
                ),
            },
        },
        "required": ["value", "evidence", "derivation"],
        "additionalProperties": False,
    }


def build_field_prompt(field_key: str, pages: list[dict[str, Any]]) -> str:
    """Build a focused prompt that prevents fields competing in one response."""
    evidence = "\n\n".join(
        f"===== PAGE {page['page']} | ROLE HINT: {page['role_hint']} =====\n{page['text']}"
        for page in pages
    )
    common = """Use supplier invoice evidence first when it supports the field,
then supplier delivery-order evidence, then buyer purchase-order evidence. A
preferred document that does not contain the requested value does not block
fallback to a lower-priority document. Return an empty value only when no page
supports it. Each quote must be one exact complete OCR line."""
    field_rules = {
        "supplier_name": (
            "Select the supplier issuer, never FUJI TRADING. If the supplier "
            "name is omitted from supplier-page OCR, the same vendor explicitly "
            "listed as SUPPLIER on the buyer PO is valid fallback evidence."
        ),
        "invoice_or_delivery_order_number": (
            "Select the exact identifier beside Invoice No, Tax Invoice No, "
            "Delivery Order, DO No, or D/O No on a supplier page. A value in "
            "SXXXXXX style is an FTS project or marking, never this identifier."
        ),
        "purchase_order_number": (
            "Select the exact buyer PO identifier beside Purchase Order, PO No, "
            "P/O No, or Your PO. Do not return an invoice, DO, or project number."
        ),
        "total_amount": (
            "Use the supplier invoice payable total including GST. When the "
            "supplier invoice shows an amount in words plus labelled SUB-TOTAL "
            "and GST but omits the numeric final total, add SUB-TOTAL and GST "
            "and state the arithmetic. Never substitute an attached buyer PO "
            "total when supplier invoice components establish a different total."
        ),
    }
    return (
        f"Resolve only this configured field: {field_key}\n"
        f"Definition: {FIELD_DESCRIPTIONS[field_key]}\n\n"
        f"{common}\n{field_rules[field_key]}\n\nOCR EVIDENCE\n{evidence}"
    )


def normalize_text(value: str) -> str:
    """Normalize whitespace and case for evidence containment checks."""
    return re.sub(r"\s+", " ", value).strip().casefold()


def parse_total(value: str) -> float | None:
    """Parse a model total string without accepting unrelated characters."""
    stripped = value.strip().replace(",", "")
    if not stripped:
        return None
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", stripped):
        return None
    return float(stripped)


def normalized_values(extraction: dict[str, Any]) -> dict[str, Any]:
    """Convert schema strings to the configured business value types."""
    values: dict[str, Any] = {}
    for field_key in FIELD_KEYS:
        field = extraction.get(field_key)
        value = field.get("value", "") if isinstance(field, dict) else ""
        if not isinstance(value, str):
            value = str(value)
        values[field_key] = parse_total(value) if field_key == "total_amount" else value.strip() or None
    return values


def validate_evidence(
    extraction: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Check that every returned quote occurs on its claimed OCR page."""
    page_text = {int(page["page"]): normalize_text(str(page["text"])) for page in pages}
    checks: dict[str, dict[str, Any]] = {}
    for field_key in FIELD_KEYS:
        field = extraction.get(field_key)
        if not isinstance(field, dict):
            checks[field_key] = {
                "valid": False,
                "grounded": False,
                "reason": "field is not an object",
            }
            continue
        value = field.get("value")
        evidence = field.get("evidence")
        if not isinstance(value, str) or not isinstance(evidence, list):
            checks[field_key] = {
                "valid": False,
                "grounded": False,
                "reason": "invalid value or evidence type",
            }
            continue
        quote_checks: list[dict[str, Any]] = []
        for item in evidence:
            if not isinstance(item, dict):
                quote_checks.append({"valid": False, "reason": "evidence is not an object"})
                continue
            page = item.get("page")
            quote = item.get("quote")
            valid = (
                isinstance(page, int)
                and isinstance(quote, str)
                and bool(normalize_text(quote))
                and normalize_text(quote) in page_text.get(page, "")
            )
            quote_checks.append({"page": page, "quote": quote, "valid": valid})
        has_value = bool(value.strip())
        valid = bool(quote_checks) and all(item["valid"] for item in quote_checks)
        if not has_value:
            valid = not quote_checks
        checks[field_key] = {
            "valid": valid,
            "grounded": has_value and valid,
            "quote_checks": quote_checks,
            "reason": None if valid else "missing or non-verbatim page evidence",
        }
    return checks


def exact_line_evidence(value: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Locate exact OCR lines containing a returned value without changing it."""
    needle = normalize_text(value)
    if not needle:
        return []
    found: list[dict[str, Any]] = []
    for page in pages:
        for raw_line in str(page["text"]).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("[REGION ") or needle not in normalize_text(line):
                continue
            if len(line) > 200:
                position = normalize_text(line).find(needle)
                start = max(0, position - 60)
                line = line[start : start + 200].strip()
            found.append({"page": int(page["page"]), "quote": line})
            if len(found) == 2:
                return found
    return found


def ground_extraction(
    extraction: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Filter model quotes and add exact value-bearing OCR lines when available."""
    grounded = copy.deepcopy(extraction)
    page_text = {int(page["page"]): normalize_text(str(page["text"])) for page in pages}
    for field_key in FIELD_KEYS:
        field = grounded.get(field_key)
        if not isinstance(field, dict):
            continue
        value = field.get("value")
        if not isinstance(value, str) or not value.strip():
            field["evidence"] = []
            continue
        retained: list[dict[str, Any]] = []
        for item in field.get("evidence", []):
            if not isinstance(item, dict):
                continue
            page = item.get("page")
            quote = item.get("quote")
            if (
                isinstance(page, int)
                and isinstance(quote, str)
                and normalize_text(quote) in page_text.get(page, "")
            ):
                retained.append({"page": page, "quote": quote})
        direct = exact_line_evidence(value, pages)
        combined = direct if direct else retained
        unique: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for item in combined:
            identity = (int(item["page"]), normalize_text(str(item["quote"])))
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(item)
            if len(unique) == 3:
                break
        field["evidence"] = unique
        if field_key != "total_amount" or direct:
            field["derivation"] = ""
    return grounded


def exact_values_match(actual: Any, expected: Any) -> bool:
    """Compare extracted values without normalizing legal-name punctuation."""
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and abs(float(actual) - float(expected)) < 0.005
    if isinstance(actual, str) and isinstance(expected, str):
        return normalize_text(actual) == normalize_text(expected)
    return actual == expected


def semantic_values_match(field_key: str, actual: Any, expected: Any) -> bool:
    """Compare company names despite punctuation that OCR may omit."""
    if field_key != "supplier_name":
        return exact_values_match(actual, expected)
    if not isinstance(actual, str) or not isinstance(expected, str):
        return actual == expected
    company_tokens = lambda value: re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    return company_tokens(actual) == company_tokens(expected)


def run_resolver(
    client: ollama.Client,
    model: str,
    pages: list[dict[str, Any]],
    num_ctx: int,
) -> dict[str, Any]:
    """Run deterministic field-isolated Qwen extraction over one document."""
    started = time.perf_counter()
    extraction: dict[str, Any] = {}
    prompt_chars: dict[str, int] = {}
    model_metrics: dict[str, list[dict[str, Any]]] = {}
    max_page = max(int(page["page"]) for page in pages)
    for field_key in FIELD_KEYS:
        prompt = build_field_prompt(field_key, pages)
        attempts: list[dict[str, Any]] = []
        decoded: dict[str, Any] | None = None
        for attempt in range(3):
            if attempt == 0:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            elif attempt == 1:
                messages = [
                    {
                        "role": "user",
                        "content": (
                            f"{prompt}\n\nRECHECK: The previous attempt returned an empty "
                            "value. Examine every explicit label and apply the stated "
                            "fallback hierarchy before returning empty."
                        ),
                    }
                ]
            else:
                messages = [
                    {
                        "role": "user",
                        "content": (
                            f"{prompt}\n\nSCHEMA CONSISTENCY REPAIR: Your previous "
                            "JSON is shown below. If its evidence or derivation "
                            "identifies a supported value, put that exact value in "
                            "the value property and cite the supporting OCR line. "
                            "Otherwise keep value empty. Do not introduce a value "
                            "that your prior analysis did not support.\n"
                            f"{json.dumps(decoded, ensure_ascii=False)}"
                        ),
                    }
                ]
            response = client.chat(
                model=model,
                messages=messages,
                format=single_field_response_schema(max_page, field_key),
                stream=False,
                think=False,
                options={
                    "temperature": 0,
                    "num_ctx": num_ctx,
                    "num_predict": 512,
                },
                keep_alive="10m",
            )
            response_text = response.message.content or ""
            candidate = json.loads(response_text)
            if not isinstance(candidate, dict):
                raise TypeError(f"Qwen {field_key} response must be a JSON object")
            decoded = candidate
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "done_reason": response.done_reason,
                    "total_duration": response.total_duration,
                    "load_duration": response.load_duration,
                    "prompt_eval_count": response.prompt_eval_count,
                    "eval_count": response.eval_count,
                }
            )
            value = decoded.get("value")
            if isinstance(value, str) and value.strip():
                break
        if decoded is None:
            raise RuntimeError(f"Qwen returned no {field_key} response")
        extraction[field_key] = decoded
        prompt_chars[field_key] = len(prompt)
        model_metrics[field_key] = attempts
    seconds = time.perf_counter() - started
    grounded = ground_extraction(extraction, pages)
    return {
        "raw": extraction,
        "grounded": grounded,
        "values": normalized_values(grounded),
        "evidence_checks": validate_evidence(grounded, pages),
        "seconds": round(seconds, 3),
        "prompt_chars": prompt_chars,
        "model_metrics": model_metrics,
    }


def load_results(checkpoint: Path) -> list[dict[str, Any]]:
    """Load completed SDK document results from the prior checkpoint."""
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    results = payload.get("results") if isinstance(payload, dict) else None
    if payload.get("state") != "documents_complete" or not isinstance(results, list):
        raise ValueError("Checkpoint does not contain completed document results")
    return [item for item in results if isinstance(item, dict)]


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate accuracy, grounding, context size, and latency."""
    return {
        "documents": len(results),
        "total_fields": len(results) * len(FIELD_KEYS),
        "fields_correct": sum(sum(item["matches"].values()) for item in results),
        "documents_exact": sum(item["document_exact"] for item in results),
        "fields_with_valid_evidence": sum(
            check["grounded"]
            for item in results
            for check in item["resolver"]["evidence_checks"].values()
        ),
        "correct_fields_with_valid_evidence": sum(
            item["matches"][field_key]
            and item["resolver"]["evidence_checks"][field_key]["grounded"]
            for item in results
            for field_key in FIELD_KEYS
        ),
        "fields_exact_text_match": sum(
            sum(item["exact_matches"].values()) for item in results
        ),
        "resolver_seconds": round(sum(item["resolver"]["seconds"] for item in results), 3),
        "sdk_original_chars": sum(item["sdk_original_chars"] for item in results),
        "compacted_chars": sum(item["compacted_chars"] for item in results),
    }


def main() -> int:
    """Run Qwen resolution over all four completed GLM-OCR SDK parses."""
    args = parse_args()
    source_results = load_results(args.checkpoint)
    if len(source_results) != 4:
        raise ValueError(f"Expected four checkpoint documents, found {len(source_results)}")

    client = ollama.Client(host=OLLAMA_HOST, timeout=args.timeout)
    results: list[dict[str, Any]] = []
    for index, source in enumerate(source_results, start=1):
        filename = str(source.get("pdf"))
        expected = source.get("expected")
        test_b = source.get("test_b")
        if not isinstance(expected, dict) or not isinstance(test_b, dict):
            raise TypeError(f"Incomplete checkpoint entry for {filename}")
        raw_pages = test_b.get("pages")
        if not isinstance(raw_pages, list):
            raise TypeError(f"No SDK pages for {filename}")

        pages = compact_pages(raw_pages)
        compacted_chars = sum(int(page["char_count"]) for page in pages)
        print(
            f"[{index}/{len(source_results)}] {filename}: "
            f"{len(pages)} pages, {compacted_chars:,} compacted chars",
            flush=True,
        )
        resolver = run_resolver(client, args.model, pages, args.num_ctx)
        matches = {
            field_key: semantic_values_match(
                field_key,
                resolver["values"].get(field_key),
                expected.get(field_key),
            )
            for field_key in FIELD_KEYS
        }
        exact_matches = {
            field_key: exact_values_match(
                resolver["values"].get(field_key), expected.get(field_key)
            )
            for field_key in FIELD_KEYS
        }
        result = {
            "pdf": filename,
            "page_count": len(pages),
            "expected": expected,
            "sdk_original_chars": len(str(test_b.get("combined_text") or "")),
            "compacted_chars": compacted_chars,
            "compacted_pages": pages,
            "resolver": resolver,
            "matches": matches,
            "exact_matches": exact_matches,
            "document_exact": all(matches.values()),
        }
        results.append(result)
        print(
            json.dumps(
                {
                    "values": resolver["values"],
                    "matches": matches,
                    "exact_matches": exact_matches,
                    "evidence_grounded": {
                        key: check["grounded"]
                        for key, check in resolver["evidence_checks"].items()
                    },
                    "seconds": resolver["seconds"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )

    summary = build_summary(results)
    payload = {
        "experiment": {
            "pipeline": "cached official GLM-OCR SDK parse -> Qwen evidence resolver",
            "ocr_checkpoint": str(args.checkpoint),
            "resolver_model": args.model,
            "resolver_num_ctx": args.num_ctx,
            "resolver_thinking": False,
            "resolver_temperature": 0,
            "production_code_changed": False,
            "expected_values_used_in_prompt": False,
        },
        "summary": summary,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(args.output)}, indent=2), flush=True)
    return 0 if summary["documents_exact"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
