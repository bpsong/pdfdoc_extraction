# Archived Planning and Audit Documents

This directory contains completed, superseded, or point-in-time engineering
records. These files are retained for implementation history and should not be
treated as current product or architecture guidance.

Current guidance lives in:

- `docs/design_architecture.md`
- `docs/user_guide.md`
- `docs/config_check_troubleshooting.md`
- `docs/review_schema_admin_guide.md`
- `tasks/standard_task_creation_guidelines.md`

Active future proposals live directly under `tasks/`.

Archive groups:

- [Multiple pipeline templates direction](future-multi-document-routing.md):
  implemented ingestion selection, immutable versions, and split inheritance.
- [Local GLM-OCR extraction plan](design-and-implementation-glm-ocr-extract-task.md):
  completed implementation; live visual verification confirmed by the maintainer
  on 2026-10-11.
- `tasks-multiple-versioned-pipeline-templates.md`: completed implementation
  and verification record for immutable SQLite-backed pipelines and review
  schemas.
- `admin-panel-style-consistency-plan.md`: completed shared panel and header
  styling for the production Schema and Pipeline editors.
- `future-design-visual-pipeline-builder.md`: superseded full node-canvas
  direction; the production serial-list editor is the accepted implementation.
- `unified-refactor/`: completed SQLite-backed unified application refactor.
- `config-checker/`: completed config-check requirements and implementation
  task list.
- `pre-sqlite-redesign/`: superseded status-file-centered design and task list.
- `ui-ux-audits/`: dated interface audits and supporting research notes.

Links inside archived documents may reflect their original repository
locations and the code structure that existed when they were written.

## Completed implementation and verification records

- [R3 CSV reference lookup and enrichment](tasks-r3-csv-reference-lookup.md)
- [Pipeline editor focus jump bug](pipeline_editor_focus_jump_bug.md)
- [Tasks documentation reorganization](tasks-documentation-reorganization.md)
- [Tasks documentation current implementation audit](tasks-documentation-current-implementation-audit.md)
- [Tasks frontend controller modularization](tasks-frontend-controller-modularization.md)
- [Tasks manual split](tasks-manual-split.md)
- [Plan single document split continuation](plan-single-document-split-continuation.md)
- [Tasks pipeline archive cleanup](tasks-pipeline-archive-cleanup.md)
- [Tasks watch folder management](tasks-watch-folder-management.md)
