# Current implementation documentation audit

Status: Complete, 2026-11-13. Source reviewed against the working tree based on
`d447706`. Verification used synthetic/offline inputs; no live provider or
active deployment check was performed.

## Scope and review method

Inventoried 160 tracked Markdown files, the production Python/browser source,
configuration tooling, tests, standalone experiments and visual editor prototype.
Reviewed current procedures against route declarations, service ownership,
schema/migration markers, task constructors/execution/helpers and regression
contracts. Repeated cross-document searches after corrections, including a
122-route inventory, Python-file references and local links/anchors.

Dated evidence, completed implementation records, future proposals and exact
archived snapshots retain their original scope. The pre-existing untracked
`research-business-validation-patterns.md` is a labelled recommendation document
and remains unchanged. No staging, commits or active runtime-state edits occurred.

## Checklist

- [x] Inventory maintained guides, compatibility links, plans and historical evidence.
- [x] Compare runtime, persistence, security and configuration contracts with source.
- [x] Compare task, API, operator and admin guidance with source and tests.
- [x] Check developer/support commands, tooling, experiment and prototype guidance.
- [x] Correct stale material and repeat cross-document/link checks.
- [x] Run focused verification, review the complete diff and record outcomes.

## Source coverage and corrections

| Area | Source checked | Documentation outcome |
| --- | --- | --- |
| Supervision, auth and process setup | main, web server, configuration/path/security/auth modules, startup/health/shutdown services | Correct synchronous execution, fixed SQLite accounts, migration ownership, retired upload and environment commands in source docstrings. |
| Persistence and versions | Schema 9, connection/migrations/repositories, pipeline template/definition/legacy/portable services | Correct service ownership, publication trace, missing queue/receipt/manual-decision table entries and legacy-cutover publication behavior. |
| Intake and APIs | Upload receiver/storage locks/receipts, assignment/batch/job/worker services, binding/coordinator, router | Correct Watch folders navigation and real upload function/service names; distinguish YAML validation, normalized binding paths and working-directory consumers. |
| Tasks, review and artifacts | All approved task families, loader/manager/base, resume/split/fan-in, review and artifact services | Document cleanup path/lookup limits, strict registration, CSV table detection, JSON override limits, Nanoid regeneration, review queue default and exact form selection. |
| Archive path | ArchivePdfTask plus reserve_unique_filepath | Normal execution creates missing destinations; the standalone validation hook requires an existing directory and is not automatically called. Confirmed with a synthetic direct run. |
| Business validation and browser modules | Evaluator/registry/schema/catalog/report services, review completion, production templates/controllers | Update architecture and module ownership for pinned rules, atomic acceptance, separate admin catalog/operator labels and stale-result guards; remove references to removed templates. |
| Deployment and support | Logging handlers, stdout capture, backup paths and startup migration | Document 10 MiB/five-backup role rotation with direct-stdio caveat; include source/working PDFs in backup and distinguish UI import from one-time cutover. |
| Config-check | CLI parser, stored/portable validation, parameter checks and package metadata | Remove false pipeline-file incompatibility claims: CLI kind pipeline accepts serialized pipeline-bundle; document embedded/read-only dependency resolution. Replace unshipped YAML examples with a verified inline sample and explicit repository interpreter commands. |
| Experiments and prototype | Experiment scripts/manifests/reports; prototype package, Vite middleware and React entry | Label historical environment/results, explain missing local PDFs/sample YAML, and add a prototype README covering local file writes and static-preview limitations. |
| Historical/current boundaries | Documentation map, compatibility links, audience indexes, planning statuses and QA records | Preserve immutable archives and original results, label standalone QA records, refresh verification metadata only on changed current guides. |

## Verification

Commands run from the repository root unless specified. Counts below are separate
runs and must not be added as unique test totals.

```powershell
# Initial documentation baseline: 18 passed.
.\.venv\Scripts\python.exe -m pytest -q test\tools\test_documentation_structure.py --tb=short

# Focused implementation contracts: 483 passed, 3 skipped.
.\.venv\Scripts\python.exe -m pytest -q test\tools\config_check test\standard_step\housekeeping\test_cleanup_task.py test\standard_step\test_standard_steps.py test\storage test\services\test_artifact_service.py test\services\test_runtime_health_service.py test\core\test_config_manager.py test\core\test_configuration_boundaries.py --tb=short

# Full offline suite: 2,051 passed, 4 skipped, 529.24 seconds.
$env:RUN_LLAMACLOUD_SPLIT_SMOKE = '0'
.\.venv\Scripts\python.exe -m pytest -q --ignore=test/third_party/llamacloud_connection_test.py --tb=short

# Static types: 0 errors, 0 warnings, 0 informations.
.\.venv\Scripts\python.exe -m pyright --project pyrightconfig.json --pythonpath .\.venv\Scripts\python.exe

# Documentation/archive and animation contracts: 34 passed.
.\.venv\Scripts\python.exe -m pytest -q test\tools\test_documentation_structure.py test\tools\test_architecture_animations.py --tb=short

# All 16 production feature release graphs validated.
.\.venv\Scripts\python.exe -m tools.frontend_release_check check

# Additional standalone synthetic experiment suites: 80 passed.
.\.venv\Scripts\python.exe -m pytest -q experimentc experimentd --tb=short

# From pipeline_visual_editor_prototype: 67 tests passed in 18 files; build passed.
Set-Location pipeline_visual_editor_prototype
npm test
npm run build

# From repository root: final whitespace/diff check and repeated documentation checks.
git diff --check
.\.venv\Scripts\python.exe -m pytest -q test\tools\test_documentation_structure.py --tb=short
```

