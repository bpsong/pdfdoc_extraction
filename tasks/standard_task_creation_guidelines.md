# Standardized Rules and Guidelines for Creating New Tasks

This document outlines the standardized structure, rules, and best practices for creating new tasks within the PDF document processing system. Following these guidelines will ensure consistency, maintainability, and ease of integration with the dynamic Prefect pipeline.

---

## 1. Task Structure Overview

Each task is a self-contained Python module that implements a specific step in the processing pipeline. Tasks must inherit from the `BaseTask` abstract class and implement required methods to integrate seamlessly with the workflow.

### Required Methods

- `__init__(self, config_manager: ConfigManager, **params)`
  Initialize the task instance, extract and validate configuration parameters, and prepare any necessary internal state. This method is called once when the task is instantiated.

- `on_start(self, context: dict) -> None`
  Initialize the task environment and perform any necessary setup or context validation before execution.

- `run(self, context: dict) -> dict | None`
  Implement the core business logic of the task. This method receives the shared `context` dictionary and must return an updated `context` dictionary reflecting the task's output or any errors. Terminal tasks may return `None`.

- `validate_required_fields(self, context: dict) -> None`
  Validate that all required configuration parameters and context data are present and correct. This method is called automatically before `run()`. For terminal tasks, validation may be minimal.

### Error Handling

- Use the `TaskError` exception class to signal critical failures.
- Wrap the `run()` method logic in a try-except block to catch `TaskError` and register errors in the context.
- Update the context with error details and the task identifier (`error_step`) to support the Railway Programming pattern.
- Do not write text status files or call `StatusManager` from new configured workflow tasks. Workflow lifecycle state is recorded by `WorkflowLoader`/`WorkflowManager` through SQLite `task_runs` and `documents` when `document_id` context exists.

---

## 2. Initial Setup Before Core Logic

- Extract and validate configuration parameters from the centralized `ConfigManager` singleton or task parameters during `__init__`.
- Use the `windows_long_path` utility function from `modules/utils.py` for all file and directory paths to ensure compatibility with Windows path length limitations.
- Initialize logging for the task to capture detailed execution information.
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

---

## 4. Final Step: Passing the Context Onward

- After completing the core logic, the task must return the updated `context` dictionary.
- The `context` dictionary should include keys such as:
  - `data`: The processed or extracted data.
  - `error`: Any error messages encountered during execution.
  - `error_step`: The name of the task where an error occurred.
- Ensure that the context is passed unchanged if the task is skipped or encounters non-critical issues. Terminal tasks may return `None` instead of context.

---

## 5. Workflow State, Audit, and Artifact Convention

SQLite is the primary workflow-state source. New tasks must integrate with the shared workflow context and services instead of writing status text files.

### 5.1. Task-Run State

The workflow runner records standardized task lifecycle events:

- On start: a SQLite `task_runs` row is started for the configured task key.
- On success: the task run is completed with output summary data from the returned context.
- On failure: the task run is failed with error details, and document status is updated where appropriate.

Task implementations should:

- keep a stable task slug/key that matches the `pipeline` and `tasks` configuration key;
- return meaningful context changes so the workflow runner can summarize outputs;
- call `self.register_error(context, TaskError(...))` before returning or raising when the task handles an error;
- raise `TaskError` for failures that should stop the current happy path;
- avoid direct writes to `StatusManager`, status `.txt` files, `/api/files`, or `/api/status/{file_id}` compatibility shapes.

Task slug mapping examples:

- `ExtractPdfTask` -> `extract_document_data`
- `StoreMetadataAsCsv` -> `store_metadata_csv`
- `StoreMetadataAsJson` -> `store_metadata_json`
- `StoreFileToLocaldrive` -> `store_file_to_localdrive`
- `ArchivePdfTask` -> `archive_pdf`

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
    metadata={"task": self.__class__.__name__},
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

---

## 6. Additional Best Practices

- **Retry Logic:** Implement retry mechanisms for transient I/O errors using decorators or context managers.
- **Sanitization:** Sanitize all filenames and paths to remove invalid characters and prevent collisions.
- **Logging:** Log detailed information at each step, including errors and warnings, to facilitate troubleshooting.
- **Configuration:** Obtain all configuration parameters from the centralized `ConfigManager` to maintain consistency.
- **Extensibility:** Design tasks to be modular and easily extendable for future enhancements or customizations.

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
- `standard_step.storage.store_metadata_as_csv`
- `standard_step.storage.store_metadata_as_json`
- `standard_step.storage.store_file_to_localdrive`
- `standard_step.archiver.archive_pdf`

---

This document should be updated as new standards emerge or improvements are made to the task creation process.

Note: Terminal tasks, for example housekeeping, may omit artifact registration when they only delete transient processing files, but they should log operations and preserve registered business artifacts.
