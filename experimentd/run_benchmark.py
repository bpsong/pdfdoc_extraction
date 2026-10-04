"""Run the six local invoice samples; ground truth is never passed to Qwen."""

from __future__ import annotations

import argparse
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
from urllib.error import URLError

from liteparse import ParseError

try:
    from .evaluate import evaluate
    from .extract_invoice import MODEL, PROMPT, extract, local_request, save_json, validate_host
except ImportError:
    from evaluate import evaluate
    from extract_invoice import MODEL, PROMPT, extract, local_request, save_json, validate_host


def run(args: argparse.Namespace) -> None:
    """Run serially to avoid GPU contention and checkpoint successful samples."""
    validate_host(args.host)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.manifest.resolve().parent.parent
    failures = []
    samples = manifest["samples"]
    if len({s["id"] for s in samples}) != len(samples):
        raise ValueError("Sample IDs must be unique.")
    tags = local_request(args.host, "/api/tags", timeout=30)
    installed = next((m for m in tags["models"] if m["name"] == args.model), None)
    if installed is None:
        raise ValueError("Requested model is not installed locally.")
    for i, sample in enumerate(samples, 1):
        directory = args.output / sample["id"]
        pdf = (root / sample["pdf"]).resolve(strict=True)
        run_file = directory / "run.json"
        if args.resume and run_file.exists() and (directory / "invoice.json").exists():
            old = json.loads(run_file.read_text(encoding="utf-8"))
            if (old["source_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
                    and old["model"] == args.model and old["pages"] == sample["pages"]
                    and old["liteparse_version"] == version("liteparse")
                    and old.get("prompt_sha256") == hashlib.sha256(PROMPT.encode()).hexdigest()
                    and old.get("model_digest") == installed["digest"]
                    and old.get("options") == {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": 4096}
                    and old.get("dpi") == args.dpi):
                print(f"[{i}/{len(samples)}] {sample['id']}: resumed", flush=True)
                continue
        print(f"[{i}/{len(samples)}] {sample['id']}: local OCR + extraction", flush=True)
        # Clear previous success markers before starting a new attempt.
        (directory / "invoice.json").unlink(missing_ok=True)
        run_file.unlink(missing_ok=True)
        try:
            extract(pdf, directory, sample["pages"], args.host, args.model, args.dpi, args.timeout)
        except (URLError, ValueError, RuntimeError, OSError, ParseError) as exc:
            # Persist only the exception type, never document content in logs.
            failures.append({"id": sample["id"], "error_type": type(exc).__name__})
            save_json(directory / "error.json", failures[-1])
            print(f"  Failed: {type(exc).__name__}; inspect local artifacts.", flush=True)
        else:
            (directory / "error.json").unlink(missing_ok=True)
            metadata = json.loads(run_file.read_text(encoding="utf-8"))
            print(f"  Completed in {metadata['elapsed_seconds']} s", flush=True)
    save_json(args.output / "failures.json", failures)
    report = evaluate(args.manifest, args.output)
    print(json.dumps(report["groups"], indent=2))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples.local.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output" / "benchmark")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--resume", action="store_true")
    run(parser.parse_args())
