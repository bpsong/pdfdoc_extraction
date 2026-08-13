"""Throwaway live experiment for conflict-aware multi-page GLM-OCR merging."""

from __future__ import annotations

import json
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
PER_PAGE_NUM_CTX = 8192
RESOLVER_NUM_CTX = 32768
NUM_PREDICT = 512

DOCUMENT_INSTRUCTIONS = (
    "These are multi-page supplier document packets addressed to FUJI TRADING "
    "(S) PTE LTD. The packet may contain a delivery order, tax invoice, and an "
    "attached Fuji Trading purchase order. Extract values only when visibly "
    "supported on the current page. For supplier_name, return the company "
    "issuing the delivery order or invoice, or the company explicitly identified "
    "as SUPPLIER on a purchase order. FUJI TRADING (S) PTE LTD and FUJI TRADING "
    "(SINGAPORE) PTE LTD are the customer/buyer and must never be returned as "
    "supplier_name. For invoice_or_delivery_order_number, return the supplier "
    "invoice number or delivery order number, never a PO number. FTS project "
    "numbers use the format SXXXXXX: the letter S followed by six digits, for "
    "example S268588. Such a value is a project or marking number and must never "
    "be returned as the supplier invoice or delivery-order number. For "
    "purchase_order_number, return the buyer P/O number. For total_amount, use "
    "the final invoice total including GST; if there is no invoice total, use "
    "the delivery-order final total; otherwise use the purchase-order TOTAL SGD "
    "value. Return null when the requested value is not visible on the current page."
)

