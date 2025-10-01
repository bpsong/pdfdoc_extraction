"""Persist extracted metadata (v2) as a JSON file while preserving array-of-objects.

This v2 task is intended to work with extract_pdf_v2 which normalizes
array-of-objects to List[Any] under context["data"][normalized_field_name]
(e.g., "items"). The task preserves list-of-objects for fields marked as
is_table: true in the extraction.fields configuration while maintaining
backwards compatibility for scalar fields.

Behavior:
- Reads configuration (data_dir, filename template) from task params via
  ConfigManager singleton.
- Uses alias mapping from extraction.fields config when available.
- For fields marked with is_table: true, it keeps the list-of-objects
  structure intact under the alias/normalized field name.
- Generates a safe, unique filename (appending _1, _2, ...) to avoid
  overwrites.
- Uses windows_long_path for all filesystem paths.
- Updates StatusManager with start/completed/failed messages using
  task_slug = "store_metadata_json_v2".

This file follows the conventions used in the existing
standard_step/storage/store_metadata_as_json.py module but adapts the
transformation step for v2 array-of-objects support.
"""

from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
from modules.utils import (
    sanitize_filename,
    generate_unique_filepath,
    preprocess_filename_value,
    windows_long_path,
)
from modules.status_manager import StatusManager

# Task slug used for status updates
TASK_SLUG = "store_metadata_json_v2"


