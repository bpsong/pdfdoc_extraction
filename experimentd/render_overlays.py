"""Create private PNG previews of model citations and reference value regions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import fitz

try:
    from .extract_invoice import HEADER_FIELDS, ITEM_FIELDS
except ImportError:
    from extract_invoice import HEADER_FIELDS, ITEM_FIELDS


def fields(invoice: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Flatten invoice fields while preserving row labels."""
    result = [(name, invoice[name]) for name in HEADER_FIELDS]
    for i, row in enumerate(invoice["line_items"], 1):
        result.extend((f"row{i}.{name}", row[name]) for name in ITEM_FIELDS)
    return result


def render_sample(pdf: Path, directory: Path, reference: dict[str, Any] | None = None) -> list[Path]:
    """Draw each cited word box in red, reference regions in blue, on source pages.

    The in-memory document is rendered with PyMuPDF; original PDFs are never
    saved or modified. Rotated pages retain their viewport coordinate system.
    """
    invoice = json.loads((directory / "invoice.json").read_text(encoding="utf-8"))
    grouped: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for label, field in fields(invoice):
        for entry in field["boxes"]:
            grouped.setdefault(entry["page"], []).append((label, entry))
    if reference:
        reference_fields = list(reference["fields"].values())
        reference_fields.extend(f for row in reference["line_items"] for f in row.values())
        for field in reference_fields:
            for region in field["regions"]:
                grouped.setdefault(region["page"], [])
    outputs = []
    with fitz.open(pdf) as document:
        for page_number, entries in grouped.items():
            page = document[page_number - 1]
            if reference:
                for field in reference_fields:
                    for region in field["regions"]:
                        if region["page"] != page_number:
                            continue
                        a, b, c, d = region["bbox_normalized"]
                        rect = fitz.Rect(a * page.rect.width, b * page.rect.height,
                                         c * page.rect.width, d * page.rect.height)
                        page.draw_rect(rect * page.derotation_matrix, color=(0, .35, 1), width=.5)
            for _, entry in entries:
                page.draw_rect(fitz.Rect(entry["bbox"]) * page.derotation_matrix,
                               color=(1, 0, 0), width=.6)
            destination = directory / f"overlay_page_{page_number}.png"
            page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(destination)
            outputs.append(destination)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples.local.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output" / "benchmark")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.manifest.resolve().parent.parent
    for sample in manifest["samples"]:
        directory = args.output / sample["id"]
        if (directory / "invoice.json").exists():
            render_sample(root / sample["pdf"], directory, sample)
            print(f"Rendered local overlay: {sample['id']}")


if __name__ == "__main__":
    main()
