"""Negative-path coverage for portable pipeline configuration contracts."""

from __future__ import annotations

import pytest

from modules.services.portable_config_service import (
    PortableConfigError,
    export_pipeline_bundle,
    import_pipeline_bundle,
    parse_schema_coordinate,
)
from modules.services.versioned_config_contracts import ReviewSchemaCoordinate, PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION


HASH = "a" * 64
COORD = {"key": "invoice", "version": 1, "content_hash": HASH}


@pytest.mark.parametrize(
    "value, message",
    [
        (None, "object"),
        ({"key": "invoice", "version": 0, "content_hash": HASH}, "positive"),
        ({"key": "invoice", "version": True, "content_hash": HASH}, "positive"),
        ({"key": "invoice", "version": 1, "content_hash": "short"}, "SHA-256"),
        ({"key": "invoice", "version": 1, "content_hash": "z" * 64}, "hexadecimal"),
    ],
)
def test_schema_coordinate_rejects_invalid_inputs(value, message) -> None:
    with pytest.raises(PortableConfigError, match=message):
        parse_schema_coordinate(value)


def test_import_pipeline_bundle_rejects_invalid_shapes_and_duplicates() -> None:
    base = {"kind": "pipeline-bundle", "format_version": PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION, "definition": {"tasks": {}}, "dependencies": {}}
    with pytest.raises(PortableConfigError, match="kind"):
        import_pipeline_bundle({**base, "kind": "runtime"})
    with pytest.raises(PortableConfigError, match="format_version"):
        import_pipeline_bundle({**base, "format_version": 99})
    with pytest.raises(PortableConfigError, match="definition"):
        import_pipeline_bundle({**base, "definition": []})
    with pytest.raises(PortableConfigError, match="tasks"):
        import_pipeline_bundle({**base, "definition": {"tasks": []}})
    with pytest.raises(PortableConfigError, match="dependencies"):
        import_pipeline_bundle({**base, "dependencies": []})
    bad_dep = {**base, "dependencies": {"review_schemas": ["bad"]}}
    with pytest.raises(PortableConfigError, match="dependency"):
        import_pipeline_bundle(bad_dep)
    duplicate = {**base, "dependencies": {"review_schemas": [COORD, COORD]}}
    with pytest.raises(PortableConfigError, match="Duplicate"):
        import_pipeline_bundle(duplicate)


def test_import_and_export_cover_embedded_and_unknown_dependencies() -> None:
    definition = {"tasks": {"review": {"params": {"schema": COORD}}}}
    bundle = {"kind": "pipeline-bundle", "format_version": PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION, "definition": definition, "dependencies": {"review_schemas": [{**COORD, "schema": {"title": "wrong"}}]}}
    with pytest.raises(PortableConfigError, match="hash"):
        import_pipeline_bundle(bundle)

    embedded_schema = {"title": "Invoice", "fields": {"amount": {"type": "number"}}}
    embedded_coord = {**COORD, "content_hash": ""}
    from modules.services.versioned_config_contracts import content_hash
    embedded_coord["content_hash"] = content_hash(embedded_schema)
    imported, dependencies = import_pipeline_bundle(
        {
            "kind": "pipeline-bundle",
            "format_version": PORTABLE_PIPELINE_BUNDLE_FORMAT_VERSION,
            "definition": {"tasks": {"review": {"params": {"schema": embedded_coord}}}},
            "dependencies": {"review_schemas": [{**embedded_coord, "schema": embedded_schema}]},
        }
    )
    assert imported["tasks"]["review"]["params"]["schema_version_id"].startswith("embedded:")
    assert dependencies["review"].key == "invoice"

    with pytest.raises(PortableConfigError, match="Unknown"):
        export_pipeline_bundle({"tasks": {"review": {"params": {"schema_version_id": "missing"}}}}, template_key="x", template_name="X", resolve_version=lambda _version: None)
    coordinate = ReviewSchemaCoordinate("invoice", 1, embedded_coord["content_hash"])
    exported = export_pipeline_bundle(
        {"tasks": {"a": {"params": {"schema_version_id": "v1"}}, "b": {"params": {"schema_version_id": "v1"}}}},
        template_key="x", template_name="X", resolve_version=lambda _version: coordinate,
        embedded_schemas={"v1": embedded_schema},
    )
    assert len(exported["dependencies"]["review_schemas"]) == 1
    with pytest.raises(PortableConfigError, match="mismatch"):
        export_pipeline_bundle({"tasks": {"a": {"params": {"schema_version_id": "v1"}}}}, template_key="x", template_name="X", resolve_version=lambda _version: coordinate, embedded_schemas={"v1": {"title": "bad"}})
