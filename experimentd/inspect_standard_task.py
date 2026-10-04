"""Read-only audit of a UI-run invoice batch against private visual references.

Run from the repository root with the repository virtual environment. This
script never submits documents, edits workflow state, or sends model requests.
Detailed customer values stay in the ignored output directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from typing import Any

from experimentd.evaluate import score_sample, summarize
from experimentd.extract_invoice import HEADER_FIELDS, ITEM_FIELDS
from modules.config_manager import ConfigManager
from modules.db.connection import get_db_path


def wrap_values(data: dict[str, Any]) -> dict[str, Any]:
    """Adapt typed business values to the experiment's independent scorer."""
    def field(value: Any) -> dict[str, Any]:
        return {"value": str(value) if value is not None else None}

    result = {name: field(data.get(name)) for name in HEADER_FIELDS}
    result["line_items"] = [
        {name: field(row.get(name)) for name in ITEM_FIELDS}
        for row in data.get("line_items", [])
    ]
    return result


def audit_batch(batch_id: str, config_path: Path, manifest: Path,
                output: Path) -> dict[str, Any]:
    """Save raw/final scoring and artifact evidence without modifying SQLite."""
    config = ConfigManager(config_path, prepare_directories=False)
    references = {
        sample["id"]: sample
        for sample in json.loads(manifest.read_text(encoding="utf-8"))["samples"]
    }
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(get_db_path(config).as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        documents = conn.execute(
            "SELECT * FROM documents WHERE batch_id=? ORDER BY original_filename",
            (batch_id,),
        ).fetchall()
        evidence, raw_scores, final_scores = [], [], []
        for document in documents:
            sample_id = document["original_filename"].removeprefix("liteparse-").removesuffix(".pdf")
            reference = deepcopy(references[sample_id])
            reference["geometry_reviewed"] = False
            result = conn.execute(
                "SELECT * FROM extraction_results WHERE document_id=? ORDER BY created_at DESC LIMIT 1",
                (document["id"],),
            ).fetchone()
            raw = json.loads(result["data_json"]) if result else {}
            raw_score = score_sample(reference, wrap_values(raw), {"pages": []})
            if not result:
                for check in raw_score["checks"]:
                    check["correct"] = False
            raw_scores.append(raw_score)
            fields = conn.execute(
                "SELECT * FROM extracted_fields WHERE document_id=?", (document["id"],),
            ).fetchall()
            final = {row["field_key"]: json.loads(row["final_value_json"]) for row in fields}
            final_scores.append(score_sample(reference, wrap_values(final), {"pages": []}))
            artifacts = [dict(row) for row in conn.execute(
                "SELECT * FROM document_files WHERE document_id=? AND file_type='export_json'",
                (document["id"],),
            )]
            export_matches = []
            for artifact in artifacts:
                path = Path(artifact["file_path"])
                export = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
                export_matches.append(export == final)
            runs = [dict(row) for row in conn.execute(
                "SELECT task_key,task_index,status,pipeline_version_id,error FROM task_runs WHERE document_id=? ORDER BY task_index,started_at",
                (document["id"],),
            )]
            reviews = [dict(row) for row in conn.execute(
                "SELECT id,status,scope,queue_name,review_schema_version_id FROM review_items WHERE document_id=?",
                (document["id"],),
            )]
            evidence.append({
                "sample_id": sample_id, "document_id": document["id"],
                "status": document["status"], "pipeline_version_id": document["pipeline_version_id"],
                "provider": result["provider"] if result else None,
                "metadata": json.loads(result["metadata_json"]) if result else {},
                "raw": raw, "final": final, "runs": runs, "reviews": reviews,
                "artifacts": artifacts, "exports_match_final": export_matches,
                "changed_top_level_fields": [key for key in final if raw.get(key) != final[key]],
                "confidence_all_null": bool(fields) and all(row["confidence"] is None for row in fields),
            })
    groups = sorted({score["group"] for score in raw_scores})
    report = {
        "batch_id": batch_id,
        "status_counts": dict(Counter(row["status"] for row in evidence)),
        "raw_groups": {group: summarize([score for score in raw_scores if score["group"] == group]) for group in groups},
        "final_groups": {group: summarize([score for score in final_scores if score["group"] == group]) for group in groups},
        "raw_scores": raw_scores, "final_scores": final_scores, "documents": evidence,
    }
    (output / f"{batch_id}.local.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return report


def combine_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the latest supplied attempt per sample, retaining attempt counts."""
    selected: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    for report in reports:
        raw = {score["id"]: score for score in report["raw_scores"]}
        final = {score["id"]: score for score in report["final_scores"]}
        for document in report["documents"]:
            sample_id = document["sample_id"]
            selected[sample_id] = (document, raw[sample_id], final[sample_id])
    documents = [entry[0] for entry in selected.values()]
    raw_scores = [entry[1] for entry in selected.values()]
    final_scores = [entry[2] for entry in selected.values()]
    groups = sorted({score["group"] for score in raw_scores})
    return {
        "batch_ids": [report["batch_id"] for report in reports],
        "attempt_status_counts": dict(Counter(
            document["status"] for report in reports for document in report["documents"]
        )),
        "status_counts": dict(Counter(document["status"] for document in documents)),
        "raw_groups": {group: summarize([score for score in raw_scores if score["group"] == group]) for group in groups},
        "final_groups": {group: summarize([score for score in final_scores if score["group"] == group]) for group in groups},
        "documents": documents, "raw_scores": raw_scores, "final_scores": final_scores,
        "export_count": sum(len(document["artifacts"]) for document in documents),
        "all_exports_match_final": bool(documents) and all(
            len(document["exports_match_final"]) == 1 and all(document["exports_match_final"])
            for document in documents
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, action="append")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--manifest", type=Path, default=Path("experimentd/samples.local.json"))
    parser.add_argument("--output", type=Path, default=Path("experimentd/output/liteparse_pipeline_validation"))
    args = parser.parse_args()
    report = combine_reports([
        audit_batch(batch_id, args.config, args.manifest, args.output)
        for batch_id in args.batch
    ])
    (args.output / "validation.local.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({
        "batch_ids": args.batch, "status_counts": report["status_counts"],
        "raw_groups": report["raw_groups"],
        "export_count": report["export_count"],
        "all_exports_match_final": report["all_exports_match_final"],
    }, indent=2))
