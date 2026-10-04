"""Run and score both local extraction methods on identical invoice references."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import URLError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liteparse import ParseError

from experimentd.evaluate import score_sample, summarize
from experimentd.extract_invoice import MODEL, PROMPT, extract, local_request, save_json, validate_host
from experimentd.glm_comparison import GLM_MODEL, INSTRUCTIONS, SETTINGS, configured_fields, extract_glm
from standard_step.extraction import glm_ocr_adapter

METHODS = ("liteparse", "glm_task")
LABELS = {"liteparse": "LiteParse + Qwen (text/word citations)",
          "glm_task": "Production GLM-OCR + Qwen (image resolver)"}
DEFAULT_OUTPUT = Path(__file__).parent / "output" / "comparison"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def cache_matches(method: str, sample: dict[str, Any], pdf: Path,
                  directory: Path, tags: dict[str, dict[str, Any]]) -> bool:
    """Require identical source, model digests, instructions and extraction settings."""
    required = ["invoice.json", "run.json", "parsed.json"]
    if method == "glm_task":
        required.append("field_config.json")
    if any(not (directory / name).exists() for name in required):
        return False
    metadata = read_json(directory / "run.json")
    if (metadata.get("source_sha256") != hashlib.sha256(pdf.read_bytes()).hexdigest()
            or metadata.get("pages") != sample["pages"]
            or metadata.get("model_digest") != tags[MODEL if method == "liteparse" else GLM_MODEL]["digest"]):
        return False
    if method == "liteparse":
        return (metadata.get("model") == MODEL and metadata.get("dpi") == 300
                and metadata.get("liteparse_version") == version("liteparse")
                and metadata.get("prompt_sha256") == hashlib.sha256(PROMPT.encode()).hexdigest()
                and metadata.get("options") == {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": 4096})
    return (metadata.get("model") == GLM_MODEL
            and metadata.get("method") == "production_glm_adapter_document"
            and metadata.get("resolver_model") == MODEL
            and metadata.get("resolver_digest") == tags[MODEL]["digest"]
            and metadata.get("settings") == SETTINGS
            and metadata.get("document_instructions_sha256") == hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()
            and metadata.get("adapter_source_sha256") == hashlib.sha256(Path(glm_ocr_adapter.__file__).read_bytes()).hexdigest()
            and read_json(directory / "field_config.json") == configured_fields())


def timing(metadata: dict[str, Any], method: str) -> dict[str, Any]:
    """Keep total wall time separate from Ollama durations excluding model load."""
    if method == "liteparse":
        durations = metadata["durations_seconds"]
        return {"elapsed_seconds": metadata["elapsed_seconds"], "load_seconds": durations["load_duration"],
                "inference_excluding_load_seconds": round(durations["total_duration"] - durations["load_duration"], 3),
                "model_call_count": 1}
    return {"elapsed_seconds": metadata["elapsed_seconds"], "load_seconds": metadata["total_load_seconds"],
            "inference_excluding_load_seconds": metadata["total_inference_excluding_load_seconds"],
            "model_call_count": len(metadata["model_calls"])}


def score_method(references: list[dict[str, Any]], output: Path, method: str) -> dict[str, Any]:
    """Apply exactly the same reference/value scorer; unavailable geometry stays null."""
    samples, failures = [], []
    for reference in references:
        directory = output / method / reference["id"]
        successful = (directory / "invoice.json").exists() and (directory / "run.json").exists()
        invoice = read_json(directory / "invoice.json") if successful else {}
        parsed = read_json(directory / "parsed.json") if successful else {"pages": []}
        score = score_sample(reference, invoice, parsed)
        score["cohort"] = reference.get("cohort", "original")
        if not successful:
            failures.append(reference["id"])
            for check in score["checks"]:
                check["correct"] = False
                check["value_and_location_correct"] = False
        if method == "glm_task":
            for check in score["checks"]:
                check["location_correct"] = None
                check["value_and_location_correct"] = None
        score["timing"] = timing(read_json(directory / "run.json"), method) if successful else None
        samples.append(score)
    groups = {group: summarize([sample for sample in samples if sample["group"] == group])
              for group in sorted({sample["group"] for sample in samples})}
    overall = summarize(samples)
    cohorts = {cohort: {"overall": summarize([s for s in samples if s["cohort"] == cohort]),
                       "groups": {group: summarize([s for s in samples if s["cohort"] == cohort and s["group"] == group])
                                  for group in groups}}
               for cohort in sorted({s["cohort"] for s in samples})}
    for stats in [overall, *groups.values(),
                  *(stats for cohort in cohorts.values() for stats in [cohort["overall"], *cohort["groups"].values()])]:
        if method == "glm_task":
            stats["location_accuracy"] = None
            stats["value_and_location_accuracy"] = None
    for group, stats in {**groups, "overall": overall}.items():
        timed = [sample["timing"] for sample in samples
                 if sample["timing"] is not None and (group == "overall" or sample["group"] == group)]
        stats["timing"] = {"successful_samples": len(timed),
                           "total_elapsed_seconds": round(sum(t["elapsed_seconds"] for t in timed), 3),
                           "mean_elapsed_seconds": round(sum(t["elapsed_seconds"] for t in timed) / len(timed), 3) if timed else None,
                           "total_inference_excluding_load_seconds": round(sum(t["inference_excluding_load_seconds"] for t in timed), 3),
                           "mean_inference_excluding_load_seconds": round(sum(t["inference_excluding_load_seconds"] for t in timed) / len(timed), 3) if timed else None,
                           "total_model_load_seconds": round(sum(t["load_seconds"] for t in timed), 3),
                           "model_call_count": sum(t["model_call_count"] for t in timed)}
    breakdown: dict[str, Any] = {}
    for name in sorted({check["field"].split(".")[-1] for sample in samples for check in sample["checks"]
                        if not check["field"].startswith("extra")}):
        checks = [check for sample in samples for check in sample["checks"]
                  if check["field"].split(".")[-1] == name and not check["field"].startswith("extra")]
        breakdown[name] = {"correct": sum(c["correct"] for c in checks), "total": len(checks)}
    return {"label": LABELS[method], "bbox_available": method == "liteparse", "failures": failures,
            "groups": groups, "overall": overall, "cohorts": cohorts, "field_breakdown": breakdown, "samples": samples}


def paired_results(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Compare reference fields only; extra rows remain penalized in method scores."""
    counter: Counter[str] = Counter()
    disagreements = []
    right_samples = {sample["id"]: sample for sample in right["samples"]}
    for sample in left["samples"]:
        other = {check["field"]: check for check in right_samples[sample["id"]]["checks"]}
        for check in sample["checks"]:
            if check["field"].startswith("extra"):
                continue
            matched = other[check["field"]]
            key = ("both_correct" if check["correct"] and matched["correct"] else
                   "liteparse_only_correct" if check["correct"] else
                   "glm_only_correct" if matched["correct"] else "both_wrong")
            counter[key] += 1
            if key != "both_correct":
                disagreements.append({"id": sample["id"], "field": check["field"], "result": key,
                                      "expected": check["expected"], "liteparse": check["actual"], "glm_task": matched["actual"]})
    return {"counts": {key: counter[key] for key in ("both_correct", "liteparse_only_correct", "glm_only_correct", "both_wrong")},
            "disagreements": disagreements}


