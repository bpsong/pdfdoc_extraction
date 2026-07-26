"""Unit tests for versioned admin page state helpers."""

from modules.services.versioned_admin_view_models import (
    group_findings,
    lifecycle_actions,
    revision_conflict_view,
    schema_selector_options,
    version_label,
)


def test_lifecycle_actions_and_revision_conflict_are_fail_closed():
    assert lifecycle_actions("inactive", has_published_version=False) == {
        "can_activate": False,
        "can_deactivate": False,
        "can_archive": True,
        "can_edit": True,
        "can_publish": True,
    }
    conflict = revision_conflict_view(
        {"message": "Stale", "current": {"revision": 4}}
    )
    assert conflict["reload_required"] is True
    assert conflict["overwrite_allowed"] is False
    assert conflict["current"]["revision"] == 4


def test_schema_selectors_and_finding_groups_preserve_exact_identity():
    versions = [
        {
            "id": "schema-v2",
            "schema_key": "invoice",
            "version_number": 2,
            "content_hash": "a" * 64,
        }
    ]
    options = schema_selector_options(versions)
    assert options == [
        {
            "value": "schema-v2",
            "label": "invoice · v2 · aaaaaaaaaa",
            "content_hash": "a" * 64,
            "version_number": 2,
        }
    ]
    assert version_label(versions[0], kind="schema") == options[0]["label"]
    assert group_findings(
        [
            {"severity": "warning", "path": "one"},
            {"severity": "error", "path": "two"},
        ]
    ) == {
        "warning": [{"severity": "warning", "path": "one"}],
        "error": [{"severity": "error", "path": "two"}],
    }
