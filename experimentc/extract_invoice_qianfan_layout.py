"""Standalone PDF invoice extraction with Qianfan-OCR through local Ollama."""

import argparse
import base64
import json
import re
import time
from pathlib import Path
from typing import Any

import fitz
import httpx


ROOT = Path(__file__).resolve().parent
MODEL = "maternion/Qianfan-OCR:4b"
DEFAULT_PDF = ROOT.parent / "sample stock invoices from internet" / "invoice_Aaron Bergman_36258.pdf"


def timing_summary(result: dict[str, Any], page: int) -> dict[str, Any]:
    """Convert Ollama nanoseconds into per-page timings, excluding loading."""
    total = result.get("total_duration", 0) / 1e9
    load = result.get("load_duration", 0) / 1e9
    return {"page": page, "total_seconds": round(total, 3),
            "load_seconds": round(load, 3), "excluding_load_seconds": round(total - load, 3),
            "prompt_seconds": round(result.get("prompt_eval_duration", 0) / 1e9, 3),
            "generation_seconds": round(result.get("eval_duration", 0) / 1e9, 3),
            "output_tokens": result.get("eval_count")}


DEFAULT_PROMPT = "OCR the image and output in Markdown.<think>"


def inspect_boxes(message: dict[str, Any]) -> dict[str, Any]:
    """Find explicit layout boxes without treating arbitrary numbers as coordinates."""
    boxes = []
    markers = []
    for channel in ("thinking", "content"):
        text = message.get(channel, "") or ""
        if "<layout>" in text or "<box>" in text:
            markers.append(channel)
        for match in re.finditer(r"<box>\s*(.*?)\s*</box>", text, re.DOTALL):
            numbers = re.findall(r"-?\d+(?:\.\d+)?", match.group(1))
            if len(numbers) == 4:
                coordinates = [float(value) for value in numbers]
                x1, y1, x2, y2 = coordinates
                boxes.append({"channel": channel, "coordinates": coordinates,
                              "valid_normalized_box": (
                                  0 <= x1 < x2 <= 999 and 0 <= y1 < y2 <= 999)})
    return {"box_count": len(boxes), "boxes": boxes,
            "layout_marker_channels": markers,
            "thinking_returned": bool(message.get("thinking")),
            "coordinate_system": "0-999 assumed from paper; verify before overlay"}

def build_request(image: bytes, prompt: str, model: str, max_tokens: int) -> dict[str, Any]:
    """Send a targeted natural-language prompt without a JSON constraint."""
    return {
        "model": model, "stream": False, "think": True,
        "messages": [{"role": "user", "content": prompt,
                      "images": [base64.b64encode(image).decode("ascii")]}],
        "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": 8192},
    }

def run(args: argparse.Namespace) -> Path:
    """Render PDF pages and save raw responses, Markdown and per-page timings."""
    if args.dpi <= 0 or args.timeout <= 0 or args.max_tokens <= 0:
        raise ValueError("DPI, timeout and max tokens must be positive.")
    pdf = args.pdf.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    pages: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    with httpx.Client(base_url=args.host.rstrip("/"), timeout=args.timeout) as client:
        response = client.post("/api/show", json={"model": args.model})
        response.raise_for_status()
        if "vision" not in response.json().get("capabilities", []):
            raise ValueError("Ollama model does not report vision support.")
        with fitz.open(pdf) as document:
            if document.needs_pass or not len(document):
                raise ValueError("PDF must be nonempty and unencrypted.")
            for index, page in enumerate(document, start=1):
                print(f"Extracting page {index}/{len(document)} ...", flush=True)
                png = page.get_pixmap(dpi=args.dpi, alpha=False).tobytes("png")
                response = client.post("/api/chat", json=build_request(
                    png, args.prompt, args.model, args.max_tokens))
                response.raise_for_status()
                result = response.json()
                timings.append(timing_summary(result, index))
                (output / f"page_{index:03d}_response.json").write_text(
                    json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                report = inspect_boxes(result.get("message", {}))
                (output / f"page_{index:03d}_boxes.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8")
                print(f"Explicit boxes: {report['box_count']}; thinking returned: "
                      f"{report['thinking_returned']}", flush=True)
                content = result.get("message", {}).get("content", "").strip()
                if not result.get("done") or result.get("done_reason") == "length" or not content:
                    raise ValueError("Empty or incomplete generation; raw response saved.")
                pages.append({"page": index, "text": content})
                (output / f"page_{index:03d}.md").write_text(content, encoding="utf-8")
    (output / "extraction.md").write_text(
        "\n\n".join(f"## Page {p['page']}\n\n{p['text']}" for p in pages),
        encoding="utf-8")
    (output / "run.json").write_text(json.dumps({
        "pdf": str(pdf), "model": args.model, "prompt": args.prompt, "thinking": True,
        "dpi": args.dpi, "pages": len(pages),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "page_timings": timings,
        "inference_excluding_load_seconds": round(sum(
            timing["excluding_load_seconds"] for timing in timings), 3),
    }, indent=2), encoding="utf-8")
    return output


def main() -> None:
    """Run independently of application configuration, databases and other experiments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "qianfan-layout")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--max-tokens", type=int, default=4096)
    print(f"Saved results to {run(parser.parse_args())}")


if __name__ == "__main__":
    main()
