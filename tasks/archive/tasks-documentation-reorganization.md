# Audience-based documentation reorganisation

Requested outcome: create every page in the agreed Operator, Admin,
Architecture, Developer, IT Support, Reference and History structure; adapt
language to the reader; archive all original documentation for historical use.

## Implementation and verification

- [x] 1. Inventory the current documents and preserve an exact dated snapshot
  with a checksum manifest before replacing any original.
- [x] 2. Create the complete Operator and Admin guides with screen-based,
  non-programmer language and clear support handoffs.
- [x] 3. Create the Architecture and Developer reading paths, retaining the
  stable architecture entry point and canonical task-creation standards.
- [x] 4. Create IT Support runbooks and shared technical references, preserving
  important configuration, API, provider, recovery and compatibility details.
- [x] 5. Organise historical evidence, update repository navigation, and keep
  existing document URLs and section anchors usable through navigation pages.
- [x] 6. Verify required-page coverage, archived-file fidelity, current local
  links and anchors, reader boundaries, and the final diff. Run focused tests.

## Admin guidance follow-up

The initial Admin pages removed too much practical configuration guidance.
The original snapshot is already complete and must remain unchanged.

- [x] 7. Restore detailed review-form authoring, field controls, nested examples,
  review routing and publication steps, checking the production editor.
- [x] 8. Expand extraction selection and configuration advice, including the
  LiteParse/GLM-OCR speed and document-size tradeoffs and their limits.
- [x] 9. Document every approved built-in task, task ordering, output and rule
  settings, and an end-to-end pipeline example for non-programmer Admins.
- [x] 10. Review the remaining Admin guides for rollout, validation and support
  handoff gaps; update navigation/inventory and run documentation checks.

Follow-up relevant files: `docs/admin/*.md` (operational instructions),
`docs/admin/task-guide.md` (complete built-in task selection and setup),
`docs/documentation-map.json` (page inventory),
`docs/history/changes/2026-10-10.md` (scope of the documentation correction),
`test/tools/test_documentation_structure.py` (catalog completeness and navigation),
`docs/reference/tasks/README.md` (Admin entry link),
`docs/reference/tasks/storage-and-archiving.md` (current-PDF archive semantics),
and this checklist.

## Operator guidance follow-up

Prerequisites: the original snapshot is intact and the Admin guidance review
is complete. Compare the original Operator section/FAQ and manual-split guide
with production screens before restoring procedures.

- [x] 11. Restore submission preparation, limits and uncertain-acceptance recovery,
  and explain everyday navigation and processing terminology.
- [x] 12. Restore queue filters, claim/draft/completion handling, source display,
  field/table corrections and worked review examples.
- [x] 13. Expand progress, extraction/results, split decisions and failure
  investigation; distinguish screen reload, continuation retry and new submission.
- [x] 14. Review all Operator guidance against source, check archive fidelity,
  navigation and reader language, and run focused documentation verification.

Relevant files: `docs/operator/*.md` (all seven Operator pages),
`docs/history/changes/2026-10-10.md` (documentation correction record),
and this checklist (coverage evidence and verification results).

Operator detail coverage after restoration:

| Original material | Maintained destination and restored detail |
| --- | --- |
| User guide 3.1–3.2 | `docs/operator/submitting-documents.md`: incoming-folder intake, single-pipeline batches, selection/limits, transfer cancellation and same-tab acceptance recovery. |
| User guide 3.3 navigation/statuses | `docs/operator/quick-start.md` and `monitoring-and-results.md`: work areas, batch lookup, current/last step, intermediate versus final outcomes and Reports interpretation. |
| Human Review and Review Gate Example | `docs/operator/reviewing-extracted-data.md`: ownership/search/sort/pagination, claims, source modes, confidence, scalar/group/table correction, diff/draft/completion, handover and worked amount correction. |
| Split Results | `docs/operator/monitoring-and-results.md`: children versus continued originals, no-split versus no-children outcomes, page ranges and independent child review/failures. |
| Manual Split Review / manual-split task | `docs/operator/manual-splitting.md`: boundary controls, worked page ranges, drafts/renewal/stale plans, final decisions, History and bounded continuation recovery. |
| Failures and Operator FAQs | `docs/operator/troubleshooting.md`: detail inspection, source/segment grouping, distinct retry actions, review/file/access questions and support information. |
| Remaining role-relevant overview/FAQ | `docs/operator/README.md` and `quick-start.md`: terminology, daily reading path, role boundaries and complete-document workflow. |

