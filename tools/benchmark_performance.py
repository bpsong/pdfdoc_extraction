"""Measure selected PDF pipeline costs with synthetic, temporary data.

Run from the repository root with the repository virtual environment's Python:
``tools/benchmark_performance.py``. No configured database or external OCR service is
used. Results are measurements of this machine, not fixed pass/fail limits.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
from time import perf_counter
from typing import Any, Callable
from unittest.mock import patch

import bcrypt
import psutil
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.db.repositories import ConfigVersionRepository, DocumentRepository  # noqa: E402
from modules.services.failure_service import FailureService  # noqa: E402
from modules.services.processing_state_service import ProcessingStateService  # noqa: E402
from modules.services.upload_receiver import receive_multipart_upload  # noqa: E402
from standard_step.extraction.glm_ocr_adapter import GlmOcrAdapter  # noqa: E402
from tools.generate_performance_pdf import generate_pdf  # noqa: E402

MIB = 1024 * 1024
STAMP = "2026-01-01T00:00:00+00:00"
PDF_FIXTURE = ROOT / "test" / "performance_fixtures" / "synthetic_30_page_49_mib.pdf"


class BenchConfig:
    """Provide only settings needed by the measured services."""

    def __init__(self, root: Path) -> None:
        self.values = {
            "database.path": str(root / "benchmark.sqlite3"),
            "web.upload_dir": str(root / "uploads"),
            "web.max_upload_mb": 50,
            "web.max_upload_files": 20,
            "web.max_upload_request_mb": 200,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


def _timed(call: Callable[[], Any], *, repeats: int = 7) -> dict[str, float]:
    """Warm one call, then report median and maximum of repeated calls."""
    call()
    timings = []
    for _ in range(repeats):
        started = perf_counter()
        call()
        timings.append((perf_counter() - started) * 1000)
    return {
        "median_ms": round(statistics.median(timings), 2),
        "max_ms": round(max(timings), 2),
    }


def _query_count(conn: sqlite3.Connection, call: Callable[[], Any]) -> int:
    count = 0

    def trace(statement: str) -> None:
        nonlocal count
        if statement.lstrip().upper().startswith("SELECT"):
            count += 1

    conn.set_trace_callback(trace)
    try:
        call()
    finally:
        conn.set_trace_callback(None)
    return count


def _seed_batch(conn: sqlite3.Connection, batch_id: str, count: int) -> None:
    snapshot = {
        "version": 1,
        "source": "synthetic_benchmark",
        "content_hash": "synthetic",
        "step_count": 3,
        "steps": [
            {"key": f"step-{i}", "position": i, "category": "extract"}
            for i in range(3)
        ],
    }
    conn.execute(
        """INSERT INTO batches(id, source, status, total_documents,
               created_at, updated_at, metadata_json) VALUES (?, 'web', 'running', ?, ?, ?, ?)""",
        (batch_id, count, STAMP, STAMP, json.dumps({"pipeline_snapshot": snapshot})),
    )
    docs = [
        (
            f"{batch_id}-doc-{i}", batch_id, "running", f"synthetic-{i}.pdf",
            f"synthetic/{i}.pdf", STAMP, STAMP,
        )
        for i in range(count)
    ]
    conn.executemany(
        """INSERT INTO documents(id, batch_id, status, original_filename,
               file_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        docs,
    )
    runs = [
        (
            f"{doc_id}-run-{step}", batch_id, doc_id, f"step-{step}", step,
            "synthetic", "SyntheticTask", "completed", STAMP, "{}", "{}",
        )
        for doc_id, *_ in docs
        for step in range(3)
    ]
    conn.executemany(
        """INSERT INTO task_runs(id, batch_id, document_id, task_key,
               task_index, module_name, class_name, status, started_at,
               input_json, output_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        runs,
    )
    conn.executemany(
        """INSERT INTO audit_events(id, batch_id, document_id, event_type,
               event_json, created_at) VALUES (?, ?, ?, 'document.status_changed', '{}', ?)""",
        [(f"{doc_id}-audit", batch_id, doc_id, STAMP) for doc_id, *_ in docs],
    )
    conn.commit()


def _seed_failures(conn: sqlite3.Connection, siblings: int) -> str:
    batch_id = "failure-batch"
    conn.execute(
        """INSERT INTO batches(id, source, status, created_at, updated_at)
               VALUES (?, 'web', 'failed', ?, ?)""",
        (batch_id, STAMP, STAMP),
    )
    parent_id = "failure-parent"
    conn.execute(
        """INSERT INTO documents(id, batch_id, status, file_path,
               created_at, updated_at) VALUES (?, ?, 'failed', 'synthetic/parent.pdf', ?, ?)""",
        (parent_id, batch_id, STAMP, STAMP),
    )
    conn.executemany(
        """INSERT INTO documents(id, batch_id, parent_document_id, status,
               file_path, created_at, updated_at) VALUES (?, ?, ?, 'failed', ?, ?, ?)""",
        [
            (f"failure-child-{i}", batch_id, parent_id, f"synthetic/{i}.pdf", STAMP, STAMP)
            for i in range(siblings)
        ],
    )
    conn.executemany(
        """INSERT INTO task_runs(id, batch_id, document_id, task_key,
               task_index, module_name, class_name, status, started_at,
               error, input_json, output_json)
               VALUES (?, ?, ?, 'extract', 0, 'synthetic', 'SyntheticTask',
                       'failed', ?, 'synthetic error', '{}', '{}')""",
        [
            (f"failure-run-{i}", batch_id, f"failure-child-{i}", STAMP)
            for i in range(siblings)
        ],
    )
    conn.commit()
    return "failure-child-0"


def _seed_versions(conn: sqlite3.Connection, count: int) -> None:
    content = "S" * (64 * 1024)
    conn.executemany(
        """INSERT INTO config_versions(id, config_type, name, status,
               content_text, content_hash, created_at)
               VALUES (?, 'pipeline', 'synthetic', ?, ?, 'synthetic', ?)""",
        [
            (f"version-{i}", "published" if i % 4 == 0 else "archived", content, STAMP)
            for i in range(count)
        ],
    )
    conn.commit()


def _database_benchmarks(root: Path) -> dict[str, Any]:
    db_path = root / "benchmark.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((ROOT / "modules" / "db" / "schema.sql").read_text(encoding="utf-8"))
    config = BenchConfig(root)
    result: dict[str, Any] = {}
    overview = ProcessingStateService(config, conn)
    result["processing_overview"] = {}
    for count in (50, 250, 1000):
        batch_id = f"overview-{count}"
        _seed_batch(conn, batch_id, count)
        call = lambda batch_id=batch_id: overview.get_batch_state(batch_id)
        result["processing_overview"][str(count)] = {
            "selects": _query_count(conn, call),
            **_timed(call),
        }
    # Run the former per-document read strategy against the same seeded data
    # and payload builder, so machine load affects both timings similarly.
    reference = ProcessingStateService(config, conn)
    def per_document_runs(ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {document_id: reference.task_runs.list_by_document(document_id) for document_id in ids}

    def per_document_history(ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {
            document_id: [
                row for row in reference.audit.list_for_document(document_id)
                if row["event_type"] == "document.status_changed"
            ]
            for document_id in ids
        }

    with (
        patch.object(reference.task_runs, "list_by_documents", side_effect=per_document_runs),
        patch.object(reference.audit, "list_status_changes_by_documents", side_effect=per_document_history),
    ):
        reference_call = lambda: reference.get_batch_state("overview-1000")
        result["processing_overview"]["1000"]["per_document_reference"] = {
            "selects": _query_count(conn, reference_call),
            **_timed(reference_call),
        }

    result["failure_detail"] = {}
    for count in (25, 100, 500):
        # Each scenario uses its own database so sibling count is exact.
        temp = sqlite3.connect(":memory:")
        temp.row_factory = sqlite3.Row
        temp.execute("PRAGMA foreign_keys = ON")
        temp.executescript((ROOT / "modules" / "db" / "schema.sql").read_text(encoding="utf-8"))
        document_id = _seed_failures(temp, count)
        call = lambda: FailureService(temp).get_failure(document_id)
        result["failure_detail"][str(count)] = {
            "selects": _query_count(temp, call),
            **_timed(call),
        }
        temp.close()

    _seed_versions(conn, 1000)
    versions = ConfigVersionRepository(conn)
    full = lambda: versions.list_versions()
    result["config_version_counts"] = {
        "versions": 1000,
        "content_kib_per_version": 64,
        "full_rows_reference": _timed(full),
        "summary_status_counts": _timed(versions.status_counts),
        "full_text_mib": round(1000 * 64 / 1024, 2),
    }

    # Isolate the cost of one missing foreign-key index at a useful table size.
    conn.execute(
        """INSERT INTO batches(id, source, status, created_at, updated_at)
               VALUES ('index-batch', 'web', 'completed', ?, ?)""",
        (STAMP, STAMP),
    )
    conn.execute(
        """INSERT INTO documents(id, batch_id, status, file_path,
               created_at, updated_at)
               VALUES ('index-parent', 'index-batch', 'completed',
                       'synthetic/parent.pdf', ?, ?)""",
        (STAMP, STAMP),
    )
    conn.executemany(
        """INSERT INTO documents(id, batch_id, parent_document_id, status,
               file_path, created_at, updated_at)
               VALUES (?, 'index-batch', ?, 'completed', ?, ?, ?)""",
        [
            (f"index-doc-{i}", "index-parent" if i == 25000 else None,
             f"synthetic/index-{i}.pdf", STAMP, STAMP)
            for i in range(50000)
        ],
    )
    conn.commit()
    lookup = lambda: DocumentRepository(conn).list_children("index-parent")
    before_plan = [row[3] for row in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM documents WHERE parent_document_id = ?",
        ("index-parent",),
    )]
    before = _timed(lookup)
    conn.execute("CREATE INDEX benchmark_parent_document_id ON documents(parent_document_id)")
    after_plan = [row[3] for row in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM documents WHERE parent_document_id = ?",
        ("index-parent",),
    )]
    after = _timed(lookup)
    result["parent_document_index"] = {
        "table_rows": 50000,
        "matches": 1,
        "without_index": {"plan": before_plan, **before},
        "with_index": {"plan": after_plan, **after},
    }
    conn.close()
    return result


def _bcrypt_benchmark() -> dict[str, Any]:
    password = b"SyntheticPassword1!"
    hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
    return _timed(lambda: bcrypt.checkpw(password, hashed), repeats=5)


async def _receive_pdf(pdf_path: Path, root: Path) -> dict[str, Any]:
    boundary = b"benchmarkboundary"
    header = (
        b"--" + boundary + b'\r\nContent-Disposition: form-data; name="pipeline_version_id"\r\n\r\nv1'
        b"\r\n--" + boundary + b'\r\nContent-Disposition: form-data; name="files"; filename="synthetic.pdf"'
        b"\r\nContent-Type: application/pdf\r\n\r\n"
    )
    tail = b"\r\n--" + boundary + b"--\r\n"
    file = pdf_path.open("rb")
    part = 0
    process = psutil.Process()
    peak_rss = process.memory_info().rss

    async def receive() -> dict[str, Any]:
        nonlocal part, peak_rss
        peak_rss = max(peak_rss, process.memory_info().rss)
        if part == 0:
            part = 1
            return {"type": "http.request", "body": header, "more_body": True}
        chunk = file.read(MIB)
        if chunk:
            return {"type": "http.request", "body": chunk, "more_body": True}
        part = 2
        return {"type": "http.request", "body": tail, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/receive",
        "headers": [(b"content-type", b"multipart/form-data; boundary=" + boundary)],
    }
    started = perf_counter()
    try:
        received = await receive_multipart_upload(
            Request(scope, receive), BenchConfig(root), staging_root=root / "staging"
        )
        elapsed = (perf_counter() - started) * 1000
        peak_rss = max(peak_rss, process.memory_info().rss)
        return {
            "elapsed_ms": round(elapsed, 2),
            "peak_rss_mib": round(peak_rss / MIB, 2),
            "received_bytes": received.files[0].size_bytes,
        }
    finally:
        file.close()


def _pdf_benchmarks(root: Path) -> dict[str, Any]:
    fixture = PDF_FIXTURE if PDF_FIXTURE.exists() else generate_pdf(root / PDF_FIXTURE.name)
    fixture_bytes = fixture.stat().st_size
    process = psutil.Process()
    before = process.memory_info().rss
    upload = asyncio.run(_receive_pdf(fixture, root))
    upload["rss_delta_mib"] = round(upload["peak_rss_mib"] - before / MIB, 2)
    if upload["received_bytes"] != fixture_bytes:
        raise RuntimeError("Upload receiver did not preserve fixture size")
    gc.collect()
    before_render = process.memory_info().rss
    adapter = GlmOcrAdapter(ollama_host="http://localhost:11434", model="synthetic")
    started = perf_counter()
    pages = adapter.render_pdf(str(fixture))
    render_ms = (perf_counter() - started) * 1000
    after_render = process.memory_info().rss
    result = {
        "fixture_mib": round(fixture_bytes / MIB, 2),
        "upload_receiver": upload,
        "render_pdf": {
            "elapsed_ms": round(render_ms, 2),
            "pages": len(pages),
            "png_bytes_mib": round(sum(map(len, pages)) / MIB, 2),
            "rss_increase_mib": round((after_render - before_render) / MIB, 2),
        },
    }
    del pages
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write machine-readable JSON results")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pdfdoc-benchmark-") as directory:
        root = Path(directory)
        results = {
            "database": _database_benchmarks(root),
            "bcrypt_checkpw": _bcrypt_benchmark(),
            "pdf": _pdf_benchmarks(root),
        }
    encoded = json.dumps(results, indent=2)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
