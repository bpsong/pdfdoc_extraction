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
- Update the context with error details and the task identifier (`error_step`) to support the Railway Programming pattern. Wrap status updates in try/except to prevent masking primary errors.

---

## 2. Initial Setup Before Core Logic

- Extract and validate configuration parameters from the centralized `ConfigManager` singleton or task parameters during `__init__`.
- Use the `windows_long_path` utility function from `modules/utils.py` for all file and directory paths to ensure compatibility with Windows path length limitations.
- Initialize logging for the task to capture detailed execution information.
- Prepare any necessary data structures or models (e.g., Pydantic models for data validation in extraction tasks). Use utilities like `normalize_field_path` and `resolve_field` from `modules/utils.py` for context access.

---

## 3. Core Functionality Expectations

The core functionality of tasks varies widely depending on their purpose. While many standard tasks perform operations such as data extraction, storage, or file handling, tasks may also implement other logic such as data validation, calculations, or conditional processing.

For example, a task might:

- Extract structured data from PDFs.
- Store metadata as CSV or JSON files.
- Save processed files to a local drive.
- Perform calculations on extracted data (e.g., compute total invoice amount after discounts).
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

## 5. Standardized Status Timestamp Convention

All tasks must emit consistent, action-oriented status timestamps via StatusManager to ensure observability and analytics across the pipeline.

Required events per task (use the task slug, not class name):
- On start (in on_start):
  - StatusManager.update_status(unique_id, f"Task Started: <task_slug>", step=f"Task Started: <task_slug>")
- On successful completion (end of run):
  - StatusManager.update_status(unique_id, f"Task Completed: <task_slug>", step=f"Task Completed: <task_slug>")
- On failure (any exception path):
  - StatusManager.update_status(unique_id, f"Task Failed: <task_slug>", step=f"Task Failed: <task_slug>", error=str(e))

Task slug mapping examples:
- ExtractPdfTask → extract_document_data
- StoreMetadataAsCsv → store_metadata_csv
- StoreMetadataAsJson → store_metadata_json
- StoreFileToLocaldrive → store_file_to_localdrive
- ArchivePdfTask → archive_pdf

Notes:
- Use UTC ISO-8601 format provided by StatusManager; do not craft timestamps manually.
- Do not let status writes fail the task start/end; wrap in try/except to avoid masking primary task errors.
- Keep keys stable and lowercase with underscores for slugs to preserve analytics compatibility.

Example snippet (pattern):
- On start:
  self.status_manager.update_status(str(context.get("id", "unknown")), f"Task Started: {self.task_slug}", step=f"Task Started: {self.task_slug}")
- On success:
  self.status_manager.update_status(str(context.get("id", "unknown")), f"Task Completed: {self.task_slug}", step=f"Task Completed: {self.task_slug}", details={"task": self.__class__.__name__, ...})
- On failure:
  self.status_manager.update_status(str(context.get("id", "unknown")), f"Task Failed: {self.task_slug}", step=f"Task Failed: {self.task_slug}", error=str(e), details={"task": self.__class__.__name__})

---

## 5. Additional Best Practices

- **Retry Logic:**  
  Implement retry mechanisms for transient I/O errors using decorators or context managers.

- **Sanitization:**  
  Sanitize all filenames and paths to remove invalid characters and prevent collisions.

- **Logging:**  
  Log detailed information at each step, including errors and warnings, to facilitate troubleshooting.

- **Configuration:**  
  Obtain all configuration parameters from the centralized `ConfigManager` to maintain consistency.

- **Extensibility:**  
  Design tasks to be modular and easily extendable for future enhancements or customizations.

---

## 6. Accessing the UUID PDF Document in Context

For tasks that need to access the UUID-named PDF document in the processing folder (the core input file for processing), **always use the `file_path` key in the shared `context` dictionary** to retrieve the file path.

This convention is used consistently across standard tasks such as:

- `standard_step.extraction.extract_pdf`
- `standard_step.storage.store_file_to_localdrive`
- `standard_step.archiver.archive_pdf`

Avoid using other keys like `processed_file_path` for this purpose, as they may not be set or consistent across tasks.

---

## 7. Example Task Modules

Refer to the following standard task modules as examples of best practices and structure:

- `standard_step.extraction.extract_pdf`  
- `standard_step.storage.store_metadata_as_csv`  
- `standard_step.storage.store_metadata_as_json`  
- `standard_step.storage.store_file_to_localdrive`  
- `standard_step.archiver.archive_pdf`  

---

This document should be updated as new standards emerge or improvements are made to the task creation process.

Note: Terminal tasks (e.g., housekeeping) may omit status updates if they finalize the pipeline, but should log operations for auditability.