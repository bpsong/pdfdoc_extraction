"""Regression checks for browser-driven sliding session renewal."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_app_javascript_renews_session_only_from_user_activity() -> None:
    source = (ROOT / "web/static/js/app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/session/refresh"' in source
    assert "SESSION_REFRESH_INTERVAL_MS = 30_000" in source
    assert '["pointerdown", "keydown", "touchstart", "scroll"]' in source
    assert "setInterval(refreshSessionAfterActivity" not in source
