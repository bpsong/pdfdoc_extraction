"""Publish aggregate expanded results without copying private invoice content."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from experimentd.compare_methods import METHODS, read_json, write_report
from experimentd.evaluate import summarize


def statistics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Distinguish reference-field accuracy, extra rows and invoice-level averages."""
    reference_checks = [c for s in samples for c in s["checks"] if not c["field"].startswith("extra")]
    correct = sum(c["correct"] for c in reference_checks)
    total = len(reference_checks)
    per_invoice = [sum(c["correct"] for c in s["checks"]) / len(s["checks"]) for s in samples]
    times = [s["timing"] for s in samples if s["timing"] is not None]
    return {**summarize(samples),
            "reference_accuracy": {"correct": correct, "total": total,
                                   "percent": round(100 * correct / total, 2) if total else None},
            "macro_invoice_percent": round(100 * sum(per_invoice) / len(per_invoice), 2) if per_invoice else None,
            "extra_rows": sum(max(0, s["actual_rows"] - s["expected_rows"]) for s in samples),
            "missing_rows": sum(max(0, s["expected_rows"] - s["actual_rows"]) for s in samples),
            "successful_timing_count": len(times),
            "mean_elapsed_seconds": round(sum(t["elapsed_seconds"] for t in times) / len(times), 2) if times else None,
            "total_elapsed_seconds": round(sum(t["elapsed_seconds"] for t in times), 2),
            "model_calls": sum(t["model_call_count"] for t in times),
            "load_seconds": round(sum(t["load_seconds"] for t in times), 2),
            "inference_excluding_load_seconds": round(sum(t["inference_excluding_load_seconds"] for t in times), 2)}


