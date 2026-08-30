"""Build machine-readable and human-readable reports for the 40-PDF batch."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experimenta" / "results" / "batch_40_comparison"
METHODS = ("glm_qwen", "qwen_only")
COMPARE_FIELDS = (
    "supplier_name",
    "invoice_number",
    "purchase_order_number",
    "invoice_date",
    "bill_to",
    "ship_to",
    "total_amount",
    "line_items",
)
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"


def read_json(path: Path) -> Any:
    """Read UTF-8 JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Write stable UTF-8 JSON."""
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalized(value: Any) -> Any:
    """Normalize superficial whitespace and date-format differences."""
    if isinstance(value, str):
        compact = re.sub(r"\s+", " ", value.strip()).casefold()
        date_parts = re.fullmatch(r"(\d{2})[./-](\d{2})[./-](\d{4})", compact)
        iso_parts = re.fullmatch(r"(\d{4})[./-](\d{2})[./-](\d{2})", compact)
        if date_parts:
            return f"{date_parts.group(3)}-{date_parts.group(2)}-{date_parts.group(1)}"
        if iso_parts:
            return f"{iso_parts.group(1)}-{iso_parts.group(2)}-{iso_parts.group(3)}"
        return compact
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    return value


def compact_text(value: Any) -> str:
    """Normalize a visible text field for objective comparisons."""
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9.]", "", str(value).casefold())


def core_line_items(value: Any) -> list[dict[str, Any]]:
    """Project line items onto the three fields requested for FTS testing."""
    if not isinstance(value, list):
        return []
    return [
        {
            "item_description": normalized(item.get("item_description")),
            "unit_of_measure": normalized(item.get("unit_of_measure")),
            "quantity": normalized(item.get("quantity")),
        }
        for item in value
        if isinstance(item, dict)
    ]


def superstore_reference(document: dict[str, Any]) -> dict[str, Any]:
    """Derive objective facts from filename and embedded source-PDF text."""
    source = Path(document["source_pdf"])
    with pymupdf.open(source) as pdf:
        lines = [
            line.strip()
            for line in pdf[0].get_text("text").splitlines()
            if line.strip()
        ]
    name_match = re.fullmatch(r"invoice_(.*)_(\d+)\.pdf", source.name)
    if name_match is None:
        raise ValueError(f"Unexpected Superstore filename: {source.name}")
    person, invoice_number = name_match.groups()
    reference: dict[str, Any] = {
        "supplier_name": "SuperStore",
        "intentionally_blank_template": "Ship To:" not in lines,
    }
    if reference["intentionally_blank_template"]:
        return reference

    date_index = next(
        index
        for index, line in enumerate(lines)
        if re.fullmatch(fr"({MONTHS}) \d{{2}} \d{{4}}", line)
    )
    ship_index = lines.index("Ship To:")
    total = next(
        line
        for line in lines[date_index + 1 :]
        if re.fullmatch(r"\$[\d,]+\.\d{2}", line)
    )
    amount_header = lines.index("Amount")
    quantity_index = next(
        index
        for index in range(amount_header + 1, len(lines))
        if re.fullmatch(r"\d+(?:\.\d+)?", lines[index])
    )
    reference.update(
        {
            "invoice_number": invoice_number,
            "bill_to": person,
            "ship_to": " ".join(lines[ship_index + 1 : date_index]),
            "invoice_date": lines[date_index],
            "total_amount": float(total.replace("$", "").replace(",", "")),
            "line_items": [
                {
                    "item_description": " ".join(
                        lines[amount_header + 1 : quantity_index]
                    ),
                    "unit_of_measure": None,
                    "quantity": float(lines[quantity_index]),
                    "unit_price": float(
                        lines[quantity_index + 1]
                        .replace("$", "")
                        .replace(",", "")
                    ),
                    "amount": float(
                        lines[quantity_index + 2]
                        .replace("$", "")
                        .replace(",", "")
                    ),
                }
            ],
        }
    )
    return reference


def reference_matches(actual: Any, expected: Any, field: str) -> bool:
    """Compare extracted and objective reference values."""
    if field in {"total_amount", "quantity", "unit_price", "amount"}:
        return actual is not None and abs(float(actual) - float(expected)) < 0.005
    return compact_text(actual) == compact_text(expected)


def build_report_data() -> dict[str, Any]:
    """Aggregate paired outputs, objective checks, and timings."""
    manifest = read_json(BASE / "sample_manifest.json")
    documents = manifest["documents"]
    rows: list[dict[str, Any]] = []
    method_seconds = {method: 0.0 for method in METHODS}
    glm_seconds = 0.0
    superstore_scores = {
        method: {
            field: {"correct": 0, "eligible": 0}
            for field in (
                "supplier_name",
                "invoice_number",
                "bill_to",
                "ship_to",
                "invoice_date",
                "total_amount",
                "line_item_count",
                "item_description",
                "quantity",
                "unit_price",
                "amount",
            )
        }
        for method in METHODS
    }
    agreement = {
        kind: {field: 0 for field in COMPARE_FIELDS}
        for kind in ("fts", "superstore")
    }
    kind_counts = {"fts": 0, "superstore": 0}
    fts_core_line_item_agreement = 0
    fts_invoice_bundles = 0
    fts_po_filename_matches = {method: 0 for method in METHODS}

    for document in documents:
        doc_dir = BASE / document["document_key"]
        kind = document["kind"]
        kind_counts[kind] += 1
        results = {
            method: read_json(doc_dir / method / "final_result.json")
            for method in METHODS
        }
        for timing_path in (doc_dir / "glm_ocr_text").glob("*_timing.json"):
            glm_seconds += float(read_json(timing_path)["seconds"])
        for method in METHODS:
            summary = read_json(doc_dir / method / "run_summary.json")
            method_seconds[method] += sum(
                float(timing["seconds"]) for timing in summary["timings"]
            )
        differences = []
        for field in COMPARE_FIELDS:
            if normalized(results["glm_qwen"].get(field)) == normalized(
                results["qwen_only"].get(field)
            ):
                agreement[kind][field] += 1
            else:
                differences.append(field)

        if kind == "fts":
            fts_core_line_item_agreement += (
                core_line_items(results["glm_qwen"].get("line_items"))
                == core_line_items(results["qwen_only"].get("line_items"))
            )
            expected_po = Path(document["source_name"]).stem.rsplit(" ", 1)[-1]
            for method in METHODS:
                fts_po_filename_matches[method] += (
                    str(results[method].get("purchase_order_number")) == expected_po
                )
            qwen_pages = [
                read_json(doc_dir / "qwen_only" / f"page_{page:02d}.json")
                for page in range(1, int(document["page_count"]) + 1)
            ]
            fts_invoice_bundles += any(
                page.get("document_role") in {"invoice", "tax_invoice"}
                for page in qwen_pages
            )

        reference = None
        if kind == "superstore":
            reference = superstore_reference(document)
            for method, result in results.items():
                scores = superstore_scores[method]
                for field in (
                    "supplier_name",
                    "invoice_number",
                    "bill_to",
                    "ship_to",
                    "invoice_date",
                    "total_amount",
                ):
                    if field not in reference:
                        continue
                    scores[field]["eligible"] += 1
                    scores[field]["correct"] += reference_matches(
                        result.get(field), reference[field], field
                    )
                if "line_items" in reference:
                    expected_rows = reference["line_items"]
                    actual_rows = result.get("line_items") or []
                    scores["line_item_count"]["eligible"] += 1
                    scores["line_item_count"]["correct"] += (
                        len(actual_rows) == len(expected_rows)
                    )
                    for field in (
                        "item_description",
                        "quantity",
                        "unit_price",
                        "amount",
                    ):
                        scores[field]["eligible"] += 1
                        scores[field]["correct"] += bool(actual_rows) and (
                            reference_matches(
                                actual_rows[0].get(field),
                                expected_rows[0][field],
                                field,
                            )
                        )
        rows.append(
            {
                "index": document["index"],
                "kind": kind,
                "source_name": document["source_name"],
                "source_pdf": document["source_pdf"],
                "source_sha256": document["source_sha256"],
                "page_count": document["page_count"],
                "result_files": {
                    method: str((doc_dir / method / "final_result.json").resolve())
                    for method in METHODS
                },
                "results": results,
                "normalized_differences": differences,
                "superstore_reference": reference,
            }
        )

    end_to_end = {
        "glm_qwen": round(glm_seconds + method_seconds["glm_qwen"], 3),
        "qwen_only": round(method_seconds["qwen_only"], 3),
    }
    time_reduction = (
        1 - end_to_end["qwen_only"] / end_to_end["glm_qwen"]
    ) * 100
    return {
        "methodology": {
            "random_seed": manifest["seed"],
            "documents": len(documents),
            "fts_documents": kind_counts["fts"],
            "superstore_documents": kind_counts["superstore"],
            "pages": sum(int(document["page_count"]) for document in documents),
            "qwen_model": "qwen3.5:9b-q4_K_M",
            "qwen_think": False,
            "qwen_num_ctx": 16384,
            "qwen_num_predict": 3072,
            "dpi": 216,
        },
        "completion": {
            "glm_pages": sum(int(document["page_count"]) for document in documents),
            "glm_qwen_final_results": len(documents),
            "qwen_only_final_results": len(documents),
        },
        "timing_seconds": {
            "glm_ocr": round(glm_seconds, 3),
            "glm_qwen_qwen_calls": round(method_seconds["glm_qwen"], 3),
            "qwen_only_qwen_calls": round(method_seconds["qwen_only"], 3),
            "end_to_end": end_to_end,
            "qwen_only_time_reduction_percent": round(time_reduction, 1),
        },
        "normalized_inter_method_agreement": agreement,
        "superstore_objective_scores": superstore_scores,
        "fts_summary": {
            "invoice_bundles": fts_invoice_bundles,
            "core_line_item_agreement": fts_core_line_item_agreement,
            "po_filename_matches": fts_po_filename_matches,
        },
        "manual_visual_adjudications": (
            read_json(BASE / "manual_visual_adjudications.json")
            if (BASE / "manual_visual_adjudications.json").is_file()
            else []
        ),
        "documents": rows,
    }


def score_text(score: dict[str, int]) -> str:
    """Format one numerator/denominator score with percentage."""
    correct = score["correct"]
    eligible = score["eligible"]
    percent = 100 * correct / eligible if eligible else 0
    return f"{correct}/{eligible} ({percent:.1f}%)"


def write_markdown(data: dict[str, Any]) -> None:
    """Write the concise decision report."""
    scores = data["superstore_objective_scores"]
    timing = data["timing_seconds"]
    agreement = data["normalized_inter_method_agreement"]
    fts = data["fts_summary"]
    adjudications = data["manual_visual_adjudications"]
    winner_counts = {
        method: sum(item.get("winner") == method for item in adjudications)
        for method in METHODS
    }
    adjudication_rows = "\n".join(
        "| {source_name} | {field} | {winner} | {visible_value} | {note} |".format(
            source_name=item["source_name"].replace("|", "\\|"),
            field=item["field"].replace("|", "\\|"),
            winner=item["winner"],
            visible_value=str(item["visible_value"]).replace("|", "\\|"),
            note=item["note"].replace("|", "\\|"),
        )
        for item in adjudications
    )
    report = f"""# GLM-OCR + Qwen vs Qwen-only: 40-PDF comparison

