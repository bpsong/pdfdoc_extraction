"""Test the experimental one-object/flat-date structure with task normalization."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import ollama

from standard_step.extraction.glm_ocr_adapter import GlmOcrAdapter
from standard_step.extraction.glm_ocr_prompt import build_glm_ocr_schemas
from standard_step.extraction.structured_fields import normalize_configured_fields


REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "output/pdf/glm-ocr-date-grouping"

FIELDS: dict[str, Any] = {
    "insurance_company": {"type": "str", "alias": "Insurance Company"},
    "note_type": {
        "type": "str",
        "alias": "Debit or Credit Note",
        "choices": ["debit", "credit"],
    },
    "customer": {
        "type": "Dict[str, Any]",
        "alias": "Customer / Insured",
        "object_fields": {
            "name": {"type": "str", "alias": "Customer Name"},
            "address": {"type": "str", "alias": "Customer Address"},
        },
    },
    "total_premium": {"type": "float", "alias": "Total Premium"},
    "insurance_start_date": {
        "type": "str",
        "alias": "Insurance Start Date",
        "normalizer": "iso_date",
    },
    "insurance_end_date": {
        "type": "str",
        "alias": "Insurance End Date",
        "normalizer": "iso_date",
    },
    "policy_number": {"type": "str", "alias": "Policy Number"},
}

PROMPT = """Extract the requested fields from this insurance invoice image.

Use only information visible in the document. Return only JSON matching the provided schema; do not add Markdown or explanations.

Field rules:
- insurance_company: the issuing insurer or underwriter. Prefer its full legal entity name from the header; do not return the insured, policyholder, broker, or payment recipient.
- note_type: debit or credit from the document's invoice or note type.
- customer: the insured, policyholder, or billed customer. Locate the labelled Name and Address of Insured, Insured, Policyholder, Customer, or Bill To block. customer.name is the first non-label line in that block. customer.address is every following address line in that same block. Never use the issuing insurer's header address.
- total_premium: the final Total Premium as a number without currency text or masking asterisks. Do not select Gross Premium, an individual line amount, or tax.
- insurance_start_date and insurance_end_date: the coverage-period FROM and TO dates. Do not use Date of Issue, invoice date, document date, payment date, or due date. Transcribe both dates exactly as printed.
- policy_number: the main value beside Policy No.; not a document, account, reference, endorsement, or previous-policy number.
"""


def main() -> None:
    schemas = build_glm_ocr_schemas(FIELDS)
    if schemas.scalar_page_schema is None:
        raise RuntimeError("Missing scalar page schema")
    schema = schemas.scalar_page_schema
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "flat-lean-final-prompt.txt").write_text(PROMPT, encoding="utf-8")
    (OUT_DIR / "flat-lean-sent-schema.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    adapter = GlmOcrAdapter(
        ollama_host="http://127.0.0.1:11434",
        model="glm-ocr:latest",
        dpi=180,
        num_ctx=8192,
        num_predict=512,
        timeout_seconds=300,
    )
    images = adapter.render_pdf(str(REPO / "sample_invoice.pdf"))
    client = ollama.Client(host="http://127.0.0.1:11434", timeout=300)
    results = []
    for run_number in range(1, 4):
        started = time.perf_counter()
        response = client.generate(
            model="glm-ocr:latest",
            prompt=PROMPT,
            images=[images[0]],
            format=schema,
            stream=False,
            options={
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": 512,
            },
        )
        payload = json.loads((response.response or "").strip())
        normalized = normalize_configured_fields(payload, FIELDS)
        results.append(
            {
                "run": run_number,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "data": normalized.data,
            }
        )
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
