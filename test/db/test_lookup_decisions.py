"""Verify lookup decisions through SQLite upgrades, retries and retention."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

from modules.db.connection import managed_connect
from modules.db.repositories import (
    AuditRepository,
    BatchRepository,
    DocumentRepository,
    ExtractionRepository,
    LookupKey,
)
from modules.db.schema_version import SCHEMA_VERSION
from modules.services.csv_reference_lookup import LookupConfig, LookupEvaluation, evaluate_reference
from modules.services.lookup_decision_service import LookupConflictError, LookupDecisionService
from modules.services.pipeline_cleanup_service import PipelineCleanupService
from modules.services.startup_migration_service import initialize_database
from modules.services.startup_service import StartupReadinessError, verify_database_schema
from test.helpers_sqlite import TempConfig, seed_pipeline


@pytest.fixture
def state(tmp_path: Path) -> tuple[TempConfig, LookupKey, str, LookupConfig]:
    config = TempConfig(tmp_path / "app.sqlite3")
    initialize_database(config)
    version = seed_pipeline(config)
    with managed_connect(config) as conn:
        batch = BatchRepository(conn).create(
            source="test", status="completed", pipeline_template_id=version["template_id"],
            pipeline_version_id=version["id"],
        )
        document = DocumentRepository(conn).create_root(
            batch_id=batch["id"], file_path="synthetic.pdf", original_filename="synthetic.pdf",
            status="completed", pipeline_template_id=version["template_id"],
            pipeline_version_id=version["id"],
        )
        extraction = ExtractionRepository(conn).save_result(
            document_id=document["id"], provider="test", data={"tax": "001"},
        )
    source = tmp_path / "reference.csv"
    source.write_text("Tax,ID\n001,00042\n001,00043\n002,00044\n", encoding="utf-8")
    settings = LookupConfig.model_validate({
        "reference_file": str(source),
        "clauses": [{"field": "tax", "column": "Tax"}],
        "returns": [{"field": "supplier_id", "column": "ID"}],
    })
    return config, LookupKey(document["id"], version["id"], "supplier"), extraction["id"], settings


def test_schema_10_upgrade_preserves_existing_documents_and_extraction(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, _ = state
    verify_database_schema(config)
    with managed_connect(config) as conn:
        conn.execute("DROP TABLE lookup_decisions")
        conn.execute("UPDATE schema_migrations SET version=10 WHERE version=?", (SCHEMA_VERSION,))
    with pytest.raises(StartupReadinessError, match="lookup_decisions"):
        verify_database_schema(config)

    initialize_database(config)
    initialize_database(config)
    verify_database_schema(config)
    with managed_connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM lookup_decisions").fetchone()[0] == 0
        assert DocumentRepository(conn).get(key.document_id)
        assert ExtractionRepository(conn).get_result(extraction_id)
        values = {"tax": "001", "manually_corrected": None}
        assert LookupDecisionService(conn).effective_data(
            key.document_id, key.pipeline_version_id, extraction_id, values,
        ) == values


def test_retry_after_restart_reuses_decision_without_reading_register(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, settings = state

    def evaluate() -> LookupEvaluation:
        return evaluate_reference(settings, {"tax": "002"})

    with managed_connect(config) as conn:
        initial = LookupDecisionService(conn).record_initial(key, extraction_id, evaluate)
    Path(settings.reference_file).unlink()
    initialize_database(config)
    with managed_connect(config) as conn:
        service = LookupDecisionService(conn)
        assert service.record_initial(key, extraction_id, evaluate) == initial
        values = {"tax": "002"}
        assert service.effective_data(key.document_id, key.pipeline_version_id, extraction_id, values) == {
            "tax": "002", "supplier_id": "00044",
        }
        assert values == {"tax": "002"}
        with pytest.raises(LookupConflictError, match="conflicts"):
            service.effective_data(
                key.document_id, key.pipeline_version_id, extraction_id,
                {"supplier_id": None},
            )


def test_concurrent_initial_evaluations_reuse_the_winner(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, settings = state
    gate = Barrier(2, timeout=5)

    def record() -> str:
        def evaluate() -> LookupEvaluation:
            gate.wait()
            return evaluate_reference(settings, {"tax": "002"})

        with managed_connect(config) as conn:
            return LookupDecisionService(conn).record_initial(key, extraction_id, evaluate).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(record), executor.submit(record)
        assert first.result() == second.result()
    with managed_connect(config) as conn:
        assert conn.execute("SELECT COUNT(*) FROM lookup_decisions").fetchone()[0] == 1


def test_concurrent_selection_commits_exactly_one_revision_and_audit(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, settings = state
    with managed_connect(config) as conn:
        initial = LookupDecisionService(conn).record_initial(
            key, extraction_id, lambda: evaluate_reference(settings, {"tax": "001"}),
        )
    assert initial.state == "pending"
    gate = Barrier(2, timeout=5)

    def select(record: int) -> int | None:
        with managed_connect(config) as conn:
            gate.wait()
            try:
                return LookupDecisionService(conn).resolve(
                    key, expected_revision=1, record_number=record,
                    actor="operator", reason="Synthetic invoice match",
                ).selected_record_number
            except LookupConflictError:
                return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(select, [1, 2]))
    assert results.count(None) == 1
    with managed_connect(config) as conn:
        decision = LookupDecisionService(conn).current(key)
        assert decision is not None and decision.revision == 2
        assert decision.supersedes_id == initial.id
        assert decision.evaluation.source_sha256 == initial.evaluation.source_sha256
        assert decision.selected_record_number in results
        assert decision.reason == "Synthetic invoice match"
        assert conn.execute("SELECT COUNT(*) FROM lookup_decisions").fetchone()[0] == 2
        events = AuditRepository(conn).list_for_document(key.document_id)
        assert [event["event_type"] for event in events] == ["lookup_resolved"]
        assert "Synthetic invoice match" not in events[0]["event_json"]
        assert "0004" not in events[0]["event_json"]


def test_audit_failure_rolls_back_resolution_inside_existing_transaction(
    state: tuple[TempConfig, LookupKey, str, LookupConfig], monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, key, extraction_id, settings = state
    with managed_connect(config) as conn:
        service = LookupDecisionService(conn)
        initial = service.record_initial(key, extraction_id, lambda: evaluate_reference(settings, {"tax": "001"}))
        append = AuditRepository.append_uncommitted

        def fail_after_audit(repo: AuditRepository, **kwargs: Any) -> None:
            append(repo, **kwargs)
            raise RuntimeError("Injected audit failure")

        monkeypatch.setattr(AuditRepository, "append_uncommitted", fail_after_audit)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE documents SET original_filename='kept.pdf' WHERE id=?", (key.document_id,))
        with pytest.raises(RuntimeError, match="Injected"):
            service.resolve(key, expected_revision=1, record_number=1, actor="operator", reason="Confirmed")
        assert conn.in_transaction
        assert service.current(key) == initial
        assert AuditRepository(conn).list_for_document(key.document_id) == []
    with managed_connect(config) as conn:
        assert conn.execute("SELECT original_filename FROM documents").fetchone()[0] == "kept.pdf"
        assert conn.execute("SELECT COUNT(*) FROM lookup_decisions").fetchone()[0] == 1


def test_revisions_optional_skip_and_truncated_candidate_rules(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, settings = state
    with managed_connect(config) as conn:
        service = LookupDecisionService(conn)
        initial = service.record_initial(
            key, extraction_id, lambda: evaluate_reference(settings, {"tax": "001"}, max_candidates=1),
        )
        with pytest.raises(ValueError, match="complete set"):
            service.resolve(key, expected_revision=1, record_number=1, actor="operator", reason="Confirmed")
        with pytest.raises(ValueError, match="required"):
            service.resolve(key, expected_revision=1, record_number=None, actor="operator", reason="Missing")

        Path(settings.reference_file).write_text("Tax,ID\n001,X-001\n", encoding="utf-8")
        new_evaluation = evaluate_reference(settings, {"tax": "001"})
        with pytest.raises(ValueError, match="requires a reason"):
            service.record_reevaluation(key, new_evaluation, expected_revision=1, actor="operator")
        adopted = service.record_reevaluation(
            key, new_evaluation, expected_revision=1, actor="operator", adoption_reason="Register repaired",
        )
        assert adopted.supersedes_id == initial.id
        assert adopted.returned_values() == {"supplier_id": "X-001"}
        assert adopted.evaluation.source_sha256 != initial.evaluation.source_sha256
        assert conn.execute(
            "SELECT id FROM lookup_decisions WHERE id=?", (initial.id,),
        ).fetchone() is not None

        optional = settings.model_copy(update={"required": False})
        optional_key = key._replace(task_key="optional")
        service.record_initial(optional_key, extraction_id, lambda: evaluate_reference(optional, {"tax": "missing"}))
        skipped = service.resolve(
            optional_key, expected_revision=1, record_number=None,
            actor="operator", reason="Optional value unavailable",
        )
        assert skipped.state == "skipped"
        assert skipped.returned_values() == {}


def test_lookup_projection_scopes_task_keys_extractions_and_children(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, settings = state
    with managed_connect(config) as conn:
        parent = DocumentRepository(conn).get(key.document_id)
        assert parent is not None
        child = DocumentRepository(conn).create_child(
            batch_id=parent["batch_id"], parent_document_id=key.document_id,
            file_path="synthetic-child.pdf", status="completed",
            pipeline_template_id=parent["pipeline_template_id"], pipeline_version_id=key.pipeline_version_id,
        )
        child_extraction_id = ExtractionRepository(conn).save_result(
            document_id=child["id"], provider="test", data={"tax": "001"},
        )["id"]
        service = LookupDecisionService(conn)
        with pytest.raises(LookupConflictError, match="extraction"):
            service.record_initial(key, child_extraction_id, lambda: evaluate_reference(settings, {"tax": "001"}))
        service.record_initial(key, extraction_id, lambda: evaluate_reference(settings, {"tax": "002"}))
        second = LookupConfig.model_validate({
            **settings.model_dump(), "returns": [{"field": "another_id", "column": "ID"}],
        })
        service.record_initial(
            key._replace(task_key="second"), extraction_id, lambda: evaluate_reference(second, {"tax": "002"}),
        )
        child_key = key._replace(document_id=child["id"])
        service.record_initial(
            child_key, child_extraction_id, lambda: evaluate_reference(settings, {"tax": "001"}),
        )
        service.resolve(child_key, expected_revision=1, record_number=1, actor="operator", reason="Confirmed")
        assert service.effective_data(key.document_id, key.pipeline_version_id, extraction_id, {}) == {
            "supplier_id": "00044", "another_id": "00044",
        }
        assert service.effective_data(child["id"], key.pipeline_version_id, child_extraction_id, {}) == {
            "supplier_id": "00042",
        }


def test_retention_preview_tracks_and_deletes_all_lookup_revisions(
    state: tuple[TempConfig, LookupKey, str, LookupConfig],
) -> None:
    config, key, extraction_id, settings = state
    with managed_connect(config) as conn:
        service = LookupDecisionService(conn)
        service.record_initial(key, extraction_id, lambda: evaluate_reference(settings, {"tax": "001"}))
        service.resolve(key, expected_revision=1, record_number=2, actor="operator", reason="Matched")
        document = DocumentRepository(conn).get(key.document_id)
        assert document is not None
        cleanup = PipelineCleanupService(conn)
        for query in (
            "UPDATE batches SET updated_at=?", "UPDATE documents SET updated_at=?",
            "UPDATE extraction_results SET created_at=?",
        ):
            conn.execute(query, ("2000-01-01T00:00:00+00:00",))
        preview = cleanup.preview(document["pipeline_template_id"], cutoff_date="2001-01-01", user="admin")
        assert preview["counts"]["lookup_decisions"] == 0
        assert preview["excluded"]["recent_activity"]["batches"] == 1
        conn.execute("UPDATE lookup_decisions SET created_at='2000-01-01T00:00:00+00:00'")
        preview = cleanup.preview(document["pipeline_template_id"], cutoff_date="2001-01-01", user="admin")
        assert preview["counts"]["lookup_decisions"] == 2
        result = cleanup.cleanup(
            document["pipeline_template_id"], preview_id=preview["preview_id"],
            confirmation_name=preview["template_name"], user="admin",
        )
        assert result["deleted"]["lookup_decisions"] == 2
        assert service.current(key) is None
        assert AuditRepository(conn).list_for_document(key.document_id)[0]["event_type"] == "lookup_resolved"
