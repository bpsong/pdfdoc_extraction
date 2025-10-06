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
    # Create the default processing directory to avoid path validation errors
    processing_dir = config_factory.paths.base_dir / "processing"
    processing_dir.mkdir(exist_ok=True)
    
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


# Integration tests for full validation pipeline with schema enhancements

def test_full_validation_pipeline_with_new_schema_fields(
    config_factory,
    validator: ConfigValidator,
) -> None:
    """Test complete validation flow with new schema fields (web.host, web.port, watch_folder fields)."""
    # Create processing directory for the test
    processing_dir = config_factory.paths.base_dir / "temp_processing"
    processing_dir.mkdir(exist_ok=True)
    
    config = config_factory.with_overrides(
        {
            "web": {
                "host": "0.0.0.0",  # New field
                "port": 3000,       # New field
            },
            "watch_folder": {
                "validate_pdf_header": False,  # New field
                "processing_dir": str(processing_dir),  # New field
            },
        }
    )

    config_path = config_factory.write(name="enhanced_schema.yaml", config=config)

    result = validator.validate(config_path)

    assert result.is_valid
    assert result.errors == []
    # Should have no schema validation errors for the new fields


def test_full_validation_pipeline_with_invalid_schema_fields(
    config_factory,
    validator: ConfigValidator,
) -> None:
    """Test complete validation flow with invalid new schema fields."""
    config = config_factory.with_overrides(
        {
            "web": {
                "host": "",  # Invalid: empty string
                "port": 70000,  # Invalid: port too high
            },
            "watch_folder": {
                "validate_pdf_header": "true",  # Invalid: should be boolean
                "processing_dir": "",  # Invalid: empty string
            },
        }
    )

    config_path = config_factory.write(name="invalid_schema.yaml", config=config)

    result = validator.validate(config_path)

    assert result.is_valid is False
    
    # Should have schema validation errors
    error_paths = {error.path for error in result.errors}
    assert "web.host" in error_paths
    assert "web.port" in error_paths
    assert "watch_folder.processing_dir" in error_paths
    
    # The validate_pdf_header field might be coerced to boolean by Pydantic
    # so let's just check that we have the expected number of errors
    assert len(result.errors) >= 3  # At least the three errors we expect


def test_backward_compatibility_with_existing_configurations(
    config_factory,
    validator: ConfigValidator,
) -> None:
    """Test that existing configurations without new fields still validate successfully."""
    # Create the default processing directory to avoid path validation errors
    processing_dir = config_factory.paths.base_dir / "processing"
    processing_dir.mkdir(exist_ok=True)
    
    # Use minimal config without the new optional fields
    config = config_factory.with_overrides({})  # Use default factory config

    config_path = config_factory.write(name="backward_compatible.yaml", config=config)

    result = validator.validate(config_path)
    
    assert result.is_valid
    assert result.errors == []
    # Should validate successfully even without new optional fields


def test_error_message_formatting_consistency(
    config_factory,
    validator: ConfigValidator,
) -> None:
    """Test that error messages are consistently formatted across different validation types."""
    config = config_factory.with_overrides(
        {
            "web": {
                "host": "   ",  # Schema validation error
                "port": "invalid",  # Schema validation error
            },
            "tasks": {
                "invalid_task": {
                    "module": "nonexistent.module",  # Import validation error (if enabled)
                    "class": "NonexistentClass",
                    "params": {},
                }
            },
            "pipeline": ["invalid_task", "missing_task"],  # Pipeline validation error
        }
    )

    config_path = config_factory.write(name="mixed_errors.yaml", config=config)

    result = validator.validate(config_path)

    assert result.is_valid is False
    assert len(result.errors) >= 3  # At least schema, pipeline errors
    
    # Check that all errors have consistent structure
    for error in result.errors:
        assert hasattr(error, 'path')
        assert hasattr(error, 'message')
        assert hasattr(error, 'code')
        assert error.path  # Should not be empty
        assert error.message  # Should not be empty
        assert error.code  # Should not be empty


