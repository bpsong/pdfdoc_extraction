"""Standalone TeleOCR full-page recognition experiment using native Transformers."""

import argparse
import io
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = ROOT.parent / "sample stock invoices from internet" / "invoice_Aaron Bergman_36258.pdf"
MODEL = "XingChen-AGI/TeleOCR"
REVISION = "e92585356c0d0b7b7a65938f3da035c6593cc9a6"
PROMPT = "Please output the text content from the image."


def has_repetition(text: str) -> bool:
    """Flag a repeated-line generation loop rather than accepting it as OCR."""
    from collections import Counter

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    counts = Counter(lines)
    return bool(lines) and any(count >= 10 and count / len(lines) >= 0.2
                               for count in counts.values())


def build_messages(prompt: str) -> list[dict[str, Any]]:
    """Use the model card's image-bearing chat format."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]},
    ]


def run(args: argparse.Namespace) -> Path:
    """Recognize PDF page images and preserve raw output and runtime evidence."""
    if args.dpi <= 0 or args.max_pixels <= 0 or args.max_tokens <= 0:
        raise ValueError("DPI, max pixels, and max tokens must be positive.")
    pdf = args.pdf.resolve(strict=True)
    import fitz
    import torch
    from PIL import Image
    from transformers import AutoModel, AutoProcessor

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA PyTorch is required for this GPU experiment.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    print("Loading TeleOCR on CUDA in FP16...", flush=True)
    processor = AutoProcessor.from_pretrained(
        MODEL, revision=REVISION, trust_remote_code=True, use_fast=True,
        max_pixels=args.max_pixels,
    )
    model = AutoModel.from_pretrained(
        MODEL, revision=REVISION, trust_remote_code=True,
        torch_dtype=torch.float16, attn_implementation="sdpa", device_map="cuda:0",
    ).eval()
    loaded = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    page_results: list[dict[str, Any]] = []
    with fitz.open(pdf) as document:
        if document.needs_pass or not len(document):
            raise ValueError("PDF must be nonempty and unencrypted.")
        for index, page in enumerate(document, start=1):
            print(f"Recognizing page {index}/{len(document)}...", flush=True)
            image = Image.open(io.BytesIO(page.get_pixmap(dpi=args.dpi, alpha=False).tobytes("png"))).convert("RGB")
            prompt = processor.apply_chat_template(build_messages(args.prompt), tokenize=False,
                                                   add_generation_prompt=True)
            inputs = processor(text=[prompt], images=[image], padding=True,
                               return_tensors="pt").to(device=model.device, dtype=model.dtype)
            page_started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**inputs, use_cache=True,
                                           max_new_tokens=args.max_tokens, do_sample=False)
            tokens = generated[0, inputs.input_ids.shape[1]:]
            text = processor.batch_decode([tokens.cpu().tolist()], skip_special_tokens=True,
                                          clean_up_tokenization_spaces=False)[0].strip()
            result = {"page": index, "text": text, "output_tokens": len(tokens),
                      "elapsed_seconds": round(time.perf_counter() - page_started, 2),
                      "possibly_truncated": len(tokens) >= args.max_tokens,
                      "repetition_detected": has_repetition(text)}
            (output / f"page_{index:03d}.json").write_text(json.dumps(result, indent=2,
                                                                          ensure_ascii=False), encoding="utf-8")
            page_results.append(result)
    (output / "ocr.md").write_text("\n\n".join(
        f"--- PAGE {page['page']} ---\n{page['text']}" for page in page_results
    ), encoding="utf-8")
    (output / "run.json").write_text(json.dumps({
        "pdf": str(pdf), "model": MODEL, "revision": REVISION, "dtype": "float16",
        "torch_version": torch.__version__, "gpu": torch.cuda.get_device_name(0),
        "prompt": args.prompt, "dpi": args.dpi, "max_pixels": args.max_pixels,
        "pages": len(page_results), "load_seconds": round(loaded - started, 2),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "peak_gpu_allocated_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "recognition_valid": all(page["text"] and not page["possibly_truncated"]
                                 and not page["repetition_detected"] for page in page_results),
    }, indent=2), encoding="utf-8")
    if any(not page["text"] or page["possibly_truncated"] or page["repetition_detected"]
           for page in page_results):
        raise ValueError("Recognition failed quality checks; raw results saved for inspection.")
    return output


def main() -> None:
    """Run independently of application configuration, PaddleOCR and Ollama."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "teleocr")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--max-pixels", type=int, default=1003520)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--prompt", default=PROMPT)
    args = parser.parse_args()
    print(f"Saved results to {run(args)}")


if __name__ == "__main__":
    main()
