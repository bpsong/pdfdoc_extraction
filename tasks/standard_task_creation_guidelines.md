# Standardized Rules and Guidelines for Creating New Tasks

This document outlines the standardized structure, rules, and best practices for creating or substantially changing tasks within the PDF document processing system. Following these guidelines will ensure consistency, maintainability, safe dynamic imports, and integration with the Prefect-backed workflow runner and SQLite workflow state.

---

## 1. Task Structure Overview

Each task is a self-contained Python module that implements a specific step in the processing pipeline. Tasks must inherit from the `BaseTask` abstract class and implement required methods to integrate seamlessly with the workflow.

### Required Methods

- `__init__(self, config_manager: ConfigManager, **params)`
  Initialize the task instance and capture task parameters. Keep construction
  side-effect free beyond basic field initialization: do not perform network
  calls, durable file operations, or database writes here. Validation should
  normally occur in `validate_required_fields()` or `on_start()`.

- `on_start(self, context: dict) -> None`
  Initialize or normalize the shared context and perform lightweight setup
  before execution. `WorkflowLoader` calls this hook before `run()`.

- `run(self, context: dict) -> dict`
  Implement the core business logic of the task. This method receives the
  shared `context` dictionary and must return the same context, possibly
  mutated, with the task's output or error details. Do not return `None`;
  `WorkflowLoader` normalizes a falsey task result to an empty dictionary,
  which would discard the existing workflow context.

- `validate_required_fields(self, context: dict) -> None`
  Validate that all required configuration parameters and context data are
  present and correct. The base class and workflow loader do not call this
  method automatically. The task must invoke it from `on_start()` or `run()`
  before performing the operation. For terminal tasks, validation may be
  minimal.

### Error Handling

- Import and use `TaskError` from `modules.exceptions` to signal expected task
  failures.
- When a task handles an error and returns context, call
  `self.register_error(context, error)` so `error` and `error_step` are set
  consistently.
- When execution cannot continue normally, raise `TaskError`. The workflow
  loader translates raised task errors into failed task-run state and applies
  the configured `on_error` policy.
- Task implementation approval/import failures are runner-owned
  `TaskSetupError` failures. They always stop the affected document regardless
  of `on_error`, but must not terminate the application process. Task code
  should not raise `SystemExit` or call `ShutdownManager`.
- For `on_error: continue`, the workflow loader preserves the failure in its
  internal `continued_failures` history and clears transient error fields before
  invoking the next task. Tasks must not use or overwrite
  `continued_failures`; finalization restores the earlier failure so it remains
  visible in terminal document state.
- Catch specific lower-level exceptions and translate them to useful
  `TaskError` messages. Do not include API keys, credentials, provider
  payloads, customer data, or other secrets in context, logs, or persisted
  failure details.
- Do not write text status files or call `StatusManager` from new configured workflow tasks. Workflow lifecycle state is recorded by `WorkflowLoader`/`WorkflowManager` through SQLite `task_runs` and `documents` when `document_id` context exists.

---

## 2. Initial Setup Before Core Logic

- Read configuration through the injected configuration provider and task
  parameters captured by `BaseTask`; do not create another configuration
  singleton inside the task or reload the task's own parameters from a fixed
  `tasks.<name>.params` path. The same implementation may be configured under
  more than one task key.
- Prefer `pathlib.Path` for filesystem operations. Use `windows_long_path` from
  `modules/utils.py` where an underlying Windows API or library needs a
  long-path-compatible string.
- Use the logger initialized by `BaseTask` rather than creating unrelated
  logging configuration inside the task.
- Prepare any necessary data structures or models (for example, Pydantic models for data validation in extraction tasks).
- Use utilities like `normalize_field_path` and `resolve_field` from `modules/utils.py` for context access.

---

## 3. Core Functionality Expectations

The core functionality of tasks varies widely depending on their purpose. While many standard tasks perform operations such as data extraction, storage, or file handling, tasks may also implement other logic such as data validation, calculations, or conditional processing.

For example, a task might:

- Extract structured data from PDFs.
- Store metadata as CSV or JSON files.
- Save processed files to a local drive.
- Perform calculations on extracted data, such as computing total invoice amount after discounts.
- Validate or transform data before passing it along.
- Update the shared context with new or modified data for downstream tasks.

Tasks should focus on a single responsibility but are not limited to the common functions listed here. The key is to update and pass the shared `context` dictionary appropriately to enable seamless pipeline execution.

