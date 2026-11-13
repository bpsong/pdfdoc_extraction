# Codebase map and ownership

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-11-13 — repository/source review; no live deployment check; offline regressions |
| Applies to | Production application; SQLite schema 9 |

Use the ownership map to choose a change location, then follow the linked source.
Operational state belongs in SQLite; runtime directories contain generated
data, not application code.

## Component boundaries

| Component | Responsibility | Boundary |
| --- | --- | --- |
| [`main.py`](../../main.py) | Startup, supervision, shutdown | No workflow business logic |
| [`WatchFolderCoordinator`](../../modules/services/watch_folder_coordinator.py) | Reconcile enabled bindings, validate and claim PDFs, and enqueue assigned jobs | Does not execute workflows |
| [`ProcessingWorker`](../../modules/services/processing_worker.py) | Lease queued jobs and trigger the assigned workflow | No ingestion or task policy |
| [`FileProcessor`](../../modules/file_processor.py) | Validate the assigned SQLite context and trigger processing for a worker job | No task policy |
| [`WorkflowManager`](../../modules/workflow_manager.py) | Start root, child, and resumed flows | No table-specific persistence |
| [`WorkflowLoader`](../../modules/workflow_loader.py) | Approve, instantiate, and execute configured tasks | No domain task behavior |
| [`BaseTask`](../../modules/base_task.py), `standard_step/` | One configured operation | Preserve context and failure contracts |
| [`modules/services/`](../../modules/services) | Use cases and cross-table invariants | No HTTP request concerns |
| [`modules/db/repositories.py`](../../modules/db/repositories.py) | Table-specific persistence | No cross-domain orchestration |
| [`modules/api_router.py`](../../modules/api_router.py) | JSON API composition | New business logic belongs in services |
| [`web/server.py`](../../web/server.py) | App construction and authenticated page routes | No workflow-state ownership |
| [`web/templates/`](../../web/templates) | Server-rendered structure | No authorization enforcement |
| [`web/static/js/`](../../web/static/js) | Browser interaction and API consumption | No authoritative business state |

## Service ownership map

The `modules/services/` directory is intentionally split by use case. When
changing behavior, put the cross-table invariant in the service that owns the
use case rather than adding it to a route or repository.

| Service | Primary responsibility |
| --- | --- |
| `upload_receiver.py` | Multipart parsing, staging, limits, and cancellation cleanup |
| `upload_submission_service.py` | Submission fingerprints and owner-scoped receipt lookup |
| `ingestion_assignment_service.py` | Exact version eligibility, assigned batch/documents and queue creation |
| `processing_job_service.py` | Queue state, leases, retries, and requeue behavior |
| `processing_worker.py` | Poll jobs and invoke the assigned workflow |
| `workflow_state_service.py` | Document/task state transitions and finalization |
| `review_service.py` | Review claims, edits, locks, completion, and release |
| `business_validation.py` | Pure bounded evaluation of approved versioned rules |
| `business_validation_registry.py`, `business_validation_metadata.py` | Reviewed validator implementations, binding and generic editor descriptors |
| `business_validation_schema.py` | Rule syntax and schema-binding validation |
| `business_validation_catalog_service.py` | Admin authoring catalog and separate operator display labels |
| `review_business_validation.py` | Pinned review/gate report identity, provenance and release policy |
| [`modules/resume_manager.py`](../../modules/resume_manager.py) | Reconstruct context and resume downstream work |
| `pipeline_definition_service.py` | Resolve and verify immutable executable versions |
| `pipeline_template_service.py` | Named pipeline drafts, validation, publication, lifecycle and cloning |
| `versioned_admin_service.py` | Template-scoped read models and portable import/export for current admin APIs |
| `pipeline_config_service.py` | Legacy global pipeline/config_versions compatibility APIs; not the named pipeline runtime owner |
| `review_schema_version_service.py` | Review-schema draft/version lifecycle |
| `artifact_service.py` | Register durable filesystem artifacts in SQLite |
| `runtime_health_service.py` | Process readiness, heartbeats, and component health |
| `task_registry_service.py` | Approved dynamic task imports and startup trust checks |
| `schema_service.py` | Legacy/filesystem schema resolution and loading |
| `startup_migration_service.py` | Structural migration and legacy configuration import |


## Other source areas

- [Database schema](../../modules/db/schema.sql),
  [structural migrations](../../modules/db/migrations.py) and
  [repositories](../../modules/db/repositories.py) define persistence.
- [Standard steps](../../standard_step/) implement approved task families.
- [Config-check](../../tools/config_check/) provides validation tooling.
- [Tests](../../test/) are the authoritative inventory of behaviour coverage.
- [Task standards](../../tasks/standard_task_creation_guidelines.md) define the
  shared task contract; planning documents in `tasks/` need their status checked
  before being treated as implemented behaviour.
- Experiment and prototype directories are separate from production code.

See [execution walkthroughs](execution-walkthroughs.md) to trace one operation.
