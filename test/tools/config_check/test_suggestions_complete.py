"""Contract tests for every config-check suggestion handler."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tools.config_check import suggestions


@pytest.mark.parametrize("code", sorted(suggestions._SUGGESTION_HANDLERS))
def test_registered_suggestions_are_actionable(code: str) -> None:
    """Every registered code produces a useful, non-empty message."""
    details = {
        "config_key": "tasks.example.params.value",
        "path": "C:/tmp/example",
        "task_name": "example",
        "field": "supplier",
        "token": "supplier",
        "index": 0,
        "fields": ["items"],
        "dangerous_patterns": [".."],
        "field_count": 21,
        "recommended_max": 20,
        "table_field_count": 2,
        "task_count": 16,
        "extraction_task_count": 2,
        "rules_task_count": 2,
    }

    message = suggestions.get_suggestion(code, details)

    assert isinstance(message, str)
    assert message


def test_suggestion_helpers_cover_default_and_present_details() -> None:
    """Optional detail values select both the concise and contextual wording."""
    assert suggestions._describe_config_key({}) == "this setting"
    assert suggestions._describe_config_key({"config_key": "x"}) == "'x'"
    assert suggestions._describe_clause({}) == "each clause"
    assert suggestions._describe_clause({"index": 2}) == "clause[2]"
    assert "existing directory" in suggestions._suggest_create_dir({})
    assert "watch folder directory" in suggestions._suggest_watch_folder({})
    assert "referenced file" in suggestions._suggest_create_file({})
    assert "the storage task" in suggestions._suggest_pipeline_storage({})
    assert "table fields" in suggestions._suggest_multiple_tables({})
    assert "the path" in suggestions._suggest_fix_path_traversal({})
    assert suggestions._suggest_required_param({"config_key": "x"}) == "Provide a value for 'x'."


def test_get_suggestion_handles_missing_and_broken_handlers() -> None:
    """Unknown codes and handler failures are intentionally non-fatal."""
    assert suggestions.get_suggestion(None) is None
    assert suggestions.get_suggestion("unknown-code") is None

    with patch.dict(
        suggestions._SUGGESTION_HANDLERS,
        {"broken": lambda _details: (_ for _ in ()).throw(RuntimeError("boom"))},
    ):
        assert suggestions.get_suggestion("broken") is None
