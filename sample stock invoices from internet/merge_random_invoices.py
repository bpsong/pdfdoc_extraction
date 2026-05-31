"""Merge four random invoice PDFs into a new PDF file.

This script selects four PDF files from the current folder, merges them
into a brand-new output PDF, and prints the chosen file names.
"""

from __future__ import annotations

from pathlib import Path
from random import sample
from uuid import uuid4

from pypdf import PdfWriter


SOURCE_DIR = Path(__file__).resolve().parent


def merge_random_invoices(source_dir: Path, count: int = 4) -> Path:
    """Merge ``count`` random PDFs from ``source_dir`` into a new PDF.

    Args:
        source_dir: Directory that contains source invoice PDFs.
        count: Number of PDFs to merge.

    Returns:
        The path to the newly created merged PDF.

    Raises:
        ValueError: If there are fewer than ``count`` PDF files available.
    """
    pdf_files = sorted(source_dir.glob("*.pdf"))
    if len(pdf_files) < count:
        raise ValueError(
            f"Need at least {count} PDF files, found {len(pdf_files)} in {source_dir}"
        )

    selected_files = sample(pdf_files, count)
    output_file = source_dir / f"random_merged_invoices_{uuid4().hex}.pdf"

    writer = PdfWriter()
    try:
        for pdf_file in selected_files:
            writer.append(str(pdf_file))
        with output_file.open("wb") as output_stream:
            writer.write(output_stream)
    finally:
        writer.close()

    print("Merged files:")
    for pdf_file in selected_files:
        print(f" - {pdf_file.name}")
    print(f"Output written to: {output_file}")

    return output_file


if __name__ == "__main__":
    merge_random_invoices(SOURCE_DIR, count=4)
