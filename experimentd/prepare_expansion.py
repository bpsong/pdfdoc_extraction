"""Select additional local invoices and render independent reference-review pages."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
from typing import Any

import fitz

from experimentd.glm_comparison import select_pages


def select_additional(paths: list[Path], existing: set[Path], count: int,
                      seed: int = 42, randomize: bool = True) -> list[Path]:
    """Select without replacement from a stable filename order."""
    available = sorted(set(paths) - existing)
    if count > len(available):
        raise ValueError("Insufficient distinct source invoices.")
    if randomize:
        return random.Random(seed).sample(available, count)
    return available[:count]


def prepare(root: Path, manifest: Path, output: Path, per_type: int = 20,
            fts_pages: dict[str, str] | None = None) -> None:
    """Export source evidence before inference; no model output supplies references."""
    original = json.loads(manifest.read_text(encoding="utf-8"))
    poppler = shutil.which("pdftoppm")
    if poppler is None:
        raise RuntimeError("pdftoppm is required for independent visual review.")
    if fts_pages is None:
        raise ValueError("A manually reviewed FTS filename-to-invoice-pages map is required.")
    output.mkdir(parents=True, exist_ok=True)
    selection: list[dict[str, Any]] = []
    for group, folder in [("superstore", "sample stock invoices from internet"),
                          ("fts", "fts_test_files/fts_data")]:
        old = [sample for sample in original["samples"] if sample["group"] == group]
        existing = {(root / sample["pdf"]).resolve() for sample in old}
        candidates = sorted((root / folder).glob("*.pdf"))
        if group == "fts":
            candidates = [p for p in candidates if p.name in fts_pages]
        if group == "superstore":
            # Exclude demonstrably empty template PDFs before seeded sampling.
            eligible = []
            for path in candidates:
                with fitz.open(path) as document:
                    text = "\n".join(page.get_text() for page in document)
                if "SuperStore" in text and "# " in text:
                    eligible.append(path.resolve())
            candidates = eligible
        new = select_additional([p.resolve() for p in candidates], existing,
                                per_type - len(old), randomize=group == "superstore")
        for index, path in enumerate(new, len(old) + 1):
            sample_id = f"{group}_{index}"
            page_specification = "1" if group == "superstore" else fts_pages[path.name]
            directory = output / sample_id
            directory.mkdir(parents=True, exist_ok=True)
            with fitz.open(path) as document:
                pages = [{"page": i + 1, "width": page.rect.width,
                          "height": page.rect.height, "text": page.get_text(),
                          "words": page.get_text("words")} for i, page in enumerate(document)]
            entry = {"id": sample_id, "group": group,
                     "pdf": path.relative_to(root).as_posix(), "pages": page_specification,
                     "cohort": "additional", "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "page_count": len(pages)}
            (directory / "source.json").write_text(json.dumps({**entry, "source_pages": pages}, indent=2), encoding="utf-8")
            for page_number in select_pages(page_specification, len(pages)):
                subprocess.run([poppler, "-f", str(page_number), "-l", str(page_number),
                                "-r", "110", "-singlefile", "-png", str(path),
                                str(directory / f"source_page_{page_number}")], check=True, capture_output=True)
            selection.append(entry)
    (output / "selection.json").write_text(json.dumps({"seed": 42,
        "selection": "Original six retained; seeded random eligible Superstore additions; FTS additions in filename order from independently reviewed invoice-page map. No inference results consulted.",
        "samples": selection}, indent=2), encoding="utf-8")
    print(f"Prepared {len(selection)} additional reference-review pages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "samples.local.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output" / "expanded_sources")
    parser.add_argument("--per-type", type=int, default=20)
    parser.add_argument("--fts-pages", type=Path, default=Path(__file__).parent / "fts_pages.local.json")
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parent.parent, args.manifest, args.output, args.per_type,
            json.loads(args.fts_pages.read_text(encoding="utf-8")))
