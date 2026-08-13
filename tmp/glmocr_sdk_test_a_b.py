"""Throwaway A/B benchmark using the official GLM-OCR SDK for Test B.

Test A is the current production-style per-page schema KIE plus first-nonempty
merge. Test B passes each PDF directly to ``GlmOcr.parse`` as one document,
rebuilds page-aware text from the SDK layout JSON, and runs the same
evidence-backed document extraction used by the earlier simulation.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import ollama
from glmocr import GlmOcr, __version__ as glmocr_version


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from standard_step.extraction.glm_ocr_adapter import GlmOcrAdapter  # noqa: E402
from standard_step.extraction.glm_ocr_prompt import (  # noqa: E402
    build_glm_ocr_schemas,
    build_scalar_object_prompt,
)
from tmp.glm_ocr_test_a_b import (  # noqa: E402
    DOCUMENT_INSTRUCTIONS,
    DPI,
    EXTRACT_NUM_CTX,
    EXTRACT_NUM_PREDICT,
    FIELDS,
    GROUND_TRUTH,
    MODEL,
    OLLAMA_HOST,
    PDF_DIR,
    build_document_prompt,
    evidence_schema,
    expected_visible,
    normalize_evidence_result,
    run_test_a,
    validate_evidence,
    values_match,
)


SDK_PDF_DPI = 200
SDK_REGION_MAX_TOKENS = 512
SDK_MAX_WORKERS = 1
SDK_REQUEST_TIMEOUT = 300


def sdk_overrides() -> dict[str, Any]:
    """Return minimal overrides layered over the SDK's complete defaults."""
    return {
        "pipeline.ocr_api.api_path": "/api/generate",
        "pipeline.ocr_api.api_mode": "ollama_generate",
        "pipeline.ocr_api.request_timeout": SDK_REQUEST_TIMEOUT,
        "pipeline.ocr_api.connection_pool_size": 4,
        "pipeline.max_workers": SDK_MAX_WORKERS,
        "pipeline.page_loader.pdf_dpi": SDK_PDF_DPI,
        "pipeline.page_loader.max_tokens": SDK_REGION_MAX_TOKENS,
        "logging.level": "INFO",
    }


def create_sdk_parser() -> GlmOcr:
    """Initialize the self-hosted SDK against the existing Ollama model."""
    return GlmOcr(
        mode="selfhosted",
        model=MODEL,
        ocr_api_host="127.0.0.1",
        ocr_api_port=11434,
        layout_device="cpu",
        _dotted=sdk_overrides(),
    )


def page_text_from_regions(regions: list[dict[str, Any]]) -> str:
    """Assemble one page in SDK reading order while retaining region labels."""
    parts: list[str] = []
    for region in regions:
        content = region.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        native_label = str(region.get("native_label") or region.get("label") or "text")
        parts.append(f"[REGION: {native_label}]\n{content.strip()}")
    return "\n\n".join(parts)


def parse_with_sdk(parser: GlmOcr, pdf_path: Path) -> dict[str, Any]:
    """Parse one full PDF through the SDK and expose page-aware outputs."""
    started = time.perf_counter()
    result = parser.parse(
        str(pdf_path),
        save_layout_visualization=False,
        preserve_order=True,
    )
    seconds = time.perf_counter() - started
    if not isinstance(result.json_result, list):
        raise TypeError("SDK json_result must be a list of pages")
    pages: list[dict[str, Any]] = []
    for page_number, raw_regions in enumerate(result.json_result, start=1):
        if not isinstance(raw_regions, list):
            raise TypeError(f"SDK page {page_number} must contain a region list")
        regions = [region for region in raw_regions if isinstance(region, dict)]
        pages.append(
            {
                "page": page_number,
                "text": page_text_from_regions(regions),
                "region_count": len(regions),
                "regions": regions,
            }
        )
    combined_text = "\n\n".join(
        f"===== PAGE {page['page']} =====\n{page['text']}" for page in pages
    )
    return {
        "pages": pages,
        "combined_text": combined_text,
        "sdk_markdown": result.markdown_result or "",
        "sdk_raw_json_result": result.raw_json_result,
        "sdk_parse_seconds": round(seconds, 3),
        "region_count": sum(page["region_count"] for page in pages),
    }


