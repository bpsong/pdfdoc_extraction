# Markdown Documentation Audit

Audit date: 2026-06-03

This audit covers tracked Markdown files. Ignored Markdown under `.kiro/` and
`.pytest_cache/` is not maintained project documentation and should not be
updated as part of task 26.

Update on 2026-06-04: maintained runtime docs were restored to their detailed
baseline and updated in place. Superseded planning docs were marked historical
rather than removed, to preserve implementation context without presenting old
status-file or Streamlit paths as current guidance.

## Summary

Task 26 should treat the unified refactor documents as the source of truth:

- `tasks/prd-refactor-unified-pdfdoc-processing.md`
- `tasks/design-refactor-unified-pdfdoc-processing.md`
- `tasks/tasks-prd-refactor-unified-pdfdoc-processing.md`
- `tasks/standard-step-sqlite-state-audit.md`

The public/runtime documentation is stale relative to tasks 1-25. It still
describes the old dashboard, `/api/files`, `/api/status/{file_id}`, and direct
`StatusManager` file-state patterns as primary behavior. Those docs must be
updated after SQLite-only state cleanup is implemented.

## Tracked Markdown Inventory

| File | Last commit age on 2026-06-03 | Action | Reason |
| --- | ---: | --- | --- |
| `README.md` | 19 days | Updated | Restored detailed README content and added SQLite DB, `/app/*`, operator/admin roles, current API overview, artifact registry, and validation notes. |
| `docs/user_guide.md` | 19 days | Updated | Restored full guide and added FastAPI/Jinja operator/admin UI, review flow, split results, reports, settings, QA migration, LlamaCloud v2, and SQLite state model. |
| `docs/design_architecture.md` | 19 days | Updated | Restored architecture content and added SQLite repositories/services, task runs, review, fan-out/fan-in, audit, config versions, QA migration, and artifact registration. |
| `docs/config_check_troubleshooting.md` | 19 days | Updated | Kept as troubleshooting reference; corrected stale status-file wording and reconciled command usage with current CLI. |
| `docs/llamacloud_extract_v2_migration.md` | 19 days | Marked historical | Stable migration content merged into README/user guide/design docs; standalone plan retained as historical implementation context. |
| `tasks/prd-refactor-unified-pdfdoc-processing.md` | 4 days | Keep, minor final update only | Current refactor PRD and source of truth for task 26. Update only if final implementation changes scope. |
| `tasks/design-refactor-unified-pdfdoc-processing.md` | 2 days | Keep, final implementation notes only | Current refactor design. Update only with final SQLite-only state decisions and any deviations. |
| `tasks/tasks-prd-refactor-unified-pdfdoc-processing.md` | 0 days | Keep current | Active task list; task 26 should be expanded from this audit. |
| `tasks/standard-step-sqlite-state-audit.md` | 4 days | Updated | Reflects final post-cleanup state/artifact boundaries and compatibility notes. |
| `tasks/standard_task_creation_guidelines.md` | 245 days | Updated | Replaced direct `StatusManager` guidance with SQLite task-run events, audit guidance, and explicit artifact registration. |
| `tasks/future_todos.md` | 19 days | Marked historical | Completed backlog retained for context; active work belongs in current task lists. |
| `tasks/prd-design-pdf-processing.md` | 19 days | Marked historical | Superseded by unified refactor PRD/design; retained as historical context. |
| `tasks/tasks-prd-redesigned-pdf-processing.md` | 19 days | Marked historical | Completed/superseded task list for the pre-SQLite redesign. |
| `tasks/prd-config-checker.md` | 19 days | Marked historical | Completed config-check PRD; current usage lives in config-check docs. |
| `tasks/tasks-prd-config-checker.md` | 19 days | Marked historical | Completed config-check task list; current usage lives in config-check docs. |
| `tools/config_check/README.md` | 19 days | Updated | Command examples reconciled with current CLI; UI validation references added. |
| `tools/config_check/examples/README.md` | 238 days | Updated | Example commands reconciled with current CLI. |
| `tools/config_check/examples/ERROR_CODES.md` | 238 days | Updated | Command examples reconciled with current CLI. |
| `AGENTS.MD` | 245 days | Keep, review only | Project agent instructions are still relevant and separate from product/runtime docs. Update only if development commands or conventions change. |

## Merge And Removal Plan

- Public docs to keep and update: `README.md`, `docs/user_guide.md`,
  `docs/design_architecture.md`.
- Operational references to keep and update:
  `tasks/standard_task_creation_guidelines.md`,
  `tasks/standard-step-sqlite-state-audit.md`,
  `tools/config_check/README.md`,
  `docs/config_check_troubleshooting.md`.
- Migration content merged into maintained docs; `docs/llamacloud_extract_v2_migration.md`
  is retained with a historical banner.
- Historical planning docs are retained with historical banners:
  `tasks/prd-design-pdf-processing.md`,
  `tasks/tasks-prd-redesigned-pdf-processing.md`,
  `tasks/prd-config-checker.md`, and `tasks/tasks-prd-config-checker.md`.
- Backlog cleanup: `tasks/future_todos.md` is retained with a historical banner.
  New work should go into an active task list rather than this completed backlog.

## Stale Content Checks For Task 26

Before marking task 26 complete, run text checks for stale primary-state
references:

```powershell
rg -n "StatusManager|/api/files|/api/status|dashboard.html|status.js|status file|Streamlit" README.md docs tasks tools/config_check -g "*.md"
```

Expected result: any remaining hits clearly describe legacy compatibility,
historical archived docs, or deprecated behavior. Maintained runtime docs must
describe SQLite as the primary workflow-state source.

2026-06-04 result: stale-reference checks were run after documentation updates.
Remaining hits in maintained runtime docs are explicit legacy compatibility,
historical migration, or deprecation notes. Hits in superseded PRD/task files are
covered by historical banners.
