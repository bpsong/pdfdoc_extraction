"""Boundary tests for parameter validation helpers and task classification."""

from __future__ import annotations

from tools.config_check import parameter_validator as pv


def _issues(params, *, module="standard_step.extraction.extract_pdf", cls="ExtractPdfTask"):
    result = pv.validate_parameters({"tasks": {"task": {"module": module, "class": cls, "params": params}}})
    return result.errors, result.warnings


def test_task_classification_and_non_mapping_sections() -> None:
    assert pv.validate_parameters({"tasks": []}).errors[0].code == "tasks-not-mapping"
    errors, _ = pv.validate_parameters({"tasks": {"bad": []}}), []
    assert errors.errors[0].code == "task-definition-not-mapping"
    assert pv._classify_task(None, "LlamaCloudSplitTask", {}) == "split"
    assert pv._classify_task("standard_step.rules.update_reference", None, {}) == "rules"
    assert pv._classify_task(None, None, {"fields": {}}) == "extraction"
    assert pv._classify_task(None, None, {}) is None
    assert not pv._requires_extraction_credentials(None)
    assert pv._is_localdrive_storage("standard_step.storage.store_file_to_localdrive")


def test_storage_extraction_field_and_glm_validation_errors() -> None:
    errors, warnings = _issues(None, module="standard_step.storage.store_metadata_as_json", cls="StoreMetadataAsJson")
    assert errors[0].code == "param-not-mapping"
    errors, warnings = _issues({"storage": {"unknown": 1}}, module="standard_step.storage.store_metadata_as_json", cls="StoreMetadataAsJson")
    assert warnings[0].code == "param-storage-unknown-storage-key"
    errors, _ = _issues({}, module="standard_step.storage.store_file_to_localdrive", cls="StoreFileToLocalDriveTask")
    assert {item.code for item in errors} >= {"param-localdrive-missing-files-dir", "param-localdrive-missing-filename"}
    errors, _ = _issues(None)
    assert errors[0].code == "param-extraction-not-mapping"
    errors, _ = _issues({"fields": {"one": {"alias": "One", "type": "str", "is_table": True, "item_fields": {"x": {"alias": "X", "type": "str"}}}, "two": {"alias": "Two", "type": "str", "is_table": True, "item_fields": {"x": {"alias": "X", "type": "str"}}}}}, module="standard_step.extraction.glm_ocr_extract", cls="GlmOcrExtractTask")
    assert any(item.code == "param-extraction-multiple-tables" for item in errors)


def test_glm_runtime_option_matrix() -> None:
    params = {"fields": {"name": {"alias": "Name", "type": "str"}}, "ollama_host": "http://user:pass@host:1", "model": "", "resolution_mode": "document", "resolver_model": "", "document_instructions": 1, "prompt_style": "verbatim", "dpi": 0, "resolver_max_attempts": 6, "resolver_max_dimension": 5000, "timeout_seconds": 0}
    errors, _ = _issues(params, module="standard_step.extraction.glm_ocr_extract", cls="GlmOcrExtractTask")
    codes = {item.code for item in errors}
    assert {"param-glm-host-credentials", "param-glm-missing-model", "param-glm-missing-resolver-model", "param-glm-invalid-document-instructions", "param-glm-missing-verbatim-instructions", "param-glm-invalid-dpi", "param-glm-invalid-resolver-max-attempts", "param-glm-invalid-resolver-max-dimension", "param-glm-invalid-timeout-seconds"} <= codes
    cloud_params = {"api_key": "x", "configuration_id": "y", "fields": {"x": {"alias": "X", "type": "str"}}}
    errors, _ = _issues(cloud_params, module="standard_step.extraction.glm_ocr_extract", cls="GlmOcrExtractTask")
    assert any(item.code == "param-glm-llamacloud-only" for item in errors)


def test_field_rules_context_housekeeping_split_and_recursive_values() -> None:
    errors, _ = _issues({"fields": {"x": {"alias": "X", "type": "str", "is_table": "yes", "item_fields": {}}}})
    assert {item.code for item in errors} >= {"param-field-istable-bool", "param-field-missing-item-fields"}
    errors, _ = _issues({"reference_file": "", "update_field": 1, "csv_match": {"type": "wrong", "clauses": [None] }}, module="standard_step.rules.update_reference", cls="UpdateReference")
    assert any(item.code == "param-rules-clause-not-mapping" for item in errors)
    for module, cls, params, code in [
        ("standard_step.context.assign_nanoid", "AssignNanoid", None, "param-not-mapping"),
        ("standard_step.context.assign_nanoid", "AssignNanoid", {"length": 2}, "param-context-length-bounds"),
        ("standard_step.housekeeping.cleanup_task", "CleanupTask", None, "param-housekeeping-not-mapping"),
        ("standard_step.housekeeping.cleanup_task", "CleanupTask", {"processing_dir": ""}, "param-housekeeping-processing-dir-invalid"),
        ("standard_step.split.llamacloud_split", "LlamaCloudSplitTask", None, "param-split-not-mapping"),
    ]:
        errors, _ = _issues(params, module=module, cls=cls)
        assert any(item.code == code for item in errors)
    errors, _ = _issues({"split_dir": "x", "fail_on_confidence_levels": ["bad"], "fail_on_unknown_category": "yes", "allowed_categories": [""]}, module="standard_step.split.llamacloud_split", cls="LlamaCloudSplitTask")
    assert len(errors) == 3
    assert list(pv._iter_string_values({"a": ["x"]}, "root")) == [("root.a[0]", "x")]
    assert pv._is_valid_field_type("Optional[List[int]]")
    assert not pv._is_valid_field_type("Tuple[str]")
    assert pv._unwrap_optional_field_type("Optional[str]") == "str"
    assert pv._is_table_field_spec({"is_table": True})