def publish(manifest: Path, output: Path, destination: Path) -> None:
    """Re-score fixed references and write a public report containing aggregate data."""
    report = write_report(manifest, output)
    reference = read_json(manifest)
    references = reference["samples"]
    expected_rows = sum(len(s["line_items"]) for s in references)
    expected_fields = sum(5 + 5 * len(s["line_items"]) for s in references)
    groups = sorted({s["group"] for s in references})
    results = {method: statistics(data["samples"]) for method, data in report["methods"].items()}

    def fmt(metric: dict[str, Any]) -> str:
        return f"{metric['correct']}/{metric['total']} ({metric['percent']}%)"

    lines = ["# Expanded local invoice comparison", "",
             f"Compared {len(references)} invoices: " + ", ".join(f"{sum(s['group'] == group for s in references)} {group}" for group in groups) + ".",
             f"The reference set contains {expected_rows} item rows and {expected_fields} expected structured fields.", "",
             "The original six results are reused only after verifying source/model digests, pages, prompts and settings. The additional samples use the same frozen extraction configuration. References were independently transcribed/visually checked before their inference, and never entered model requests.", "",
             "## All samples", "",
             "| Group | Method | Headers | Line fields including extra-row penalties | All fields | Complete invoices |",
             "|---|---|---:|---:|---:|---:|"]
    for group in [*groups, "overall"]:
        for method in METHODS:
            selected = [s for s in report["methods"][method]["samples"] if group == "overall" or s["group"] == group]
            stats = statistics(selected)
            lines.append(f"| {group} | {method} | {fmt(stats['header_accuracy'])} | {fmt(stats['line_item_accuracy'])} | {fmt(stats['overall_accuracy'])} | {fmt(stats['complete_invoice_accuracy'])} |")
    lines.extend(["", "## Additional samples only", "",
                  "These samples were not used to tune the prompts. FTS selection was based on source-page eligibility/readability rather than model output; it is not random production sampling.", "",
                  "| Group | Method | All fields | Same reference fields | Complete invoices | Mean elapsed seconds (successful samples) |",
                  "|---|---|---:|---:|---:|---:|"])
    for group in [*groups, "overall"]:
        for method in METHODS:
            selected = [s for s in report["methods"][method]["samples"] if s["cohort"] == "additional" and (group == "overall" or s["group"] == group)]
            stats = statistics(selected)
            lines.append(f"| {group} | {method} | {fmt(stats['overall_accuracy'])} | {fmt(stats['reference_accuracy'])} | {fmt(stats['complete_invoice_accuracy'])} | {stats['mean_elapsed_seconds']} |")
    lines.extend(["", "## Row counts, timing and field weighting", "",
                  "| Method | Same reference fields (all samples) | Extra rows | Missing rows | Mean per-invoice field accuracy | Mean elapsed seconds | Model calls | Load seconds | Inference seconds excluding load |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for method, stats in results.items():
        lines.append(f"| {method} | {fmt(stats['reference_accuracy'])} | {stats['extra_rows']} | {stats['missing_rows']} | {stats['macro_invoice_percent']}% | {stats['mean_elapsed_seconds']} | {stats['model_calls']} | {stats['load_seconds']} | {stats['inference_excluding_load_seconds']} |")
    lines.extend(["", "All-field accuracy counts missing fields/rows and adds five error slots per extra row. Same-reference accuracy uses identical expected-field denominators for both methods; extra rows remain reported separately. Complete-invoice accuracy requires every scored field correct and no extra rows. The mean per-invoice score weights each invoice equally; field-level accuracy gives larger invoices more weight.", "",
                  "Timings combine cached original-six measurements and fresh additional runs, not 40 freshly repeated measurements. Additional-only timings above are preferable for the expanded comparison. Single-run wall timings include model switches and loads; inference-only times sum Ollama durations excluding load. Failed samples count as incorrect in accuracy; successful-only timing means do not conceal the listed failures.", "",
                  "## Accuracy by structured field", "",
                  "These counts use expected fields only; extra rows are penalized separately in the all-field score.", "",
                  "| Field | LiteParse + Qwen | GLM task |", "|---|---:|---:|"])
    for field, left in report["methods"]["liteparse"]["field_breakdown"].items():
        right = report["methods"]["glm_task"]["field_breakdown"][field]
        lines.append(f"| {field} | {left['correct']}/{left['total']} | {right['correct']}/{right['total']} |")
    lines.extend(["", "## Resolution and location diagnostics", "",
                  "Raw GLM-arm Qwen decisions before production table grounding: " + fmt(report["glm_resolution_diagnostic"]["raw_qwen_accuracy"]) + ".",
                  "Diagnostic completed samples: " + str(report["glm_resolution_diagnostic"]["completed_sample_count"]) + ".",
                  "Postprocessing correctness changes: " + str(report["glm_resolution_diagnostic"]["postprocessing_changes"]) + ".", "",
                  "LiteParse's retained word-box check covers only the original independently marked reference regions: " + fmt(results["liteparse"]["value_and_location_accuracy"]) + " correct value plus location. The 34 additional samples contribute to value accuracy and retain extraction boxes, but have no independently marked geometry references. GLM supplies page evidence, so word-box accuracy is unavailable.", "",
                  "## Selection, scoring and privacy", "",
                  reference.get("selection", report["selection"]), "",
                  "Text matching ignores case, punctuation and layout whitespace. Numeric comparisons use exact decimals. Full descriptions include relevant codes/continuations in the description column; separate item/code columns, accounting/project section headings and unrelated delivery notes are excluded. Null units remain null when unprinted. Printed discounted line amounts are scored against the source, separately from calculated quantity × unit price.", "",
                  "Before additional FTS inference, the shared scorer was corrected to deny null-cell credit for entirely missing rows and ignore CJK line-wrap spaces without ignoring character changes. Both corrections apply equally to both methods; original-six accuracy and all extraction prompts/settings are unchanged.", "",
                  "LiteParse uses 300-DPI local OCR and one text/coordinate Qwen request; GLM uses the existing document-mode adapter, 216-DPI OCR and Qwen images capped at 1280 pixels. Context/output settings remain 16384/4096 and 8192/2048 plus 18000/10000 respectively. Numeric GLM fields remain float/Optional[float]. Both use the same Qwen digest, temperature zero and seed 42; Qwen thinking is disabled.", "",
                  "Failures: " + str({m: d["failures"] for m, d in report["methods"].items()}) + ".", "",
                  "All invoice content, references, requests, outputs and detailed mismatches remain local in ignored files. No production application files or state were changed. Full private details are in output/comparison_expanded/comparison.json, SUMMARY.md, glm_stage_comparison.json and method/sample directories.", "",
                  "The scripts/tests and exact execution commands are documented in README.md. Twenty invoices per type broaden this experiment, but related layouts, nonrandom FTS selection and a small invoice count still limit generalization."])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved aggregate expanded report: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples_expanded.local.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output" / "comparison_expanded")
    parser.add_argument("--report-path", type=Path, default=Path(__file__).parent / "EXPANDED_COMPARISON.md")
    args = parser.parse_args()
    publish(args.manifest, args.output, args.report_path)
