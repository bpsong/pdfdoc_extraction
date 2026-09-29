"""Checks that performance fixtures and query-count probes are valid."""

from pathlib import Path
import sqlite3

import fitz
from pypdf import PdfReader

from tools.benchmark_performance import BenchConfig, _query_count, _seed_batch
from tools.generate_performance_pdf import generate_pdf
from modules.services.processing_state_service import ProcessingStateService


def test_generated_performance_pdf_opens_in_both_project_readers(tmp_path: Path) -> None:
    path = generate_pdf(tmp_path / "synthetic.pdf", pages=1, target_mib=1)

    assert 0.95 * 1024 * 1024 <= path.stat().st_size < 1024 * 1024
    assert len(PdfReader(str(path), strict=False).pages) == 1
    with fitz.open(path) as document:
        assert document.page_count == 1
        assert document.embfile_count() == 1


def test_processing_probe_select_count_stays_bounded(tmp_path: Path) -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    schema = Path(__file__).resolve().parents[2] / "modules" / "db" / "schema.sql"
    connection.executescript(schema.read_text(encoding="utf-8"))
    try:
        _seed_batch(connection, "small", 1)
        _seed_batch(connection, "larger", 4)
        _seed_batch(connection, "chunked", 501)
        service = ProcessingStateService(BenchConfig(tmp_path), connection)

        small = _query_count(connection, lambda: service.get_batch_state("small"))
        larger = _query_count(connection, lambda: service.get_batch_state("larger"))
        chunked = _query_count(connection, lambda: service.get_batch_state("chunked"))

        assert small == 4
        assert larger == 4
        assert chunked == 6
    finally:
        connection.close()
