"""Synthetic checks for deterministic expansion, cohorts and geometry coverage."""

from copy import deepcopy
from pathlib import Path

import pytest

from experimentd.compare_methods import score_method
from experimentd.evaluate import score_sample, summarize, value_matches
from experimentd.extract_invoice import HEADER_FIELDS, ITEM_FIELDS, save_json
from experimentd.glm_comparison import canonical_invoice
from experimentd.prepare_expansion import select_additional
from experimentd.report_expanded import publish, statistics
from experimentd.test_experiment import synthetic_reference


def test_seeded_selection_is_stable_unique_and_excludes_originals() -> None:
    paths = [Path(f"synthetic_{i}.pdf") for i in range(25)]
    original = set(paths[:3])
    first = select_additional(paths, original, 17)
    assert first == select_additional(list(reversed(paths)), original, 17)
    assert len(set(first)) == 17
    assert not original.intersection(first)


def test_ordered_selection_and_insufficient_sources() -> None:
    paths = [Path("c.pdf"), Path("a.pdf"), Path("b.pdf")]
    assert select_additional(paths, {Path("a.pdf")}, 2, randomize=False) == [Path("b.pdf"), Path("c.pdf")]
    with pytest.raises(ValueError):
        select_additional(paths, set(paths), 1)


def test_unreviewed_geometry_is_excluded_without_affecting_value_score() -> None:
    reference = synthetic_reference()
    reference["geometry_reviewed"] = False
    data = {name: reference["fields"][name]["value"] for name in HEADER_FIELDS}
    data["line_items"] = [{name: row[name]["value"] for name in ITEM_FIELDS} for row in reference["line_items"]]
    result = score_sample(reference, canonical_invoice(data, {}, [1]), {"pages": []})
    summary = summarize([result])
    assert summary["overall_accuracy"]["correct"] == 10
    assert summary["location_accuracy"]["total"] == 0
    assert summary["value_and_location_accuracy"]["total"] == 0
    assert summary["complete_invoice_accuracy"]["correct"] == 1


def test_cohorts_include_failures_and_extra_rows_in_complete_invoice_score(tmp_path: Path) -> None:
    first = synthetic_reference()
    first["cohort"] = "original"
    second = deepcopy(first)
    second.update(id="additional", cohort="additional", geometry_reviewed=False)
    data = {name: first["fields"][name]["value"] for name in HEADER_FIELDS}
    data["line_items"] = [{name: row[name]["value"] for name in ITEM_FIELDS} for row in first["line_items"]]
    data["line_items"].append(deepcopy(data["line_items"][0]))
    directory = tmp_path / "glm_task" / first["id"]
    save_json(directory / "invoice.json", canonical_invoice(data, {}, [1]))
    save_json(directory / "parsed.json", {"pages": []})
    save_json(directory / "run.json", {"elapsed_seconds": 1, "total_load_seconds": 0,
                                      "total_inference_excluding_load_seconds": 1, "model_calls": []})
    report = score_method([first, second], tmp_path, "glm_task")
    assert report["overall"]["overall_accuracy"] == {"correct": 10, "total": 25, "percent": 40.0}
    assert report["overall"]["complete_invoice_accuracy"]["correct"] == 0
    assert report["cohorts"]["additional"]["overall"]["sample_count"] == 1
    assert report["cohorts"]["original"]["overall"]["location_accuracy"] is None
    assert report["failures"] == ["additional"]


def test_macro_accuracy_weights_invoices_equally_and_reports_missing_rows() -> None:
    reference = synthetic_reference()
    data = {name: reference["fields"][name]["value"] for name in HEADER_FIELDS}
    data["line_items"] = [{name: row[name]["value"] for name in ITEM_FIELDS} for row in reference["line_items"]]
    invoice = canonical_invoice(data, {}, [1])
    first = score_sample(reference, invoice, {"pages": []})
    larger = deepcopy(reference)
    larger["line_items"].append(deepcopy(larger["line_items"][0]))
    second = score_sample(larger, invoice, {"pages": []})
    for sample in (first, second):
        sample["timing"] = None
    stats = statistics([first, second])
    assert stats["overall_accuracy"]["percent"] == 80.0
    assert stats["macro_invoice_percent"] == 83.33
    assert stats["missing_rows"] == 1
    assert stats["complete_invoice_accuracy"]["correct"] == 1


def test_public_report_does_not_copy_private_reference_values(tmp_path: Path) -> None:
    reference = synthetic_reference()
    reference.update(cohort="additional", geometry_reviewed=False)
    reference["fields"]["customer_name"]["value"] = "PRIVATE_REFERENCE_CUSTOMER"
    manifest = tmp_path / "samples.local.json"
    save_json(manifest, {"samples": [reference], "selection": "Synthetic selection."})
    destination = tmp_path / "report.md"
    publish(manifest, tmp_path / "output", destination)
    report = destination.read_text(encoding="utf-8")
    assert "PRIVATE_REFERENCE_CUSTOMER" not in report
    assert "Additional samples only" in report
    assert "Failures:" in report
    assert "Accuracy by structured field" in report
    assert "| description | 0/1 | 0/1 |" in report


def test_cjk_line_wraps_are_ignored_but_changed_characters_are_not() -> None:
    assert value_matches("description", "松夏牌 饭锅", "松夏牌饭锅")
    assert value_matches("description", "松夏牌\n饭锅", "松夏牌饭锅")
    assert not value_matches("description", "松夏牌饭锅", "松下牌饭锅")
