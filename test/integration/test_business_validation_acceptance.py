"""R4 acceptance from pinned extraction through review/resume to real outputs."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest

from test.helpers_assertions import require_present

from modules.db.connection import managed_connect, json_loads
from modules.db.repositories import DocumentRepository, ReviewRepository, TaskRunRepository
from modules.resume_manager import ResumeManager
from modules.services.review_schema_version_service import ReviewSchemaVersionService
from modules.services.review_service import ReviewBusinessError, ReviewService, ReviewServiceError
from modules.services.startup_migration_service import initialize_database
from modules.services.ingestion_assignment_service import IngestionAssignmentService
from test.helpers_business_validation_workflow import (
    ACCEPTED_VALUES, SOURCE_VALUES, create_invoice_workflow, offline_invoice_workflows, run_invoice_workflow,
)
from test.helpers_sqlite import TempConfig


def test_repeated_invoice_numbers_export_registered_document_ids_after_resume(tmp_path: Path) -> None:
    """Two accepted documents retain distinct paths through real resume/export."""
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'}})
    initialize_database(config)
    case = create_invoice_workflow(config, tmp_path, filename_template='{invoice_number}_{id}')
    with managed_connect(config) as conn:
        second = IngestionAssignmentService(conn, config).create_batch(
            pipeline_version_id=case['pipeline']['id'], role='operator', source='web', assignment_source='upload',
            files=[{'file_path': str(case['source']), 'original_filename': case['source'].name, 'status': 'queued'}],
            user='operator',
        )
    documents = [case['document'], second['documents'][0]]
    paths: list[Path] = []
    with offline_invoice_workflows() as calls:
        for document in documents:
            paused = run_invoice_workflow(config, {**case, 'document': document})
            assert paused['pipeline_state'] == 'paused'
            with managed_connect(config) as conn:
                service = ReviewService(conn, config)
                review = require_present(ReviewRepository(conn).find_latest_for_document(document['id']))
                service.claim(review['id'], 'operator')
                detail = require_present(service.get_detail(review['id']))
                service.complete(review['id'], 'operator', ACCEPTED_VALUES, expected_revision=detail['review_revision'])
                assert require_present(DocumentRepository(conn).get(document['id']))['status'] == 'completed'
                exports = [file for file in DocumentRepository(conn).list_files(document['id'])
                           if file['file_type'] == 'export_json']
                assert len(exports) == 1
                path = Path(exports[0]['file_path'])
                assert path.name == f"INV-OK_{document['id']}.json"
                paths.append(path)
        assert len(calls) == 2
    assert paths[0] != paths[1]
    assert len(list(case['output'].glob('*'))) == 6
    for path in paths:
        assert json.loads(path.read_text(encoding='utf-8'))['Items'] == ACCEPTED_VALUES['items']


@pytest.mark.parametrize('with_rules', [True, False])
def test_accepted_values_resume_once_and_reach_json_csv_and_named_pdf(tmp_path: Path, with_rules: bool) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'}})
    initialize_database(config)
    case = create_invoice_workflow(config, tmp_path, with_rules=with_rules)
    with offline_invoice_workflows() as extraction_calls:
        paused = run_invoice_workflow(config, case)
        assert paused['pipeline_state'] == 'paused'
        assert not case['output'].exists()
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            review = require_present(ReviewRepository(conn).find_latest_for_document(case['document']['id']))
            service.claim(review['id'], 'operator')
            loaded = require_present(service.get_detail(review['id']))
            if with_rules:
                assert [check['status'] for check in loaded['business_validation']['checks']] == ['failed', 'passed', 'failed']
            else:
                assert loaded['business_validation'] is None
            service.save_draft(review['id'], 'operator', ACCEPTED_VALUES, expected_revision=loaded['review_revision'])

        # Recreate the service/connection as if the web process had restarted.
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            restored = require_present(service.get_detail(review['id']))
            assert restored['metadata']['draft']['corrections'] == ACCEPTED_VALUES
            if with_rules:
                assert all(check['status'] == 'passed' for check in restored['business_validation']['checks'])
                with pytest.raises(ReviewBusinessError, match='blocking'):
                    service.complete(review['id'], 'operator', SOURCE_VALUES, expected_revision=restored['review_revision'])
                assert not case['output'].exists()
            accepted = service.complete(review['id'], 'operator', ACCEPTED_VALUES,
                                        expected_revision=restored['review_revision'])
            assert accepted['resume_triggered']

        assert len(extraction_calls) == 1
        assert not ResumeManager(config).resume_document(case['document']['id'], user='operator')

    output = case['output']
    exported = json.loads((output / 'INV-OK.json').read_text(encoding='utf-8'))
    assert exported['Invoice number'] == 'INV-OK'
    assert exported['Items'] == ACCEPTED_VALUES['items']
    assert exported['Subtotal'] == 50
    with (output / 'INV-OK.csv').open(newline='', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert [row['item_line_total'] for row in rows] == ['30', '20']
    assert {row['Invoice number'] for row in rows} == {'INV-OK'}
    assert {row['Subtotal'] for row in rows} == {'50'}
    assert (output / 'INV-OK.pdf').read_bytes() == case['source'].read_bytes()
    assert sorted(file.name for file in output.iterdir()) == ['INV-OK.csv', 'INV-OK.json', 'INV-OK.pdf']
    with managed_connect(config) as conn:
        runs = TaskRunRepository(conn).list_by_document(case['document']['id'])
        assert [run['task_key'] for run in runs] == ['extract', 'review', 'json', 'csv', 'pdf', 'cleanup_task']
        assert all(run['status'] == 'completed' for run in runs)
        assert {run['pipeline_version_id'] for run in runs} == {case['pipeline']['id']}
        assert require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'completed'
        files = DocumentRepository(conn).list_files(case['document']['id'])
        assert {'export_json', 'export_csv'} <= {file['file_type'] for file in files}
        metadata = require_present(ReviewService(conn, config).get_detail(review['id']))['metadata']
        if with_rules:
            report = metadata['business_validation']['accepted']
            assert report['schema_version_id'] == case['schema_version']['id']
            assert report['schema_hash'] == case['schema_version']['content_hash']
            assert all(check['status'] == 'passed' for check in report['checks'])


def test_new_publication_does_not_change_a_paused_invoices_rules_or_resume_version(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'}})
    initialize_database(config)
    case = create_invoice_workflow(config, tmp_path)
    with offline_invoice_workflows() as extraction_calls:
        paused = run_invoice_workflow(config, case)
        with managed_connect(config) as conn:
            forms = ReviewSchemaVersionService(conn)
            schema = deepcopy(case['schema'])
            schema['business_validation']['rules'][1]['tolerance'] = '999'
            saved = forms.save_draft(case['form']['id'], expected_revision=2, schema=schema, user='admin')
            new = forms.publish(case['form']['id'], expected_revision=saved['revision'], user='admin')['version']
            service = ReviewService(conn, config)
            service.claim(paused['review_item_id'], 'operator')
            detail = require_present(service.get_detail(paused['review_item_id']))
            assert detail['business_validation']['schema_version_id'] != new['id']
            assert detail['business_validation']['has_blocking_findings']
            service.complete(paused['review_item_id'], 'operator', ACCEPTED_VALUES,
                             expected_revision=detail['review_revision'])
            runs = TaskRunRepository(conn).list_by_document(case['document']['id'])
            assert {run['pipeline_version_id'] for run in runs} == {case['pipeline']['id']}
        assert len(extraction_calls) == 1


def test_extended_rules_recover_after_acceptance_interruption_and_export_once(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'}})
    initialize_database(config)
    case = create_invoice_workflow(config, tmp_path, extended_rules=True)
    with offline_invoice_workflows(case['source_values']) as extraction_calls:
        paused = run_invoice_workflow(config, case)
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(paused['review_item_id'], 'operator')
            detail = require_present(service.get_detail(paused['review_item_id']))
            assert [check['status'] for check in detail['business_validation']['checks']] == ['failed', 'passed', 'failed', 'failed', 'failed']
            corrected = case['accepted_values']
            checked = service.revalidate(paused['review_item_id'], 'operator', corrected,
                                         expected_revision=detail['review_revision'], request_revision=1)
            assert all(check['status'] == 'passed' for check in checked['business_validation']['checks'])
            service.complete(paused['review_item_id'], 'operator', corrected, expected_revision=detail['review_revision'], trigger_resume=False)
            assert require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'review_completed'
        assert not case['output'].exists()
        assert ResumeManager(config).resume_document(case['document']['id'], user='operator')
        assert not ResumeManager(config).resume_document(case['document']['id'], user='operator')
        assert len(extraction_calls) == 1
    payload = json.loads((case['output'] / 'INV-OK.json').read_text(encoding='utf-8'))
    assert payload['issued'] == '2026-10-01' and payload['due'] == '2026-10-30'
    assert payload['po_number'] == 'PO-OK'
    assert len(list(case['output'].glob('*'))) == 3


def test_two_tabs_cannot_accept_the_same_revision_twice(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'}})
    initialize_database(config)
    case = create_invoice_workflow(config, tmp_path)
    with offline_invoice_workflows() as extraction_calls:
        paused = run_invoice_workflow(config, case)
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(paused['review_item_id'], 'operator')
            revision = require_present(service.get_detail(paused['review_item_id']))['review_revision']
        barrier = Barrier(2)
        original_report = ReviewService._business_report

        def report_together(service: ReviewService, snapshot: dict, values: dict) -> dict:
            report = original_report(service, snapshot, values)
            assert report is not None
            barrier.wait(timeout=10)
            return report

        def accept() -> str:
            with managed_connect(config) as conn:
                try:
                    ReviewService(conn, config).complete(paused['review_item_id'], 'operator', ACCEPTED_VALUES,
                                                         expected_revision=revision, trigger_resume=False)
                    return 'accepted'
                except ReviewServiceError:
                    return 'conflict'

        with patch.object(ReviewService, '_business_report', report_together), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: accept(), range(2)))
        assert sorted(results) == ['accepted', 'conflict']
        assert not case['output'].exists()
        assert ResumeManager(config).resume_document(case['document']['id'], user='operator')
        assert len(extraction_calls) == 1
    with managed_connect(config) as conn:
        assert conn.execute("SELECT count(*) FROM audit_events WHERE event_type='review_completed'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM task_runs WHERE task_key='json'").fetchone()[0] == 1


@pytest.mark.parametrize('failure', ['evaluator', 'row_limit'])
def test_failed_evaluation_never_releases_exports_and_can_be_corrected(tmp_path: Path, failure: str) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'synthetic-unused-value'}})
    initialize_database(config)
    case = create_invoice_workflow(config, tmp_path)
    source = deepcopy(SOURCE_VALUES)
    if failure == 'row_limit':
        source['items'] = [deepcopy(source['items'][0]) for _ in range(1001)]
    with offline_invoice_workflows(source) as extraction_calls:
        if failure == 'evaluator':
            with patch('modules.services.business_validation._evaluate_rule', side_effect=RuntimeError('synthetic private detail')):
                paused = run_invoice_workflow(config, case)
        else:
            paused = run_invoice_workflow(config, case)
        assert not case['output'].exists()
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            gate = require_present(service.get_detail(paused['review_item_id']))['metadata']['business_validation']['gate']
            assert gate['has_blocking_findings']
            assert any(check['status'] == 'error' for check in gate['checks'])
            assert 'synthetic private detail' not in str(gate)
            service.claim(paused['review_item_id'], 'operator')
            revision = require_present(service.get_detail(paused['review_item_id']))['review_revision']
            if failure == 'evaluator':
                with patch('modules.services.business_validation._evaluate_rule', side_effect=RuntimeError('synthetic private detail')):
                    with pytest.raises(ReviewBusinessError, match='blocking'):
                        service.complete(paused['review_item_id'], 'operator', ACCEPTED_VALUES, expected_revision=revision)
            else:
                with pytest.raises(ReviewBusinessError, match='blocking'):
                    service.complete(paused['review_item_id'], 'operator', source, expected_revision=revision)
            assert not case['output'].exists()
            service.complete(paused['review_item_id'], 'operator', ACCEPTED_VALUES, expected_revision=revision)
        assert len(extraction_calls) == 1
    assert sorted(file.name for file in case['output'].iterdir()) == ['INV-OK.csv', 'INV-OK.json', 'INV-OK.pdf']
