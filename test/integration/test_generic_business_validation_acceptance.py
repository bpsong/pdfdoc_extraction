"""Different document types retain the full versioned review/release contract."""

import json
from pathlib import Path

import pytest

from modules.db.connection import managed_connect
from modules.db.repositories import DocumentRepository, ReviewRepository
from modules.services.review_service import ReviewBusinessError, ReviewService
from modules.services.startup_migration_service import initialize_database
from modules.services.startup_service import StartupReadinessError, verify_business_validation_compatibility
from test.helpers_assertions import require_present
from test.helpers_business_validation_workflow import offline_invoice_workflows, run_invoice_workflow
from test.helpers_generic_business_validation import create_generic_workflow
from test.helpers_sqlite import TempConfig


@pytest.mark.parametrize('kind', ['shipping', 'insurance', 'invoice'])
def test_document_types_publish_pin_block_correct_resume_and_export(tmp_path: Path, kind: str) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'unused-synthetic'}})
    initialize_database(config)
    case = create_generic_workflow(config, tmp_path, kind)
    with offline_invoice_workflows(case['source_values']) as calls:
        paused = run_invoice_workflow(config, case)
        assert paused['pipeline_state'] == 'paused'
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            review = require_present(ReviewRepository(conn).find_latest_for_document(case['document']['id']))
            service.claim(review['id'], 'operator')
            detail = require_present(service.get_detail(review['id']))
            assert detail['business_validation']['has_blocking_findings']
            original_report = json.dumps(detail['business_validation'], sort_keys=True)
            checked = service.revalidate(review['id'], 'operator', {}, expected_revision=detail['review_revision'], request_revision=1)
            assert checked['business_validation_labels']['line_amount:v1'] == 'Multiply two row fields'
            assert json.dumps(checked['business_validation'], sort_keys=True) == original_report
            with pytest.raises(ReviewBusinessError, match='blocking'):
                service.complete(review['id'], 'operator', {}, expected_revision=detail['review_revision'])
            assert not case['output'].exists()
            accepted = service.complete(review['id'], 'operator', case['accepted_values'], expected_revision=detail['review_revision'])
            assert accepted['resume_triggered']
            assert require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'completed'
            files = DocumentRepository(conn).list_files(case['document']['id'])
            assert {'export_json', 'export_csv'} <= {file['file_type'] for file in files}
        assert len(calls) == 1
    exported = json.loads(next(case['output'].glob('*.json')).read_text(encoding='utf-8'))
    assert exported == case['accepted_values']
    assert len(list(case['output'].iterdir())) == 3
    assert next(case['output'].glob('*.pdf')).read_bytes() == case['source'].read_bytes()


def test_release_without_new_validator_refuses_its_published_forms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.services import business_validation_registry as registry
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'unused-synthetic'}})
    initialize_database(config)
    create_generic_workflow(config, tmp_path, 'shipping')
    monkeypatch.setattr(registry, 'APPROVED_VALIDATORS', {
        key: value for key, value in registry.APPROVED_VALIDATORS.items() if key != 'compare_number:v1'})
    with pytest.raises(StartupReadinessError):
        verify_business_validation_compatibility(config)


@pytest.mark.parametrize('kind', ['shipping', 'insurance', 'invoice'])
def test_no_rules_forms_keep_drafts_completion_and_real_exports(tmp_path: Path, kind: str) -> None:
    config = TempConfig(tmp_path / 'state.sqlite3', {'pipeline_secrets': {'synthetic-extract': 'unused-synthetic'}})
    initialize_database(config)
    case = create_generic_workflow(config, tmp_path, kind, with_rules=False)
    assert case['schema_version']['format_version'] == 1
    assert 'business_validation' not in case['schema_version']['schema']
    with offline_invoice_workflows(case['source_values']) as calls:
        paused = run_invoice_workflow(config, case)
        assert paused['pipeline_state'] == 'paused'
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            service.claim(paused['review_item_id'], 'operator')
            detail = require_present(service.get_detail(paused['review_item_id']))
            assert detail['business_validation'] is None
            service.save_draft(paused['review_item_id'], 'operator', case['accepted_values'])
        with managed_connect(config) as conn:
            service = ReviewService(conn, config)
            restored = require_present(service.get_detail(paused['review_item_id']))
            assert restored['metadata']['draft']['corrections'] == case['accepted_values']
            assert restored['business_validation'] is None
            assert service.complete(paused['review_item_id'], 'operator', case['accepted_values'])['resume_triggered']
            completed = require_present(service.get_detail(paused['review_item_id']))
            assert completed['business_validation'] is None
            assert 'business_validation' not in completed['metadata']
            assert require_present(DocumentRepository(conn).get(case['document']['id']))['status'] == 'completed'
        assert len(calls) == 1
    assert json.loads(next(case['output'].glob('*.json')).read_text(encoding='utf-8')) == case['accepted_values']
    assert len(list(case['output'].iterdir())) == 3
