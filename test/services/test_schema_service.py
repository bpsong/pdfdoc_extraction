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
    max_length: 12
    pattern: "^[A-Z].+"
    placeholder: Supplier name
  total:
    type: number
    required: true
    min_value: 0
    step: 0.01
    decimal_places: 2
    format: money
  status:
    type: enum
    default: new
    choices:
      - label: New
        value: new
      - label: Approved
        value: approved
  invoice_date:
    type: date
    required: true
  approved_at:
    type: datetime
  address:
    type: object
    properties:
      city:
        type: string
        readonly: true
  line_items:
    type: array
    items:
      type: object
      properties:
        description:
          type: string
        quantity:
          type: integer
        unit_price:
          type: number
          step: 0.01
          decimal_places: 2
  tags:
    type: array
    items:
      type: enum
      choices: [urgent, standard]
""",
        encoding="utf-8",
    )
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    service = SchemaService(config)

    normalized = service.normalize_schema("invoice.yaml")
    errors = service.validate_payload(
        {
            "supplier": "",
            "total": -1,
            "status": "bad",
            "invoice_date": "12/06/2026",
            "approved_at": "not-a-date",
            "address": {"city": "SG"},
            "line_items": [{"quantity": 1, "unit_price": 4.5}],
            "tags": ["bad"],
        },
        schema_name="invoice.yaml",
    )

    assert normalized is not None
    assert normalized["hash"] == service.schema_hash("invoice.yaml")
    assert [field["key"] for field in normalized["fields"]] == [
        "supplier",
        "total",
        "status",
        "invoice_date",
        "approved_at",
        "address",
        "line_items",
        "tags",
    ]
    assert normalized["fields"][0]["pattern"] == "^[A-Z].+"
    assert normalized["fields"][1]["step"] == 0.01
    assert normalized["fields"][1]["decimal_places"] == 2
    assert normalized["fields"][2]["option_items"] == [
        {"label": "New", "value": "new"},
        {"label": "Approved", "value": "approved"},
    ]
    assert normalized["fields"][5]["children"][0]["readonly"] is True
    assert normalized["fields"][6]["editor"] == "object_array"
    assert normalized["fields"][6]["item_schema"]["fields"][2]["step"] == 0.01
    assert normalized["fields"][7]["item_schema"]["option_items"][0]["value"] == "urgent"
    assert {error["path"] for error in errors} >= {
        "supplier",
        "total",
        "status",
        "invoice_date",
        "approved_at",
        "tags[0]",
    }


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


def test_schema_service_rejects_incompatible_array_item_config(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    service = SchemaService(config)

    findings = service.validate_schema(
        {
            "fields": {
                "bad_items": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "choices": ["A", "B"],
                        "properties": {"nested": {"type": "string"}},
                    },
                }
            }
        }
    )

    paths = {finding["path"] for finding in findings}
    assert "bad_items.items.choices" in paths
    assert "bad_items.items.properties" in paths


def test_schema_service_preserves_typed_defaults_on_save_load_roundtrip(tmp_path):
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    config = TempConfig(tmp_path / "app.sqlite3", {"schema": {"directories": [str(schema_dir)]}})
    service = SchemaService(config)
    schema = {
        "title": "Typed defaults",
        "fields": {
            "approved": {"type": "boolean", "default": True},
            "total": {"type": "number", "default": 12.5, "step": 0.01, "decimal_places": 2},
            "status": {"type": "enum", "choices": [{"label": "New", "value": "new"}], "default": "new"},
            "tags": {"type": "array", "items": {"type": "enum", "choices": ["urgent"], "default": "urgent"}},
        },
    }

    normalized = service.save_schema("typed.yaml", schema)
    loaded = service.load_schema("typed.yaml")

    assert normalized["fields"][0]["default"] is True
    assert normalized["fields"][1]["default"] == 12.5
    assert normalized["fields"][1]["step"] == 0.01
    assert normalized["fields"][2]["option_items"] == [{"label": "New", "value": "new"}]
    assert normalized["fields"][3]["item_schema"]["default"] == "urgent"
    assert loaded is not None
    assert loaded["fields"]["approved"]["default"] is True
    assert loaded["fields"]["total"]["default"] == 12.5
