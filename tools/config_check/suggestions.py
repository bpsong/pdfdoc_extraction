"""Suggestion generation for config-check findings."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

SuggestionHandler = Callable[[Dict[str, Any]], Optional[str]]


def _describe_config_key(details: Dict[str, Any]) -> str:
    """Return a human-friendly label for the configuration key in a finding."""
    key = details.get("config_key")
    if not key:
        return "this setting"
    return f"'{key}'"


def _describe_clause(details: Dict[str, Any]) -> str:
    """Return a label for a csv_match clause using its index when available."""
    index = details.get("index")
    if index is None:
        return "each clause"
    return f"clause[{index}]"


def _suggest_create_dir(details: Dict[str, Any]) -> str:
    """Suggest creating a directory or updating the path reference."""
    path = details.get("path")
    config_key = _describe_config_key(details)
    if path:
        return f"Create the directory at '{path}' or update {config_key} to point to an existing directory."
    return f"Create the directory or update {config_key} to point to an existing directory."


def _suggest_watch_folder(details: Dict[str, Any]) -> str:
    """Suggest preparing the watch folder ahead of time."""
    path = details.get("path")
    if path:
        return f"Create the watch folder '{path}' before running the service or update watch_folder.dir."
    return "Create the watch folder directory before running the service or update watch_folder.dir."


def _suggest_directory_type(details: Dict[str, Any]) -> str:
    """Suggest correcting values that should reference directories."""
    config_key = _describe_config_key(details)
    return f"Update {config_key} so it points to an existing directory."


def _suggest_create_file(details: Dict[str, Any]) -> str:
    """Suggest providing files required by the configuration."""
    path = details.get("path")
    config_key = _describe_config_key(details)
    if path:
        return f"Create the file at '{path}' or update {config_key} to an existing file."
    return f"Create the referenced file or update {config_key} to an existing file."


def _suggest_required_string(details: Dict[str, Any]) -> str:
    """Suggest providing a non-empty string for required parameters."""
    config_key = _describe_config_key(details)
    return f"Set {config_key} to a non-empty string path."


def _suggest_pipeline_missing_task(details: Dict[str, Any]) -> str:
    """Suggest adding a missing task or removing the pipeline reference."""
    task_name = details.get("task_name", "the task")
    return f"Add tasks.{task_name} or remove '{task_name}' from the pipeline."


def _suggest_pipeline_duplicate(details: Dict[str, Any]) -> str:
    """Suggest resolving duplicate pipeline entries."""
    task_name = details.get("task_name", "the task")
    return f"Confirm whether '{task_name}' needs to run twice or remove the duplicate pipeline entry."


def _suggest_pipeline_storage(details: Dict[str, Any]) -> str:
    """Suggest placing extraction tasks before storage tasks."""
    task_name = details.get("task_name", "the storage task")
    return f"Move an extraction task before '{task_name}' or remove extraction tokens from its parameters."


def _suggest_storage_filename_scalar(details: Dict[str, Any]) -> str:
    '''Suggest using scalar extraction fields for storage filenames.'''
    token = details.get("token", "token")
    task_name = details.get("task_name", "the storage task")
    config_key = _describe_config_key(details)
    return (
        f"Expose '{token}' as a scalar extraction field before '{task_name}' runs or update {config_key} to remove the '{{{token}}}' placeholder."
    )



def _suggest_pipeline_storage_metadata(details: Dict[str, Any]) -> str:
    """Suggest adding metadata-producing extraction before v2 storage."""
    task_name = details.get("task_name", "the storage task")
    return (
        f"Schedule a metadata-producing extraction task (e.g., extract_document_data_v2) before '{task_name}' or update the storage configuration."
    )




def _suggest_multiple_tables(details: Dict[str, Any]) -> str:
    """Suggest reconciling multiple table field declarations."""
    table_fields = details.get('fields') or []
    formatted = ', '.join(table_fields) if table_fields else 'table fields'
    return (
        f"Leave only one field with is_table: true (currently: {formatted}) or split tables into"
        " separate extraction tasks."
    )


def _suggest_pipeline_nanoid(details: Dict[str, Any]) -> str:
    """Suggest scheduling a context task before nanoid usage."""
    task_name = details.get("task_name", "the task")
    return f"Schedule a context initializer (e.g., assign_nanoid) before '{task_name}'."


def _suggest_pipeline_missing_extraction(details: Dict[str, Any]) -> str:
    """Suggest inserting at least one extraction step."""
    return "Add an extraction task (e.g., standard_step.extraction.extract_pdf) before downstream steps."


def _suggest_unknown_token(details: Dict[str, Any]) -> str:
    """Suggest reconciling unknown template tokens with extraction fields."""
    token = details.get("token", "token")
    config_key = details.get("config_key", "this value")
    return (
        f"Add scalar extraction field '{token}' or update {config_key} to remove the '{{{token}}}' placeholder."
    )


def _suggest_import_module(details: Dict[str, Any]) -> str:
    """Suggest ensuring modules are importable."""
    module = details.get("module", "the module")
    return f"Check that module '{module}' is installed and available on PYTHONPATH."


def _suggest_import_class(details: Dict[str, Any]) -> str:
    """Suggest ensuring the configured class exists in the module."""
    module = details.get("module", "the module")
    class_name = details.get("class", "the class")
    return f"Verify that class '{class_name}' is defined in module '{module}'."


def _suggest_import_not_class(details: Dict[str, Any]) -> str:
    """Suggest pointing to a class rather than other attribute types."""
    class_name = details.get("class", "the attribute")
    return f"Ensure '{class_name}' references a task class, not a function or constant."


def _suggest_required_param(details: Dict[str, Any]) -> str:
    """Suggest providing a value for a missing required parameter."""
    config_key = _describe_config_key(details)
    return f"Provide a value for {config_key}."


def _suggest_field_alias(details: Dict[str, Any]) -> str:
    """Suggest adding aliases to extraction fields."""
    field_name = details.get("field", "the field")
    return f"Add an 'alias' for field '{field_name}' (e.g., alias: Supplier)."


def _suggest_field_type(details: Dict[str, Any]) -> str:
    """Suggest specifying valid field types."""
    field_name = details.get("field", "the field")
    return (
        f"Set the type for field '{field_name}' to one of str, int, float, bool, Any, Optional[T], or List[T]."
    )


def _suggest_field_item_fields(details: Dict[str, Any]) -> str:
    """Suggest defining table field column metadata."""
    field_name = details.get("field", "the field")
    return f"Define item_fields for table field '{field_name}' describing the columns returned."


def _suggest_context_length(details: Dict[str, Any]) -> str:
    """Suggest choosing a valid nanoid length."""
    return "Choose a length between 5 and 21 for nanoid generation."


_SUGGESTION_HANDLERS: Dict[str, SuggestionHandler] = {
    "path-missing-dir": _suggest_create_dir,
    "path-not-dir": _suggest_directory_type,
    "path-missing-file": _suggest_create_file,
    "path-not-file": _suggest_directory_type,
    "path-value-missing": _suggest_required_string,
    "path-value-type": _suggest_required_string,
    "path-value-empty": _suggest_required_string,
    "watch-folder-missing-dir": _suggest_watch_folder,
    "pipeline-entry-invalid": lambda _: "Ensure pipeline entries are task ids (non-empty strings).",
    "pipeline-missing-task": _suggest_pipeline_missing_task,
    "pipeline-duplicate-task": _suggest_pipeline_duplicate,
    "pipeline-storage-before-extraction": _suggest_pipeline_storage,
    "pipeline-storage-metadata-missing": _suggest_pipeline_storage_metadata,
    "pipeline-storage-filename-non-scalar": _suggest_storage_filename_scalar,
    "pipeline-nanoid-before-context": _suggest_pipeline_nanoid,
    "pipeline-missing-extraction": _suggest_pipeline_missing_extraction,
    "pipeline-unknown-token": _suggest_unknown_token,
    "pipeline-not-list": lambda _: "Define pipeline as a list of task identifiers in execution order.",
    "tasks-not-mapping": lambda _: "Define the tasks section as a mapping of task ids to definitions.",
    "task-definition-not-mapping": lambda d: f"Define tasks.{d.get('task_name', 'task')} as a mapping with module, class, and params.",
    "task-import-invalid-module": lambda _: "Provide a module path string (e.g., standard_step.extraction.extract_pdf).",
    "task-import-invalid-class": lambda _: "Provide a class name string matching the task implementation.",
    "task-import-module": _suggest_import_module,
    "task-import-class": _suggest_import_class,
    "task-import-not-class": _suggest_import_not_class,
    "pipeline-duplicate-task": _suggest_pipeline_duplicate,
    "param-extraction-not-mapping": lambda _: "Define params as a mapping of parameter names to values for this extraction task.",
    "param-extraction-missing-fields": lambda _: "Add a 'fields' mapping describing the data to extract.",
    "param-field-invalid": lambda d: f"Define field '{d.get('field', 'field')}' as a mapping with alias and type.",
    "param-field-missing-alias": _suggest_field_alias,
    "param-field-invalid-type": _suggest_field_type,
    "param-field-istable-bool": lambda d: f"Set 'is_table' for field '{d.get('field', 'field')}' to true or false.",
    "param-field-missing-item-fields": _suggest_field_item_fields,
    "param-extraction-multiple-tables": _suggest_multiple_tables,
    "param-rules-not-mapping": lambda _: "Define this task's params as a mapping that includes reference_file, update_field, and csv_match.",
    "param-rules-missing-reference-file": lambda _: "Set reference_file to the CSV file that should be updated.",
    "param-rules-missing-update-field": lambda _: "Set update_field to the column name that must be updated.",
    "param-rules-csv-match-mapping": lambda _: "Provide a csv_match mapping with a type and clauses list.",
    "param-rules-csv-type": lambda _: "Set csv_match.type to 'column_equals_all'.",
    "param-rules-clauses-type": lambda _: "Define csv_match.clauses as a list of clause mappings.",
    "param-rules-clauses-count": lambda _: "Provide between 1 and 5 clause definitions in csv_match.clauses.",
    "param-rules-clause-not-mapping": lambda d: f"Ensure {_describe_clause(d)} is a mapping with column and from_context entries.",
    "param-rules-clause-column": lambda d: f"Provide a non-empty column value for {_describe_clause(d)}.",
    "param-rules-clause-context": lambda d: f"Provide a non-empty from_context value for {_describe_clause(d)}.",
    "param-rules-clause-number-type": lambda d: f"Set number on {_describe_clause(d)} to true/false or remove it.",
    "param-storage-missing-data-dir": lambda _: "Set data_dir to the output directory (e.g., ./output).",
    "param-storage-missing-filename": lambda _: "Provide a filename pattern (e.g., {supplier_name}.json).",
    "param-archiver-missing-archive-dir": lambda _: "Set archive_dir to the folder for archived files.",
    "param-not-mapping": lambda d: f"Define {d.get('config_key', 'these parameters')} as a mapping of names to values.",
    "param-context-length-type": lambda _: "Set length to an integer between 5 and 21.",
    "param-context-length-bounds": _suggest_context_length,
}


def get_suggestion(code: Optional[str], details: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return an actionable suggestion for a validation finding."""
    if not code:
        return None

    handler = _SUGGESTION_HANDLERS.get(code)
    if not handler:
        return None

    try:
        return handler(details or {})
    except Exception:
        return None