If a task needs state for resume, operator visibility, audit, reporting, or
cross-process behavior, persist that state through the appropriate repository
and service. The context dictionary is an execution protocol, not the
authoritative store for durable workflow state.

---

## 4. Final Step: Passing the Context Onward

- After completing the core logic, the task must return the updated `context` dictionary.
- Preserve existing context keys unless the task intentionally owns their
  transition. Representative keys include:
  - identity: `id`, `batch_id`, and `document_id`;
  - input: `file_path`, `original_filename`, and `source`;
  - workflow position: `current_task_index`, `current_task_key`, and
    `task_run_id`;
  - `data`: The processed or extracted data.
  - `metadata`: Supporting extraction or task metadata.
  - `error`: Any error messages encountered during execution.
  - `error_step`: The name of the task where an error occurred.
  - `fatal_failure`: A redacted structured failure summary where a task has
    domain-specific operator guidance.
  - `continued_failures`: Runner-owned history for failures whose configured
    policy allowed later tasks to execute; tasks must preserve it unchanged.
  - control-flow keys such as `pipeline_state`, `review_item_id`,
    `split_children`, and `fan_out_start_task_index`.
- Ensure that the context is passed unchanged if the task is skipped or
  encounters a non-critical condition.
- A task that intentionally pauses review sets `pipeline_state` to `paused`.
  A split task that creates child workflows sets it to `fan_out`. These are
  workflow-runner signals: downstream tasks in the current flow do not execute.
- Do not overwrite workflow-owned identity or position keys with unrelated
  task data.

---

## 5. Workflow State, Audit, and Artifact Convention

SQLite is the primary workflow-state source. New tasks must integrate with the shared workflow context and services instead of writing status text files.

### 5.1. Task-Run State

The workflow runner records standardized task lifecycle events:

- On start: a SQLite `task_runs` row is started for the configured task key.
- On success: the task run is completed with output summary data from the returned context.
- On failure: the task run is failed with error details, and document status is updated where appropriate.
- After configured execution finishes or stops on an ordinary failure, the
  runner records the internally managed cleanup operation under the reserved
  `cleanup_task` key at the index immediately after the configured pipeline.
  This internal run does not move the document's configured pipeline cursor
  and must not be added to user-authored `tasks` or `pipeline` configuration.

Task implementations should:

- treat the key referenced by the YAML `pipeline` list as the authoritative
  configured task key used for task-run tracking;
- read that identity from `context["current_task_key"]`; the workflow loader
  sets the task key and index before task setup even when SQLite state is not
  available;
- do not define a separate `task_slug` parameter. Legacy `task_slug` values are
  accepted temporarily, logged as deprecated, and ignored by built-in tasks;
- use `self.task_key(context)` when error or artifact metadata needs producer
  attribution. It returns the configured key and falls back to the task class
  name only for direct execution outside the workflow loader;
- return meaningful context changes so the workflow runner can summarize outputs;
- call `self.register_error(context, TaskError(...))` before returning context
  with a handled error;
- raise `TaskError` for failures that should stop the current happy path;
- avoid direct writes to `StatusManager`, status `.txt` files, `/api/files`, or `/api/status/{file_id}` compatibility shapes.

Common configured task-key examples:

- `ExtractPdfTask` -> `extract_document_data`
- `StoreMetadataAsCsv` -> `store_metadata_csv`
- `StoreMetadataAsJson` -> `store_metadata_json`
- `StoreFileToLocaldrive` -> `store_file_to_localdrive`
- `ArchivePdfTask` -> `archive_pdf`

`cleanup_task` is reserved for the runner-managed `CleanupTask`; it is not a
configured task-key example and must not be reused by another task.

### 5.2. Audit Events

Use audit events for meaningful user, administrator, or business actions, not for every low-level task lifecycle event. Examples include:

- admin pipeline or settings publish;
- review claim, draft, diff, or completion;
- split settings changes or connection checks;
- explicit retention, archive, or delete actions that affect durable records.

Task lifecycle start/completion/failure belongs in `task_runs`; business or administrative accountability belongs in audit services.

### 5.3. Artifact Registration

When a task creates or copies a durable file, it must register the artifact when `document_id` exists in context.

Preferred helper:

```python
from modules.services.artifact_service import register_document_artifact

register_document_artifact(
    config_manager=self.config_manager,
    context=context,
    file_type="export_json",
    file_path=output_path,
    metadata={"task_key": self.task_key(context)},
)
```

Common artifact roles:

