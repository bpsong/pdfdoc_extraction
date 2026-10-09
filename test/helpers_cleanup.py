"""Synthetic whole-batch histories shared by cleanup and browser tests."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from modules.db.connection import json_dumps
from modules.services.batch_service import BatchService


OLD = "2020-01-02T00:00:00+00:00"
CUTOFF = "2021-01-01"


def seed_history(
    conn: sqlite3.Connection, root: Path, template_id: str, version_id: str,
    *, status: str = "completed", child: bool = False,
) -> dict[str, Any]:
    """Create a completed history including every processing dependency."""
    file_path = root / f"synthetic-{uuid.uuid4()}.pdf"
    file_path.write_bytes(b"%PDF-1.4\nSynthetic cleanup fixture\n")
    created = BatchService(conn).create_ingestion_batch(
        source="test", file_path=str(file_path), original_filename="synthetic.pdf",
        pipeline_template_id=template_id, pipeline_version_id=version_id,
        pipeline_assignment_source="upload",
    )
    batch_id, doc_id = created["batch"]["id"], created["document"]["id"]
    ids = {key: str(uuid.uuid4()) for key in ("run", "result", "field", "review", "lock", "decision", "job", "audit", "receipt")}
    conn.execute("UPDATE batches SET status='completed', created_at=?, updated_at=? WHERE id=?", (OLD, OLD, batch_id))
    conn.execute("UPDATE documents SET status=?, created_at=?, updated_at=? WHERE id=?", (status, OLD, OLD, doc_id))
    conn.execute("UPDATE document_files SET created_at=? WHERE document_id=?", (OLD, doc_id))
    conn.execute("""INSERT INTO task_runs
        (id,batch_id,document_id,task_key,task_index,module_name,class_name,status,started_at,ended_at,pipeline_version_id)
        VALUES (?,?,?,'extract',0,'synthetic','SyntheticTask','completed',?,?,?)""",
        (ids["run"], batch_id, doc_id, OLD, OLD, version_id))
    conn.execute("INSERT INTO extraction_results(id,document_id,task_run_id,provider,data_json,created_at) VALUES (?,?,?,'test','{}',?)",
                 (ids["result"], doc_id, ids["run"], OLD))
    conn.execute("INSERT INTO extracted_fields(id,document_id,extraction_result_id,field_key,field_alias,created_at,updated_at) VALUES (?,?,?,'total','Total',?,?)",
                 (ids["field"], doc_id, ids["result"], OLD, OLD))
    conn.execute("""INSERT INTO review_items
        (id,batch_id,document_id,queue_name,status,reason,scope,created_by_task_run_id,created_at,updated_at,completed_at)
        VALUES (?,?,?,'test','completed','test','all',?,?,?,?)""",
        (ids["review"], batch_id, doc_id, ids["run"], OLD, OLD, OLD))
    conn.execute("INSERT INTO review_locks VALUES (?,?,'admin',?,?)", (ids["lock"], ids["review"], OLD, OLD))
    conn.execute("""INSERT INTO manual_split_decisions
        (id,document_id,pipeline_version_id,task_key,task_index,task_run_id,review_item_id,source_sha256,page_count,phase,created_at,updated_at)
        VALUES (?,?,?,'extract',0,?,?,'synthetic-sha',1,'applied',?,?)""",
        (ids["decision"], doc_id, version_id, ids["run"], ids["review"], OLD, OLD))
    conn.execute("""INSERT INTO processing_jobs
        (id,batch_id,document_id,status,available_at,created_at,completed_at,updated_at)
        VALUES (?,?,?,'completed',?,?,?,?)""", (ids["job"], batch_id, doc_id, OLD, OLD, OLD, OLD))
    conn.execute("INSERT INTO audit_events VALUES (?,?,?,?,'admin','synthetic_event','{}',?)",
                 (ids["audit"], batch_id, doc_id, ids["review"], OLD))
    conn.execute("INSERT INTO upload_submissions VALUES ('admin',?,'synthetic-fingerprint',?,?)",
                 (ids["receipt"], json_dumps({"batch": created["batch"], "documents": [created["document"]]}), OLD))
    if child:
        child_id = str(uuid.uuid4())
        conn.execute("""INSERT INTO documents
            (id,batch_id,parent_document_id,status,file_path,pipeline_template_id,pipeline_version_id,created_at,updated_at)
            VALUES (?,?,?,'completed',?,?,?,?,?)""",
            (child_id, batch_id, doc_id, str(file_path), template_id, version_id, OLD, OLD))
        conn.execute("UPDATE documents SET status='split_completed' WHERE id=?", (doc_id,))
        ids["child"] = child_id
    conn.commit()
    return {"batch_id": batch_id, "document_id": doc_id, "file_path": file_path, **ids}
