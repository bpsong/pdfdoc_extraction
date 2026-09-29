"""Generate a synthetic PDF for upload-size and OCR-render benchmarks."""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import random

import fitz
from PIL import Image, ImageDraw, ImageFont

MIB = 1024 * 1024


def generate_pdf(path: Path, *, pages: int = 30, target_mib: float = 49) -> Path:
    """Write scanned-style pages and a synthetic attachment near the target size.

    The attachment exercises upload size without increasing rendered page memory.
    The page rasters separately exercise multi-page rendering. The output is
    intentionally synthetic and contains no business documents.
    """
    if pages < 1 or target_mib <= 0:
        raise ValueError("pages and target_mib must be positive")
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1836, 2376  # US Letter at the default GLM OCR 216 DPI.
    page_rect = fitz.Rect(0, 0, 612, 792)
    font = ImageFont.load_default()
    document = fitz.open()
    for page_no in range(pages):
        rng = random.Random(81000 + page_no)
        image = Image.new("L", (width, height), color=247)
        draw = ImageDraw.Draw(image)
        draw.text(
            (110, 105),
            f"SYNTHETIC PERFORMANCE FIXTURE - PAGE {page_no + 1:02d}",
            fill=20,
            font=font,
        )
        draw.line((110, 165, width - 110, 165), fill=70, width=3)
        y = 220
        for _ in range(46):
            line_width = rng.randint(450, width - 250)
            draw.rectangle(
                (115, y, 115 + line_width, y + rng.randint(2, 5)),
                fill=rng.randint(60, 155),
            )
            y += 42
        pixels = bytearray(image.tobytes())
        for _ in range(110_000):
            index = rng.randrange(len(pixels))
            pixels[index] = max(
                0,
                min(255, pixels[index] + rng.choice((-3, -2, -1, 1, 2, 3))),
            )
        image = Image.frombytes("L", image.size, bytes(pixels))
        image_buffer = io.BytesIO()
        image.save(image_buffer, format="JPEG", quality=91, optimize=True)
        page = document.new_page(width=612, height=792)
        page.insert_image(page_rect, stream=image_buffer.getvalue())
        image.close()

    base_pdf = document.tobytes(garbage=4, deflate=True)
    document.close()
    target_bytes = round(target_mib * MIB)
    payload_size = target_bytes - len(base_pdf) - 16_384
    if payload_size <= 0:
        raise ValueError("Target size is smaller than the rendered pages")
    for _ in range(3):
        document = fitz.open(stream=base_pdf, filetype="pdf")
        document.embfile_add(
            "synthetic-size-payload.bin",
            os.urandom(payload_size),
            desc="Synthetic upload-size test payload; not a business document",
        )
        final_bytes = document.tobytes(garbage=4, deflate=True)
        document.close()
        delta = target_bytes - len(final_bytes)
        if 0 <= delta < 64 * 1024:
            break
        payload_size += delta - 4096
        if payload_size <= 0:
            raise ValueError("Target size is too small")
    else:
        raise RuntimeError("Could not tune the PDF to the target size")
    with path.open("xb") as output:
        output.write(final_bytes)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--target-mib", type=float, default=49)
    args = parser.parse_args()
    path = generate_pdf(args.path, pages=args.pages, target_mib=args.target_mib)
    print(f"Created {path.resolve()} ({path.stat().st_size / MIB:.2f} MiB)")


if __name__ == "__main__":
    main()