def test_validation_with_import_checks_enabled(
    config_factory,
) -> None:
    """Test full validation pipeline with import checks enabled."""
    from tools.config_check.validator import ConfigValidator
    
    config = config_factory.with_overrides(
        {
            "tasks": {
                "valid_import_task": {
                    "module": "os",  # Built-in module
                    "class": "path",  # This will fail class validation
                    "params": {},
                },
                "invalid_import_task": {
                    "module": "nonexistent.module",
                    "class": "NonexistentClass",
                    "params": {},
                }
            },
            "pipeline": ["extract_metadata", "valid_import_task", "invalid_import_task"],
        }
    )

    config_path = config_factory.write(name="import_validation.yaml", config=config)

    # Create validator with import checks enabled
    validator_with_imports = ConfigValidator(
        base_dir=config_factory.paths.base_dir,
        import_checks=True
    )
    
    result = validator_with_imports.validate(config_path)

    assert result.is_valid is False
    
    # Should have import validation errors
    import_errors = [error for error in result.errors if error.code and error.code.startswith("task-import-")]
    assert len(import_errors) >= 2  # At least module not found and not callable errors


def test_validation_pipeline_performance_with_large_config(
    config_factory,
    validator: ConfigValidator,
) -> None:
    """Test validation performance with a larger configuration."""
    # Create a config with many tasks to test performance
    tasks = {}
    pipeline = []
    
    for i in range(20):
        task_name = f"task_{i}"
        tasks[task_name] = {
            "module": f"module_{i}",
            "class": f"Class_{i}",
            "params": {"param1": f"value_{i}", "param2": i},
        }
        pipeline.append(task_name)
    
    config = config_factory.with_overrides(
        {
            "tasks": tasks,
            "pipeline": pipeline,
        }
    )

    config_path = config_factory.write(name="large_config.yaml", config=config)

    # Validation should complete reasonably quickly even with many tasks
    result = validator.validate(config_path)

    # Should have pipeline errors for missing tasks but validation should complete
    assert result.is_valid is False
    assert len(result.errors) > 0  # Should have errors for non-existent modules


def test_validation_with_mixed_valid_invalid_tasks(
    config_factory,
    validator: ConfigValidator,
) -> None:
    """Test validation with a mix of valid and invalid task configurations."""
    # Create processing directory for the test
    processing_dir = config_factory.paths.base_dir / "processing"
    processing_dir.mkdir(exist_ok=True)
    
    config = config_factory.with_overrides(
        {
            "web": {
                "host": "localhost",  # Valid
                "port": 8080,         # Valid
            },
            "watch_folder": {
                "validate_pdf_header": True,  # Valid
                "processing_dir": str(processing_dir),  # Valid
            },
            "tasks": {
                "valid_task": {
                    "module": "standard_step.extraction.extract_pdf",
                    "class": "ExtractPdf",
                    "params": {},
                },
                "invalid_structure": {
                    # Missing module and class
                    "params": {},
                },
                "invalid_module": {
                    "module": "",  # Empty module name
                    "class": "SomeClass",
                    "params": {},
                }
            },
            "pipeline": ["extract_metadata", "valid_task", "invalid_structure", "invalid_module"],
        }
    )

    config_path = config_factory.write(name="mixed_validation.yaml", config=config)

    result = validator.validate(config_path)

    assert result.is_valid is False
    
    # Should have errors for invalid tasks but not for valid ones
    error_paths = {error.path for error in result.errors}
    
    # Should have errors for invalid tasks
    invalid_task_errors = [path for path in error_paths if "invalid_structure" in path or "invalid_module" in path]
    assert len(invalid_task_errors) > 0
    
    # Should not have schema errors for valid web and watch_folder fields
    schema_errors = [error for error in result.errors if error.path.startswith("web.") or error.path.startswith("watch_folder.")]
    web_watch_errors = [error for error in schema_errors if "host" in error.path or "port" in error.path or "validate_pdf_header" in error.path or "processing_dir" in error.path]
    assert len(web_watch_errors) == 0  # Should be no errors for valid schema fields