def extract_from_sdk_text(
    client: ollama.Client,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Run one document-level evidence extraction over SDK page text."""
    started = time.perf_counter()
    response = client.generate(
        model=MODEL,
        prompt=build_document_prompt(parsed["combined_text"]),
        format=evidence_schema(len(parsed["pages"])),
        stream=False,
        options={
            "temperature": 0,
            "num_ctx": EXTRACT_NUM_CTX,
            "num_predict": EXTRACT_NUM_PREDICT,
        },
    )
    response_text = response.get("response") if isinstance(response, dict) else response.response
    try:
        raw = json.loads(response_text)
    except json.JSONDecodeError as exc:
        empty_evidence = {
            key: {"value": None, "raw_text": None, "page": None}
            for key in FIELDS
        }
        return {
            "values": {key: None for key in FIELDS},
            "evidence": empty_evidence,
            "evidence_checks": validate_evidence(empty_evidence, parsed["pages"]),
            "seconds": round(time.perf_counter() - started, 3),
            "error": f"Invalid JSON response: {exc}",
            "raw_response": response_text,
        }
    if not isinstance(raw, dict):
        raise TypeError("Document extraction response must be an object")
    values, evidence = normalize_evidence_result(raw)
    checks = validate_evidence(evidence, parsed["pages"])
    return {
        "values": values,
        "evidence": evidence,
        "evidence_checks": checks,
        "seconds": round(time.perf_counter() - started, 3),
    }


def score_test_b(test_b: dict[str, Any], expected: dict[str, Any]) -> None:
    """Score SDK parsing separately from downstream semantic extraction."""
    visibility = {
        key: expected_visible(value, test_b["combined_text"])
        for key, value in expected.items()
    }
    matches = {
        key: values_match(test_b["document_extraction"]["values"].get(key), value)
        for key, value in expected.items()
    }
    classifications: dict[str, str] = {}
    for field_key in FIELDS:
        evidence_valid = test_b["document_extraction"]["evidence_checks"][field_key]["valid"]
        if not visibility[field_key]:
            classifications[field_key] = "sdk_parsing_failure"
        elif not matches[field_key]:
            classifications[field_key] = "semantic_selection_failure"
        elif not evidence_valid:
            classifications[field_key] = "evidence_failure"
        else:
            classifications[field_key] = "correct"
    test_b["expected_visible_in_sdk_text"] = visibility
    test_b["matches"] = matches
    test_b["failure_classification"] = classifications
    test_b["document_exact"] = all(matches.values())


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate control, SDK parsing, and downstream extraction metrics."""
    total_fields = len(results) * len(FIELDS)
    names = (
        "correct",
        "sdk_parsing_failure",
        "semantic_selection_failure",
        "evidence_failure",
    )
    return {
        "documents": len(results),
        "total_fields": total_fields,
        "test_a": {
            "fields_correct": sum(sum(item["test_a"]["matches"].values()) for item in results),
            "documents_exact": sum(item["test_a"]["document_exact"] for item in results),
            "seconds": round(sum(item["test_a"]["seconds"] for item in results), 3),
        },
        "test_b_sdk": {
            "expected_values_visible": sum(
                sum(item["test_b"]["expected_visible_in_sdk_text"].values())
                for item in results
            ),
            "fields_extracted_correctly": sum(
                sum(item["test_b"]["matches"].values()) for item in results
            ),
            "documents_exact": sum(item["test_b"]["document_exact"] for item in results),
            "valid_nonempty_evidence_fields": sum(
                check["valid"]
                for item in results
                for field_key, check in item["test_b"]["document_extraction"]["evidence_checks"].items()
                if item["test_b"]["document_extraction"]["values"][field_key] not in (None, "")
            ),
            "classifications": {
                name: sum(
                    value == name
                    for item in results
                    for value in item["test_b"]["failure_classification"].values()
                )
                for name in names
            },
            "sdk_parse_seconds": round(
                sum(item["test_b"]["sdk_parse_seconds"] for item in results),
                3,
            ),
            "document_extraction_seconds": round(
                sum(item["test_b"]["document_extraction"]["seconds"] for item in results),
                3,
            ),
            "regions": sum(item["test_b"]["region_count"] for item in results),
        },
    }


def main() -> int:
    """Run the SDK-native A/B benchmark against all four selected PDFs."""
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
        num_ctx=8192,
        num_predict=512,
        timeout_seconds=600,
        client=client,
    )

    output_path = ROOT / "tmp" / "glmocr_sdk_test_a_b_results.json"
    checkpoint_path = ROOT / "tmp" / "glmocr_sdk_test_a_b_checkpoint.json"
    results: list[dict[str, Any]] = []
    with create_sdk_parser() as parser:
        for index, (filename, expected) in enumerate(GROUND_TRUTH.items(), start=1):
            print(f"[{index}/{len(GROUND_TRUTH)}] {filename}", flush=True)
            page_images = adapter.render_pdf(str(PDF_DIR / filename))
            test_a = run_test_a(client, page_images, test_a_prompt, schemas.scalar_page_schema)
            test_a["matches"] = {
                key: values_match(test_a["values"].get(key), value)
                for key, value in expected.items()
            }
            test_a["document_exact"] = all(test_a["matches"].values())
            print("    Test B SDK whole-PDF parse starting", flush=True)
            test_b = parse_with_sdk(parser, PDF_DIR / filename)
            print(
                f"    Test B SDK parse complete: {test_b['region_count']} regions, "
                f"{test_b['sdk_parse_seconds']}s",
                flush=True,
            )
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "state": "sdk_parse_complete",
                        "pdf": filename,
                        "expected": expected,
                        "test_a": test_a,
                        "test_b": test_b,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            test_b["document_extraction"] = extract_from_sdk_text(client, test_b)
            score_test_b(test_b, expected)
            results.append(
                {
                    "pdf": filename,
                    "page_count": len(page_images),
                    "expected": expected,
                    "test_a": test_a,
                    "test_b": test_b,
                }
            )
            checkpoint_path.write_text(
                json.dumps(
                    {"state": "documents_complete", "results": results},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "test_a": test_a["values"],
                        "sdk_visibility": test_b["expected_visible_in_sdk_text"],
                        "test_b_extraction": test_b["document_extraction"]["values"],
                        "test_b_classification": test_b["failure_classification"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                flush=True,
            )

    summary = build_summary(results)
    payload = {
        "experiment": {
            "glmocr_sdk_version": glmocr_version,
            "model": MODEL,
            "test_a": "production-style per-page schema KIE plus first-nonempty merge",
            "test_b": (
                "native GlmOcr.parse(full PDF), page-aware SDK layout text, then one "
                "evidence-backed document extraction"
            ),
            "sdk": {
                "mode": "selfhosted",
                "backend": "Ollama native /api/generate",
                "layout_model": "PaddlePaddle/PP-DocLayoutV3_safetensors",
                "layout_device": "cpu",
                "pdf_dpi": SDK_PDF_DPI,
                "region_max_tokens": SDK_REGION_MAX_TOKENS,
                "max_workers": SDK_MAX_WORKERS,
                "note": (
                    "The official 8192-token default did not complete the first "
                    "two-page smoke test after approximately 14 minutes."
                ),
            },
            "production_code_changed": False,
        },
        "summary": summary,
        "results": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(output_path)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
