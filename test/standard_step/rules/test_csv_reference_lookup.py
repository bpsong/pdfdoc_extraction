"""Exercise deterministic lookup without modifying the reference register."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from modules.services.csv_reference_lookup import (
    LookupConfig,
    ReferenceChangedError,
    ReferenceDataError,
    evaluate_reference,
)


def test_mixed_and_clauses_preserve_exact_returned_text(tmp_path: Path) -> None:
    config = LookupConfig.model_validate({
        "reference_file": "register.csv",
        "clauses": [
            {"field": "tax", "column": "Tax"},
            {"field": "name", "column": "Name", "mode": "case_insensitive"},
            {"field": "number", "column": "Number", "mode": "numeric"},
        ],
        "returns": [{"column": "ID", "field": "supplier_id"}, {"column": "Label", "field": "label"}],
    })
    path = tmp_path / "register.csv"
    raw = (
        '\ufeffTax,Name,Number,ID,Label\r\n'
        '00123,Straße,+01.00,00042,"One, Inc.\nSecond line"\r\n'
        '123,STRASSE,1,OTHER,Other\r\n'
        '00123,Another,1,OTHER,Other\r\n'
        '00123,STRASSE,2,OTHER,Other\r\n'
    ).encode("utf-8")
    path.write_bytes(raw)
    config_path = tmp_path / "config.yaml"
    values = {"tax": " 00123 ", "name": "STRASSE", "number": 1}
    result = evaluate_reference(config, values, config_path=config_path)

    assert result == evaluate_reference(config, values, config_path=config_path)
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.match_count == 1
    assert result.disposition == "matched"
    assert result.inputs[1].normalized == "strasse"
    assert result.candidates[0].complete_values() == {
        "supplier_id": "00042", "label": "One, Inc.\nSecond line",
    }
    assert values["tax"] == " 00123 "
    assert path.read_bytes() == raw


def config_for(path: Path, **extra: object) -> LookupConfig:
    return LookupConfig.model_validate({
        "reference_file": str(path),
        "clauses": [{"field": "source", "column": "Key"}],
        "returns": [{"column": "ID", "field": "id_from_reference"}],
        **extra,
    })


def test_case_opt_in_and_bounded_candidate_evidence(tmp_path: Path) -> None:
    path = tmp_path / "register.csv"
    path.write_text("Key,ID,Private\nACME,Sup-007,x\nAcme,Sup-007,y\nacme,Extra-001,z\n", encoding="utf-8")
    sensitive = evaluate_reference(config_for(path), {"source": "Acme"})
    insensitive = config_for(
        path, clauses=[{"field": "source", "column": "Key", "mode": "case_insensitive"}],
    )
    result = evaluate_reference(insensitive, {"source": "Acme"}, max_candidates=2)

    assert sensitive.candidates[0].record_number == 2
    assert result.match_count == 3
    assert result.disposition == "pending"
    assert [candidate.record_number for candidate in result.candidates] == [1, 2]
    assert result.candidates[0].matched_columns == {"Key": "ACME"}
    assert result.candidates[0].values == {"id_from_reference": "Sup-007"}


@pytest.mark.parametrize(("value", "issue"), [
    (None, "missing"), ("  ", "blank"), (True, "invalid"), (float("inf"), "invalid"),
    ("1e3", "invalid"), ("$1000", "invalid"), ("1,000", "invalid"),
])
def test_invalid_numeric_document_values_use_no_match_policy(
    tmp_path: Path, value: object, issue: str,
) -> None:
    path = tmp_path / "register.csv"
    path.write_text("Key,ID\n1000,a\n ,b\n", encoding="utf-8")
    config = config_for(path, clauses=[{"field": "source", "column": "Key", "mode": "numeric"}],
                        required=False, on_no_match="continue")
    result = evaluate_reference(config, {"source": value})
    assert (result.match_count, result.disposition, result.inputs[0].issue) == (0, "skipped", issue)


@pytest.mark.parametrize(("raw", "error"), [
    (b"Key,ID\na,\xff\n", "UTF-8"),
    (b"Key,Key,ID\na,a,x\n", "unique"),
    (b"Key,Other\na,x\n", "missing"),
    (b"Key,ID\na,x,extra\n", "column count"),
    (b'Key,ID\na,"unclosed\n', "malformed"),
    (b"Key,ID\na,   \n", "blank return"),
    (b"Key,ID\na,x\0\n", "null character"),
])
def test_broken_reference_stops_even_when_optional(tmp_path: Path, raw: bytes, error: str) -> None:
    path = tmp_path / "register.csv"
    path.write_bytes(raw)
    with pytest.raises(ReferenceDataError, match=error):
        evaluate_reference(config_for(path, required=False, on_no_match="continue"), {"source": "a"})


def test_reference_bounds_and_digest_are_checked(tmp_path: Path) -> None:
    path = tmp_path / "register.csv"
    path.write_bytes(b"Key,ID\na,x\n")
    config = config_for(path)
    result = evaluate_reference(config, {"source": "a"})
    with pytest.raises(ReferenceDataError, match="byte limit"):
        evaluate_reference(config, {"source": "a"}, max_bytes=8)
    path.write_bytes(b"Key,ID\na," + b"x" * 32 + b"\n")
    with pytest.raises(ReferenceChangedError, match="unavailable"):
        evaluate_reference(config, {"source": "a"}, expected_sha256=result.source_sha256, max_bytes=32)
    path.write_bytes(b"Key,ID\na,y\n")
    with pytest.raises(ReferenceChangedError, match="changed"):
        evaluate_reference(config, {"source": "a"}, expected_sha256=result.source_sha256)
    path.unlink()
    with pytest.raises(ReferenceChangedError, match="unavailable"):
        evaluate_reference(config, {"source": "a"}, expected_sha256=result.source_sha256)
    with pytest.raises(ReferenceDataError, match="could not be read"):
        evaluate_reference(config, {"source": "a"})


def test_invalid_numeric_reference_key_is_an_error_even_with_a_valid_match(tmp_path: Path) -> None:
    path = tmp_path / "register.csv"
    path.write_text("Key,ID\n1,first\n1e1,invalid\n", encoding="utf-8")
    config = config_for(path, clauses=[{"field": "source", "column": "Key", "mode": "numeric"}])
    with pytest.raises(ReferenceDataError, match="invalid numeric key"):
        evaluate_reference(config, {"source": 1})


def test_numeric_lookup_accepts_a_trailing_decimal_separator(tmp_path: Path) -> None:
    path = tmp_path / "register.csv"
    path.write_text("Key,ID\n1.,00042\n", encoding="utf-8")
    config = config_for(path, clauses=[{"field": "source", "column": "Key", "mode": "numeric"}])
    result = evaluate_reference(config, {"source": 1})
    assert result.candidates[0].complete_values() == {"id_from_reference": "00042"}


@pytest.mark.parametrize("override", [
    {"clauses": []},
    {"clauses": [{"field": "source", "column": "Key"}] * 6},
    {"clauses": [{"field": "items.0.key", "column": "Key"}]},
    {"returns": [{"field": "id_from_reference", "column": "ID"}] * 2},
    {"returns": [{"field": "source", "column": "ID"}]},
    {"on_no_match": "continue"},
    {"required": "false"},
])
def test_configuration_rejects_invalid_bindings(tmp_path: Path, override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        config_for(tmp_path / "register.csv", **override)