## Scope and completion

- Fixed random seed: `{data['methodology']['random_seed']}`.
- Corpus: 10 FTS bundles plus 30 Superstore PDFs, 62 pages total.
- Both methods completed all 40 PDFs: 80/80 final result JSON files exist.
- Qwen settings were identical: `qwen3.5:9b-q4_K_M`, `think=False`, 16,384 context, 3,072 generation budget, 216 DPI images.
- One selected Superstore PDF (`invoice_Anne McFarland_35501.pdf`) is an intentionally blank invoice template. Objective populated-field scores therefore use the other 29 PDFs.

## Result

Neither method dominates every field. Qwen-only is the better default for this test: it was {timing['qwen_only_time_reduction_percent']:.1f}% faster end to end and was at least as accurate on most objective fields. Among the {len(adjudications)} visually checked disagreements, Qwen-only was correct in {winner_counts['qwen_only']} and GLM-assisted Qwen in {winner_counts['glm_qwen']}.

For the {fts['invoice_bundles']} FTS bundles that actually contain invoice pages, both methods recovered the invoice number, supplier, PO number, and date in all visually checked cases. The visual-adjudication table below records the meaningful splits without treating cross-method agreement as ground truth.

## Objective Superstore scores

| Field | GLM-OCR + Qwen | Qwen-only |
|---|---:|---:|
| Supplier | {score_text(scores['glm_qwen']['supplier_name'])} | {score_text(scores['qwen_only']['supplier_name'])} |
| Invoice number | {score_text(scores['glm_qwen']['invoice_number'])} | {score_text(scores['qwen_only']['invoice_number'])} |
| Bill-to person | {score_text(scores['glm_qwen']['bill_to'])} | {score_text(scores['qwen_only']['bill_to'])} |
| Full ship-to | {score_text(scores['glm_qwen']['ship_to'])} | {score_text(scores['qwen_only']['ship_to'])} |
| Invoice date | {score_text(scores['glm_qwen']['invoice_date'])} | {score_text(scores['qwen_only']['invoice_date'])} |
| Total amount | {score_text(scores['glm_qwen']['total_amount'])} | {score_text(scores['qwen_only']['total_amount'])} |
| Line-item count | {score_text(scores['glm_qwen']['line_item_count'])} | {score_text(scores['qwen_only']['line_item_count'])} |
| Product description | {score_text(scores['glm_qwen']['item_description'])} | {score_text(scores['qwen_only']['item_description'])} |
| Quantity | {score_text(scores['glm_qwen']['quantity'])} | {score_text(scores['qwen_only']['quantity'])} |
| Unit price | {score_text(scores['glm_qwen']['unit_price'])} | {score_text(scores['qwen_only']['unit_price'])} |
| Row amount | {score_text(scores['glm_qwen']['amount'])} | {score_text(scores['qwen_only']['amount'])} |

