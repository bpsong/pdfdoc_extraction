"""Test a non-duplicated production GLM prompt with schema passed via format."""

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
    "insurance_company": {
        "type": "str",
        "alias": "Insurance Company",
        "description": (
            "Full legal name of the issuing insurer or underwriter in the page "
            "header beside its logo and registration details; never the insured, "
            "policyholder, broker, agent, or payment recipient."
        ),
    },
    "customer": {
        "type": "Dict[str, Any]",
        "alias": "Customer / Insured",
        "description": "The labelled Name and Address of Insured block.",
        "object_fields": {
            "name": {
                "type": "str",
                "alias": "Customer Name",
                "description": "Name in the labelled insured block.",
            },
            "address": {
                "type": "str",
                "alias": "Customer Address",
                "description": "All address lines in the same insured block.",
            },
        },
    },
    "coverage_period": {
        "type": "Dict[str, Any]",
        "alias": "Period of Insurance",
        "description": "The labelled Period of Insurance FROM/TO block.",
        "object_fields": {
            "start_date": {
                "type": "str",
                "alias": "FROM",
                "description": "Date beside FROM; never Date of Issue.",
                "normalizer": "iso_date",
            },
            "end_date": {
                "type": "str",
                "alias": "TO",
                "description": "Date beside TO in the same block.",
                "normalizer": "iso_date",
            },
        },
    },
    "total_premium": {
        "type": "float",
        "alias": "Total Premium",
        "description": (
            "Final Total Premium as a number after removing currency text and "
            "leading masking asterisks; not Gross Premium."
        ),
    },
    "policy_number": {
        "type": "str",
        "alias": "Policy No.",
        "description": "Main value beside Policy No.; not another reference number.",
    },
    "note_type": {
        "type": "str",
        "alias": "Debit or Credit Note",
        "description": "Return debit for Debit Note or credit for Credit Note.",
        "choices": ["debit", "credit"],
    },
}


PROMPT = """Extract the configured values from this single PDF page.
Use only information visibly present in the document image.
Return only one JSON object matching the supplied JSON Schema; do not add Markdown or explanations.
Use the configured field keys exactly and return every configured key.
Do not invent, infer, or copy an example value.
For numeric fields, return JSON numbers without currency or masking characters.
For fields normalized as iso_date, transcribe the selected date exactly as printed.

Field rules:
- insurance_company: the issuing insurer or underwriter from the page header beside its logo and registration details; never the insured or policyholder.
- customer: the name and address from one labelled Name and Address of Insured block; never the insurer header.
- coverage_period: the two dates in one labelled Period of Insurance block. start_date is beside FROM and end_date is beside TO. Never use Date of Issue.
- total_premium: the final Total Premium as a number, not Gross Premium.
- policy_number: the main value beside Policy No.
- note_type: debit for a Debit Note or credit for a Credit Note.
"""


def main() -> None:
    schemas = build_glm_ocr_schemas(FIELDS)
    if schemas.scalar_page_schema is None:
        raise RuntimeError("Missing scalar page schema")
    schema = schemas.scalar_page_schema
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "grouped-lean-final-prompt.txt").write_text(
        PROMPT, encoding="utf-8"
    )
    (OUT_DIR / "grouped-lean-sent-schema.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
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
