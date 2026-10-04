"""Compare recorded raw Qwen decisions with the production adapter's final data."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experimentd.evaluate import score_sample, summarize
from experimentd.extract_invoice import HEADER_FIELDS, save_json
from experimentd.glm_comparison import canonical_invoice


def recorded_qwen_invoice(directory: Path) -> dict[str, Any]:
    """Reconstruct successful final resolver attempts from private recorded calls.

    This is a diagnostic before production normalization/grounding; it is not
    another model run or a substitute for the final task output. Retry attempts
    for a field/chunk replace earlier attempts. No expected values are consulted.
    """
    data: dict[str, Any] = {name: None for name in HEADER_FIELDS}
    field_pages: dict[str, list[int]] = {}
    chunks: dict[int, list[dict[str, Any]]] = {}
    for call in sorted((directory / "calls").glob("*")):
        if not (call / "response.json").exists():
            continue
        request = json.loads((call / "request.json").read_text(encoding="utf-8"))
        if "messages" not in request:
            continue
        response = json.loads((call / "response.json").read_text(encoding="utf-8"))
        if not response.get("done") or response.get("done_reason") in ("length", "max_tokens", "token_limit"):
            continue
        try:
            parsed = json.loads(response["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
        prompt = request["messages"][0]["content"]
        for line in prompt.splitlines():
            if line.startswith("Configured field: "):
                field = json.loads(line.removeprefix("Configured field: "))["key"]
                data[field] = parsed.get("value")
                field_pages[field] = parsed.get("page_numbers", [])
            elif line.startswith("This is ordered evidence chunk "):
                chunk = int(line.split()[5])
                value = parsed.get("value")
                if isinstance(value, list):
                    chunks[chunk] = value
                    field_pages["line_items"] = sorted(set(field_pages.get("line_items", [])) | set(parsed.get("page_numbers", [])))
    data["line_items"] = [row for key in sorted(chunks) for row in chunks[key]]
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    return canonical_invoice(data, field_pages, metadata["selected_pages"])


def trace(manifest: Path, output: Path) -> dict[str, Any]:
    """Score raw decisions separately and attribute accuracy changes after resolution."""
    references = json.loads(manifest.read_text(encoding="utf-8"))["samples"]
    raw_samples, final_samples, changes = [], [], []
    counter: Counter[str] = Counter()
    for reference in references:
        directory = output / "glm_task" / reference["id"]
        if not (directory / "run.json").exists() or not (directory / "invoice.json").exists():
            continue
        raw = recorded_qwen_invoice(directory)
        save_json(directory / "raw_qwen_invoice.json", raw)
        parsed = json.loads((directory / "parsed.json").read_text(encoding="utf-8"))
        raw_score = score_sample(reference, raw, parsed)
        final = json.loads((directory / "invoice.json").read_text(encoding="utf-8"))
        final_score = score_sample(reference, final, parsed)
        raw_samples.append(raw_score)
        final_samples.append(final_score)
        raw_checks = {check["field"]: check for check in raw_score["checks"]}
        for check in final_score["checks"]:
            before = raw_checks.get(check["field"])
            if before is None or check["field"].startswith("extra"):
                continue
            if before["correct"] and not check["correct"]:
                classification = "correct_to_wrong"
            elif not before["correct"] and check["correct"]:
                classification = "wrong_to_correct"
            else:
                continue
            counter[classification] += 1
            changes.append({"id": reference["id"], "field": check["field"], "change": classification,
                            "expected": check["expected"], "raw_qwen": before["actual"], "final_task": check["actual"]})
    def values_only_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
        result = summarize(samples)
        result["location_accuracy"] = None
        result["value_and_location_accuracy"] = None
        return result

    report = {"scope": "Diagnostic only: raw Qwen response before the existing adapter's normalization and table grounding. No additional model calls.",
              "raw_qwen_overall": values_only_summary(raw_samples), "final_task_overall": values_only_summary(final_samples),
              "raw_qwen_groups": {group: values_only_summary([s for s in raw_samples if s["group"] == group])
                                  for group in sorted({s["group"] for s in raw_samples})},
              "postprocessing_changes": {"correct_to_wrong": counter["correct_to_wrong"],
                                         "wrong_to_correct": counter["wrong_to_correct"]}, "changes": changes}
    save_json(output / "glm_stage_comparison.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples.local.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output" / "comparison")
    args = parser.parse_args()
    result = trace(args.manifest, args.output)
    print(json.dumps({"raw_qwen_accuracy": result["raw_qwen_overall"]["overall_accuracy"],
                      "postprocessing_changes": result["postprocessing_changes"]}, indent=2))
