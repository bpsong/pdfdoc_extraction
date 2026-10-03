"""Parse PDF layout, text and tables with the native PaddleOCR-VL pipeline."""

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = ROOT.parent / "sample stock invoices from internet" / "invoice_Aaron Bergman_36258.pdf"


def export_results(results: Any, destination: Path) -> int:
    """Save every result, consuming lazy pipeline output when necessary."""
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for result in results:
        result.save_to_json(save_path=str(destination))
        result.save_to_markdown(save_path=str(destination))
        count += 1
    return count


def run(args: argparse.Namespace) -> Path:
    """Run the full native pipeline and save original and restructured pages."""
    pdf = args.pdf.resolve(strict=True)
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise ValueError("Input must be a PDF file.")
    paddleocr = importlib.import_module("paddleocr")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    print(f"Initializing PaddleOCR-VL v1.6 on {args.device}...", flush=True)
    pipeline = paddleocr.PaddleOCRVL(
        pipeline_version="v1.6", device=args.device,
        use_doc_orientation_classify=args.orientation,
        use_doc_unwarping=args.unwarp,
        use_queues=False,
        markdown_ignore_labels=[],
    )
    print(f"Processing {pdf.name}...", flush=True)
    pages: list[Any] = []
    page_output = output / "pages"
    for page in pipeline.predict(input=str(pdf)):
        export_results([page], page_output)
        pages.append(page)
        print(f"Saved page {len(pages)}", flush=True)
    if not pages:
        raise ValueError("Pipeline returned no pages.")
    merged_count = export_results(
        pipeline.restructure_pages(
            pages, merge_tables=not args.no_merge_tables,
            concatenate_pages=True,
        ), output / "merged",
    )
    if not merged_count:
        raise ValueError("Pipeline returned no restructured results.")
    (output / "run.json").write_text(json.dumps({
        "pdf": str(pdf), "pipeline_version": "v1.6", "device": args.device,
        "paddleocr_version": getattr(paddleocr, "__version__", "unknown"),
        "pages": len(pages), "merged_results": merged_count,
        "merge_tables": not args.no_merge_tables, "concatenate_pages": True,
        "orientation": args.orientation, "unwarp": args.unwarp,
        "use_queues": False, "markdown_ignore_labels": [],
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }, indent=2), encoding="utf-8")
    return output


def main() -> None:
    """Provide a standalone CLI without application imports or Ollama."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "pipeline")
    parser.add_argument("--device", choices=("gpu:0", "cpu"), default="gpu:0")
    parser.add_argument("--orientation", action="store_true", help="Enable orientation correction")
    parser.add_argument("--unwarp", action="store_true", help="Enable document unwarping")
    parser.add_argument("--no-merge-tables", action="store_true")
    args = parser.parse_args()
    try:
        output = run(args)
    except ModuleNotFoundError as exc:
        parser.exit(1, f"Missing dependency: {exc.name}. See experimentc/README.md "
                    "for native pipeline installation.\n")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Pipeline failed ({type(exc).__name__}). Check the PDF, "
                    "device and runtime installation. Completed pages remain in output.\n")
    print(f"Saved document blocks and tables to {output}")
    print("These are document parsing results; named invoice fields need a separate mapping step.")


if __name__ == "__main__":
    main()
