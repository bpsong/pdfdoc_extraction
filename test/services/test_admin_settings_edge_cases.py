from unittest.mock import Mock

import pytest

from modules.services.admin_settings_service import (
    AdminSettingsError,
    AdminSettingsService,
    PipelineConfigError,
    PipelineDryRunService,
    _audit_event_payload,
    _default_for_setting,
    _first_matching_step,
    _first_step,
    _float_between,
    _get_nested,
    _normalize_categories,
    _positive_float,
    _positive_int,
    _redact_secrets,
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

    steps = [{"class": "ExtractPdfTask"}, "bad"]
    assert _first_step(steps, "Missing") is None
    assert _first_matching_step(steps, lambda step: step.get("class") == "ExtractPdfTask") == steps[0]
    assert _redact_secrets({"api_key": "secret", "nested": [{"token": "x"}]}) == {
        "api_key": "[REDACTED]",
        "nested": [{"token": "[REDACTED]"}],
    }


def test_pipeline_dry_run_invalid_models_and_not_configured_summaries(monkeypatch):
    service = object.__new__(PipelineDryRunService)
    with pytest.raises(PipelineConfigError, match="Dry-run model"):
        service.run({"model": []})
    service.config_manager = Mock()
    service.conn = Mock()
    pipeline_service = Mock()
    pipeline_service.get_pipeline.return_value = {
        "draft": None,
        "active": {"model": []},
    }
    monkeypatch.setattr(
        "modules.services.admin_settings_service.PipelineConfigService",
        Mock(return_value=pipeline_service),
    )
    with pytest.raises(PipelineConfigError, match="pipeline model"):
        service.run({})

    assert service._split_summary([], {}) == {
        "status": "not_configured",
        "decisions": [],
    }
    assert service._extraction_summary([], {})["status"] == "not_configured"
    assert service._review_gate_summary([], {}) == {
        "status": "not_configured",
        "review_required": False,
        "reasons": [],
    }

    review = service._review_gate_summary(
        [{"class": "ReviewGateTask", "params": {"confidence_threshold": 0.8}}],
        {
            "extraction_fields": [
                {"field_key": "missing", "confidence": None},
                {"field_key": "invalid", "confidence": "bad"},
            ]
        },
    )
    assert review["review_required"] is True
