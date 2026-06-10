from modules.services.schema_service import SchemaService
from test.helpers_sqlite import TempConfig


def test_schema_service_loads_normalizes_validates_and_hashes_complex_schema(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    schema_file = schema_dir / "invoice.yaml"
    schema_file.write_text(
        """
title: Invoice
fields:
  supplier:
    type: string
    label: Supplier
    required: true
    min_length: 2
  total:
    type: number
    required: true
    min_value: 0
  status:
    type: enum
    choices: [new, approved]
  address:
    type: object
    properties:
      city:
        type: string
  line_items:
    type: array
    items:
      type: object
      properties:
        description:
          type: string
        quantity:
          type: integer
""",
        encoding="utf-8",
    )
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    service = SchemaService(config)

    normalized = service.normalize_schema("invoice.yaml")
    errors = service.validate_payload(
        {"supplier": "", "total": -1, "status": "bad", "address": {"city": "SG"}, "line_items": [{"quantity": 1}]},
        schema_name="invoice.yaml",
    )

    assert normalized is not None
    assert normalized["hash"] == service.schema_hash("invoice.yaml")
    assert [field["key"] for field in normalized["fields"]] == ["supplier", "total", "status", "address", "line_items"]
    assert normalized["fields"][3]["children"][0]["key"] == "city"
    assert normalized["fields"][4]["editor"] == "object_array"
    assert {error["path"] for error in errors} >= {"supplier", "total", "status"}


def test_schema_service_resolves_config_relative_schema_paths(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        """
title: Invoice
fields:
  total:
    type: float
""",
        encoding="utf-8",
    )
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    service = SchemaService(config)

    normalized = service.normalize_schema("schemas/invoice.yaml")

    assert normalized is not None
    assert normalized["title"] == "Invoice"
    assert normalized["fields"][0]["key"] == "total"
