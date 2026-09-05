from pathlib import Path
from unittest.mock import Mock

import pytest

import modules.services.admin_settings_service as admin_module
from modules.services.admin_settings_service import (
    AdminSettingsError,
    AdminSettingsService,
    _audit_event_payload,
    _default_for_setting,
    _float_between,
    _get_nested,
    _normalize_categories,
    _positive_float,
    _positive_int,
    _set_nested,
    _settings_groups,
    _string_list,
    _summary_for_findings,
    _threshold_map,
)


def test_admin_setting_value_normalizers_cover_invalid_inputs():
    with pytest.raises(AdminSettingsError, match="number between 0 and 1"):
        _float_between("bad", "threshold")
    with pytest.raises(AdminSettingsError, match="between 0 and 1"):
        _float_between(2, "threshold")
    with pytest.raises(AdminSettingsError, match="positive number"):
        _positive_float("bad", "timeout")
    with pytest.raises(AdminSettingsError, match="positive number"):
        _positive_float(0, "timeout")
    with pytest.raises(AdminSettingsError, match="positive integer"):
        _positive_int("bad", "count")
    with pytest.raises(AdminSettingsError, match="positive integer"):
        _positive_int(0, "count")
    assert _threshold_map(None, "thresholds") == {}
    with pytest.raises(AdminSettingsError, match="must be an object"):
        _threshold_map([], "thresholds")
    assert _string_list(None) == []
    assert _string_list("a, b") == ["a", "b"]
    with pytest.raises(AdminSettingsError, match="list of strings"):
        _string_list({})


def test_category_and_setting_helpers_cover_fallbacks():
    assert _normalize_categories(None) == []
    with pytest.raises(AdminSettingsError, match="must be a list"):
        _normalize_categories({})
    assert _normalize_categories(["invoice"]) == [
        {"name": "invoice", "description": ""}
    ]
    with pytest.raises(AdminSettingsError, match=r"categories\[0\]"):
        _normalize_categories([1])
    with pytest.raises(AdminSettingsError, match="name is required"):
        _normalize_categories([{}])

    assert _default_for_setting({"type": "bool"}) is False
    assert _default_for_setting({"type": "positive_int"}) == 1
    assert _default_for_setting({"type": "string"}) == ""
    assert _default_for_setting({"default": "configured", "type": "string"}) == "configured"

    config = {}
    _set_nested(config, "a.b.c", 1)
    assert _get_nested(config, "a.b.c") == 1
    assert _get_nested(config, "a.missing", "default") == "default"


def test_admin_payload_audit_summary_and_step_helpers():
    service = object.__new__(AdminSettingsService)
    with pytest.raises(AdminSettingsError, match="must be an object"):
        service._payload_settings({"settings": []})
    with pytest.raises(AdminSettingsError, match="cannot be empty"):
        service._normalize_admin_setting("ui.app_name", "")
    with pytest.raises(AdminSettingsError, match="review_scope"):
        service._normalize_review_gate_rules({"review_scope": "bad"})
    with pytest.raises(AdminSettingsError, match="resume_policy"):
        service._normalize_review_gate_rules({"resume_policy": "bad"})
    assert service._task_params({"tasks": {}}, "MissingTask") == (None, {}, [])

    grouped = _settings_groups(
        {
            "ui.app_name": {"value": "App", "group": "UI"},
            "review.timeout": {"value": 1, "group": "Review"},
        }
    )
    assert {group["name"] for group in grouped} == {"ui", "review", "validation"}
    assert _audit_event_payload({"event_json": '"value"'})["event"] == {
        "value": "value"
    }
    assert _summary_for_findings(None) == {"errors": 0, "warnings": 0}
    assert _summary_for_findings(
        [{"severity": "error"}, {"severity": "warning"}]
    ) == {"errors": 1, "warnings": 1}


def test_admin_settings_remaining_defensive_helpers(tmp_path: Path, monkeypatch) -> None:
    service = object.__new__(AdminSettingsService)
    with pytest.raises(AdminSettingsError, match="allow_uncategorized"):
        service._normalize_split_settings({"allow_uncategorized": "invalid"})

    config = {"tasks": {"split": {"class": "LlamaCloudSplitTask", "params": {"old": 1}}}}
    service._update_task_params(config, "LlamaCloudSplitTask", {"old": None, "new": 2})
    assert config["tasks"]["split"]["params"] == {"new": 2}
    service._update_task_params(
        {"tasks": {"bad": {"class": "LlamaCloudSplitTask", "params": []}}},
        "LlamaCloudSplitTask",
        {"new": 2},
    )

    service.config_manager = object()
    service._write_active_config({"x": 1})
    service.config_manager = type("Config", (), {"_config_path": str(tmp_path / "config.yaml")})()
    service._write_active_config({"x": 1})
    assert service.config_manager._config_path and (tmp_path / "config.yaml").exists()

    service.config_manager = type("Config", (), {"config": {}, "_values": {}, "values": {}})()
    service._replace_in_memory_config({"x": 1})
    assert service.config_manager.config == {"x": 1}
    assert service.config_manager._values == {"x": 1}
    assert service.config_manager.values == {"x": 1}

    assert service._split_adapter_status({"enabled": False}, api_key_configured=False)["status"] == "disabled"
    assert service._split_adapter_status({"enabled": True}, api_key_configured=False)["status"] == "missing_api_key"
    assert service._split_adapter_status({"enabled": True}, api_key_configured=True)["status"] == "missing_configuration"
    monkeypatch.setitem(__import__("sys").modules, "llama_cloud", None)
    assert service._split_adapter_status(
        {"enabled": True, "categories": [{"name": "invoice"}]}, api_key_configured=True
    )["status"] == "package_missing"

    assert AdminSettingsService._contains_secret_key({"nested": [{"token": "secret"}]}) is True
    monkeypatch.setattr(admin_module.ConfigValidationService, "validate_active_config", lambda self: (_ for _ in ()).throw(ValueError("bad config")))
    summary = admin_module.AdminSummaryService.__new__(admin_module.AdminSummaryService)
    summary.config_manager = object()
    assert summary._safe_active_config_validation()["valid"] is False
    monkeypatch.setattr(admin_module.ConfigValidationService, "validate_all_schemas", lambda self: (_ for _ in ()).throw(TypeError("bad schemas")))
    assert summary._safe_schema_validation()["valid"] is False

    assert _get_nested({"a": 1}, "a.b", "fallback") == "fallback"
    target = {"a": "not-a-map"}
    _set_nested(target, "a.b", 2)
    assert target == {"a": {"b": 2}}