Additional repository-interpreter checks:

- Parsed both HEAD and edited Python files with ast, removed docstrings, and
  compared full ASTs: all 16 edited Python files have identical executable ASTs.
- Resolved current guide/CLI/experiment/prototype/task-standard local links and
  Markdown anchors; checked mentioned Python files and documented app/API paths.
- Loaded the inline deployment YAML from the examples README into a temporary
  file, supplied synthetic signing/path values and created required directories;
  config-check runtime-file validation returned 0 without opening SQLite.
- Used TemporaryDirectory and a synthetic PDF to confirm ArchivePdfTask's
  standalone missing-directory validation and successful directory-creating run.
- Reviewed changed files for generated runtime state, credentials, customer
  content and unintended code edits; exact snapshot hashes remain verified.

No live LlamaCloud/Ollama/model checks, dependency installation, root CSS rebuild,
or production-state changes were needed. Frontend source/assets and Python
execution behavior are unchanged. Prototype build output is ignored local data.

## Relevant Files

- `README.md`: Correct onboarding, Watch folders navigation and offline test/type-check commands.
- `design-qa.md`: Label original visual evidence as a historical checkpoint.
- `docs/README.md`: Link the completed implementation documentation audit.
- `docs/admin/task-guide.md`: Split artifact retention and CSV/JSON/archive setup guidance.
- `docs/architecture/configuration-and-versioning.md`: Current runtime, persistence, configuration and trust contracts.
- `docs/architecture/decisions-and-constraints.md`: Current runtime, persistence, configuration and trust contracts.
- `docs/architecture/persistence-and-artifacts.md`: Current runtime, persistence, configuration and trust contracts.
- `docs/architecture/security-and-trust.md`: Current runtime, persistence, configuration and trust contracts.
- `docs/architecture/workflow-and-state.md`: Current runtime, persistence, configuration and trust contracts.
- `docs/developer/codebase-map.md`: Current ownership, execution traces, environment and verification guidance.
- `docs/developer/database-migrations.md`: Current ownership, execution traces, environment and verification guidance.
- `docs/developer/development-setup.md`: Current ownership, execution traces, environment and verification guidance.
- `docs/developer/execution-walkthroughs.md`: Current ownership, execution traces, environment and verification guidance.
- `docs/developer/frontend-development.md`: Current ownership, execution traces, environment and verification guidance.
- `docs/developer/testing-and-verification.md`: Current ownership, execution traces, environment and verification guidance.
- `docs/documentation-map.json`: Record current verification date without changing archived mappings.
- `docs/it-support/backup-and-restore.md`: Accurate operational setup, path, log, validation and recovery procedures.
- `docs/it-support/config-check-troubleshooting.md`: Accurate operational setup, path, log, validation and recovery procedures.
- `docs/it-support/configuration-and-access.md`: Accurate operational setup, path, log, validation and recovery procedures.
- `docs/it-support/monitoring-and-logs.md`: Accurate operational setup, path, log, validation and recovery procedures.
- `docs/reference/deployment-configuration.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/glossary.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/pipeline-definition-format.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/tasks/liteparse-extraction.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/tasks/llamacloud-extraction.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/tasks/review-gate.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/tasks/rules-context-housekeeping.md`: Exact implemented configuration/task terminology and contracts.
- `docs/reference/tasks/storage-and-archiving.md`: Exact implemented configuration/task terminology and contracts.
- `experimentc/README.md`: Separate historical environment/results from current prerequisites.
- `main.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/api_router.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/auth_utils.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/base_task.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/file_processor.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/services/pipeline_config_service.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/workflow_loader.py`: Source docstrings aligned with current execution; executable code unchanged.
- `modules/workflow_manager.py`: Source docstrings aligned with current execution; executable code unchanged.
- `pipeline_visual_editor_prototype/README.md`: Document local YAML setup, dev APIs, testing and preview limits.
- `pipeline_visual_editor_prototype/design-qa.md`: Label original visual evidence as a historical checkpoint.
- `standard_step/archiver/archive_pdf.py`: Source docstrings aligned with current execution; executable code unchanged.
- `standard_step/extraction/extract_pdf.py`: Source docstrings aligned with current execution; executable code unchanged.
- `standard_step/storage/store_file_to_localdrive.py`: Source docstrings aligned with current execution; executable code unchanged.
- `standard_step/storage/store_metadata_as_csv.py`: Source docstrings aligned with current execution; executable code unchanged.
- `standard_step/storage/store_metadata_as_json.py`: Source docstrings aligned with current execution; executable code unchanged.
- `tasks/standard_task_creation_guidelines.md`: Clarify strict/default artifact registration and cleanup path ownership.
- `tasks/tasks-documentation-current-implementation-audit.md`: Audit scope, coverage, changes and verification record.
- `tools/config_check/README.md`: Runnable repository-environment commands and shipped example scope.
- `tools/config_check/__main__.py`: Source docstrings aligned with current execution; executable code unchanged.
- `tools/config_check/examples/README.md`: Runnable repository-environment commands and shipped example scope.
- `tools/generate_password_hash.py`: Source docstrings aligned with current execution; executable code unchanged.
- `tools/setup_users.py`: Source docstrings aligned with current execution; executable code unchanged.