Corrections based on current source rather than copying older claims: the
Extraction file list renders filenames/types without download buttons; Source
values are original extraction rather than verified PDF truth; acquiring an
extraction-review claim reloads saved values, unlike manual-split renewal's
explicit preservation of visible unsaved boundaries. Queue ownership uses the
signed-in account, so staff sharing the operator account must coordinate work.

## Migration relevant files

- `tasks/tasks-documentation-reorganization.md`: scope, migration checklist and
  final file inventory.
- `docs/`: audience-specific guides, technical references, historical evidence,
  archive manifest and stable navigation pages; individual files are listed below.
- `README.md`: repository entrance to the new reading paths.
- `test/tools/test_documentation_structure.py`: documentation migration checks.

## Created and migrated files

- `docs/README.md`: PDF processing documentation.
- `docs/admin/README.md`: Application administrator guide.
- `docs/admin/accounts-and-settings.md`: Manage passwords and application settings.
- `docs/admin/archiving-and-retention.md`: Archive pipelines and clean processing history.
- `docs/admin/configuring-extraction.md`: Configure document extraction.
- `docs/admin/managing-pipelines.md`: Manage pipelines.
- `docs/admin/managing-review-forms.md`: Manage review forms.
- `docs/admin/task-guide.md`: all built-in tasks, selection, ordering and setup.
- `docs/admin/managing-watch-folders.md`: Manage incoming watch folders.
- `docs/admin/validation-and-audit.md`: Validate settings and inspect administrative history.
- `docs/architecture/README.md`: Architecture reading path.
- `docs/architecture/configuration-and-versioning.md`: Configuration ownership and immutable versions.
- `docs/architecture/decisions-and-constraints.md`: Architectural decisions and constraints.
- `docs/architecture/persistence-and-artifacts.md`: Persistence and artifact ownership.
- `docs/architecture/runtime-and-boundaries.md`: Runtime topology and component boundaries.
- `docs/architecture/security-and-trust.md`: Security and trust boundaries.
- `docs/architecture/workflow-and-state.md`: Workflow execution and state.
- `docs/audits/admin-navigation-2026-07-03/audit.md`: Moved: Admin Navigation Information Architecture Audit.
- `docs/change-summary-2026-09-05.md`: Moved: Change summary — 2026-09-05.
- `docs/config_check_troubleshooting.md`: Moved: Config Check Troubleshooting Guide.
- `docs/design_architecture.md`: PDF processing system architecture.
- `docs/developer/README.md`: Developer and maintainer guide.
- `docs/developer/backend-development.md`: Change backend behaviour.
- `docs/developer/codebase-map.md`: Codebase map and ownership.
- `docs/developer/database-migrations.md`: Develop database migrations.
- `docs/developer/development-setup.md`: Set up a development environment.
- `docs/developer/execution-walkthroughs.md`: Trace execution through the code.
- `docs/developer/frontend-development.md`: Maintain the production frontend.
- `docs/developer/performance.md`: Measure and investigate performance.
- `docs/developer/task-development.md`: Develop and change pipeline tasks.
- `docs/developer/testing-and-verification.md`: Test and verify changes.
- `docs/frontend_deployment.md`: Moved: Frontend module deployment and rollback.
- `docs/history/README.md`: Historical records.
- `docs/history/archive/2026-10-10/README.md`: Original documentation snapshot: 2026-10-10.
- `docs/history/audits/admin-navigation-2026-07-03/audit.md`: Admin navigation audit: 2026-07-03.
- `docs/history/benchmarks/performance-2026-09-29.md`: Performance measurement: 2026-09-29.
- `docs/history/changes/2026-09-05.md`: Change record: 2026-09-05.
- `docs/history/changes/2026-10-10.md`: Documentation reorganisation: 2026-10-10.
- `docs/history/changes/user-guide-history.md`: Earlier user-guide revision history.
- `docs/history/validation/liteparse-pipeline-2026-10-04.md`: LiteParse pipeline validation: 2026-10-04.
- `docs/history/validation/manual-split-2026-10-07.md`: Manual split validation: 2026-10-07.
- `docs/it-support/README.md`: IT Support guide.
- `docs/it-support/account-recovery.md`: Provision accounts and recover administrator access.
- `docs/it-support/backup-and-restore.md`: Back up, restore and maintain deployment storage.
- `docs/it-support/config-check-troubleshooting.md`: Troubleshoot configuration validation.
- `docs/it-support/configuration-and-access.md`: Configure deployment access and filesystem permissions.
- `docs/it-support/deployment-and-upgrades.md`: Deploy, upgrade and roll back the application.
- `docs/it-support/incident-runbooks.md`: Investigate runtime incidents.
- `docs/it-support/installation-and-provider-setup.md`: Install the application and extraction providers.
- `docs/it-support/monitoring-and-logs.md`: Monitor runtime health and logs.
- `docs/it-support/starting-and-stopping.md`: Start, stop and restart the application.
- `docs/liteparse_extract_task.md`: Moved: LiteParse + Ollama extraction.
- `docs/liteparse_pipeline_validation.md`: Moved: LiteParse production pipeline validation.
- `docs/manual_split_task.md`: Moved: Manual PDF split task.
- `docs/manual_split_validation.md`: Moved: Manual split validation — 2026-10-07.
- `docs/operator/README.md`: Operator guide.
- `docs/operator/manual-splitting.md`: Split a PDF during review.
- `docs/operator/monitoring-and-results.md`: Monitor processing and find results.
- `docs/operator/quick-start.md`: Process your first document.
- `docs/operator/reviewing-extracted-data.md`: Review extracted information.
- `docs/operator/submitting-documents.md`: Submit documents.
- `docs/operator/troubleshooting.md`: Resolve common problems and request help.
- `docs/performance_benchmark.md`: Moved: Performance benchmark.
- `docs/pipeline_retention_admin_guide.md`: Moved: Pipeline archiving and processing-data cleanup.
- `docs/reference/README.md`: Shared technical reference.
- `docs/reference/api-contracts.md`: API contracts and compatibility.
- `docs/reference/deployment-configuration.md`: Deployment configuration reference.
- `docs/reference/glossary.md`: Shared terminology.
- `docs/reference/pipeline-definition-format.md`: Portable pipeline definition format.
- `docs/reference/review-schema-format.md`: Review schema format and validation.
- `docs/reference/tasks/README.md`: Pipeline task reference.
- `docs/reference/tasks/glm-ocr-extraction.md`: GLM-OCR extraction task reference.
- `docs/reference/tasks/liteparse-extraction.md`: LiteParse extraction task reference.
- `docs/reference/tasks/llamacloud-extraction.md`: LlamaCloud extraction task reference.
- `docs/reference/tasks/review-gate.md`: Review gate task reference.
- `docs/reference/tasks/rules-context-housekeeping.md`: Rules, context and housekeeping task reference.
- `docs/reference/tasks/splitting.md`: Split task parameters and continuation contracts.
- `docs/reference/tasks/storage-and-archiving.md`: Storage and archive task reference.
- `docs/review_schema_admin_guide.md`: Moved: Review Schema Administrator Guide.
- `docs/technical_operations_reference.md`: Moved: Technical Operations Reference.
- `docs/user_guide.md`: Moved: PDF Processing System: User Guide.
- `docs/watch_folder_admin_reference.md`: Moved: Watch-folder administration reference.
- `docs/documentation-map.json`: required-page and compatibility-address inventory.
- `docs/history/archive/2026-10-10/manifest.json`: original-file checksums and byte lengths.
- `docs/history/archive/2026-10-10/docs/audits/admin-navigation-2026-07-03/01-admin-navigation.png`: exact original `docs/audits/admin-navigation-2026-07-03/01-admin-navigation.png`.
- `docs/history/audits/admin-navigation-2026-07-03/01-admin-navigation.png`: relocated historical audit image.
- `docs/history/archive/2026-10-10/docs/audits/admin-navigation-2026-07-03/02-review-schema-editor.png`: exact original `docs/audits/admin-navigation-2026-07-03/02-review-schema-editor.png`.
- `docs/history/audits/admin-navigation-2026-07-03/02-review-schema-editor.png`: relocated historical audit image.
- `docs/history/archive/2026-10-10/docs/audits/admin-navigation-2026-07-03/03-task-catalog.png`: exact original `docs/audits/admin-navigation-2026-07-03/03-task-catalog.png`.
- `docs/history/audits/admin-navigation-2026-07-03/03-task-catalog.png`: relocated historical audit image.
- `docs/history/archive/2026-10-10/docs/audits/admin-navigation-2026-07-03/04-pipeline-configuration.png`: exact original `docs/audits/admin-navigation-2026-07-03/04-pipeline-configuration.png`.
- `docs/history/audits/admin-navigation-2026-07-03/04-pipeline-configuration.png`: relocated historical audit image.
- `docs/history/archive/2026-10-10/docs/audits/admin-navigation-2026-07-03/05-validation-center.png`: exact original `docs/audits/admin-navigation-2026-07-03/05-validation-center.png`.
- `docs/history/audits/admin-navigation-2026-07-03/05-validation-center.png`: relocated historical audit image.
- `docs/history/archive/2026-10-10/docs/audits/admin-navigation-2026-07-03/audit.md`: exact original `docs/audits/admin-navigation-2026-07-03/audit.md`.
- `docs/history/archive/2026-10-10/docs/change-summary-2026-09-05.md`: exact original `docs/change-summary-2026-09-05.md`.
- `docs/history/archive/2026-10-10/docs/config_check_troubleshooting.md`: exact original `docs/config_check_troubleshooting.md`.
- `docs/history/archive/2026-10-10/docs/design_architecture.md`: exact original `docs/design_architecture.md`.
- `docs/history/archive/2026-10-10/docs/frontend_deployment.md`: exact original `docs/frontend_deployment.md`.
- `docs/history/archive/2026-10-10/docs/liteparse_extract_task.md`: exact original `docs/liteparse_extract_task.md`.
- `docs/history/archive/2026-10-10/docs/liteparse_pipeline_validation.md`: exact original `docs/liteparse_pipeline_validation.md`.
- `docs/history/archive/2026-10-10/docs/manual_split_task.md`: exact original `docs/manual_split_task.md`.
- `docs/history/archive/2026-10-10/docs/manual_split_validation.md`: exact original `docs/manual_split_validation.md`.
- `docs/history/archive/2026-10-10/docs/performance_benchmark.md`: exact original `docs/performance_benchmark.md`.
- `docs/history/archive/2026-10-10/docs/pipeline_retention_admin_guide.md`: exact original `docs/pipeline_retention_admin_guide.md`.
- `docs/history/archive/2026-10-10/docs/review_schema_admin_guide.md`: exact original `docs/review_schema_admin_guide.md`.
- `docs/history/archive/2026-10-10/docs/technical_operations_reference.md`: exact original `docs/technical_operations_reference.md`.
- `docs/history/archive/2026-10-10/docs/user_guide.md`: exact original `docs/user_guide.md`.
- `docs/history/archive/2026-10-10/docs/watch_folder_admin_reference.md`: exact original `docs/watch_folder_admin_reference.md`.