- `source_original`: uploaded or watched source PDF.
- `split_pdf`: child PDF generated by split processing.
- `export_pdf`: final PDF output.
- `export_json`: JSON metadata output.
- `export_csv`: CSV metadata output.
- `source_archive`: archived source PDF.

Do not encode artifact paths only in status details. Store durable files on disk and register them in SQLite `document_files`.

Artifact registration is currently best-effort and may return `None` when
there is no persisted document or when registration fails. A task should still
report the primary file-operation outcome accurately, while logging enough
non-sensitive information to diagnose missing artifact registration. The
shared helper logs database failures centrally using the document identifier,
artifact role, and exception type; do not add artifact paths, extracted values,
or exception messages that may contain sensitive data to this warning.

### 5.4. Task Approval and Dynamic Imports

Dynamic task imports are allow-listed by exact module/class pair.

- A built-in task must use the `standard_step.*` namespace and be added to
  `BUILTIN_TASKS` in `modules/services/task_registry_service.py`.
- A deployment-specific custom task must use the `custom_step.*` namespace,
  be enabled under `custom_steps.enabled`, and have its exact module/class pair
  listed under `custom_steps.registry`.
- Do not place customer-specific code under `standard_step.*` or weaken the
  approval check to accept arbitrary imports.
- Keep the registry-coverage tests passing so every `BaseTask` subclass under
  `standard_step/` is explicitly approved.

---

## 6. Additional Best Practices

- **Retry Logic:** Configured tasks already receive one Prefect retry from
  `WorkflowLoader`. Add task- or provider-level retries only for clearly
  transient operations, and avoid multiplying retries unintentionally.
- **Idempotency:** Assume `run()` may execute more than once. Use unique-path,
  existence, transaction, or deduplication safeguards so retries do not create
  duplicate database rows or corrupt durable files. Overlapping workflows must
  reserve generated output paths atomically (for example with
  `reserve_unique_filepath`) rather than relying on a separate existence check.
  Remove a reservation when the subsequent write fails.
- **Compensation:** When a task creates multiple related files or database rows,
  compensate already-created state if a later item fails. If compensation
  cannot remove partial workflow records, mark those records terminal so fan-in
  and operator views cannot remain indefinitely in a queued/processing state.
- **Sanitization:** Sanitize all filenames and paths to remove invalid characters and prevent collisions.
- **Logging:** Log useful task milestones, errors, and warnings without logging
  secrets, raw provider payloads, or unnecessary customer content.
- **Configuration:** Obtain configuration through the injected configuration
  provider and constructor parameters to maintain consistency and testability.
- **Extensibility:** Design tasks to be modular and easily extendable for future enhancements or customizations.
- **Testing:** Add focused unit tests for validation, success, handled errors,
  raised `TaskError`, retries or idempotency where relevant, and context
  preservation. Add workflow or integration tests when the task affects
  SQLite state, artifacts, pause/resume, split fan-out, or pipeline ordering.
- **Configuration validation:** Update the runtime/config-check validators,
  schemas, examples, and documentation when a task introduces new parameters
  or pipeline-order constraints.

---

## 7. Accessing the UUID PDF Document in Context

For tasks that need to access the UUID-named PDF document in the processing folder, always use the `file_path` key in the shared `context` dictionary to retrieve the file path.

This convention is used consistently across standard tasks such as:

- `standard_step.extraction.extract_pdf`
- `standard_step.storage.store_file_to_localdrive`
- `standard_step.archiver.archive_pdf`

Avoid using other keys like `processed_file_path` for this purpose, as they may not be set or consistent across tasks.

---

## 8. Example Task Modules

Refer to the following standard task modules as examples of best practices and structure:

- `standard_step.extraction.extract_pdf`
- `standard_step.split.llamacloud_split`
- `standard_step.review.review_gate`
- `standard_step.storage.store_metadata_as_csv`
- `standard_step.storage.store_metadata_as_json`
- `standard_step.storage.store_file_to_localdrive`
- `standard_step.archiver.archive_pdf`
- `standard_step.rules.update_reference`
- `standard_step.context.assign_nanoid`
- `standard_step.housekeeping.cleanup_task`

Helper modules such as provider adapters do not need to inherit `BaseTask`
unless they are directly configured as pipeline steps.

---

This document should be updated as new standards emerge or improvements are made to the task creation process.

Note: Terminal tasks, for example housekeeping, may omit artifact registration
when they only delete transient processing files, but they must return the
context, log operations, and preserve registered business artifacts. The
built-in housekeeping task is invoked and tracked by `WorkflowLoader`, not
listed in deployment YAML.
