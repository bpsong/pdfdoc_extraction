"""Score saved extractions against independently transcribed local references."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

try:
    from .extract_invoice import HEADER_FIELDS, ITEM_FIELDS, decimal_value, save_json
except ImportError:
    from extract_invoice import HEADER_FIELDS, ITEM_FIELDS, decimal_value, save_json

NUMERIC = {"invoice_total", "quantity", "unit_price", "line_total"}


def tokens(value: str) -> list[str]:
    """Ignore case, punctuation and layout whitespace, preserving words/digits."""
    # CJK has no required word spaces; PDF line wraps must not change equality.
    normalized = re.sub(r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])", r" \1 ", value.casefold())
    return re.findall(r"\w+", normalized)


def value_matches(name: str, expected: str | None, actual: str | None) -> bool:
    """Compare printed numeric values exactly and text after layout normalization."""
    if expected is None or actual is None:
        return expected is actual
    if name in NUMERIC:
        left, right = decimal_value(expected), decimal_value(actual)
        return left is not None and right is not None and left == right
    return tokens(expected) == tokens(actual)


def token_f1(expected: str | None, actual: str | None) -> float:
    """Report partial description fidelity separately from strict field accuracy."""
    if expected is None or actual is None:
        return float(expected is actual)
    left, right = Counter(tokens(expected)), Counter(tokens(actual))
    denominator = sum(left.values()) + sum(right.values())
    return 2 * sum((left & right).values()) / denominator if denominator else 1.0


def location_matches(field: dict[str, Any], regions: list[dict[str, Any]],
                     pages: dict[int, dict[str, Any]]) -> bool:
    """Require every cited box to lie at least 80% inside a reviewed value region.

    Reference rectangles are normalized x0,y0,x1,y1, manually marked on the
    original page before model inference. This measures coarse localization,
    not tight box IoU. No source text search/fuzzy matching repairs citations.
    """
    boxes = field.get("boxes", [])
    if field.get("grounding_status") != "grounded" or not boxes or not regions:
        return False
    for entry in boxes:
        page = pages.get(entry["page"])
        if page is None:
            return False
        x0, y0, x1, y1 = entry["bbox"]
        area = (x1 - x0) * (y1 - y0)
        if area <= 0 or x0 < 0 or y0 < 0 or x1 > page["width"] or y1 > page["height"]:
            return False
        best = 0.0
        for region in regions:
            if region["page"] != entry["page"]:
                continue
            a, b, c, d = region["bbox_normalized"]
            a, c = a * page["width"], c * page["width"]
            b, d = b * page["height"], d * page["height"]
            intersection = max(0, min(x1, c) - max(x0, a)) * max(0, min(y1, d) - max(y0, b))
            best = max(best, intersection / area)
        if best < 0.8:
            return False
    return True


def score_sample(reference: dict[str, Any], invoice: dict[str, Any],
                 parsed: dict[str, Any]) -> dict[str, Any]:
    """Count missing and extra rows as errors; never remove absent-field errors."""
    checks = []
    pages = {p["page"]: p for p in parsed["pages"]}
    geometry_reviewed = reference.get("geometry_reviewed", True)

    def check(path: str, name: str, expected: dict[str, Any], actual: dict[str, Any]) -> None:
        correct = value_matches(name, expected["value"], actual.get("value"))
        present = expected["value"] is not None
        located = location_matches(actual, expected.get("regions", []), pages) if present and geometry_reviewed else None
        checks.append({"field": path, "expected": expected["value"], "actual": actual.get("value"),
                       "correct": correct, "present_in_reference": present,
                       "location_correct": located, "value_and_location_correct": bool(correct and located) if geometry_reviewed else None,
                       "description_token_f1": token_f1(expected["value"], actual.get("value"))
                       if name == "description" else None})

    for name in HEADER_FIELDS:
        check(name, name, reference["fields"][name], invoice.get(name, {}))
    expected_rows, actual_rows = reference["line_items"], invoice.get("line_items", [])
    for i, row in enumerate(expected_rows):
        actual = actual_rows[i] if i < len(actual_rows) else {}
        for name in ITEM_FIELDS:
            check(f"line_items[{i}].{name}", name, row[name], actual.get(name, {}))
            if i >= len(actual_rows):
                # An absent row cannot receive credit for a reference null cell.
                checks[-1]["correct"] = False
                checks[-1]["value_and_location_correct"] = False if geometry_reviewed else None
    for i in range(len(expected_rows), len(actual_rows)):
        for name in ITEM_FIELDS:
            checks.append({"field": f"extra_line_items[{i}].{name}", "expected": None,
                           "actual": actual_rows[i][name]["value"], "correct": False,
                           "present_in_reference": False, "location_correct": None,
                           "value_and_location_correct": False, "description_token_f1": None})
    return {"id": reference["id"], "group": reference["group"],
            "expected_rows": len(expected_rows), "actual_rows": len(actual_rows),
            "checks": checks, "arithmetic": [{"row": i, "computed": row.get("computed_line_total"),
                                               "printed": row["line_total"]["value"],
                                               "difference": row.get("printed_minus_computed")}
                                              for i, row in enumerate(actual_rows)]}


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate field-level metrics with explicit numerators and denominators."""
    checks = [c for sample in samples for c in sample["checks"]]
    header = [c for c in checks if c["field"] in HEADER_FIELDS]
    rows = [c for c in checks if c["field"] not in HEADER_FIELDS]
    present = [c for c in checks if c["present_in_reference"]]
    absent = [c for c in checks if not c["present_in_reference"]]

    def metric(values: list[dict[str, Any]], key: str) -> dict[str, Any]:
        correct = sum(bool(v[key]) for v in values)
        return {"correct": correct, "total": len(values),
                "percent": round(100 * correct / len(values), 2) if values else None}

    descriptions = [c["description_token_f1"] for c in checks if c["description_token_f1"] is not None]
    return {"sample_count": len(samples), "header_accuracy": metric(header, "correct"),
            "line_item_accuracy": metric(rows, "correct"), "overall_accuracy": metric(checks, "correct"),
            "present_field_accuracy": metric(present, "correct"), "absent_field_accuracy": metric(absent, "correct"),
            "location_accuracy": metric([c for c in present if c["location_correct"] is not None], "location_correct"),
            "value_and_location_accuracy": metric([c for c in present if c["value_and_location_correct"] is not None], "value_and_location_correct"),
            "mean_description_token_f1": round(sum(descriptions) / len(descriptions), 4) if descriptions else None,
            "row_count_correct": sum(s["expected_rows"] == s["actual_rows"] for s in samples),
            "complete_invoice_accuracy": {"correct": sum(all(c["correct"] for c in s["checks"]) for s in samples),
                                          "total": len(samples),
                                          "percent": round(100 * sum(all(c["correct"] for c in s["checks"]) for s in samples) / len(samples), 2) if samples else None}}