class StoreMetadataAsJsonV2(BaseTask):
    """Write v2 extracted metadata to JSON while preserving list-of-objects.

    This task expects the pipeline to put normalized extraction into
    context["data"] (dict). Fields that are arrays of objects (tables)
    should be preserved under their normalized names when the extraction
    configuration marks them with is_table: true.
    """

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        """Initialize task and read configuration.

        Args:
            config_manager: ConfigManager singleton instance.
            **params: Task parameters; expected keys: 'data_dir', 'filename'.

        Raises:
            TaskError: If required parameters are missing.
        """
        super().__init__(config_manager=config_manager, **params)
        logging.getLogger(__name__)  # ensure logging config has been applied
        self.logger = logging.getLogger(__name__)

        # Required params
        data_dir_str = self.params.get("data_dir")
        filename_template = self.params.get("filename")

        if not data_dir_str:
            raise TaskError("Missing 'data_dir' parameter in configuration for StoreMetadataAsJsonV2 task.")
        if not filename_template:
            raise TaskError("Missing 'filename' parameter in configuration for StoreMetadataAsJsonV2 task.")

        self.data_dir: Path = Path(windows_long_path(str(data_dir_str)))
        self.filename_template: str = str(filename_template)

        # Attempt to locate extraction.fields config for aliasing and is_table flags.
        tasks_config = self.config_manager.get_all().get("tasks", {})
        # Try a few likely extract task keys used in project (backwards compatible)
        extract_task_def = (
            tasks_config.get("extract_document_data")
            or tasks_config.get("extract_document")
            or tasks_config.get("extract_document_data_v2")
            or {}
        )
        extraction_params = extract_task_def.get("params", {}) if isinstance(extract_task_def, dict) else {}
        self.extraction_fields_config: Dict[str, Any] = extraction_params.get("fields", {})

        if not self.extraction_fields_config:
            # Not fatal; we can still write JSON without aliasing/is_table metadata
            self.logger.debug("No extraction.fields config found; aliasing/is_table info unavailable.")

    def on_start(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook executed when the task starts.

        Updates StatusManager that the task has started.
        """
        self.initialize_context(context)
        unique_id = str(context.get("id", "unknown"))
        try:
            StatusManager(self.config_manager).update_status(unique_id, f"Task Started: {TASK_SLUG}", step=f"Task Started: {TASK_SLUG}")
        except Exception:
            # Do not fail on status update errors
            self.logger.debug("Failed to write start status", exc_info=True)

    def validate_required_fields(self, context: Dict[str, Any]) -> None:
        """Validate that required internal configuration is present.

        Raises:
            TaskError: If required configuration is missing.
        """
        if not self.data_dir:
            raise TaskError("StoreMetadataAsJsonV2 missing required 'data_dir'.")
        if not self.filename_template:
            raise TaskError("StoreMetadataAsJsonV2 missing required 'filename' template.")

    def _build_safe_filename(self, data: Dict[str, Any]) -> str:
        """Build and sanitize filename from template and extracted data.

        Missing fields are filled with 'unknown'. Lists are joined by comma
        for filename purposes (but are preserved in JSON output).

        Args:
            data: Extracted data dictionary.

        Returns:
            str: base filename with .json extension
        """
        # Prepare formatting dict: convert values to safe strings
        formatted_parts: Dict[str, str] = {}
        for k in self._extract_template_keys(self.filename_template):
            raw_val = data.get(k, "unknown")
            if isinstance(raw_val, list):
                # For filename only, join simple values; nested objects become 'list'
                try:
                    joined = ",".join(preprocess_filename_value(x) if not isinstance(x, dict) else "list" for x in raw_val)
                    formatted_parts[k] = sanitize_filename(joined or "unknown")
                except Exception:
                    formatted_parts[k] = "unknown"
            else:
                formatted_parts[k] = sanitize_filename(preprocess_filename_value(raw_val))
        try:
            base = self.filename_template.format(**formatted_parts)
        except Exception:
            # Fallback: use a safe fallback name
            base = "metadata.json"
        if not base.lower().endswith(".json"):
            base += ".json"
        return base

    @staticmethod
    def _extract_template_keys(template: str) -> set:
        """Naive extraction of {keys} from a format string.

        This is intentionally simple and sufficient for our filename templates.
        """
        keys = set()
        cur = ""
        in_brace = False
        for ch in template:
            if ch == "{":
                in_brace = True
                cur = ""
                continue
            if ch == "}" and in_brace:
                in_brace = False
                if cur:
                    keys.add(cur)
                cur = ""
                continue
            if in_brace:
                cur += ch
        return keys

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the task: transform and write JSON to disk.

        Args:
            context: Pipeline context. Expects context["data"] to exist.

        Returns:
            The original context (Railway pattern). On errors, context is updated
            with 'error' and 'error_step' keys and returned.

        Behavior:
            - Map top-level scalar fields to aliases (if configured).
            - Preserve list-of-objects fields (is_table: true) under alias.
            - Ensure output filename uniqueness.
            - Update StatusManager at key points.
        """
        unique_id = str(context.get("id", "unknown"))
        try:
            data = context.get("data")
            if data is None:
                self.logger.warning(f"No extracted data found for {unique_id}. Skipping JSON storage.")
                return context

            if not isinstance(data, dict):
                raise TaskError("Extracted data must be a dict for JSON storage (v2).")

            if isinstance(data, dict) and not data:  # Empty dict
                self.logger.warning(f"Empty data dict found for {unique_id}. Creating minimal JSON file.")
                data = {"_empty": True}

            self.validate_required_fields(context)

            # Prepare filename
            try:
                base_filename = self._build_safe_filename(data)
            except Exception as e:
                raise TaskError(f"Failed to generate filename: {e}")

            # Determine unique output path (use generate_unique_filepath helper)
            name_without_ext, _ = os.path.splitext(base_filename)
            try:
                output_path = generate_unique_filepath(self.data_dir, name_without_ext, ".json")
                output_path = windows_long_path(str(output_path))
            except Exception as e:
                raise TaskError(f"Failed to create unique filepath in '{self.data_dir}': {e}")

            # Status: preparing to write
            try:
                StatusManager(self.config_manager).update_status(unique_id, "Preparing to write JSON", step=f"Preparing to write JSON - {TASK_SLUG}")
            except Exception:
                self.logger.debug("Status update (preparing) failed", exc_info=True)

            # Transform data according to extraction.fields config
            processed: Dict[str, Any] = {}

            for orig_key, value in data.items():
                # Determine config for this field, if present
                field_conf = {}
                if isinstance(self.extraction_fields_config, dict) and orig_key in self.extraction_fields_config:
                    # field_conf can be a dict like {"alias": "supplier_name", "is_table": True}
                    field_conf = self.extraction_fields_config.get(orig_key, {}) or {}

                alias = field_conf.get("alias") if field_conf.get("alias") else orig_key
                # Ensure alias is never None
                if not alias:
                    alias = orig_key

                # If this field is marked as a table (is_table == True), preserve list structure
                is_table = bool(field_conf.get("is_table")) if field_conf else False

                if is_table:
                    # Expect value to be a list (possibly list of dicts). If not, try to coerce.
                    if isinstance(value, list):
                        # Validate that all items in the list are dicts
                        validated_items = []
                        for item in value:
                            if isinstance(item, dict):
                                validated_items.append(item)
                            else:
                                # Handle non-dict items by converting to string representation
                                self.logger.warning(f"Non-dict item found in table field '{orig_key}': {item}. Converting to string.")
                                validated_items.append({"value": str(item)})
                        processed[alias] = validated_items
                    else:
                        # Coerce single scalar to single-item list to avoid losing data
                        processed[alias] = [value]
                else:
                    # For scalar fields or v1-style, keep the value as-is.
                    processed[alias] = value

            # Status: writing
            try:
                StatusManager(self.config_manager).update_status(unique_id, "Writing JSON file", step=f"Writing JSON file - {TASK_SLUG}")
            except Exception:
                self.logger.debug("Status update (writing) failed", exc_info=True)

            # Ensure data_dir exists
            try:
                Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise TaskError(f"Failed to create data directory '{self.data_dir}': {e}")

            # Write JSON (use text write with utf-8)
            try:
                with open(output_path, "w", encoding="utf-8") as fh:
                    json.dump(processed, fh, indent=4, ensure_ascii=False)
                self.logger.info(f"Metadata for {unique_id} stored as JSON at {output_path}")
                try:
                    StatusManager(self.config_manager).update_status(unique_id, f"Task Completed: {TASK_SLUG}", step=f"Task Completed: {TASK_SLUG}", details={"output_path": output_path})
                except Exception:
                    self.logger.debug("Status update (completed) failed", exc_info=True)
                # Put output path into context for downstream steps
                context["output_path"] = output_path
            except Exception as e:
                # On write failure, record and re-raise as TaskError
                try:
                    StatusManager(self.config_manager).update_status(unique_id, f"Task Failed: {TASK_SLUG}", step=f"Task Failed: {TASK_SLUG}", error=str(e))
                except Exception:
                    self.logger.debug("Status update (failed) failed", exc_info=True)
                # Update context with error for Railway pattern
                context["error"] = str(e)
                context["error_step"] = "StoreMetadataAsJsonV2"
                raise TaskError(f"Failed to write JSON to '{output_path}': {e}")

        except TaskError:
            # TaskError already meaningful; ensure context contains failure info and return
            if "error_step" not in context:
                context["error_step"] = "StoreMetadataAsJsonV2"
            try:
                StatusManager(self.config_manager).update_status(unique_id, f"Task Failed: {TASK_SLUG}", step=f"Task Failed: {TASK_SLUG}", error=context.get("error", "TaskError"))
            except Exception:
                self.logger.debug("Status update (failed outer) failed", exc_info=True)
            return context
        except Exception as e:
            # Unexpected exceptions: capture in context and update status manager
            context["error"] = str(e)
            context["error_step"] = "StoreMetadataAsJsonV2"
            try:
                StatusManager(self.config_manager).update_status(unique_id, f"Task Failed: {TASK_SLUG}", step=f"Task Failed: {TASK_SLUG}", error=str(e))
            except Exception:
                self.logger.debug("Status update (failed unexpected) failed", exc_info=True)
            self.logger.exception("Unhandled exception in StoreMetadataAsJsonV2")
            return context

        return context