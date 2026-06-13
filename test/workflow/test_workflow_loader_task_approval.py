from __future__ import annotations

from pathlib import Path

import pytest

from modules.workflow_loader import WorkflowLoader
from test.helpers_sqlite import TempConfig


@pytest.fixture(autouse=True)
def reset_workflow_loader_singleton():
    WorkflowLoader._instance = None
    yield
    WorkflowLoader._instance = None


def test_workflow_loader_imports_approved_task(tmp_path: Path) -> None:
    config = TempConfig(tmp_path / "app.sqlite3", {})
    loader = WorkflowLoader(config)

    task_class = loader._import_task_class("standard_step.review.review_gate", "ReviewGateTask")

    assert task_class.__name__ == "ReviewGateTask"


def test_workflow_loader_blocks_unapproved_task_before_import(tmp_path: Path, monkeypatch) -> None:
    config = TempConfig(tmp_path / "app.sqlite3", {})
    loader = WorkflowLoader(config)
    calls: list[str] = []

    def fail_if_called(module_name: str):
        calls.append(module_name)
        raise AssertionError("importlib.import_module should not be called")

    monkeypatch.setattr("modules.workflow_loader.importlib.import_module", fail_if_called)

    with pytest.raises(SystemExit) as excinfo:
        loader._import_task_class("untrusted.module", "BadTask")

    assert excinfo.value.code == 1
    assert calls == []