Additional maintained entrances: `tasks/standard_task_creation_guidelines.md`,
`tools/config_check/README.md`, and `tools/config_check/examples/README.md` link
to the current reader/reference pages.
- `tools/config_check/examples/ERROR_CODES.md`: finding-catalog link to the current troubleshooting guide.

## Verification results

Operator follow-up verification (2026-10-10):

- `.\.venv\Scripts\python.exe -m pytest -v test\tools\test_documentation_structure.py`:
  **18 passed**. All current/legacy links and fragments, audience-page coverage,
  navigation, reader boundaries and exact archive checks remain valid.
- `git diff --check`: passed. All seven Operator pages also passed an explicit
  trailing-whitespace and unfinished-marker audit. Temporary authoring tooling
  was removed.
- Compared the original Operator section/FAQ and manual-split instructions with
  current production templates and the upload-process, review-queue, human-review,
  manual-split-review, processing-overview, reports, extraction-results,
  split-results and failures controllers/views, plus the shared PDF viewer.
  Restored coverage and corrected older screen claims are recorded above.
- No application code, dependencies, frontend assets or archived originals
  changed. Full application tests, browser/live deployment and provider checks
  were not run for this documentation-only follow-up. Verification metadata
  explicitly identifies the source-review basis.

Admin follow-up verification (2026-10-10):

