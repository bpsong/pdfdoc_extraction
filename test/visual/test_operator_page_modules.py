"""Behavior checks for modular operator pages."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


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
        ["node", "-e", script], cwd=ROOT, check=True,
        capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def test_upload_model_preserves_file_and_request_limits() -> None:
    result = _run_module(
        "upload-process/model.js",
        """
        const model = module.createModel({maxUploadMb: 1, maxUploadBytes: 1048576,
            maxUploadFiles: 2, maxUploadRequestMb: 1,
            maxUploadRequestBytes: 1048576});
        const makeFile = (name, type, size) => ({name, type, size, lastModified: 1});
        const valid = makeFile('qa.pdf', 'application/pdf', 100);
        return {
            valid: model.validateFile(valid),
            badName: model.validateFile(makeFile('qa.txt', 'application/pdf', 100)),
            badType: model.validateFile(makeFile('qa.pdf', 'text/plain', 100)),
            tooLarge: model.validateFile(makeFile('qa.pdf', 'application/pdf', 1048577)),
            tooMany: model.validateBatch([valid, valid, valid].map(file => ({file}))),
            requestTooLarge: model.validateBatch([
                {file: makeFile('large.pdf', 'application/pdf', 1040000)}]),
            key: model.fileKey(valid), formatted: model.formatBytes(1536),
        };
        """,
    )
    assert result["valid"] == ""
    assert "PDF" in result["badName"]
    assert "non-PDF" in result["badType"]
    assert "exceeds" in result["tooLarge"]
    assert "at most 2" in result["tooMany"]
    assert "request limit" in result["requestTooLarge"]
    assert result["key"] == "qa.pdf:100:1"
    assert result["formatted"] == "1.5 KB"


def test_upload_transport_keeps_csrf_identity_and_abort_behavior() -> None:
    result = _run_module(
        "upload-process/api.js",
        """
        const requests = [];
        class PendingRequest extends EventTarget {
            constructor() { super(); this.upload = new EventTarget(); this.headers = {}; }
            open(method, url) { this.method = method; this.url = url; }
            setRequestHeader(name, value) { this.headers[name] = value; }
            send() { requests.push(this); }
            abort() { this.dispatchEvent(new Event('abort')); }
        }
        globalThis.XMLHttpRequest = PendingRequest;
        const api = module.createApi({csrfHeaders: () => ({'X-CSRF-Token': 'qa'})},
            () => {}, () => 'synthetic-submission');
        const pending = api.uploadBatchRequest({});
        api.cancelUpload();
        let errorName = '';
        try { await pending; } catch (error) { errorName = error.name; }
        return {method: requests[0].method, url: requests[0].url,
            headers: requests[0].headers, errorName};
        """,
    )
    assert result["method"] == "POST"
    assert result["url"] == "/api/batches/upload"
    assert result["headers"]["Idempotency-Key"] == "synthetic-submission"
    assert result["headers"]["X-CSRF-Token"] == "qa"
    assert result["errorName"] == "AbortError"


def test_watch_folder_transport_preserves_same_origin_and_csrf() -> None:
    result = _run_module(
        "watch-folders/api.js",
        """
        let request = null;
        const fetchImpl = async (url, options) => {
            request = {url, options};
            return {ok: true, json: async () => ({bindings: []})};
        };
        const api = module.createApi(
            {csrfHeaders: method => method === 'PATCH'
                ? {'X-CSRF-Token': 'qa'} : {}}, fetchImpl);
        await api.request('/api/admin/watch-folder-bindings/qa', 'PATCH',
            {enabled: false});
        return request;
        """,
    )
    assert result["url"] == "/api/admin/watch-folder-bindings/qa"
    assert result["options"]["credentials"] == "same-origin"
    assert result["options"]["headers"]["X-CSRF-Token"] == "qa"
    assert json.loads(result["options"]["body"]) == {"enabled": False}


def test_operator_entries_share_one_release_version() -> None:
    for template_name, folder, version in (
        ("upload_process", "upload-process", "controller-modularization-7a"),
        ("processing_overview", "processing-overview", "frontend-hardening-8"),
        ("reports", "reports", "controller-modularization-7a"),
        ("failures", "failures", "controller-modularization-7a"),
        ("review_queue", "review-queue", "controller-modularization-7a"),
        ("extraction_results", "extraction-results", "controller-modularization-7a"),
        ("task_catalog", "task-catalog", "controller-modularization-7a"),
        ("admin_dashboard", "admin-dashboard", "controller-modularization-7a"),
        ("admin_audit", "admin-audit", "controller-modularization-7a"),
        ("config_validation", "config-validation", "controller-modularization-7a"),
        ("settings", "settings", "controller-modularization-7a"),
        ("split_results", "split-results", "controller-modularization-7a"),
        ("watch_folders", "watch-folders", "controller-modularization-7a"),
    ):
        template = (ROOT / "web/templates" / f"{template_name}.html").read_text(encoding="utf-8")
        entry = (ROOT / "web/static/js" / folder / "index.js").read_text(encoding="utf-8")
        controller = (ROOT / "web/static/js" / folder / "controller.js").read_text(encoding="utf-8")
        assert f"/static/js/{folder}/index.js?v={version}" in template
        assert f"./controller.js?v={version}" in entry
        assert controller.count(version) in {2, 3}
        assert "window.DocFlow.apiGet(" not in controller
        assert "window.DocFlow.apiPost(" not in controller
