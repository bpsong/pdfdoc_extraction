from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.api_router as api_router
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import DocumentRepository, ExtractionRepository, ReviewRepository
from modules.services.batch_service import BatchService
from test.helpers_sqlite import TempConfig


class _FakeAuth:
    token_exp_minutes = 30


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, dict]:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "invoice.yaml").write_text(
        """
fields:
  supplier:
    type: string
    required: true
    min_length: 2
    pattern: "^A"
  invoice_amount:
    type: number
    required: true
    step: 0.01
    decimal_places: 2
    format: money
  approved:
    type: boolean
    required: true
  reviewed_at:
    type: datetime
  address:
    type: object
    properties:
      city:
        type: string
        readonly: true
  tags:
    type: array
    items:
      type: enum
      choices: [urgent, standard]
  line_items:
    type: array
    items:
      type: object
      properties:
        sku:
          type: string
        quantity:
          type: number
          step: 0.01
          decimal_places: 2
""".strip()
        + "\n",
        encoding="utf-8",
    )
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% review api test")
    config = TempConfig(
        tmp_path / "app.sqlite3",
        {"schema": {"directories": [str(schema_dir)]}, "pipeline": []},
    )
    initialize_database(config)

    with connect(config) as conn:
        created = BatchService(conn).create_ingestion_batch(
            source="web",
            file_path=str(pdf_path),
            original_filename="invoice.pdf",
        )
        document_id = created["document"]["id"]
        DocumentRepository(conn).add_file(
            document_id=document_id,
            file_type="original_pdf",
            file_path=str(pdf_path),
        )
        extraction = ExtractionRepository(conn).save_result(
            document_id=document_id,
            provider="test",
            data={"supplier": "Acme"},
        )
        ExtractionRepository(conn).save_fields(
            document_id=document_id,
            extraction_result_id=extraction["id"],
            fields=[
                {"field_key": "supplier", "field_alias": "Supplier", "extracted_value": "Acme", "confidence": 0.61, "requires_review": True},
                {"field_key": "invoice_amount", "field_alias": "Invoice Amount", "extracted_value": 70, "confidence": 0.8},
                {"field_key": "approved", "field_alias": "Approved", "extracted_value": None, "confidence": 0.7},
                {"field_key": "reviewed_at", "field_alias": "Reviewed At", "extracted_value": "2026-06-12T09:30:00Z", "confidence": 0.7},
                {"field_key": "address", "field_alias": "Address", "extracted_value": {"city": "Singapore"}, "confidence": 0.95},
                {"field_key": "tags", "field_alias": "Tags", "extracted_value": ["urgent"], "confidence": 0.9},
                {
                    "field_key": "line_items",
                    "field_alias": "Line Items",
                    "extracted_value": [{"sku": "ABC", "quantity": 2}],
                    "confidence": 0.88,
                    "source": {
                        "confidence_details": {
                            "aggregation": "minimum_nested_confidence",
                            "confidence": 0.88,
                            "nested_confidences": {
                                "0.sku": {"confidence": 0.96, "confidence_band": "high"},
                                "0.quantity": {"confidence": 0.88, "confidence_band": "medium"},
                            },
                        }
                    },
                },
            ],
        )
        review = ReviewRepository(conn).create_review_item(
            batch_id=created["batch"]["id"],
            document_id=document_id,
            queue_name="invoice_review",
            reason="low_confidence",
            scope="low_confidence_fields",
            metadata={
                "schema_file": "invoice.yaml",
                "highlight_fields": ["supplier"],
                "editable_fields": ["supplier", "invoice_amount", "approved", "reviewed_at", "address", "tags", "line_items"],
            },
        )

    def fake_get_dependencies():
        return config, _FakeAuth(), None, None, None

    monkeypatch.setattr(api_router, "get_dependencies", fake_get_dependencies)
    app = FastAPI()
    app.include_router(api_router.build_router())
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    return TestClient(app), {"created": created, "review": review}


def test_review_queue_api_returns_ui_ready_items(tmp_path, monkeypatch) -> None:
    client, state = _client(tmp_path, monkeypatch)

    response = client.get("/api/review/items")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == state["review"]["id"]
    assert payload[0]["document"]["filename"] == "invoice.pdf"
    assert payload[0]["review_field_labels"] == ["Supplier"]
    assert payload[0]["lowest_confidence"] == 0.61


def test_review_detail_api_returns_schema_pdf_and_parsed_fields(tmp_path, monkeypatch) -> None:
    client, state = _client(tmp_path, monkeypatch)
    review_id = state["review"]["id"]

    response = client.get(f"/api/review/items/{review_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["preview_url"].endswith("/file/pdf")
    assert payload["schema"]["name"] == "invoice.yaml"
    assert [field["key"] for field in payload["schema"]["fields"]] == [
        "supplier",
        "invoice_amount",
        "approved",
        "reviewed_at",
        "address",
        "tags",
        "line_items",
    ]
    assert payload["schema"]["fields"][0]["pattern"] == "^A"
    assert payload["schema"]["fields"][1]["step"] == 0.01
    assert payload["schema"]["fields"][1]["decimal_places"] == 2
    assert payload["schema"]["fields"][4]["children"][0]["readonly"] is True
    assert payload["schema"]["fields"][5]["editor"] == "scalar_array"
    assert payload["schema"]["fields"][5]["item_schema"]["option_items"][0]["value"] == "urgent"
    assert payload["schema"]["fields"][6]["editor"] == "object_array"
    assert payload["schema"]["fields"][6]["item_schema"]["fields"][1]["step"] == 0.01
    assert payload["fields"][4]["final_value"] == {"city": "Singapore"}
    assert payload["fields"][0]["confidence_band"] == "low"
    line_items = next(field for field in payload["fields"] if field["field_key"] == "line_items")
    assert line_items["confidence_details"]["confidence"] == 0.88
    assert line_items["confidence_details"]["nested_confidences"]["0.quantity"]["confidence_band"] == "medium"


def test_review_ui_actions_claim_draft_diff_and_release(tmp_path, monkeypatch) -> None:
    client, state = _client(tmp_path, monkeypatch)
    review_id = state["review"]["id"]

    claim = client.post(f"/api/review/items/{review_id}/claim", json={"user": "admin"})
    draft = client.post(
        f"/api/review/items/{review_id}/draft",
        json={"user": "admin", "corrections": {"supplier": "Acme Pte Ltd"}},
    )
    diff = client.post(f"/api/review/items/{review_id}/diff", json={"corrections": {"supplier": "Acme Pte Ltd"}})
    release = client.post(f"/api/review/items/{review_id}/release", json={"user": "admin"})

    assert claim.status_code == 200
    assert claim.json()["status"] == "in_review"
    assert claim.json()["assigned_to"] == "operator"
    assert draft.status_code == 200
    assert draft.json()["metadata"]["draft"]["corrections"]["supplier"] == "Acme Pte Ltd"
    assert draft.json()["metadata"]["draft"]["user"] == "operator"
    assert diff.status_code == 200
    assert diff.json()["change_count"] == 1
    assert release.status_code == 200
    assert release.json()["released"] is True
