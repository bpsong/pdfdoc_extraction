"""Branch-focused tests for config-check defensive and reporting paths."""

from __future__ import annotations

import logging
import builtins
import importlib
import runpy
import sys
import warnings
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import tools.config_check.validator as validator_module

from tools.config_check import __main__ as cli
from tools.config_check.parameter_validator import (
    ParameterIssue,
    _validate_context_params,
    _validate_housekeeping_params,
    _validate_glm_schema_orders,
    _validate_optional_bool_param,
    _validate_optional_positive_number_param,
    _validate_optional_string_param,
    _validate_required_string,
    _validate_rules_params,
    _is_valid_field_type,
    _split_top_level_type_args,
)
from tools.config_check.path_validator import PathValidator
from tools.config_check.performance_analyzer import PerformanceAnalyzer
from tools.config_check.pipeline_validator import validate_pipeline
from tools.config_check.runtime_file_validator import RuntimeFileValidator
from tools.config_check.security_validator import SecurityValidator
from tools.config_check.validator import (
    ConfigValidator,
    ValidationMessage,
    ValidationResult,
)
from tools.config_check.reporter import FindingLevel, ValidationReporter
from tools.config_check.task_validator import _validate_task_imports, _validate_task_structure


def _args(**overrides):
    """Build the complete argument object consumed by CLI command helpers."""
    values = {
        "config": None,
        "format": "text",
        "strict": False,
        "verbose": False,
        "base_dir": None,
        "import_checks": False,
        "check_files": False,
        "performance_analysis": False,
        "security_analysis": False,
        "pipeline": None,
        "review_schema": None,
        "draft": False,
        "version": None,
        "all_stored": False,
        "file_option": None,
        "path": None,
        "kind": "runtime",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_config_validator_file_yaml_empty_and_non_mapping_paths(tmp_path: Path) -> None:
    missing = ConfigValidator().validate(tmp_path / "missing.yaml")
    assert missing.errors[0].code == "file-not-found"

    parser = Mock()
    parser.load.return_value = (None, None)
    empty = ConfigValidator(yaml_parser=parser).validate(tmp_path / "empty.yaml")
    # The file must exist before the parser is consulted.
    assert empty.errors[0].code == "file-not-found"
    path = tmp_path / "config.yaml"
    path.write_text("{}", encoding="utf-8")
    empty = ConfigValidator(yaml_parser=parser).validate(path)
    assert empty.errors[0].code == "empty-config"

    parser.load.return_value = (None, "bad yaml")
    parsed = ConfigValidator(yaml_parser=parser).validate(path)
    assert parsed.errors[0].code == "yaml-error"

    validator = ConfigValidator()
    assert validator._run_task_reference_pass([]).errors == []
    assert validator._run_parameter_pass([]).errors == []
    assert validator._run_pipeline_pass([]).errors == []
    assert validator._run_path_pass([]).errors == []
    assert validator._run_runtime_file_pass([]).errors == []
    assert validator._run_performance_pass([]).errors == []
    assert validator._run_security_pass([]).errors == []


def test_config_validator_translates_performance_and_security_info() -> None:
    validator = ConfigValidator()
    performance = Mock()
    performance.analyze_performance_impact.return_value = SimpleNamespace(
        errors=[SimpleNamespace(path="e", message="error", code="e", details={})],
        warnings=[SimpleNamespace(path="w", message="warning", code="w", details=None)],
        info=[SimpleNamespace(path="i", message="info", code="i", details={})],
    )
    validator.performance_analyzer = performance
    result = validator._run_performance_pass({})
    assert [item.code for item in result.errors] == ["e"]
    assert [item.code for item in result.warnings] == ["w", "i"]

    security = Mock()
    security.validate_security.return_value = SimpleNamespace(
        errors=[SimpleNamespace(path="e", message="error", code="e", details={})],
        warnings=[SimpleNamespace(path="w", message="warning", code="w", details=None)],
        info=[SimpleNamespace(path="i", message="info", code="i", details={})],
    )
    validator.security_validator = security
    result = validator._run_security_pass({})
    assert [item.code for item in result.errors] == ["e"]
    assert [item.code for item in result.warnings] == ["w", "i"]


def test_runtime_file_validator_handles_access_and_csv_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validator = RuntimeFileValidator(tmp_path)
    reference = tmp_path / "reference.csv"
    reference.write_text("a\n1\n", encoding="utf-8")
    config = {
        "tasks": {
            "rules": {
                "module": "standard_step.rules.update",
                "params": {"reference_file": "reference.csv"},
            }
        }
    }

    real_open = open
    def raise_permission(*args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr("builtins.open", raise_permission)
    errors, _ = validator._validate_reference_files(config)
    assert errors[0].code == "file-not-readable"
    monkeypatch.setattr("builtins.open", real_open)

    def raise_other(*args, **kwargs):
        raise OSError("broken")
    monkeypatch.setattr("builtins.open", raise_other)
    errors, _ = validator._validate_reference_files(config)
    assert errors[0].code == "file-access-error"
    monkeypatch.setattr("builtins.open", real_open)

    import tools.config_check.runtime_file_validator as runtime
    class PandasErrors:
        EmptyDataError = type("EmptyDataError", (Exception,), {})
    monkeypatch.setattr(runtime, "pd", SimpleNamespace(
        errors=PandasErrors,
        read_csv=Mock(side_effect=PandasErrors.EmptyDataError("empty")),
    ))
    errors, _ = validator._validate_csv_files(config)
    assert errors[0].code == "csv-invalid-format"
    runtime.pd.read_csv = Mock(side_effect=ValueError("bad csv"))
    errors, _ = validator._validate_csv_files(config)
    assert errors[0].code == "csv-parse-error"


def test_path_validator_rejects_invalid_values_and_file_directory_mismatches(tmp_path: Path) -> None:
    validator = PathValidator(base_dir=tmp_path)
    for value, code in [(None, "path-value-missing"), (3, "path-value-type"), (" ", "path-value-empty")]:
        _, actual, _ = validator._resolve_path(value)
        assert actual == code
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    assert validator._validate_directory_value(str(file_path), "x")[0].code == "path-not-dir"
    assert validator._validate_file_value(str(tmp_path), "x")[0].code == "path-not-file"
    assert validator._validate_directory_value("new", "x", allow_creation=True) == []
    assert validator._get_nested_value({"a": 1}, "a.b") is None


def test_pipeline_validator_handles_invalid_sections_reserved_and_dependencies() -> None:
    assert validate_pipeline({"tasks": [], "pipeline": "bad"}).errors
    result = validate_pipeline(
        {
            "tasks": {
                "cleanup_task": {},
                "extract": {"module": "standard_step.extraction.x", "params": {"fields": {"name": {}}}},
                "store": {"module": "standard_step.storage.store_metadata_as_json", "params": {"filename": "{name}"}},
            },
            "pipeline": ["cleanup_task", "store", "extract", "store", "", 4],
        }
    )
    codes = {issue.code for issue in result.errors + result.warnings}
    assert {"pipeline-reserved-internal-task-key", "pipeline-entry-invalid", "pipeline-duplicate-task"} <= codes


def test_performance_and_security_analyzers_cover_thresholds_and_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.config_check.performance_analyzer as performance
    analyzer = PerformanceAnalyzer()
    extraction = {"module": "standard_step.extraction.x", "params": {"fields": [{"name": str(i)} for i in range(51)]}}
    extraction["params"]["fields"] += [{"is_table": True} for _ in range(4)]
    result = analyzer.analyze_performance_impact({"tasks": {"e": extraction}, "pipeline": ["e"] * 31})
    assert result.errors
    assert result.warnings
    assert analyzer._analyze_extraction_complexity({"tasks": {"extract": {"module": "extraction", "params": {"fields": "bad"}}}}) == []
    info = analyzer._analyze_extraction_complexity({"tasks": {"extract": {"module": "extraction", "params": {"fields": [{"is_table": True}, {"is_table": True}]}}}})
    assert any(issue.code == "performance-multiple-tables" for issue in info)
    assert analyzer._analyze_rules_complexity({"tasks": {"rules": {"module": "rules", "params": {"csv_match": {"clauses": "bad"}}}}}) == []
    assert analyzer._analyze_pipeline_impact({"pipeline": "bad"}) == []
    many_rules = {f"r{i}": {"module": "rules"} for i in range(6)}
    many_rules["store"] = {"module": "storage"}
    pipeline_result = analyzer._analyze_pipeline_impact({"pipeline": list(many_rules), "tasks": many_rules})
    assert any(issue.code == "performance-multiple-rules-tasks" for issue in pipeline_result)
    summary = performance.PerformanceAnalysisResult()
    summary.add_issue(performance.PerformanceIssue("x", "x", "x", "info"))
    assert summary.all_issues
    assert performance.analyze_performance({}).all_issues == []

    security = SecurityValidator()
    result = security.validate_security({"web": {"upload_dir": "../tmp"}, "watch_folder": {"dir": "C:\\Windows\\Temp"}})
    assert result.errors or result.warnings
    monkeypatch.setattr(Path, "resolve", Mock(side_effect=OSError("cannot resolve")))
    failed = security._analyze_directory_permissions("x", "relative")
    assert failed[0].code == "security-directory-analysis-failed"
    assert security._validate_task_security({"tasks": {"bad": "task", "also_bad": {"params": "bad"}}}) == []
    import tools.config_check.security_validator as security_module
    assert security_module.validate_security({}).all_issues == []


def test_parameter_helper_validation_branches() -> None:
    errors: list[ParameterIssue] = []
    _validate_required_string("bad", "p", "name", errors)
    _validate_optional_string_param("bad", "p", "name", errors)
    _validate_optional_bool_param("bad", "p", "flag", errors)
    _validate_optional_positive_number_param("bad", "p", "count", errors)
    _validate_context_params("bad", "p", errors)
    _validate_required_string({}, "p", "name", errors)
    _validate_required_string({"name": 1}, "p", "name", errors)
    _validate_optional_string_param({"name": 1}, "p", "name", errors)
    _validate_optional_bool_param({"flag": "yes"}, "p", "flag", errors)
    _validate_optional_positive_number_param({"count": 0}, "p", "count", errors)
    _validate_context_params({"length": "x"}, "p", errors)
    _validate_housekeeping_params("bad", "p", errors)
    _validate_glm_schema_orders("bad", "p", errors)
    _validate_glm_schema_orders(
        {"one": {"schema_order": 1}, "two": {"schema_order": 1}, "nested": {"object_fields": {"child": {"schema_order": 0}}}},
        "p",
        errors,
    )
    _validate_rules_params("bad", "p", errors)
    _validate_rules_params({"match_column": "a", "update_field": "b", "csv_match": {"type": "", "clauses": "bad"}}, "p", errors)
    _validate_rules_params({"match_column": "a", "update_field": "b", "csv_match": {"type": "wrong", "clauses": [{"column": "", "from_context": "", "number": "yes"}]}}, "p", errors)
    assert _is_valid_field_type("Dict[str]") is False
    assert _split_top_level_type_args("List[str") == []
    assert _split_top_level_type_args("str]") == []
    assert errors


def test_parameter_invalid_url_port_and_path_error_details(monkeypatch, tmp_path: Path) -> None:
    from tools.config_check.parameter_validator import validate_parameters

    findings = validate_parameters(
        {"tasks": {"ocr": {"module": "standard_step.extraction.glm_ocr_extract", "class": "GlmOcrExtractTask", "params": {"ollama_host": "http://localhost:bad"}}}}
    )
    assert any(issue.code == "param-glm-invalid-host" for issue in findings.errors)

    validator = PathValidator(base_dir=tmp_path)
    resolved = tmp_path / "somewhere"
    monkeypatch.setattr(validator, "_resolve_path", lambda _value: (resolved, "path-value-type", "bad value"))
    assert validator._validate_directory_value(3, "dir")[0].details["path"] == str(resolved)
    assert validator._validate_file_value(3, "file")[0].details["path"] == str(resolved)


def test_runtime_file_validator_skips_invalid_shapes_and_checks_empty_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.config_check.runtime_file_validator as runtime

    validator = RuntimeFileValidator(tmp_path)
    assert validator._validate_reference_files({"tasks": "bad"}) == ([], [])
    config = {"tasks": {"scalar": "bad", "other": {"module": "custom", "params": "bad"}, "none": {"module": "rules", "params": {}}}}
    assert validator._validate_reference_files(config) == ([], [])
    assert validator._validate_directory_permissions({"tasks": ["bad"]}) == ([], [])
    monkeypatch.setattr(runtime, "PANDAS_AVAILABLE", True)
    monkeypatch.setattr(runtime, "pd", SimpleNamespace(errors=SimpleNamespace(EmptyDataError=Exception), read_csv=Mock()))
    assert validator._validate_csv_files({"tasks": "bad"}) == ([], [])
    assert validator._validate_csv_files({"tasks": {"scalar": "bad", "other": {"module": "custom", "params": "bad"}}}) == ([], [])

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    csv_config = {"tasks": {"rules": {"module": "standard_step.rules.update_reference", "params": {"reference_file": "empty.csv", "csv_match": {"clauses": ["bad", {"column": "missing"}]}, "update_field": "also_missing"}}}}
    class EmptyFrame:
        empty = True
        columns = []
    monkeypatch.setattr(runtime.pd, "read_csv", Mock(return_value=EmptyFrame()))
    errors, warnings = validator._validate_csv_files(csv_config)
    codes = {issue.code for issue in errors + warnings}
    assert {"csv-empty", "csv-missing-column"} <= codes

    readable_dir = tmp_path / "readable"
    readable_dir.mkdir()
    monkeypatch.setattr(runtime.os, "access", lambda _path, mode: mode == runtime.os.W_OK)
    access_errors = validator._validate_directory_access(readable_dir, "dir", "Directory")
    assert any(issue.code == "directory-not-readable" for issue in access_errors)
    monkeypatch.setattr(runtime.os, "access", lambda _path, _mode: False)
    access_errors = validator._validate_directory_access(readable_dir, "dir", "Directory")
    assert {issue.code for issue in access_errors} == {"directory-not-readable", "directory-not-writable"}


def test_config_validator_optional_passes_translate_all_finding_types(monkeypatch: pytest.MonkeyPatch) -> None:
    issue = SimpleNamespace(path="x", message="problem", code="test-code", details={})
    result = SimpleNamespace(errors=[issue], warnings=[issue], info=[issue])
    monkeypatch.setattr(validator_module, "validate_tasks", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(validator_module, "validate_parameters", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(validator_module, "validate_pipeline", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(validator_module, "validate_runtime_files", lambda *_args, **_kwargs: result)
    validator = ConfigValidator(check_files=True, performance_analysis=True, security_analysis=True)
    validator.path_validator.validate = lambda _config: result
    validator.performance_analyzer.analyze_performance_impact = lambda _config: result
    validator.security_validator.validate_security = lambda _config: result
    validated = validator.validate_config_data({"tasks": {}, "pipeline": []})
    assert len(validated.errors) >= 5
    assert len(validated.warnings) >= 5
    assert validator._run_task_reference_pass({"unrelated": True}).errors == []
    assert validator._run_parameter_pass({"unrelated": True}).errors == []
    assert validator._run_pipeline_pass({"unrelated": True}).errors == []


def test_pipeline_metadata_helper_skips_invalid_tasks_and_storage_tokens() -> None:
    import tools.config_check.pipeline_validator as pipeline

    metadata = pipeline._build_task_metadata(
        {
            "bad": "not-a-task",
            "fallback": {"params": {"fields": {"amount": {}}}},
            "storage": {"module": "standard_step.storage.store_metadata_as_json", "params": {"filename": "{amount}"}},
        }
    )
    assert metadata["classifications"]["fallback"] == "extraction"
    assert pipeline._classify_task(None, "LlamaCloudSplitTask") == "split"
    assert pipeline._is_storage_filename_path("storage", "") is False
    assert pipeline._is_table_storage_module(None) is False


def test_cli_command_helpers_cover_usage_and_cleanup_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("test-cli")
    assert cli.run_validate_command(_args(format="yaml"), logger) == 64
    monkeypatch.setattr(cli, "resolve_config_path", Mock(side_effect=ValueError("bad path")))
    assert cli.run_validate_command(_args(config="x"), logger) == 64

    path = tmp_path / "item.yaml"
    path.write_text("web: {}\n", encoding="utf-8")
    assert cli.run_validate_file_command(_args(path=None), logger) == 64
    assert cli.run_validate_file_command(_args(path=str(tmp_path / "missing.yaml")), logger) == 64
    assert cli.run_schema_command(_args(format="text"), logger) == 64
    assert cli._validate_stored_selectors(_args(all_stored=True, pipeline="p"))
    assert cli._validate_stored_selectors(_args(pipeline="p", review_schema="s"))
    assert cli._validate_stored_selectors(_args(draft=True))
    assert cli._validate_stored_selectors(_args(pipeline="p", version=0))
    assert cli.main(["unknown"]) == 64
    assert "Error" in capsys.readouterr().out


def test_cli_validate_stored_source_and_file_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("test-cli-stored")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("web: {}\n", encoding="utf-8")
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "legacy.yaml").write_text("{}", encoding="utf-8")

    class FakeStored:
        def __init__(self, _conn, runtime_config=None):
            self.runtime_config = runtime_config

        def validate_pipeline(self, *args, **kwargs):
            return ValidationResult(warnings=[ValidationMessage("stored", "ok", "stored")])

        def validate_review_schema(self, *args, **kwargs):
            return ValidationResult(warnings=[ValidationMessage("schema", "ok", "schema")])

        def validate_all(self):
            return ValidationResult()

        def validate_default(self):
            return ValidationResult()

    class FakeReporter:
        def __init__(self, *args, **kwargs):
            pass

        def add_validation_result(self, *args, **kwargs):
            pass

        def print_report(self):
            pass

        def determine_exit_code(self):
            return 0

    monkeypatch.setattr(cli, "ConfigValidator", lambda **kwargs: SimpleNamespace(validate=lambda _path: ValidationResult()))
    monkeypatch.setattr(cli, "ValidationReporter", FakeReporter)
    monkeypatch.setattr(cli, "load_document", lambda _path: {"database": {"path": "db.sqlite3"}, "pipeline": ["legacy"], "tasks": {"legacy": {}}, "schema": {"directories": ["schemas"]}})
    monkeypatch.setattr(cli, "configured_database_path", lambda *_args: tmp_path / "db.sqlite3")
    monkeypatch.setattr(cli, "open_readonly_database", lambda _path: nullcontext(object()))
    monkeypatch.setattr(cli, "validate_database_schema", lambda _conn: ValidationResult())
    monkeypatch.setattr(cli, "StoredSourceValidator", FakeStored)

    common = dict(config=str(config_path), base_dir=None, import_checks=False, check_files=False, performance_analysis=True, security_analysis=True)
    assert cli.run_validate_command(_args(**common, pipeline="p", draft=True), logger) == 0
    assert cli.run_validate_command(_args(**common, review_schema="s", version=1), logger) == 0
    assert cli.run_validate_command(_args(**common, all_stored=True), logger) == 0

    # The portable-file command closes a supplied database context even when validation fails.
    file_path = tmp_path / "portable.yaml"
    file_path.write_text("pipeline: []\n", encoding="utf-8")
    context = Mock()
    context.__enter__ = Mock(return_value=object())
    context.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(cli, "open_readonly_database", lambda _path: context)
    monkeypatch.setattr(cli, "validate_portable_file", Mock(side_effect=ValueError("bad portable file")))
    assert cli.run_validate_file_command(_args(path=str(file_path), kind="pipeline", config=str(config_path)), logger) == 1
    context.__exit__.assert_called_once()


def test_cli_remaining_usage_and_stored_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = logging.getLogger("test-cli-final")
    with patch.object(cli.Path, "resolve", side_effect=OSError("cannot resolve")):
        with pytest.raises(ValueError, match="Could not resolve config path"):
            cli.resolve_config_path("bad.yaml")

    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "ConfigValidator", lambda **_kwargs: SimpleNamespace(validate=lambda _path: ValidationResult()))
    monkeypatch.setattr(cli, "load_document", lambda _path: {})
    monkeypatch.setattr(cli, "configured_database_path", lambda *_args: None)
    assert cli.run_validate_command(_args(config=str(config_path), pipeline="stored", draft=True), logger) == 64

    class DefaultStored:
        def __init__(self, *_args, **_kwargs):
            pass

        def validate_default(self):
            return ValidationResult()

    monkeypatch.setattr(cli, "configured_database_path", lambda *_args: tmp_path / "db.sqlite3")
    monkeypatch.setattr(cli, "open_readonly_database", lambda _path: nullcontext(object()))
    monkeypatch.setattr(cli, "validate_database_schema", lambda _conn: ValidationResult())
    monkeypatch.setattr(cli, "StoredSourceValidator", DefaultStored)
    monkeypatch.setattr(cli, "ValidationReporter", lambda **_kwargs: SimpleNamespace(
        add_validation_result=lambda *_args, **_kwargs: None,
        print_report=lambda: None,
        determine_exit_code=lambda: 0,
    ))
    assert cli.run_validate_command(_args(config=str(config_path)), logger) == 0

    portable = tmp_path / "portable.yaml"
    portable.write_text("pipeline: []\n", encoding="utf-8")
    missing_config = tmp_path / "missing-config.yaml"
    assert cli.run_validate_file_command(
        _args(path=str(portable), kind="pipeline", config=str(missing_config)), logger
    ) == 64
    monkeypatch.setattr(cli, "load_document", lambda _path: {})
    monkeypatch.setattr(cli, "configured_database_path", lambda *_args: None)
    assert cli.run_validate_file_command(
        _args(path=str(portable), kind="pipeline", config=str(config_path)), logger
    ) == 64
    monkeypatch.setattr(cli, "load_document", lambda _path: {"database": {"path": "db.sqlite3"}})
    monkeypatch.setattr(cli, "configured_database_path", lambda *_args: tmp_path / "db.sqlite3")
    monkeypatch.setattr(cli, "validate_database_schema", lambda _conn: ValidationResult(
        errors=[ValidationMessage("schema", "bad", "schema-invalid")]
    ))
    monkeypatch.setattr(cli, "ValidationReporter", lambda **_kwargs: SimpleNamespace(
        add_validation_result=lambda *_args, **_kwargs: None,
        print_report=lambda: None,
        determine_exit_code=lambda: 1,
    ))
    assert cli.run_validate_file_command(
        _args(path=str(portable), kind="pipeline", config=str(config_path)), logger
    ) == 1
    capsys.readouterr()

    monkeypatch.setattr(cli.sys, "argv", ["config-check", "unknown"])
    assert cli.main() == 64

    class ParserWithoutCommand:
        def parse_args(self, _argv):
            return SimpleNamespace()

        def print_usage(self, _stream):
            pass

    monkeypatch.setattr(cli, "create_parser", lambda: ParserWithoutCommand())
    assert cli.main(["anything"]) == 64
    class ParserWithUnknownCommand:
        def parse_args(self, _argv):
            return SimpleNamespace(command="mystery", verbose=False)

        def print_usage(self, _stream):
            pass

    monkeypatch.setattr(cli, "create_parser", lambda: ParserWithUnknownCommand())
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: logger)
    assert cli.main(["anything"]) == 64
    class QuietLogger:
        handlers: list = []

        def setLevel(self, _level):
            pass

        def removeHandler(self, _handler):
            pass

        def addHandler(self, _handler):
            pass

        def info(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(logging, "getLogger", lambda *_args: QuietLogger())
    monkeypatch.setattr(sys, "exit", lambda _code: None)
    monkeypatch.setattr(sys, "argv", ["config-check", "unknown"])
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*tools\.config_check\.__main__.*found in sys\.modules.*",
            category=RuntimeWarning,
        )
        runpy.run_module("tools.config_check.__main__", run_name="__main__")


def test_cli_reporter_info_only_summary_branch() -> None:
    reporter = ValidationReporter()
    reporter.add_finding("info", FindingLevel.INFO, "informational")
    assert reporter.generate_summary() == "Validation passed with 0 errors, 0 warnings, 1 info message."


def test_pipeline_storage_token_duplicate_suppression(monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.config_check.pipeline_validator as pipeline

    config = {
        "tasks": {
            "extract": {"module": "standard_step.extraction.x"},
            "store": {"module": "standard_step.storage.store_metadata_as_json"},
        },
        "pipeline": ["extract", "store"],
    }
    assert not validate_pipeline(
        {
            "tasks": {
                "extract": {"module": "standard_step.extraction.x", "params": {"fields": {"name": {}}}},
                "store": {"module": "standard_step.storage.store_metadata_as_json", "params": {"other": "{name}", "filename": "{name}"}},
            },
            "pipeline": ["extract", "store"],
        }
    ).errors

    usage = pipeline.TokenUsage("store", "tasks.store.params.filename", {"table"})
    metadata = {
        "known_fields": {"table"},
        "tokens_by_path": [usage, usage],
        "per_task_tokens": {"extract": set(), "store": {"table"}},
        "classifications": {"extract": "extraction", "store": "storage"},
        "metadata_producers": {"extract"},
        "module_names": {"extract": "standard_step.extraction.x", "store": "standard_step.storage.store_metadata_as_json"},
        "scalar_fields": set(),
        "table_fields": {"table"},
    }
    monkeypatch.setattr(pipeline, "_build_task_metadata", lambda _tasks: metadata)
    result = pipeline.validate_pipeline(config)
    assert len([issue for issue in result.warnings if issue.code == "pipeline-storage-filename-non-scalar"]) == 1


def test_task_validator_structure_and_import_short_circuits() -> None:
    assert _validate_task_structure("broken", "not a mapping")[0].code == "task-definition-not-mapping"
    issues = _validate_task_structure("broken", {"module": None, "class": ""})
    assert {issue.code for issue in issues} == {"task-import-invalid-module", "task-import-invalid-class"}
    assert _validate_task_imports("broken", {"module": None, "class": "C"}) == []
    assert _validate_task_imports("broken", {"module": "m", "class": ""}) == []


def test_optional_pandas_import_paths_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def fail_pandas(name, *args, **kwargs):
        if name == "pandas":
            raise ImportError("pandas unavailable")
        return original_import(name, *args, **kwargs)

    import tools.config_check.rules_task_validator as rules
    import tools.config_check.runtime_file_validator as runtime
    with monkeypatch.context() as context:
        context.setattr(builtins, "__import__", fail_pandas)
        importlib.reload(rules)
        importlib.reload(runtime)
        assert rules.PANDAS_AVAILABLE is False
        assert runtime.PANDAS_AVAILABLE is False
    importlib.reload(rules)
    importlib.reload(runtime)


def test_runtime_validator_invalid_nested_shapes_are_skipped(tmp_path: Path) -> None:
    validator = RuntimeFileValidator(tmp_path)
    config = {
        "tasks": {
            "scalar": "bad",
            "rules_reference": {"module": "standard_step.rules.update", "params": "bad"},
            "rules_missing": {"module": "standard_step.rules.update", "params": {}},
        }
    }
    assert validator._validate_reference_files(config) == ([], [])
    assert validator._validate_directory_permissions(config) == ([], [])
    assert validator._validate_csv_files(config)[0] == []
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportOptionalSubscript=false
