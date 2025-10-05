"""Integration tests exercising the end-to-end validation pipeline."""

from __future__ import annotations

import pytest

from tools.config_check.validator import ConfigValidator


@pytest.fixture
def validator(config_factory) -> ConfigValidator:
    """Create a ConfigValidator instance scoped to the temp config directory."""

    return ConfigValidator(base_dir=config_factory.paths.base_dir)


def test_validator_accepts_valid_configuration(
    config_factory,
    validator: ConfigValidator,
) -> None:
    config_path = config_factory.write()

    result = validator.validate(config_path)

    assert result.is_valid
    assert result.errors == []
    assert result.warnings == []


def test_validator_reports_pipeline_violations(
    config_factory,
    validator: ConfigValidator,
) -> None:
    config_data = config_factory.with_overrides({"pipeline": ["store_json"]})
    config_path = config_factory.write(name="invalid_pipeline.yaml", config=config_data)

    result = validator.validate(config_path)

    assert result.is_valid is False
    error_codes = {error.code for error in result.errors}
    assert "pipeline-missing-extraction" in error_codes


def test_validator_emits_yaml_error_for_malformed_file(
    config_factory,
    validator: ConfigValidator,
) -> None:
    config_path = config_factory.write_text(
        """
        web:
          upload_dir: "./uploads
        """,
        name="broken.yaml",
    )

    result = validator.validate(config_path)

    assert result.is_valid is False
    assert any(message.code == "yaml-error" for message in result.errors)




def test_validator_allows_v2_storage_with_metadata(config_factory, validator: ConfigValidator) -> None:
    config = config_factory.with_overrides(
        {
            "tasks": {
                "store_json_v2": {
                    "module": "standard_step.storage.store_metadata_as_json_v2",
                    "class": "StoreMetadataAsJsonV2",
                    "params": {
                        "data_dir": str(config_factory.paths.data_dir),
                        "filename": "{id}.json",
                    },
                }
            },
            "pipeline": [
                "extract_metadata",
                "store_json_v2",
                "archive_pdf",
            ],
        }
    )

    config_path = config_factory.write(name="v2_ok.yaml", config=config)

    result = validator.validate(config_path)

    assert all(message.code != "pipeline-storage-metadata-missing" for message in result.warnings)


def test_validator_warns_when_v2_storage_precedes_metadata(config_factory, validator: ConfigValidator) -> None:
    config = config_factory.with_overrides(
        {
            "tasks": {
                "store_json_v2": {
                    "module": "standard_step.storage.store_metadata_as_json_v2",
                    "class": "StoreMetadataAsJsonV2",
                    "params": {
                        "data_dir": str(config_factory.paths.data_dir),
                        "filename": "{id}.json",
                    },
                }
            },
            "pipeline": [
                "store_json_v2",
                "extract_metadata",
                "archive_pdf",
            ],
        }
    )

    config_path = config_factory.write(name="v2_warn.yaml", config=config)

    result = validator.validate(config_path)

    assert any(message.code == "pipeline-storage-metadata-missing" for message in result.warnings)