FIELDS: dict[str, dict[str, Any]] = {
    "supplier_name": {
        "alias": "Supplier name",
        "description": (
            "Issuing supplier name. Never return FUJI TRADING (S) PTE LTD or "
            "FUJI TRADING (SINGAPORE) PTE LTD because they are the customer/buyer."
        ),
        "schema_order": 1,
        "type": "Optional[str]",
    },
    "invoice_or_delivery_order_number": {
        "alias": "Invoice or delivery order number",
        "description": (
            "Official supplier invoice number or delivery order number; never a "
            "purchase order, FTS SXXXXXX project, marking, or reference number."
        ),
        "schema_order": 2,
        "type": "Optional[str]",
    },
    "purchase_order_number": {
        "alias": "Purchase order number",
        "description": (
            "Buyer purchase order or P/O number; never an invoice, delivery "
            "order, project, marking, or reference number."
        ),
        "schema_order": 3,
        "type": "Optional[str]",
    },
    "total_amount": {
        "alias": "Total amount",
        "description": (
            "Final payable amount including GST when an invoice total is present; "
            "otherwise final delivery-order total or purchase-order TOTAL SGD. "
            "Never select a line item, subtotal, discount, or tax amount."
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


def response_json(response: Any) -> dict[str, Any]:
    """Decode one non-streaming Ollama response."""
    text = response.get("response") if isinstance(response, dict) else response.response
    decoded = json.loads(text)
    if not isinstance(decoded, dict):
        raise TypeError("GLM-OCR response must be a JSON object")
    return decoded


def stable_value(value: Any) -> str:
    """Return a stable candidate identity key."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def values_match(actual: Any, expected: Any) -> bool:
    """Compare extracted business values without treating casing as meaningful."""
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and abs(float(actual) - float(expected)) < 0.005
    if isinstance(actual, str) and isinstance(expected, str):
        return " ".join(actual.split()).casefold() == " ".join(expected.split()).casefold()
    return actual == expected


def collect_candidates(
    client: ollama.Client,
    page_images: list[bytes],
    prompt: str,
    page_schema: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], float]:
    """Run the production-style page prompt and retain distinct field candidates."""
    page_results: list[dict[str, Any]] = []
    candidates: dict[str, list[dict[str, Any]]] = {key: [] for key in FIELDS}
    candidate_keys: dict[str, dict[str, str]] = {key: {} for key in FIELDS}
    started = time.perf_counter()

    for page_number, image in enumerate(page_images, start=1):
        response = client.generate(
            model=MODEL,
            prompt=prompt,
            images=[image],
            format=page_schema,
            stream=False,
            options={
                "temperature": 0,
                "num_ctx": PER_PAGE_NUM_CTX,
                "num_predict": NUM_PREDICT,
            },
        )
        page_data = response_json(response)
        normalized_page: dict[str, Any] = {}
        for field_key, field_config in FIELDS.items():
            alias = str(field_config.get("alias", field_key))
            found, raw_value = get_extracted_value(page_data, field_key, alias)
            if not found:
                normalized_page[field_key] = None
                continue
            findings: list[Any] = []
            value = normalize_scalar_field(
                raw_value,
                field_config,
                path=field_key,
                findings=findings,
            )
            normalized_page[field_key] = value
            if value is None or value == "":
                continue
            value_key = stable_value(value)
            existing_id = candidate_keys[field_key].get(value_key)
            if existing_id is not None:
                existing = next(
                    item for item in candidates[field_key] if item["id"] == existing_id
                )
                existing["pages"].append(page_number)
                continue
            candidate_id = f"{field_key}-c{len(candidates[field_key]) + 1}"
            candidate_keys[field_key][value_key] = candidate_id
            candidates[field_key].append(
                {"id": candidate_id, "pages": [page_number], "value": value}
            )
        page_results.append({"page": page_number, "data": normalized_page})

    return page_results, candidates, time.perf_counter() - started


def resolver_schema(
    conflicted: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build a schema that permits only candidate IDs already observed."""
    properties: dict[str, Any] = {}
    for field_key, candidates in conflicted.items():
        properties[field_key] = {
            "type": "object",
            "properties": {
                "selected_candidate_id": {
                    "type": ["string", "null"],
                    "enum": [*[item["id"] for item in candidates], None],
                },
            },
            "required": ["selected_candidate_id"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def resolve_conflicts(
    client: ollama.Client,
    page_images: list[bytes],
    candidates: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any], float]:
    """Resolve conflicting candidates with all pages while forbidding invention."""
    conflicted = {key: values for key, values in candidates.items() if len(values) > 1}
    selections: dict[str, Any] = {}
    final: dict[str, Any] = {}

    for field_key, values in candidates.items():
        if len(values) == 1:
            final[field_key] = values[0]["value"]
            selections[field_key] = {
                "selected_candidate_id": values[0]["id"],
                "method": "single_candidate",
            }
        elif not values:
            final[field_key] = None
            selections[field_key] = {
                "selected_candidate_id": None,
                "method": "no_candidate",
            }

    if not conflicted:
        return final, selections, 0.0

    descriptors = {
        key: {
            "alias": FIELDS[key]["alias"],
            "description": FIELDS[key]["description"],
            "candidates": values,
        }
        for key, values in conflicted.items()
    }
    prompt = "\n".join(
        [
            "The supplied images are consecutive pages of one PDF document packet, in page order.",
            "Resolve only the configured fields that have conflicting page candidates.",
            "Use the document images, field descriptions, and document instructions as evidence.",
            "For each field, return the ID of the best visibly supported candidate.",
            "Never create, rewrite, combine, or normalize a candidate value.",
            "Return selected_candidate_id as null when the images do not support one candidate clearly.",
            "A field's selected ID must belong to that field.",
            f"Document instructions: {DOCUMENT_INSTRUCTIONS}",
            "Field evidence:",
            json.dumps(descriptors, ensure_ascii=False, sort_keys=True),
        ]
    )
    started = time.perf_counter()
    response = client.generate(
        model=MODEL,
        prompt=prompt,
        images=page_images,
        format=resolver_schema(conflicted),
        stream=False,
        options={
            "temperature": 0,
            "num_ctx": RESOLVER_NUM_CTX,
            "num_predict": NUM_PREDICT,
        },
    )
    resolution = response_json(response)
    duration = time.perf_counter() - started

    for field_key, values in conflicted.items():
        choice = resolution.get(field_key)
        if not isinstance(choice, dict):
            choice = {"selected_candidate_id": None}
        selected_id = choice.get("selected_candidate_id")
        selected = next((item for item in values if item["id"] == selected_id), None)
        if selected is None:
            final[field_key] = None
        else:
            final[field_key] = selected["value"]
        selections[field_key] = {
            "selected_candidate_id": selected_id if selected is not None else None,
            "method": "evidence_resolver",
        }

    return final, selections, duration


def evaluate_document(
    client: ollama.Client,
    adapter: GlmOcrAdapter,
    pdf_path: Path,
    prompt: str,
    page_schema: dict[str, Any],
) -> dict[str, Any]:
    """Extract, resolve, and score one PDF."""
    page_images = adapter.render_pdf(str(pdf_path))
    page_results, candidates, extraction_seconds = collect_candidates(
        client,
        page_images,
        prompt,
        page_schema,
    )
    baseline = {
        key: values[0]["value"] if values else None for key, values in candidates.items()
    }
    final, selections, resolver_seconds = resolve_conflicts(
        client,
        page_images,
        candidates,
    )
    expected = GROUND_TRUTH[pdf_path.name]
    candidate_coverage = {
        key: any(values_match(item["value"], expected[key]) for item in values)
        for key, values in candidates.items()
    }
    baseline_matches = {
        key: values_match(baseline[key], expected[key]) for key in FIELDS
    }
    final_matches = {key: values_match(final.get(key), expected[key]) for key in FIELDS}
    return {
        "pdf": pdf_path.name,
        "page_count": len(page_images),
        "expected": expected,
        "page_results": page_results,
        "candidates": candidates,
        "candidate_ground_truth_coverage": candidate_coverage,
        "first_nonempty": baseline,
        "first_nonempty_matches": baseline_matches,
        "resolver_selections": selections,
        "evidence_resolver": final,
        "evidence_resolver_matches": final_matches,
        "document_exact": all(final_matches.values()),
        "timing_seconds": {
            "page_extraction": round(extraction_seconds, 2),
            "evidence_resolver": round(resolver_seconds, 2),
        },
    }


def main() -> int:
    """Run the four-document experiment and write an inspectable result file."""
    schemas = build_glm_ocr_schemas(FIELDS)
    if schemas.scalar_page_schema is None:
        raise RuntimeError("Scalar page schema was not generated")
    prompt = build_scalar_object_prompt(
        schemas.scalar_fields,
        schemas.scalar_page_schema,
        document_instructions=DOCUMENT_INSTRUCTIONS,
        prompt_style="detailed",
    )
    client = ollama.Client(host=OLLAMA_HOST, timeout=300)
    adapter = GlmOcrAdapter(
        ollama_host=OLLAMA_HOST,
        model=MODEL,
        dpi=216,
        num_ctx=PER_PAGE_NUM_CTX,
        num_predict=NUM_PREDICT,
        timeout_seconds=300,
        client=client,
    )

    results = []
    for filename in GROUND_TRUTH:
        print(f"Processing {filename}...", flush=True)
        result = evaluate_document(
            client,
            adapter,
            PDF_DIR / filename,
            prompt,
            schemas.scalar_page_schema,
        )
        results.append(result)
        print(
            json.dumps(
                {
                    "pdf": filename,
                    "candidate_coverage": result["candidate_ground_truth_coverage"],
                    "first_nonempty": result["first_nonempty"],
                    "evidence_resolver": result["evidence_resolver"],
                    "document_exact": result["document_exact"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )

    field_count = len(results) * len(FIELDS)
    summary = {
        "documents": len(results),
        "documents_exact": sum(result["document_exact"] for result in results),
        "candidate_coverage": sum(
            sum(result["candidate_ground_truth_coverage"].values()) for result in results
        ),
        "candidate_fields": field_count,
        "first_nonempty_correct": sum(
            sum(result["first_nonempty_matches"].values()) for result in results
        ),
        "evidence_resolver_correct": sum(
            sum(result["evidence_resolver_matches"].values()) for result in results
        ),
        "total_fields": field_count,
    }
    payload = {
        "experiment": {
            "model": MODEL,
            "dpi": 216,
            "per_page_num_ctx": PER_PAGE_NUM_CTX,
            "resolver_num_ctx": RESOLVER_NUM_CTX,
            "strategy": "distinct per-page candidates plus constrained multi-image resolver",
        },
        "summary": summary,
        "results": results,
    }
    output_path = ROOT / "tmp" / "evidence_resolver_results.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"summary": summary, "output": str(output_path)}, indent=2))
    return 0 if summary["documents_exact"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
