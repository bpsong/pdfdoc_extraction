"""Performance and deployment-hardening contracts for frontend modules."""

from __future__ import annotations

import json
import subprocess
import shutil
import time
from pathlib import Path

import pytest

from tools.frontend_release_check import bump_feature, check_features

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page

from test.visual.test_schema_review_visual import page, visual_app


ROOT = Path(__file__).resolve().parents[2]


def _run_module(path: str, expression: str) -> object:
    module_path = (ROOT / "web/static/js" / path).as_posix()
    script = f"""
        const fs = require('node:fs');
        const source = fs.readFileSync({json.dumps(module_path)}, 'utf8');
        const url = 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
        import(url).then(async (module) => {{
            const result = await (async () => {{ {expression} }})();
            process.stdout.write(JSON.stringify(result));
        }}).catch((error) => {{ console.error(error); process.exit(1); }});
    """
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_polling_suspends_when_hidden_and_never_overlaps() -> None:
    result = _run_module(
        "polling.js",
        """
        const listeners = {};
        const documentRef = {
            hidden: false,
            addEventListener: (name, callback) => { listeners[name] = callback; },
            removeEventListener: (name) => { delete listeners[name]; },
        };
        const timers = new Map();
        let nextTimer = 1;
        const windowRef = {
            setInterval: callback => { const id = nextTimer++; timers.set(id, callback); return id; },
            clearInterval: id => timers.delete(id),
        };
        let calls = 0;
        let release;
        const pending = new Promise(resolve => { release = resolve; });
        const poller = module.createPollingController({
            task: async () => { calls += 1; await pending; },
            intervalMs: 3000,
            windowRef,
            documentRef,
        });
        poller.setActive(true);
        const first = poller.runNow();
        const overlapped = await poller.runNow();
        const timersWhileVisible = timers.size;
        documentRef.hidden = true;
        listeners.visibilitychange();
        const timersWhileHidden = timers.size;
        release();
        await first;
        documentRef.hidden = false;
        listeners.visibilitychange();
        await Promise.resolve();
        const timersAfterResume = timers.size;
        poller.stop();
        return {calls, overlapped, timersWhileVisible, timersWhileHidden,
            timersAfterResume, listenersAfterStop: Object.keys(listeners).length};
        """,
    )
    assert result == {
        "calls": 2,
        "overlapped": False,
        "timersWhileVisible": 1,
        "timersWhileHidden": 0,
        "timersAfterResume": 1,
        "listenersAfterStop": 0,
    }


def test_processing_controller_uses_shared_polling_boundary() -> None:
    source = (ROOT / "web/static/js/processing-overview/controller.js").read_text(
        encoding="utf-8"
    )
    assert "createPollingController" in source
    assert "setInterval(" not in source
    assert "visibilitychange" not in source
    assert "pagehide" in source


def test_feature_release_graphs_have_consistent_cache_versions() -> None:
    assert check_features(ROOT) == []


def test_feature_release_can_be_bumped_independently(tmp_path: Path) -> None:
    feature = "processing-overview"
    template_dir = tmp_path / "web/templates"
    module_dir = tmp_path / "web/static/js" / feature
    template_dir.mkdir(parents=True)
    module_dir.mkdir(parents=True)
    shutil.copy(ROOT / "web/templates/processing_overview.html", template_dir)
    for source in (ROOT / "web/static/js" / feature).glob("*.js"):
        shutil.copy(source, module_dir)

    bump_feature(feature, "qa-release", tmp_path)

    template = (template_dir / "processing_overview.html").read_text(encoding="utf-8")
    assert f"/{feature}/index.js?v=qa-release" in template
    for module_path in module_dir.glob("*.js"):
        for line in module_path.read_text(encoding="utf-8").splitlines():
            if "from './" in line or "import './" in line:
                assert "?v=qa-release" in line


def test_frontend_performance_budget(page: Page, visual_app: dict[str, str]) -> None:
    """Keep representative navigation and interaction costs bounded."""

    cdp = page.context.new_cdp_session(page)
    cdp.send("Performance.enable")
    page.goto(f"{visual_app['base_url']}/app/upload")
    page.locator("#pipeline-version-list input[type=radio]").first.wait_for()
    upload = page.evaluate(
        """() => {
            const navigation = performance.getEntriesByType('navigation')[0];
            const resources = performance.getEntriesByType('resource')
                .filter(item => item.name.includes('/static/'));
            return {
                domContentLoadedMs: navigation.domContentLoadedEventEnd,
                loadMs: navigation.loadEventEnd,
                staticDecodedBytes: resources.reduce(
                    (total, item) => total + item.decodedBodySize, 0),
                staticRequests: resources.length,
                domNodes: document.getElementsByTagName('*').length,
            };
        }"""
    )
    start = time.perf_counter()
    page.locator("#pipeline-version-list input[type=radio]").first.check()
    interaction_ms = (time.perf_counter() - start) * 1000
    chrome_metrics = {
        item["name"]: item["value"] * 1000
        for item in cdp.send("Performance.getMetrics")["metrics"]
        if item["name"] in {"ScriptDuration", "TaskDuration", "LayoutDuration"}
    }

    page.goto(f"{visual_app['base_url']}/app/batches/{visual_app['batch_id']}")
    page.locator("#processing-table-body tr").first.wait_for()
    processing = page.evaluate(
        """() => ({
            domNodes: document.getElementsByTagName('*').length,
            rows: document.querySelectorAll('#processing-table-body tr').length,
            staticDecodedBytes: performance.getEntriesByType('resource')
                .filter(item => item.name.includes('/static/'))
                .reduce((total, item) => total + item.decodedBodySize, 0),
        })"""
    )
    metrics = {"upload": upload, "interactionMs": interaction_ms,
               "chromeMs": chrome_metrics,
               "processing": processing}
    print(f"PHASE8_METRICS={json.dumps(metrics, sort_keys=True)}")

    assert upload["domContentLoadedMs"] < 2_000
    assert upload["loadMs"] < 3_000
    assert upload["staticDecodedBytes"] < 1_500_000
    assert upload["domNodes"] < 1_500
    assert interaction_ms < 750
    assert chrome_metrics["ScriptDuration"] < 750
    assert chrome_metrics["LayoutDuration"] < 250
    assert processing["domNodes"] < 1_500
