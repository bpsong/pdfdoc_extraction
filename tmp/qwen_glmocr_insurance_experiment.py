"""Throwaway GLM-OCR-to-Qwen experiment for an unstructured insurance invoice."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import ollama

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tmp.qwen_glmocr_superstore_experiment import (
    create_sdk_parser,
    normalize_text,
    page_evidence,
    parse_pdf,
    render_first_page,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PDF_PATH = ROOT / "sample_invoice.pdf"
DEFAULT_CHECKPOINT = ROOT / "tmp" / "qwen_glmocr_insurance_checkpoint.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "qwen_glmocr_insurance_results.json"
MODEL = "qwen3.5:9b-q4_K_M"
OLLAMA_HOST = "http://127.0.0.1:11434"

FIELDS = {
    "supplier_name": (
        "Full legal name of the insurance company issuing the invoice, from the "
        "issuer header. Never select the insured, client, policyholder, broker, "
        "agent, or payment recipient."
    ),
    "invoice_number": (
        "Exact identifier printed beside Document No, Invoice No, Tax Invoice No, "
        "Debit Note No, or Credit Note No. Do not return the policy, account, "
        "endorsement, or prior-policy number."
    ),
    "policy_number": (
        "Exact main insurance Policy No, preserving visible letters, digits, "
        "slashes, spaces, and revision suffix."
    ),
    "insurance_start_date": (
        "Exact date beside FROM inside the labelled Period of Insurance block. "
        "Never use Date of Issue."
    ),
    "insurance_end_date": (
        "Exact date beside TO inside the same labelled Period of Insurance block. "
        "Never use Date of Issue."
    ),
    "total_premium": (
        "Final Total Premium as digits and a decimal point only. Ignore Gross "
        "Premium, currency codes, separators, and leading masking asterisks."
    ),
    "client_name": (
        "Full insured or client name inside the labelled Name and Address of "
        "Insured block. Never return the issuing insurance company."
    ),
    "client_address": (
        "All address lines belonging to the same labelled Name and Address of "
        "Insured block, joined into one string. Do not include the client name or "
        "the issuer's header address."
    ),
}

GROUND_TRUTH = {
    "supplier_name": "Liberty Insurance Pte Ltd",
    "invoice_number": "DN24197471",
    "policy_number": "SD24B39161 / R 0",
    "insurance_start_date": "25 NOV 2024",
    "insurance_end_date": "24 NOV 2026",
    "total_premium": 70.0,
    "client_name": "KIM BOCK CONTRACTOR PRIVATE LIMITED",
    "client_address": (
        "3 PEMIMPIN DRIVE #05-05 LIP HING INDUSTRIAL BUILDING SINGAPORE 576147"
    ),
}

SYSTEM_RULES = """Use only the supplied page-aware OCR evidence.
Do not use the filename, expected answers, or outside knowledge. Distinguish the
issuing insurer from the insured client. Keep the FROM and TO dates together in
the Period of Insurance block and never substitute Date of Issue. Treat Policy
No and Document No as different identifiers. Every nonempty value must cite at
least one short exact contiguous quote from its claimed OCR page. Return an
empty value and empty evidence only when OCR does not support the field."""


def parse_args() -> argparse.Namespace:
    """Parse experiment arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser.parse_args()


def evidence_item_schema(max_page: int) -> dict[str, Any]:
    """Return exact-page-evidence JSON schema."""
    return {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "minimum": 1, "maximum": max_page},
            "quote": {"type": "string", "maxLength": 240},
        },
        "required": ["page", "quote"],
        "additionalProperties": False,
    }


def field_schema(max_page: int, field_key: str) -> dict[str, Any]:
    """Return one focused field response schema."""
    return {
        "type": "object",
        "properties": {
            "value": {"type": "string", "description": FIELDS[field_key]},
            "evidence": {
                "type": "array",
                "maxItems": 3,
                "items": evidence_item_schema(max_page),
            },
        },
        "required": ["value", "evidence"],
        "additionalProperties": False,
    }


def compound_schema(max_page: int) -> dict[str, Any]:
    """Return an all-fields response schema for the baseline call."""
    properties: dict[str, Any] = {}
    for field_key in FIELDS:
        properties[field_key] = field_schema(max_page, field_key)
    return {
        "type": "object",
        "properties": properties,
        "required": list(FIELDS),
        "additionalProperties": False,
    }