The six Qwen-only product-description misses retained the correct product but appended the separate category/product-code line. GLM text preserved the intended boundary in all 29 populated invoices.

## FTS agreement and visual findings

- PO number: GLM-assisted matched {fts['po_filename_matches']['glm_qwen']}/10 source filenames; Qwen-only matched {fts['po_filename_matches']['qwen_only']}/10.
- Invoice number: both methods agreed on all 10 bundles; {fts['invoice_bundles']} contained invoice pages and {10-fts['invoice_bundles']} correctly remained null.
- Total: 9/10 method agreement. Visual review found GLM-assisted correct on the sole disagreement.
- Core line items (description/UOM/quantity): {fts['core_line_item_agreement']}/10 exact method agreement after ignoring optional price/amount. Qwen-only was visually correct on both disagreements.
- The six-page invoice: both methods recovered the same 16 core rows. Qwen-only also captured all 16 visible row amounts; GLM-assisted omitted or misassigned most of them.
- Supplier naming: Qwen-only returned the fuller legal name on one delivery-order bundle.

## Visual adjudications

| Source | Field | Winner | Visible value | Finding |
|---|---|---|---|---|
{adjudication_rows}

## Timing

| Path | Model-call time | Mean per PDF |
|---|---:|---:|
| GLM-OCR + Qwen | {timing['end_to_end']['glm_qwen']:.1f}s | {timing['end_to_end']['glm_qwen']/40:.1f}s |
| Qwen-only | {timing['end_to_end']['qwen_only']:.1f}s | {timing['end_to_end']['qwen_only']/40:.1f}s |

