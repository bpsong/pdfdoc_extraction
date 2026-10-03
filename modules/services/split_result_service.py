"""Persist and present single-document split decisions without changing flow state."""

from __future__ import annotations

import sqlite3
from typing import Any

from modules.db.connection import immediate_transaction, json_loads
from modules.db.repositories import AuditRepository, DocumentRepository


def apply_single_document_context(
    context: dict[str, Any], decision: dict[str, Any], *, reused: bool = False,
) -> None:
    """Restore classification without introducing child identity or flow signals."""
    context.update(
        split_category=decision["category"],
        split_confidence=decision["confidence"],
        split_pages=list(decision["pages"]),
        page_start=decision["pages"][0],
        page_end=decision["pages"][-1],
        split_provider_job_id=decision["provider_job_id"],
    )
    context.setdefault("metadata", {})["split"] = dict(decision)
    context.setdefault("data", {})["split_result"] = {
        "status": "single_document", "provider_job_id": decision["provider_job_id"],
        "category": decision["category"], "confidence": decision["confidence"],
        "pages": list(decision["pages"]), "children": [], "reused": reused,
    }


def restore_single_document_context(
    context: dict[str, Any], document: dict[str, Any],
) -> None:
    """Restore the last original-document split decision after human review."""
    decision = json_loads(document.get("metadata_json"), {}).get("split_result", {})
    if decision.get("outcome") == "single_document":
        apply_single_document_context(context, decision, reused=True)


def save_single_document_decision(
    conn: sqlite3.Connection, document: dict[str, Any], decision: dict[str, Any],
) -> None:
    """Save classification, decision, and accountability together."""
    documents = DocumentRepository(conn)
    with immediate_transaction(conn):
        current = documents.get(str(document["id"])) or document
        metadata = json_loads(current.get("metadata_json"), {})
        decisions = metadata.setdefault("single_document_splits", {})
        previous = decisions.get(decision["task_key"])
        decisions[decision["task_key"]] = decision
        metadata["split_result"] = decision
        documents.update_split_classification(
            str(document["id"]), category=decision["category"],
            confidence=decision["confidence"], page_start=decision["pages"][0],
            page_end=decision["pages"][-1],
        )
        documents.update_metadata(str(document["id"]), metadata)
        if previous != decision:
            AuditRepository(conn).append(
                event_type="split_not_needed",
                event={"task_key": decision["task_key"], "outcome": "single_document"},
                batch_id=str(document["batch_id"]), document_id=str(document["id"]),
            )


def build_split_results(batch_documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a safe split-results response, preserving existing child counts."""
    roots = [doc for doc in batch_documents if not doc.get("parent_document_id")]
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for document in batch_documents:
        if document.get("parent_document_id"):
            children_by_parent.setdefault(str(document["parent_document_id"]), []).append(document)
    sources: list[dict[str, Any]] = []
    total_children = failed_children = continuing = 0
    for root in roots:
        children = children_by_parent.get(str(root["id"]), [])
        child_payloads = []
        for child in children:
            total_children += 1
            failed_children += int(child.get("status") == "failed")
            metadata = json_loads(child.get("metadata_json"), {})
            child_payloads.append({
                "document_id": child["id"], "filename": child.get("original_filename"),
                "file_path": child.get("file_path"), "category": child.get("split_category"),
                "page_start": child.get("page_start"), "page_end": child.get("page_end"),
                "pages": metadata.get("split_pages") or [],
                "split_confidence": child.get("split_confidence"), "status": child.get("status"),
                "parent_document_id": child.get("parent_document_id"),
            })
        decision = json_loads(root.get("metadata_json"), {}).get("split_result", {})
        single = decision.get("outcome") == "single_document" and not children
        continuing += int(single)
        sources.append({
            "document_id": root["id"], "source_file": root.get("original_filename"),
            "file_path": root.get("file_path"), "documents_created": len(children),
            "status": "success" if root.get("status") == "split_completed" else root.get("status"),
            "children": child_payloads,
            "split_outcome": "single_document" if single else ("split_completed" if children else None),
            "category": decision.get("category") if single else None,
            "split_confidence": decision.get("confidence") if single else None,
            "pages": decision.get("pages", []) if single else [],
            "extraction_document_id": root["id"] if single else (
                children[0]["id"] if children else None
            ),
        })
    return {"summary": {
        "total_files": len(roots), "documents_created": total_children,
        "successful": total_children - failed_children, "failed": failed_children,
        "documents_continuing": continuing,
    }, "sources": sources}