def call_qwen(
    client: ollama.Client,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    num_ctx: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call Qwen with deterministic structured output and one JSON retry."""
    started = time.perf_counter()
    errors: list[str] = []
    for attempt in range(2):
        attempt_prompt = prompt
        if attempt:
            attempt_prompt += (
                "\n\nRETRY: Return only complete JSON matching the schema. Keep "
                "quotes short and do not add explanations."
            )
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_RULES},
                {"role": "user", "content": attempt_prompt},
            ],
            format=schema,
            think=False,
            stream=False,
            options={"temperature": 0, "num_ctx": num_ctx, "num_predict": 1536},
            keep_alive="10m",
        )
        try:
            decoded = json.loads(response.message.content or "")
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(decoded, dict):
            return decoded, {
                "seconds": round(time.perf_counter() - started, 3),
                "attempts": attempt + 1,
                "prompt_eval_count": response.prompt_eval_count,
                "eval_count": response.eval_count,
                "prior_errors": errors,
            }
        errors.append("response was not a JSON object")
    raise ValueError(f"Qwen failed to return valid JSON: {errors}")


def normalized_value(field_key: str, value: Any) -> Any:
    """Normalize only comparison-safe whitespace and numeric premium syntax."""
    if field_key == "total_premium":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if not isinstance(value, str) or not value.strip():
            return None
        cleaned = value.replace(",", "").replace("$", "").replace("*", "").strip()
        cleaned = re.sub(r"^[A-Za-z]{3}\s*", "", cleaned)
        return float(cleaned) if re.fullmatch(r"\d+(?:\.\d+)?", cleaned) else None
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def normalize_extraction(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert raw field objects into business values."""
    values: dict[str, Any] = {}
    for field_key in FIELDS:
        field = raw.get(field_key)
        value = field.get("value") if isinstance(field, dict) else None
        values[field_key] = normalized_value(field_key, value)
    return values


def validate_evidence(
    raw: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Validate that every quote occurs on its claimed OCR page."""
    page_text = {
        int(page["page"]): normalize_text(page_evidence([page])) for page in pages
    }
    checks: dict[str, dict[str, Any]] = {}
    for field_key in FIELDS:
        field = raw.get(field_key)
        if not isinstance(field, dict):
            checks[field_key] = {"valid": False, "grounded": False, "quotes": []}
            continue
        value = normalized_value(field_key, field.get("value"))
        evidence = field.get("evidence")
        quote_checks: list[dict[str, Any]] = []
        if isinstance(evidence, list):
            for item in evidence:
                page = item.get("page") if isinstance(item, dict) else None
                quote = item.get("quote") if isinstance(item, dict) else None
                valid = (
                    isinstance(page, int)
                    and isinstance(quote, str)
                    and bool(normalize_text(quote))
                    and normalize_text(quote) in page_text.get(page, "")
                )
                quote_checks.append({"page": page, "quote": quote, "valid": valid})
        valid = bool(quote_checks) and all(item["valid"] for item in quote_checks)
        if value is None:
            valid = not quote_checks
        checks[field_key] = {
            "valid": valid,
            "grounded": value is not None and valid,
            "quotes": quote_checks,
        }
    return checks


def field_prompt(field_key: str, evidence: str) -> str:
    """Build one field-isolated prompt."""
    specific = {
        "supplier_name": (
            "Prefer the legal company name in the page header beside its corporate "
            "address. Do not use the Name and Address of Insured block."
        ),
        "invoice_number": (
            "On a Tax Invoice/Debit Note, Document No is the invoice/debit-note "
            "identifier when there is no separate Invoice No."
        ),
        "policy_number": "Copy the complete value beside Policy No, including revision suffix.",
        "insurance_start_date": (
            "Find Period of Insurance first, then copy only its FROM date."
        ),
        "insurance_end_date": "Find Period of Insurance first, then copy only its TO date.",
        "total_premium": (
            "Use only the Total Premium row. Remove currency and leading masking "
            "asterisks, returning digits and decimal point."
        ),
        "client_name": "Use only the name inside Name and Address of Insured.",
        "client_address": (
            "Use every address line below the insured name in that same block and "
            "stop at the block boundary. Exclude the insured name itself."
        ),
    }
    return f"""Extract only one insurance invoice field.
Field: {field_key}
Definition: {FIELDS[field_key]}
Rule: {specific[field_key]}

Return the exact printed text except for total_premium normalization. Cite exact
OCR evidence. Do not return another field from a nearby row.

OCR EVIDENCE
{evidence}"""


def image_recovery(
    client: ollama.Client,
    model: str,
    field_key: str,
) -> tuple[Any, dict[str, Any]]:
    """Recover a missing field from the original page with Qwen vision."""
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "description": FIELDS[field_key]}},
        "required": ["value"],
        "additionalProperties": False,
    }
    started = time.perf_counter()
    extra = (
        " Preserve every visibly printed space around the slash and revision "
        "suffix exactly; do not normalize the identifier."
        if field_key == "policy_number"
        else ""
    )
    response = client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Inspect this insurance invoice image. Extract only {field_key}. "
                    f"{FIELDS[field_key]} Return only the exact field value.{extra}"
                ),
                "images": [render_first_page(PDF_PATH)],
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
    return normalized_value(field_key, value), {
        "seconds": round(time.perf_counter() - started, 3),
        "raw": decoded,
    }


def values_match(actual: Any, expected: Any) -> bool:
    """Compare extracted values while ignoring whitespace and casing."""
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return isinstance(actual, (int, float)) and abs(float(actual) - float(expected)) < 0.005
    return isinstance(actual, str) and normalize_text(actual) == normalize_text(str(expected))


def same_identifier(actual: Any, recovered: Any) -> bool:
    """Confirm image formatting describes the same identifier as OCR text."""
    if not isinstance(actual, str) or not isinstance(recovered, str):
        return False
    canonical = lambda value: re.sub(r"\s+", "", value).casefold()
    return canonical(actual) == canonical(recovered)


def score(values: dict[str, Any]) -> dict[str, bool]:
    """Score all configured values against visually established truth."""
    return {
        field_key: values_match(values.get(field_key), expected)
        for field_key, expected in GROUND_TRUTH.items()
    }


def main() -> int:
    """Run compound and field-isolated extraction over one insurance invoice."""
    args = parse_args()
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    else:
        with create_sdk_parser() as parser:
            print("[OCR] Parsing sample_invoice.pdf", flush=True)
            parsed = parse_pdf(parser, PDF_PATH)
        checkpoint = {"parse": parsed}
        args.checkpoint.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[OCR] {parsed['region_count']} regions, {parsed['char_count']} chars, "
            f"{parsed['seconds']}s",
            flush=True,
        )

    parsed = checkpoint["parse"]
    pages = parsed["pages"]
    evidence = page_evidence(pages)
    max_page = max(int(page["page"]) for page in pages)
    client = ollama.Client(host=OLLAMA_HOST, timeout=args.timeout)

    print("[Qwen] Compound extraction", flush=True)
    compound_prompt = "\n".join(
        [
            "Extract all configured insurance invoice fields.",
            *[f"- {key}: {description}" for key, description in FIELDS.items()],
            "",
            "OCR EVIDENCE",
            evidence,
        ]
    )
    compound_raw, compound_metrics = call_qwen(
        client,
        args.model,
        compound_prompt,
        compound_schema(max_page),
        args.num_ctx,
    )
    compound_values = normalize_extraction(compound_raw)
    compound = {
        "values": compound_values,
        "raw": compound_raw,
        "evidence_checks": validate_evidence(compound_raw, pages),
        "matches": score(compound_values),
        "metrics": compound_metrics,
    }
    compound["document_exact"] = all(compound["matches"].values())
    print(json.dumps(compound["values"], ensure_ascii=False, indent=2), flush=True)

    print("[Qwen] Field-isolated extraction", flush=True)
    isolated_raw: dict[str, Any] = {}
    isolated_metrics: dict[str, Any] = {}
    image_recoveries: dict[str, Any] = {}
    for field_key in FIELDS:
        raw, metrics = call_qwen(
            client,
            args.model,
            field_prompt(field_key, evidence),
            field_schema(max_page, field_key),
            args.num_ctx,
        )
        isolated_raw[field_key] = raw
        isolated_metrics[field_key] = metrics
    isolated_values = normalize_extraction(isolated_raw)
    isolated_checks = validate_evidence(isolated_raw, pages)
    for field_key in FIELDS:
        if isolated_values[field_key] is None or field_key == "policy_number":
            recovered, recovery_metrics = image_recovery(client, args.model, field_key)
            image_recoveries[field_key] = recovery_metrics
            if isolated_values[field_key] is None and recovered is not None:
                isolated_values[field_key] = recovered
            elif field_key == "policy_number" and same_identifier(
                isolated_values[field_key], recovered
            ):
                isolated_values[field_key] = recovered
    isolated = {
        "values": isolated_values,
        "raw": isolated_raw,
        "evidence_checks": isolated_checks,
        "image_recoveries": image_recoveries,
        "matches": score(isolated_values),
        "metrics": isolated_metrics,
    }
    isolated["document_exact"] = all(isolated["matches"].values())
    print(json.dumps(isolated["values"], ensure_ascii=False, indent=2), flush=True)

    payload = {
        "experiment": {
            "pipeline": "official GLM-OCR SDK parse -> Qwen evidence resolver",
            "ocr_model": "glm-ocr:latest",
            "resolver_model": args.model,
            "production_code_changed": False,
            "expected_values_used_in_prompts": False,
        },
        "ground_truth": GROUND_TRUTH,
        "parse": parsed,
        "compound": compound,
        "isolated": isolated,
        "summary": {
            "compound_fields_correct": sum(compound["matches"].values()),
            "compound_fields_grounded": sum(
                check["grounded"] for check in compound["evidence_checks"].values()
            ),
            "compound_document_exact": compound["document_exact"],
            "isolated_fields_correct": sum(isolated["matches"].values()),
            "isolated_fields_grounded_in_sdk_text": sum(
                check["grounded"] for check in isolated["evidence_checks"].values()
            ),
            "isolated_image_recovery_or_verification_fields": sorted(image_recoveries),
            "isolated_document_exact": isolated["document_exact"],
            "sdk_parse_seconds": parsed["seconds"],
            "compound_seconds": compound_metrics["seconds"],
            "isolated_seconds": round(
                sum(metric["seconds"] for metric in isolated_metrics.values())
                + sum(metric["seconds"] for metric in image_recoveries.values()),
                3,
            ),
        },
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(f"Output: {args.output}", flush=True)
    return 0 if isolated["document_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