- `.\.venv\Scripts\python.exe -m pytest -v test\tools\test_documentation_structure.py`:
  **18 passed**. Includes a new comparison of the Admin task list with the
  approved built-in registry, plus all navigation, reader-boundary and exact
  historical snapshot checks.
- `git diff --check`: passed. The expanded/new Admin and affected reference
  pages also passed a whitespace/unfinished-marker audit; the temporary
  authoring script was removed.
- Compared screen labels/defaults and behaviour with production
  `web/static/js/pipeline-config/task-editors.js`, `web/static/js/pipeline_config.js`,
  `web/static/js/schema-editor/view.js`, `web/static/js/schema-editor/controller.js`,
  and the pipeline validation/publication, task registry/catalog, settings,
  splitting, extraction, storage and archive implementations. Reviewed the
  original review-form, LiteParse and operations guides for lost practical advice.
- All nine Admin pages were reviewed. Review-form, extraction, pipeline,
  watch-folder, validation, account/settings and index guidance was expanded;
  the already detailed retention guide remains applicable. Added `task-guide.md`
  and corrected the archive reference to identify the current PDF after a split.
- No live provider/deployment check, frontend build or full application suite
  was run for this documentation-only follow-up. Historical snapshot contents
  were not changed; no application code, dependency or UI assets were changed.