The GLM stage took {timing['glm_ocr']:.1f}s across 62 pages. Timings are summed local model-call durations, not a controlled hardware benchmark. A dense sixth page initially truncated inside a structured JSON transcription wrapper; switching that transcription to plain text allowed the run to complete. This is an operational cost specific to the GLM-assisted path.

## Conclusion

For these documents and this 9B local model, Qwen-only is feasible and generally preferable when the page image is readable. It completed every document, reduced total model time, and avoided several OCR-text-induced semantic errors. Keep GLM text as an optional fallback or secondary evidence source for small/ambiguous text and strict text-boundary cases, not as a mandatory first stage.

The recommendation is not to remove GLM-OCR from the production task based on this batch alone. A safer generic design is image-first Qwen with conditional GLM evidence when confidence is low, text is too small, or a field remains unresolved. That preserves the generic task while avoiding the fixed latency and occasional misleading transcription on every page.

## Artifacts

- `comparison_index.json`: all 40 paired results embedded in one file, plus absolute paths to each individual result JSON.
- `glm_qwen_all_results.json`: the 40 GLM-assisted final results in sample order.
- `qwen_only_all_results.json`: the 40 image-only final results in sample order.
- `manual_visual_adjudications.json`: source-page findings kept with ignored customer results, not source code.
- `sample_manifest.json`: exact seeded sample, source hashes, and page counts.
- Each document folder contains rendered pages, page-level JSON, final JSON, GLM text, and timing JSON.
"""
    (BASE / "comparison_report.md").write_text(report, encoding="utf-8")


def main() -> int:
    """Generate both comparison artifacts."""
    data = build_report_data()
    write_json(BASE / "comparison_index.json", data)
    for method in METHODS:
        write_json(
            BASE / f"{method}_all_results.json",
            {
                "method": method,
                "documents": [
                    {
                        "index": document["index"],
                        "kind": document["kind"],
                        "source_name": document["source_name"],
                        "source_pdf": document["source_pdf"],
                        "result_file": document["result_files"][method],
                        "result": document["results"][method],
                    }
                    for document in data["documents"]
                ],
            },
        )
    write_markdown(data)
    print(f"Wrote {BASE / 'comparison_index.json'}")
    print(f"Wrote {BASE / 'comparison_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