def evaluate(manifest: Path, output: Path) -> dict[str, Any]:
    """Produce a private detailed JSON report and a readable aggregate report."""
    references = json.loads(manifest.read_text(encoding="utf-8"))["samples"]
    samples, failures = [], []
    for reference in references:
        directory = output / reference["id"]
        if not (directory / "invoice.json").exists():
            failures.append(reference["id"])
            # Include failed samples with every expected present field missing.
            invoice = {}
            parsed = {"pages": []}
        else:
            invoice = json.loads((directory / "invoice.json").read_text(encoding="utf-8"))
            parsed = json.loads((directory / "parsed.json").read_text(encoding="utf-8"))
        sample = score_sample(reference, invoice, parsed)
        if reference["id"] in failures:
            for c in sample["checks"]:
                c["correct"] = False
        samples.append(sample)
    groups = {name: summarize([s for s in samples if s["group"] == name])
              for name in sorted({s["group"] for s in samples})}
    report = {"method": "Independent visual transcription; exact decimal equality; case/punctuation/whitespace-normalized text; row order preserved.",
              "bbox_method": "Every cited word box must have >=80% of its area inside a manually reviewed normalized page region. Coarse localization, not tight IoU.",
              "sample_selection": "Three purposively selected invoices per type; FTS invoice page selected manually from mixed bundles. Not a random or production benchmark.",
              "failures": failures, "groups": groups, "overall": summarize(samples), "samples": samples}
    save_json(output / "accuracy.json", report)
    lines = ["# LiteParse + local Qwen invoice experiment", "", report["method"], "", report["sample_selection"], "",
             "| Type | Samples | Headers | Line fields | All fields | Value + location (present fields) |", "|---|---:|---:|---:|---:|---:|"]
    for name, stats in {**groups, "overall": report["overall"]}.items():
        def fmt(key: str) -> str:
            m = stats[key]
            return f"{m['correct']}/{m['total']} ({m['percent']}%)"
        lines.append(f"| {name} | {stats['sample_count']} | {fmt('header_accuracy')} | {fmt('line_item_accuracy')} | {fmt('overall_accuracy')} | {fmt('value_and_location_accuracy')} |")
    lines.extend(["", report["bbox_method"], "", f"Failed samples: {len(failures)}; included in denominators.", "",
                  "Printed row totals are scored separately from Decimal(quantity * unit_price), rounded half up to 2 decimals.", "",
                  "Detailed mismatches, partial description scores, arithmetic and timings are in local accuracy.json and each sample directory."])
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples.local.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output" / "benchmark")
    args = parser.parse_args()
    report = evaluate(args.manifest, args.output)
    print(json.dumps({"groups": report["groups"], "failures": report["failures"]}, indent=2))
