"""Throwaway benchmark comparing per-page KIE with parse-then-extract.

This file intentionally lives under ``tmp`` and does not alter the production
GLM-OCR task. Test A mirrors its per-page structured extraction and
first-nonempty merge. Test B first asks GLM-OCR to transcribe every page, then
runs one evidence-backed extraction over the combined page-aware text.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import ollama


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from standard_step.extraction.glm_ocr_adapter import GlmOcrAdapter  # noqa: E402
from standard_step.extraction.glm_ocr_prompt import (  # noqa: E402
    build_glm_ocr_schemas,
    build_scalar_object_prompt,
)
from standard_step.extraction.structured_fields import (  # noqa: E402
    get_extracted_value,
    normalize_scalar_field,
)


OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL = "glm-ocr:latest"
DPI = 216
TEST_A_NUM_CTX = 8192
PARSE_NUM_CTX = 16384
EXTRACT_NUM_CTX = 32768
TEST_A_NUM_PREDICT = 512
PARSE_NUM_PREDICT = 8192
EXTRACT_NUM_PREDICT = 1536

DOCUMENT_INSTRUCTIONS = (
    "All pages belong to one supplier document packet addressed to FUJI TRADING "
    "(S) PTE LTD. Extract only explicitly visible values. supplier_name is the "
    "company issuing the invoice or delivery order; FUJI TRADING (S) PTE LTD and "
    "FUJI TRADING (SINGAPORE) PTE LTD are the buyer/customer and must never be "
    "returned as supplier_name. invoice_or_delivery_order_number is an official "
    "supplier invoice or delivery-order number. FTS project/marking numbers use "
    "SXXXXXX (the letter S followed by six digits, such as S268588) and must never "
    "be returned as an invoice or delivery-order number. purchase_order_number is "
    "the buyer's explicitly labelled P/O or purchase-order number. total_amount is "
    "the final invoice total including GST; if no invoice total exists, use the "
    "delivery-order final total; otherwise use the attached purchase order's TOTAL "
    "SGD value. Never use a line item, subtotal, discount, GST/tax amount, project "
    "number, marking, reference number, invoice number, or delivery-order number "
    "for a different field. Return null when a value is not explicitly supported."
)

FIELDS: dict[str, dict[str, Any]] = {
    "supplier_name": {
        "alias": "Supplier name",
        "description": (
            "Company issuing the supplier invoice or delivery order. Fuji Trading "
            "is the buyer/customer, not the supplier."
        ),
        "schema_order": 1,
        "type": "Optional[str]",
    },
    "invoice_or_delivery_order_number": {
        "alias": "Invoice or delivery order number",
        "description": (
            "Official supplier invoice or delivery-order number, never an FTS "
            "SXXXXXX project/marking number or purchase-order number."
        ),
        "schema_order": 2,
        "type": "Optional[str]",
    },
    "purchase_order_number": {
        "alias": "Purchase order number",
        "description": (
            "Buyer's explicitly labelled P/O or purchase-order number; never an "
            "invoice, delivery order, project, marking, or reference number."
        ),
        "schema_order": 3,
        "type": "Optional[str]",
    },
    "total_amount": {
        "alias": "Total amount",
        "description": (
            "Final payable invoice total including GST; otherwise delivery-order "
            "final total, otherwise attached purchase-order TOTAL SGD."
        ),
        "schema_order": 4,
        "type": "Optional[float]",
    },
}

PDF_DIR = ROOT / "fts_test_files" / "fts_data"
GROUND_TRUTH: dict[str, dict[str, Any]] = {
    "S268588 1781053.pdf": {
        "supplier_name": "Seastar Marine Supply Pte Ltd",
        "invoice_or_delivery_order_number": "DO2025052474",
        "purchase_order_number": "1781053",
        "total_amount": 414.25,
    },
    "S268588 1781062.pdf": {
        "supplier_name": "UNITECH SUPPLIES PTE LTD",
        "invoice_or_delivery_order_number": "INV/2505/00686",
        "purchase_order_number": "1781062",
        "total_amount": 315.66,
    },
    "S268588 1781068.pdf": {
        "supplier_name": "JOO YONG CO., (PTE.) LTD.",
        "invoice_or_delivery_order_number": "INV25053350",
        "purchase_order_number": "1781068",
        "total_amount": 90.39,
    },
    "S268588 1781081.pdf": {
        "supplier_name": "MARINET SERVICES PTE LTD",
        "invoice_or_delivery_order_number": "M25051227",
        "purchase_order_number": "1781081",
        "total_amount": 135.97,
    },
}


def response_text(response: Any) -> str:
    """Return response text from either Ollama response representation."""
    value = response.get("response") if isinstance(response, dict) else response.response
    if not isinstance(value, str):
        raise TypeError("Ollama response did not contain text")
    return value


def response_json(response: Any) -> dict[str, Any]:
    """Decode a non-streaming Ollama JSON response."""
    decoded = json.loads(response_text(response))
    if not isinstance(decoded, dict):
        raise TypeError("GLM-OCR response must be a JSON object")
    return decoded


def response_metadata(response: Any) -> dict[str, Any]:
    """Retain useful model timing and termination metadata."""
    names = (
        "done_reason",
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "eval_count",
    )
    metadata: dict[str, Any] = {}
    for name in names:
        value = response.get(name) if isinstance(response, dict) else getattr(response, name, None)
        if value is not None:
            metadata[name] = value
    return metadata


def values_match(actual: Any, expected: Any) -> bool:
    """Compare business values while tolerating casing and float serialization."""
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and abs(float(actual) - float(expected)) < 0.005
    if isinstance(actual, str) and isinstance(expected, str):
        return " ".join(actual.split()).casefold() == " ".join(expected.split()).casefold()
    return actual == expected


def searchable_text(value: Any) -> str:
    """Normalize OCR and evidence text for conservative containment checks."""
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def expected_visible(expected: Any, combined_text: str) -> bool:
    """Check whether the expected value survived the parsing stage."""
    haystack = searchable_text(combined_text)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        candidates = {
            searchable_text(f"{float(expected):.2f}"),
            searchable_text(str(expected)),
        }
        return any(candidate and candidate in haystack for candidate in candidates)
    return searchable_text(expected) in haystack


def normalize_test_a_page(page_data: dict[str, Any]) -> dict[str, Any]:
    """Apply the same scalar normalization helpers used by the task."""
    result: dict[str, Any] = {}
    for field_key, config in FIELDS.items():
        found, raw_value = get_extracted_value(
            page_data,
            field_key,
            str(config.get("alias", field_key)),
        )
        if not found:
            result[field_key] = None
            continue
        findings: list[Any] = []
        result[field_key] = normalize_scalar_field(
            raw_value,
            config,
            path=field_key,
            findings=findings,
        )
    return result


def run_test_a(
    client: ollama.Client,
    page_images: list[bytes],
    prompt: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Reproduce per-page full-schema KIE and first-nonempty merge."""
    started = time.perf_counter()
    pages: list[dict[str, Any]] = []
    merged: dict[str, Any] = {key: None for key in FIELDS}
    for page_number, image in enumerate(page_images, start=1):
        page_started = time.perf_counter()
        response = client.generate(
            model=MODEL,
            prompt=prompt,
            images=[image],
            format=schema,
            stream=False,
            options={
                "temperature": 0,
                "num_ctx": TEST_A_NUM_CTX,
                "num_predict": TEST_A_NUM_PREDICT,
            },
        )
        page_values = normalize_test_a_page(response_json(response))
        for field_key, value in page_values.items():
            if merged[field_key] in (None, "") and value not in (None, ""):
                merged[field_key] = value
        pages.append(
            {
                "page": page_number,
                "values": page_values,
                "seconds": round(time.perf_counter() - page_started, 3),
                "model": response_metadata(response),
            }
        )
        print(f"    Test A page {page_number}/{len(page_images)} complete", flush=True)
    return {
        "values": merged,
        "pages": pages,
        "seconds": round(time.perf_counter() - started, 3),
    }