Original migration verification:

- `.\.venv\Scripts\python.exe -m pytest -v test\tools\test_documentation_structure.py`:
  17 passed. Covers every agreed audience/reference page, navigation reachability,
  local links and fragments, incoming task/tool links, original heading anchors,
  historical labels/images, snapshot checksums, reader boundaries, referenced
  Python files and full-suite command exclusion of the credentialed connection test.
- Independent snapshot audit: all 20 archived files match both their recorded
  SHA-256/byte lengths and the original committed Git blobs, using
  `git rev-parse HEAD:<original-path>` and
  `git hash-object --path=<original-path> <snapshot-path>` for Git normalization.
- `git diff --check`: passed. Current-page whitespace and unresolved migration
  marker checks passed after removing one inherited trailing-space line.
- Reviewed the generated guides and final file scope. Operator/Admin procedures
  use app controls and support handoffs; technical setup/contracts are in the
  appropriate reading paths. Corrected stale account configuration, validator
  limitations, the configuration-validation access table and test commands.
- All temporary migration tooling was removed. No application code, dependency
  versions, UI assets, runtime databases or customer documents were changed.
- Full application pytest, live provider/deployment checks, frontend builds,
  Pyright and Ruff were not run: this change affects documentation and its
  isolated verification tests, not application behaviour or frontend assets.
