"""Synthetic safeguards for honest raw/final and failed-attempt reporting."""

from copy import deepcopy
from typing import Any

import pytest

from experimentd.evaluate import score_sample
from experimentd.inspect_standard_task import combine_reports, wrap_values


def _report(batch: str, status: str, wrong: bool) -> dict[str, Any]:
    data = {
        "customer_name": "Synthetic Customer",
        "supplier_name": "Synthetic Supplier",
        "invoice_date": "2026-01-02",
        "invoice_number": "0001",
        "invoice_total": 12.0,
        "line_items": [{"description": "Synthetic widget",
                        "unit_of_measure": None, "quantity": 2.0,
                        "unit_price": 6.0, "line_total": 12.0}],
    }
    wrapped = wrap_values(data)
    reference = {
        "id": "synthetic", "group": "synthetic", "geometry_reviewed": False,
        "fields": {key: value for key, value in wrapped.items()
                   if key != "line_items"},
        "line_items": wrapped["line_items"],
    }
    raw = deepcopy(data)
    if wrong:
        raw["invoice_number"] = "0002"
    return {
        "batch_id": batch,
        "raw_scores": [score_sample(reference, wrap_values(raw), {"pages": []})],
        "final_scores": [score_sample(reference, wrapped, {"pages": []})],
        "documents": [{
            "sample_id": "synthetic", "status": status,
            "artifacts": ["synthetic-export"] if status == "completed" else [],
            "exports_match_final": [True] if status == "completed" else [],
        }],
    }


def test_latest_attempt_retains_failures_without_inflating_raw_accuracy() -> None:
    report = combine_reports([
        _report("initial", "failed", False),
        _report("replay", "completed", True),
    ])
    assert report["attempt_status_counts"] == {"failed": 1, "completed": 1}
    assert report["status_counts"] == {"completed": 1}
    assert report["raw_groups"]["synthetic"]["overall_accuracy"]["correct"] == 9
    assert report["final_groups"]["synthetic"]["overall_accuracy"]["correct"] == 10
    assert report["export_count"] == 1
    assert report["all_exports_match_final"] is True


@pytest.mark.parametrize("reports", [[], [_report("failed", "failed", True)]])
def test_missing_exports_cannot_be_reported_as_verified(
    reports: list[dict[str, Any]],
) -> None:
    assert combine_reports(reports)["all_exports_match_final"] is False


def test_duplicate_or_mismatched_exports_fail_verification() -> None:
    report = _report("completed", "completed", False)
    report["documents"][0]["exports_match_final"] = [True, True]
    assert combine_reports([report])["all_exports_match_final"] is False
    report["documents"][0]["exports_match_final"] = [False]
    assert combine_reports([report])["all_exports_match_final"] is False
