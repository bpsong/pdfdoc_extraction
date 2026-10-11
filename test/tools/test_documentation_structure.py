"""Verify audience documentation navigation and historical preservation."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
SNAPSHOT = DOCS / "history" / "archive" / "2026-10-10"
EXPECTED: dict[str, list[str]] = {
    "operator": [
        "README", "quick-start", "submitting-documents", "monitoring-and-results",
        "reviewing-extracted-data", "manual-splitting", "troubleshooting",
    ],
    "admin": [
        "README", "managing-pipelines", "configuring-extraction",
        "managing-review-forms", "managing-watch-folders", "accounts-and-settings",
        "validation-and-audit", "archiving-and-retention", "task-guide",
    ],
    "architecture": [
        "README", "runtime-and-boundaries", "workflow-and-state",
        "persistence-and-artifacts", "configuration-and-versioning",
        "security-and-trust", "decisions-and-constraints",
    ],
    "developer": [
        "README", "development-setup", "codebase-map", "execution-walkthroughs",
        "backend-development", "frontend-development", "task-development",
        "database-migrations", "testing-and-verification", "performance",
    ],
    "it-support": [
        "README", "installation-and-provider-setup", "deployment-and-upgrades",
        "configuration-and-access", "starting-and-stopping", "monitoring-and-logs",
        "backup-and-restore", "account-recovery", "incident-runbooks",
        "config-check-troubleshooting",
    ],
    "reference": [
        "README", "glossary", "deployment-configuration",
        "pipeline-definition-format", "review-schema-format", "api-contracts",
        "tasks/README", "tasks/llamacloud-extraction", "tasks/glm-ocr-extraction",
        "tasks/liteparse-extraction", "tasks/splitting", "tasks/review-gate",
        "tasks/storage-and-archiving", "tasks/rules-context-housekeeping",
    ],
}


def _prose(text: str) -> str:
    """Remove fenced code so code examples are not treated as navigation."""
    lines = []
    fence: str | None = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def _anchors(text: str) -> set[str]:
    """Collect GitHub-style heading IDs and explicit compatibility anchors."""
    prose = _prose(text)
    anchors = set(re.findall(r'<a\s+id="([^"]+)"', prose))
    counts: dict[str, int] = {}
    for title in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose, re.MULTILINE):
        title = re.sub(r"<[^>]+>", "", title).lower()
        anchor = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        count = counts.get(anchor, 0)
        counts[anchor] = count + 1
        anchors.add(anchor + (f"-{count}" if count else ""))
    return anchors


def _links(path: Path) -> list[tuple[Path, str]]:
    """Resolve local Markdown links while excluding web/app URLs."""
    result = []
    for raw in re.findall(r"\]\(([^)\n]+)\)", _prose(path.read_text(encoding="utf-8-sig"))):
        raw = raw.strip().strip("<>")
        url = urlsplit(raw)
        if url.scheme or raw.startswith("/"):
            continue
        destination = (path.parent / unquote(url.path)).resolve() if url.path else path.resolve()
        result.append((destination, unquote(url.fragment)))
    return result


def _current_pages() -> list[Path]:
    """Include reading copies and compatibility pages, excluding exact snapshots."""
    return sorted(p for p in DOCS.rglob("*.md") if SNAPSHOT / "docs" not in p.parents)


def test_documentation_parser_ignores_code_and_understands_anchors(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text(
        '# A `field` & status\n\n## Repeated\n\n## Repeated\n'
        '<a id="old-section"></a>\n',
        encoding="utf-8",
    )
    source = tmp_path / "source.md"
    source.write_text(
        '[Read](target.md#a-field--status)\n[Old](target.md#old-section)\n'
        '```markdown\n[Example](missing.md)\n```\n[Web](https://example.com)\n'
        '[App](/app/upload)\n', encoding="utf-8",
    )
    assert _links(source) == [(target, "a-field--status"), (target, "old-section")]
    assert {"a-field--status", "repeated", "repeated-1", "old-section"} <= _anchors(
        target.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("folder,names", EXPECTED.items())
def test_every_agreed_audience_page_exists_and_is_substantive(
    folder: str, names: list[str]
) -> None:
    for name in names:
        path = DOCS / folder / f"{name}.md"
        assert path.is_file(), f"Missing agreed documentation: {path.relative_to(ROOT)}"
        text = path.read_text(encoding="utf-8")
        assert len(text.split()) >= 100, f"Incomplete guide: {path.relative_to(ROOT)}"
        assert "| Audience |" in text and "| Owner |" in text
        assert "| Status | Current |" in text
        assert "repository/source review; no live deployment check" in text
        assert not re.search(r"\b(TODO|TBD|FIXME)\b|migration://", text)


def test_original_snapshot_is_complete_and_unchanged() -> None:
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_date"] == "2026-10-10"
    originals = {
        "change-summary-2026-09-05.md", "config_check_troubleshooting.md",
        "design_architecture.md", "frontend_deployment.md", "liteparse_extract_task.md",
        "liteparse_pipeline_validation.md", "manual_split_task.md", "manual_split_validation.md",
        "performance_benchmark.md", "pipeline_retention_admin_guide.md",
        "review_schema_admin_guide.md", "technical_operations_reference.md", "user_guide.md",
        "watch_folder_admin_reference.md", "audits/admin-navigation-2026-07-03/audit.md",
        *[f"audits/admin-navigation-2026-07-03/{name}" for name in [
            "01-admin-navigation.png", "02-review-schema-editor.png", "03-task-catalog.png",
            "04-pipeline-configuration.png", "05-validation-center.png",
        ]],
    }
    assert {entry["original"] for entry in manifest["files"]} == {
        f"docs/{name}" for name in originals
    }
    archived_paths = {
        p.relative_to(SNAPSHOT).as_posix()
        for p in (SNAPSHOT / "docs").rglob("*") if p.is_file()
    }
    assert archived_paths == {
        entry["snapshot"] for entry in manifest["files"]
    }
    for entry in manifest["files"]:
        data = (SNAPSHOT / entry["snapshot"]).read_bytes()
        assert len(data) == entry["bytes"], entry["original"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["original"]


def test_admin_task_guide_covers_the_approved_builtin_catalog() -> None:
    """Detect missing/stale Admin choices without importing runtime providers."""
    registry_path = ROOT / "modules" / "services" / "task_registry_service.py"
    registry_ast = ast.parse(registry_path.read_text(encoding="utf-8"))
    registry = next(
        ast.literal_eval(node.value)
        for node in registry_ast.body
        if isinstance(node, ast.AnnAssign)
        and node.value is not None
        and isinstance(node.target, ast.Name)
        and node.target.id == "BUILTIN_TASKS"
    )
    guide = (DOCS / "admin" / "task-guide.md").read_text(encoding="utf-8")
    catalog = guide.split("## Available built-in tasks\n", 1)[1].split("\n## ", 1)[0]
    documented_keys = re.findall(
        r"^\| \*\*[^\n|]+\*\* \| `([^`]+)` \|", catalog, re.MULTILINE
    )
    assert len(documented_keys) == len(set(documented_keys)), "Repeated built-in task entry"
    assert set(documented_keys) == set(registry), "Admin catalog and approved tasks differ"


def test_current_documentation_local_links_and_fragments_resolve() -> None:
    problems = []
    for path in _current_pages():
        for destination, fragment in _links(path):
            if not destination.exists():
                problems.append(f"{path.relative_to(ROOT)} -> missing {destination}")
            elif (
                fragment and destination.suffix == ".md"
                and fragment not in _anchors(destination.read_text(encoding="utf-8-sig"))
            ):
                problems.append(
                    f"{path.relative_to(ROOT)} -> missing #{fragment} "
                    f"in {destination.relative_to(ROOT)}"
                )
    assert not problems, "\n".join(problems)


def test_original_heading_links_have_current_destinations() -> None:
    mapping = json.loads((DOCS / "documentation-map.json").read_text(encoding="utf-8"))
    for original, entries in mapping["legacy_anchors"].items():
        current = DOCS / original
        original_ids = _anchors((SNAPSHOT / "docs" / original).read_text(encoding="utf-8-sig"))
        assert {entry["id"] for entry in entries} == original_ids
        assert original_ids <= _anchors(current.read_text(encoding="utf-8")), original
        for entry in entries:
            target = DOCS / entry["target"]
            assert target.is_file(), entry
            if entry["fragment"]:
                assert entry["fragment"] in _anchors(target.read_text(encoding="utf-8")), entry


def test_all_canonical_pages_are_reachable_from_documentation_entrance() -> None:
    mapping = json.loads((DOCS / "documentation-map.json").read_text(encoding="utf-8"))
    recorded = {(DOCS / page["path"]).resolve() for page in mapping["pages"]}
    actual = {path.resolve() for path in _current_pages()}
    assert recorded == actual
    legacy = {
        (DOCS / name).resolve() for name in mapping["original_destinations"]
        if name != "design_architecture.md"
    }
    visited: set[Path] = set()
    pending = deque([(DOCS / "README.md").resolve()])
    while pending:
        path = pending.popleft()
        if path in visited or path not in recorded:
            continue
        visited.add(path)
        pending.extend(destination for destination, _ in _links(path) if destination in recorded)
    assert recorded - legacy <= visited, sorted(
        str(p.relative_to(ROOT)) for p in recorded - legacy - visited
    )


@pytest.mark.parametrize("folder", ["operator", "admin"])
def test_business_reader_guides_do_not_require_programming(folder: str) -> None:
    for path in (DOCS / folder).glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^```", text, re.MULTILINE), path.name
        for term in ["/api/", "standard_step.", "python.exe", "X-CSRF-Token", "SELECT ", "SQLite"]:
            assert term not in text, f"Technical instruction in {folder}/{path.name}: {term}"


def test_historical_reading_copies_are_labelled_and_images_preserved() -> None:
    reports = [
        "changes/2026-09-05.md", "changes/user-guide-history.md",
        "validation/manual-split-2026-10-07.md", "validation/liteparse-pipeline-2026-10-04.md",
        "benchmarks/performance-2026-09-29.md", "audits/admin-navigation-2026-07-03/audit.md",
    ]
    for report in reports:
        text = (DOCS / "history" / report).read_text(encoding="utf-8")
        assert "| Status | Historical record |" in text
        assert "archive/2026-10-10/" in text
    for path in (SNAPSHOT / "docs" / "audits").rglob("*.png"):
        relocated = DOCS / "history" / path.relative_to(SNAPSHOT / "docs")
        assert relocated.read_bytes() == path.read_bytes()


def test_repository_entrances_and_existing_incoming_doc_links_resolve() -> None:
    sources = [
        ROOT / "README.md", *(ROOT / "tasks").rglob("*.md"),
        *(ROOT / "tools" / "config_check").rglob("*.md"),
    ]
    for path in sources:
        for destination, fragment in _links(path):
            if DOCS not in destination.parents:
                continue
            assert destination.exists(), f"{path.relative_to(ROOT)} -> {destination}"
            if fragment and destination.suffix == ".md":
                assert fragment in _anchors(destination.read_text(encoding="utf-8-sig")), (
                    f"{path.relative_to(ROOT)} -> {destination}#{fragment}"
                )
    assert "docs/README.md" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_documented_python_file_references_exist() -> None:
    """Catch stale command arguments as well as broken clickable links."""
    for folder in EXPECTED:
        for path in (DOCS / folder).rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            references = re.findall(
                r"\b(?:test|tools|modules|standard_step|web)[\\/][\w\\/.-]+\.py\b", text
            )
            for reference in references:
                parts = reference.replace("\\", "/").split("/")
                if "path" in parts:  # Deliberate command placeholder.
                    continue
                assert ROOT.joinpath(*parts).is_file(), f"{path.relative_to(ROOT)}: {reference}"


def test_documented_full_suite_excludes_credentialed_connection_test() -> None:
    text = (DOCS / "developer" / "testing-and-verification.md").read_text(encoding="utf-8")
    full_suite_commands = [
        line for line in text.splitlines()
        if "-m pytest -v" in line and "test\\" not in line
    ]
    assert full_suite_commands
    assert all(
        "--ignore=test/third_party/llamacloud_connection_test.py" in line
        for line in full_suite_commands
    )
