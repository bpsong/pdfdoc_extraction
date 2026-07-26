"""Unit tests for operator pipeline-selection state."""

import pytest

from modules.services.operator_pipeline_view_models import (
    can_start_processing,
    multipart_selection_fields,
    pinned_pipeline_label,
    reconcile_selection,
)


def test_selection_starts_empty_and_stale_refresh_never_chooses_replacement():
    available = [
        {"pipeline_version_id": "v1"},
        {"pipeline_version_id": "v2"},
    ]
    assert reconcile_selection(None, available) is None
    assert reconcile_selection("v1", available) == "v1"
    assert reconcile_selection("gone", available) is None


def test_button_eligibility_and_one_batch_multipart_contract():
    files = [{"name": "one.pdf", "error": ""}, {"name": "two.pdf", "error": ""}]
    assert not can_start_processing(
        files, selected_version_id=None, uploading=False
    )
    assert can_start_processing(
        files, selected_version_id="v1", uploading=False
    )
    assert not can_start_processing(
        [*files, {"name": "bad.txt", "error": "PDF only"}],
        selected_version_id="v1",
        uploading=False,
    )
    assert multipart_selection_fields("v1", ["one.pdf", "two.pdf"]) == [
        ("pipeline_version_id", "v1"),
        ("files", "one.pdf"),
        ("files", "two.pdf"),
    ]
    with pytest.raises(ValueError):
        multipart_selection_fields("", ["one.pdf"])


def test_pinned_labels_distinguish_exact_and_migration_derived_identity():
    assert pinned_pipeline_label(
        {
            "name": "Invoice",
            "template_key": "invoice",
            "version_number": 3,
            "historical": False,
        }
    ) == "Invoice (invoice, version 3)"
    assert pinned_pipeline_label({"historical": True}) == (
        "Historical migrated pipeline"
    )
