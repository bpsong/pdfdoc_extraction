"""CLI tests for non-mutating portable file validation."""

from __future__ import annotations

import json

import yaml

from tools.config_check.__main__ import main


def _pipeline_bundle():
    return {
        "kind": "pipeline-bundle",
        "format_version": 1,
        "template": {"key": "invoice", "name": "Invoice"},
        "definition": {
            "schema_version": 1,
            "pipeline": ["extract"],
            "tasks": {
                "extract": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdfTask",
                    "params": {
                        "api_key": {"$secret": "extract-api"},
                        "fields": {
                            "supplier": {"alias": "Supplier", "type": "str"}
                        },
                    },
                }
            },
        },
        "dependencies": {"review_schemas": []},
    }


def test_validate_file_pipeline_and_review_schema_offline(tmp_path, capsys):
    pipeline_path = tmp_path / "pipeline.json"
    pipeline_path.write_text(
        json.dumps(_pipeline_bundle()), encoding="utf-8"
    )
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        yaml.safe_dump(
            {
                "kind": "review-schema",
                "format_version": 1,
                "schema_key": "invoice",
                "schema": {
                    "fields": {
                        "supplier": {
                            "type": "string",
                            "label": "Supplier",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    before_pipeline = pipeline_path.read_bytes()
    before_schema = schema_path.read_bytes()

    assert main(
        ["validate-file", str(pipeline_path), "--kind", "pipeline"]
    ) == 0
    assert main(
        [
            "validate-file",
            "--file",
            str(schema_path),
            "--kind",
            "review-schema",
        ]
    ) == 0
    assert pipeline_path.read_bytes() == before_pipeline
    assert schema_path.read_bytes() == before_schema
    assert "synthetic-secret" not in capsys.readouterr().out


def test_offline_pipeline_requires_embedded_dependency_and_rejects_hash_mismatch(
    tmp_path, capsys
):
    bundle = _pipeline_bundle()
    bundle["definition"]["pipeline"].append("review")
    bundle["definition"]["tasks"]["review"] = {
        "module": "standard_step.review.review_gate",
        "class": "ReviewGateTask",
        "params": {
            "schema": {
                "key": "invoice",
                "version": 1,
                "content_hash": "a" * 64,
            }
        },
    }
    missing = tmp_path / "missing.yaml"
    missing.write_text(yaml.safe_dump(bundle), encoding="utf-8")
    assert main(
        ["validate-file", str(missing), "--kind", "pipeline"]
    ) == 1
    assert "Unresolved review schema dependency" in capsys.readouterr().out

    bundle["dependencies"]["review_schemas"] = [
        {
            "key": "invoice",
            "version": 1,
            "content_hash": "a" * 64,
            "schema": {
                "fields": {
                    "supplier": {"type": "string", "label": "Supplier"}
                }
            },
        }
    ]
    mismatch = tmp_path / "mismatch.json"
    mismatch.write_text(json.dumps(bundle), encoding="utf-8")
    assert main(
        ["validate-file", str(mismatch), "--kind", "pipeline"]
    ) == 1
    assert "hash" in capsys.readouterr().out.lower()


def test_validate_file_runtime_never_requires_or_opens_sqlite(
    config_factory, capsys
):
    runtime = config_factory.write(name="runtime.yaml")
    assert main(
        ["validate-file", str(runtime), "--kind", "runtime"]
    ) == 0
    assert "Validation passed" in capsys.readouterr().out