def parse_pages(client: ollama.Client, page_images: list[bytes]) -> tuple[list[dict[str, Any]], float]:
    """Use GLM-OCR's document-recognition prompt to transcribe every page."""
    started = time.perf_counter()
    pages: list[dict[str, Any]] = []
    for page_number, image in enumerate(page_images, start=1):
        page_started = time.perf_counter()
        response = client.generate(
            model=MODEL,
            prompt="Text Recognition:",
            images=[image],
            stream=False,
            options={
                "temperature": 0,
                "num_ctx": PARSE_NUM_CTX,
                "num_predict": PARSE_NUM_PREDICT,
                "top_p": 0.00001,
                "top_k": 1,
                "repeat_penalty": 1.1,
            },
        )
        pages.append(
            {
                "page": page_number,
                "text": response_text(response),
                "seconds": round(time.perf_counter() - page_started, 3),
                "model": response_metadata(response),
            }
        )
        print(f"    Test B parse page {page_number}/{len(page_images)} complete", flush=True)
    return pages, time.perf_counter() - started


def evidence_schema(page_count: int) -> dict[str, Any]:
    """Build a strict document-level value plus evidence schema."""
    properties: dict[str, Any] = {}
    for field_key, config in FIELDS.items():
        is_number = "float" in str(config["type"]).casefold()
        properties[field_key] = {
            "type": "object",
            "properties": {
                "value": {"type": ["number" if is_number else "string", "null"]},
                "raw_text": {"type": ["string", "null"]},
                "page": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": page_count,
                },
            },
            "required": ["value", "raw_text", "page"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def build_document_prompt(combined_text: str) -> str:
    """Create the evidence-backed extraction prompt for parsed document text."""
    field_descriptions = {
        key: value["description"] for key, value in FIELDS.items()
    }
    return "\n".join(
        [
            "Extract four fields from ONE multi-page supplier document packet.",
            "The page-aware text was transcribed by OCR from the original pages.",
            "Return JSON matching the supplied schema and nothing else.",
            "For every non-null value, raw_text must quote the exact supporting OCR line or lines,",
            "and page must identify the matching ===== PAGE N ===== section.",
            "Set value, raw_text, and page to null unless the page text explicitly supports the field.",
            "Do not calculate, infer, repair, combine, or invent values.",
            f"Document rules: {DOCUMENT_INSTRUCTIONS}",
            "Field definitions:",
            json.dumps(field_descriptions, ensure_ascii=False, indent=2),
            "PAGE-AWARE OCR TEXT:",
            combined_text,
        ]
    )


def normalize_evidence_result(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize evidence values and preserve their model-supplied provenance."""
    values: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    for field_key, config in FIELDS.items():
        item = raw.get(field_key)
        if not isinstance(item, dict):
            item = {"value": None, "raw_text": None, "page": None}
        findings: list[Any] = []
        value = normalize_scalar_field(
            item.get("value"),
            config,
            path=field_key,
            findings=findings,
        )
        values[field_key] = value
        evidence[field_key] = {
            "value": value,
            "raw_text": item.get("raw_text"),
            "page": item.get("page"),
        }
    return values, evidence


def validate_evidence(evidence: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Check whether claimed evidence exists on the claimed parsed page."""
    result: dict[str, Any] = {}
    by_page = {page["page"]: page["text"] for page in pages}
    for field_key, item in evidence.items():
        value = item.get("value")
        raw_text = item.get("raw_text")
        page_number = item.get("page")
        if value in (None, ""):
            result[field_key] = {
                "valid": raw_text in (None, "") and page_number is None,
                "reason": "null_value",
            }
            continue
        source_text = by_page.get(page_number)
        has_raw_text = isinstance(raw_text, str) and bool(raw_text.strip())
        on_claimed_page = (
            has_raw_text
            and isinstance(source_text, str)
            and searchable_text(raw_text) in searchable_text(source_text)
        )
        value_in_raw_text = has_raw_text and expected_visible(value, raw_text)
        result[field_key] = {
            "valid": bool(
                has_raw_text
                and source_text is not None
                and on_claimed_page
                and value_in_raw_text
            ),
            "has_raw_text": has_raw_text,
            "page_in_range": source_text is not None,
            "raw_text_on_claimed_page": bool(on_claimed_page),
            "value_in_raw_text": bool(value_in_raw_text),
        }
    return result


def run_test_b(client: ollama.Client, page_images: list[bytes]) -> dict[str, Any]:
    """Parse all pages, combine them, then extract once with evidence."""
    started = time.perf_counter()
    pages, parse_seconds = parse_pages(client, page_images)
    combined_text = "\n\n".join(
        f"===== PAGE {page['page']} =====\n{page['text']}" for page in pages
    )
    extraction_started = time.perf_counter()
    response = client.generate(
        model=MODEL,
        prompt=build_document_prompt(combined_text),
        format=evidence_schema(len(pages)),
        stream=False,
        options={
            "temperature": 0,
            "num_ctx": EXTRACT_NUM_CTX,
            "num_predict": EXTRACT_NUM_PREDICT,
        },
    )
    raw = response_json(response)
    values, evidence = normalize_evidence_result(raw)
    evidence_checks = validate_evidence(evidence, pages)
    return {
        "values": values,
        "evidence": evidence,
        "evidence_checks": evidence_checks,
        "pages": pages,
        "combined_text": combined_text,
        "timing_seconds": {
            "parse": round(parse_seconds, 3),
            "document_extraction": round(time.perf_counter() - extraction_started, 3),
            "total": round(time.perf_counter() - started, 3),
        },
        "extraction_model": response_metadata(response),
    }


def score_document(result: dict[str, Any], expected: dict[str, Any]) -> None:
    """Attach comparable accuracy and failure classification to both tests."""
    test_a_matches = {
        key: values_match(result["test_a"]["values"].get(key), value)
        for key, value in expected.items()
    }
    test_b_matches = {
        key: values_match(result["test_b"]["values"].get(key), value)
        for key, value in expected.items()
    }
    visibility = {
        key: expected_visible(value, result["test_b"]["combined_text"])
        for key, value in expected.items()
    }
    classifications: dict[str, str] = {}
    for field_key in FIELDS:
        if not visibility[field_key]:
            classifications[field_key] = "ocr_or_parsing_failure"
        elif not test_b_matches[field_key]:
            classifications[field_key] = "semantic_selection_failure"
        elif not result["test_b"]["evidence_checks"][field_key]["valid"]:
            classifications[field_key] = "evidence_failure"
        else:
            classifications[field_key] = "correct"
    result["test_a"]["matches"] = test_a_matches
    result["test_a"]["document_exact"] = all(test_a_matches.values())
    result["test_b"]["expected_visible_in_parsed_text"] = visibility
    result["test_b"]["matches"] = test_b_matches
    result["test_b"]["failure_classification"] = classifications
    result["test_b"]["document_exact"] = all(test_b_matches.values())


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate document and field metrics for the final report."""
    total_fields = len(results) * len(FIELDS)
    test_a_correct = sum(sum(item["test_a"]["matches"].values()) for item in results)
    test_b_correct = sum(sum(item["test_b"]["matches"].values()) for item in results)
    classifications = {
        name: sum(
            value == name
            for item in results
            for value in item["test_b"]["failure_classification"].values()
        )
        for name in (
            "correct",
            "ocr_or_parsing_failure",
            "semantic_selection_failure",
            "evidence_failure",
        )
    }
    return {
        "documents": len(results),
        "total_fields": total_fields,
        "test_a": {
            "fields_correct": test_a_correct,
            "documents_exact": sum(item["test_a"]["document_exact"] for item in results),
            "seconds": round(sum(item["test_a"]["seconds"] for item in results), 3),
        },
        "test_b": {
            "fields_correct": test_b_correct,
            "documents_exact": sum(item["test_b"]["document_exact"] for item in results),
            "expected_values_visible_in_parsed_text": sum(
                sum(item["test_b"]["expected_visible_in_parsed_text"].values())
                for item in results
            ),
            "valid_evidence_fields": sum(
                sum(
                    check["valid"]
                    for field_key, check in item["test_b"]["evidence_checks"].items()
                    if item["test_b"]["values"][field_key] not in (None, "")
                )
                for item in results
            ),
            "classifications": classifications,
            "seconds": round(
                sum(item["test_b"]["timing_seconds"]["total"] for item in results),
                3,
            ),
        },
    }


def main() -> int:
    """Run both experiments against the four selected PDFs."""
    missing = [str(PDF_DIR / filename) for filename in GROUND_TRUTH if not (PDF_DIR / filename).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing test PDFs: {missing}")

    schemas = build_glm_ocr_schemas(FIELDS)
    if schemas.scalar_page_schema is None:
        raise RuntimeError("Production scalar page schema was not generated")
    test_a_prompt = build_scalar_object_prompt(
        schemas.scalar_fields,
        schemas.scalar_page_schema,
        document_instructions=DOCUMENT_INSTRUCTIONS,
        prompt_style="detailed",
    )
    client = ollama.Client(host=OLLAMA_HOST, timeout=600)
    adapter = GlmOcrAdapter(
        ollama_host=OLLAMA_HOST,
        model=MODEL,
        dpi=DPI,
        num_ctx=TEST_A_NUM_CTX,
        num_predict=TEST_A_NUM_PREDICT,
        timeout_seconds=600,
        client=client,
    )

    results: list[dict[str, Any]] = []
    for document_number, (filename, expected) in enumerate(GROUND_TRUTH.items(), start=1):
        print(f"[{document_number}/{len(GROUND_TRUTH)}] {filename}", flush=True)
        page_images = adapter.render_pdf(str(PDF_DIR / filename))
        result = {
            "pdf": filename,
            "page_count": len(page_images),
            "expected": expected,
            "test_a": run_test_a(client, page_images, test_a_prompt, schemas.scalar_page_schema),
            "test_b": run_test_b(client, page_images),
        }
        score_document(result, expected)
        results.append(result)
        print(
            json.dumps(
                {
                    "test_a": result["test_a"]["values"],
                    "test_b": result["test_b"]["values"],
                    "test_a_exact": result["test_a"]["document_exact"],
                    "test_b_exact": result["test_b"]["document_exact"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )

    summary = build_summary(results)
    payload = {
        "experiment": {
            "model": MODEL,
            "dpi": DPI,
            "test_a": "per-page full-schema KIE plus first-nonempty merge",
            "test_b": (
                "per-page GLM-OCR parsing with official Text Recognition prompt, "
                "page-aware text assembly, and one evidence-backed text extraction"
            ),
            "production_code_changed": False,
        },
        "summary": summary,
        "results": results,
    }
    output_path = ROOT / "tmp" / "glm_ocr_test_a_b_results.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(output_path)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
