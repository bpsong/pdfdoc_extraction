import json
from pathlib import Path

import pytest

from modules.services.schema_service import SchemaService
from test.helpers_sqlite import TempConfig


def _service(tmp_path: Path) -> SchemaService:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"schema": {"directories": [str(schema_dir)]}},
    )
    return SchemaService(config)


def test_schema_file_error_and_serialization_paths(tmp_path):
    service = _service(tmp_path)
    schema_dir = tmp_path / "schemas"
    (schema_dir / "invalid.json").write_text("[]", encoding="utf-8")
    (schema_dir / "valid.json").write_text(
        json.dumps({"fields": {"name": {"type": "string"}}}),
        encoding="utf-8",
    )

    assert service.load_schema("invalid.json") is None
    assert service.load_schema("valid.json")["fields"]["name"]["type"] == "string"
    assert service.validate_payload({}, schema_name="missing.yaml")[0]["path"] == "missing.yaml"
    assert service.validate_payload({}, schema={"fields": []})[0]["path"] == "fields"
    assert service.validate_schema({"fields": []})[0]["path"] == "fields"

    with pytest.raises(ValueError, match="validation failed"):
        service.save_schema("bad.yaml", {"fields": []})

    service.save_schema("saved.yaml", {"fields": {"name": {"type": "string"}}})
    with pytest.raises(FileExistsError):
        service.save_schema("saved.yaml", {"fields": {"name": {"type": "string"}}})
    with pytest.raises(FileNotFoundError):
        service.duplicate_schema("missing.yaml", "copy.yaml")


@pytest.mark.parametrize("name", ["../bad.yaml", "folder/bad.yaml"])
def test_schema_name_rejects_paths(tmp_path, name):
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="file name"):
        service._safe_schema_name(name)


def test_schema_name_suffix_and_json_serialization(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="must end"):
        service._safe_schema_name("schema.txt")

    serialized = service._serialize_schema(
        tmp_path / "schema.json",
        {"fields": {}},
    )
    assert serialized.endswith("\n")
    assert '"fields"' in serialized


def test_normalization_fallbacks_and_numeric_helpers(tmp_path):
    service = _service(tmp_path)
    fields = service._normalize_fields(
        {
            "unsupported": "bad",
            "object": {"type": "object", "properties": {}},
            "array": {"type": "array", "items": {}},
        }
    )

    assert fields[0]["type"] == "string"
    assert service._numeric_step({"type": "number", "decimal_places": 3}) == 0.001
    assert service._decimal_places({"decimal_places": 0}) == 0
    assert service._decimal_places({"format": "money"}) == 2
    assert service._normalize_array_item("bad") == {"type": "string"}
    assert service._editor_for({"type": "string", "multiline": True}) == "textarea"


def test_schema_structure_validation_covers_invalid_configs(tmp_path):
    service = _service(tmp_path)
    findings = service.validate_schema(
        {
            "fields": {
                "invalid": "bad",
                "enum": {"type": "enum", "choices": ["a"], "default": "b"},
                "object": {"type": "object", "properties": "bad"},
                "array_missing": {"type": "array"},
                "array_bad": {"type": "array", "items": "bad"},
                "number": {
                    "type": "number",
                    "min_value": "bad",
                    "step": 0,
                    "decimal_places": -1,
                },
                "range": {"type": "number", "min_value": 3, "max_value": 2},
            }
        }
    )
    paths = {finding["path"] for finding in findings}

    assert {
        "invalid",
        "enum.default",
        "object.properties",
        "array_missing.items",
        "array_bad.items",
        "number.min_value",
        "number.step",
        "number.decimal_places",
        "range.min_value",
    } <= paths


def test_payload_validation_covers_all_value_types(tmp_path):
    service = _service(tmp_path)
    schema = {
        "fields": {
            "required": {"type": "string", "required": True},
            "text": {
                "type": "string",
                "min_length": 3,
                "max_length": 4,
                "pattern": r"^[A-Z]+$",
            },
            "number": {"type": "number", "min_value": 1, "max_value": 2},
            "integer": {"type": "integer"},
            "boolean": {"type": "boolean"},
            "date": {"type": "date"},
            "datetime": {"type": "datetime"},
            "enum": {"type": "enum", "choices": ["a"]},
            "object": {
                "type": "object",
                "properties": {"child": {"type": "string", "required": True}},
            },
            "array": {"type": "array", "items": {"type": "integer"}},
        }
    }
    payload = {
        "required": None,
        "text": 1,
        "number": "bad",
        "integer": 1.5,
        "boolean": "yes",
        "date": "2026/01/01",
        "datetime": "bad",
        "enum": "b",
        "object": [],
        "array": "bad",
    }
    findings = service.validate_payload(payload, schema=schema)
    paths = {finding["path"] for finding in findings}

    assert {
        "required",
        "text",
        "number",
        "integer",
        "boolean",
        "date",
        "datetime",
        "enum",
        "object",
        "array",
    } <= paths

    string_findings = service._validate_value(
        "text",
        "ab",
        {"type": "string", "min_length": 3, "pattern": r"^[A-Z]+$"},
    )
    assert len(string_findings) == 2
    assert service._validate_value("optional", None, {"type": "string"}) == []
    assert service._validate_value(
        "object",
        {},
        {"type": "object", "properties": {"child": {"type": "string", "required": True}}},
    )
    assert service._validate_value(
        "array",
        ["bad"],
        {"type": "array", "items": {"type": "integer"}},
    )