def write_report(manifest: Path, output: Path) -> dict[str, Any]:
    """Write private full comparisons and a readable report without customer values."""
    references = read_json(manifest)["samples"]
    methods = {method: score_method(references, output, method) for method in METHODS}
    report = {"methods": methods, "paired": paired_results(methods["liteparse"], methods["glm_task"]),
              "reference_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
              "comparison_scope": "Same source PDFs, selected invoice pages, references and value scorer; different production input/prompt paths. Not an isolated OCR-engine benchmark.",
              "box_scope": "LiteParse boxes use manual-region containment. Production GLM adapter returns page evidence only; word-box metrics are unavailable, not zero.",
              "selection": f"Selected invoice counts: {dict(Counter(r['group'] for r in references))}. References frozen before comparison. Original and additional cohorts are reported separately; no population-accuracy claim."}
    from experimentd.trace_glm_stages import trace
    stages = trace(manifest, output)
    report["glm_resolution_diagnostic"] = {
        "scope": stages["scope"],
        "completed_sample_count": stages["raw_qwen_overall"]["sample_count"],
        "raw_qwen_accuracy": stages["raw_qwen_overall"]["overall_accuracy"],
        "postprocessing_changes": stages["postprocessing_changes"],
    }
    save_json(output / "comparison.json", report)
    lines = ["# Local invoice methods: side-by-side comparison", "", report["comparison_scope"], "", report["selection"], "",
             "| Group | Method | Headers | Line fields | All fields | Mean wall seconds | Mean inference seconds excluding model load |",
             "|---|---|---:|---:|---:|---:|---:|"]
    def fmt(metric: dict[str, Any]) -> str:
        return f"{metric['correct']}/{metric['total']} ({metric['percent']}%)"
    for group in [*sorted({r["group"] for r in references}), "overall"]:
        for method in METHODS:
            stats = methods[method]["overall"] if group == "overall" else methods[method]["groups"][group]
            lines.append(f"| {group} | {method} | {fmt(stats['header_accuracy'])} | {fmt(stats['line_item_accuracy'])} | {fmt(stats['overall_accuracy'])} | {stats['timing']['mean_elapsed_seconds']} | {stats['timing']['mean_inference_excluding_load_seconds']} |")
    lines.extend(["", "| Sample | LiteParse correct fields | GLM task correct fields | LiteParse rows | GLM task rows |",
                  "|---|---:|---:|---:|---:|"])
    for left, right in zip(methods["liteparse"]["samples"], methods["glm_task"]["samples"]):
        lines.append(f"| {left['id']} | {sum(c['correct'] for c in left['checks'])}/{len(left['checks'])} | {sum(c['correct'] for c in right['checks'])}/{len(right['checks'])} | {left['actual_rows']}/{left['expected_rows']} | {right['actual_rows']}/{right['expected_rows']} |")
    lines.extend(["", "## Cohorts and complete invoices", "",
                  "| Cohort | Group | Method | All fields | Complete invoices |", "|---|---|---|---:|---:|"])
    for method, data in methods.items():
        for cohort, summaries in data["cohorts"].items():
            for group, stats in {**summaries["groups"], "overall": summaries["overall"]}.items():
                lines.append(f"| {cohort} | {group} | {method} | {fmt(stats['overall_accuracy'])} | {fmt(stats['complete_invoice_accuracy'])} |")
    lines.extend(["", "| Field | LiteParse correct | GLM task correct |", "|---|---:|---:|"])
    for name, left in methods["liteparse"]["field_breakdown"].items():
        right = methods["glm_task"]["field_breakdown"][name]
        lines.append(f"| {name} | {left['correct']}/{left['total']} | {right['correct']}/{right['total']} |")
    lines.extend(["", report["box_scope"], "",
                  "Location denominators include only references with independently reviewed rectangles. Additional references explicitly marked geometry_reviewed=false contribute to value accuracy only, while extraction still retains word boxes.", "",
                  "Both methods count absent-value mistakes, missing/extra rows and failed samples. Text comparison ignores case/punctuation/layout whitespace; numbers use exact decimal equality. Complete description continuation lines are required.", "",
                  "GLM uses the existing production adapter in document mode: 216 DPI GLM images, 1280px Qwen images, context 8192/18000 and output limits 2048/10000. LiteParse uses 300 DPI OCR and text-only Qwen with context 16384/output limit 4096. Both use Qwen's identical model digest; seed 42 is added to the GLM transport for reproducibility.", "",
                  "GLM includes its production recovery/retry/table-evidence logic. Its page selection and loopback recording client are the only experiment wrappers. Qwen can re-read images in that method. References never enter model requests.", "",
                  "Timings are single runs; model loads/switches are included in wall time and listed separately. Excluding-load numbers sum Ollama total-duration minus load-duration across all calls, and exclude rendering/network overhead. No live application state was read or modified.", "",
                  f"Paired reference-field results: {json.dumps(report['paired']['counts'])}", "",
                  "Failures: " + json.dumps({method: value["failures"] for method, value in methods.items()}), "",
                  "Full private mismatches, printed/calculated totals, individual calls and raw outputs are saved locally in comparison.json and the method/sample directories."])
    lines.extend(["", "## GLM resolution-stage diagnostic", "",
                  "Raw Qwen decisions are inspected before production normalization/table grounding; this is a diagnostic, not another model run.", "",
                  "Raw Qwen field accuracy: " + fmt(stages["raw_qwen_overall"]["overall_accuracy"]), "",
                  "Post-processing correctness changes: " + json.dumps(stages["postprocessing_changes"]), "",
                  "Detailed stage changes are retained privately in glm_stage_comparison.json. The principal GLM score above always uses the final production adapter output."])
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def run(args: argparse.Namespace) -> None:
    """Run one method at a time to avoid GPU contention, then compare all samples."""
    validate_host(args.host)
    references = read_json(args.manifest)["samples"]
    frozen_reference_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    save_json(args.output / "reference_manifest.json", read_json(args.manifest))
    ids = [sample["id"] for sample in references]
    if len(set(ids)) != len(ids) or any(re.fullmatch(r"[A-Za-z0-9_-]+", sid) is None for sid in ids):
        raise ValueError("Sample IDs must be unique simple directory names.")
    root = args.manifest.resolve().parent.parent
    tags = {entry["name"]: entry for entry in local_request(args.host, "/api/tags", timeout=30)["models"]}
    if MODEL not in tags or GLM_MODEL not in tags:
        raise ValueError("Both requested models must already be installed locally.")
    active_model = getattr(args, "previous_model", None)
    for method in args.methods:
        print(f"Running {LABELS[method]}", flush=True)
        for i, sample in enumerate(references, 1):
            directory = args.output / method / sample["id"]
            pdf = (root / sample["pdf"]).resolve(strict=True)
            if args.resume and cache_matches(method, sample, pdf, directory, tags):
                print(f"[{i}/{len(references)}] {sample['id']}: cached verified result", flush=True)
                continue
            print(f"[{i}/{len(references)}] {sample['id']}: extracting", flush=True)
            (directory / "invoice.json").unlink(missing_ok=True)
            (directory / "run.json").unlink(missing_ok=True)
            try:
                if method == "liteparse":
                    extract(pdf, directory, sample["pages"], args.host, timeout=args.timeout)
                else:
                    extract_glm(pdf, directory, sample["pages"], args.host,
                                timeout=args.timeout, previous_model=active_model)
            except (URLError, ValueError, RuntimeError, OSError, ParseError) as error:
                save_json(directory / "error.json", {"error_type": type(error).__name__})
                print(f"  Failed: {type(error).__name__}; private diagnostics retained.", flush=True)
            else:
                active_model = MODEL
                (directory / "error.json").unlink(missing_ok=True)
                print(f"  Sample completed in {read_json(directory / 'run.json')['elapsed_seconds']} s", flush=True)
    if hashlib.sha256(args.manifest.read_bytes()).hexdigest() != frozen_reference_hash:
        raise ValueError("References changed during comparison; do not compare this run until reviewed.")
    report = write_report(args.manifest, args.output)
    print(json.dumps({method: value["overall"]["overall_accuracy"] for method, value in report["methods"].items()}, indent=2))
    if any(value["failures"] for value in report["methods"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples.local.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--previous-model", choices=[MODEL, GLM_MODEL],
                        help="Previously used benchmark model to unload on the first model switch.")
    parser.add_argument("--methods", choices=METHODS, nargs="+", default=["glm_task", "liteparse"])
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    if args.report_only:
        write_report(args.manifest, args.output)
    else:
        run(args)
