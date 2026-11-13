"""Serialize workflow data to a uniquely reserved JSON artifact.

Constructor parameters own data_dir, filename and optional extraction.fields
aliases. Nested objects/arrays remain structured without requiring table flags.
Published tasks do not inherit deployment YAML or another task's field mapping.
Filename {id} uses document_id, falling back to context.id, rather than extracted
data.id. Register the result as export_json when document context is available."""

from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict

from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager
from modules.exceptions import TaskError
from modules.services.artifact_service import register_document_artifact
from modules.utils import (
    preprocess_filename_value,
    release_reserved_filepath,
    reserve_unique_filepath,
    sanitize_filename,
    windows_long_path,
)

class StoreMetadataAsJson(BaseTask):
    """Serialize context.data with optional task-specific top-level aliases."""

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        """Capture task parameters and reject missing data_dir or filename.

        The injected configuration provider is used for shared database infrastructure;
        field aliases come only from this task's extraction.fields parameter."""
        super().__init__(config_manager=config_manager, **params)
        logging.getLogger(__name__)  # ensure logging config has been applied
        self.logger = logging.getLogger(__name__)

        # Required params
        data_dir_str = self.params.get("data_dir")
        filename_template = self.params.get("filename")

        if not data_dir_str:
            raise TaskError("Missing 'data_dir' parameter in configuration for StoreMetadataAsJson task.")
        if not filename_template:
            raise TaskError("Missing 'filename' parameter in configuration for StoreMetadataAsJson task.")

        self.data_dir: Path = Path(windows_long_path(str(data_dir_str)))
        self.filename_template: str = str(filename_template)

        # Extraction field metadata is part of this task's published
        # definition. Deployment YAML is intentionally not consulted.
        extraction_config = self.params.get("extraction")
        explicit_fields = (
            extraction_config.get("fields")
            if isinstance(extraction_config, dict)
            else None
        )
        self.extraction_fields_config: Dict[str, Any]
        if isinstance(explicit_fields, dict):
            self.extraction_fields_config = explicit_fields
        else:
            self.extraction_fields_config = {}

        if not self.extraction_fields_config:
            # Not fatal; we can still write JSON without aliasing/is_table metadata
            self.logger.debug("No extraction.fields config found; aliasing/is_table info unavailable.")

    def on_start(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook executed when the task starts."""
        self.initialize_context(context)

    def validate_required_fields(self, context: Dict[str, Any]) -> None:
        """Validate that required internal configuration is present.

        Raises:
            TaskError: If required configuration is missing.
        """
        if not self.data_dir:
            raise TaskError("StoreMetadataAsJson missing required 'data_dir'.")
        if not self.filename_template:
            raise TaskError("StoreMetadataAsJson missing required 'filename' template.")

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
            - Register the generated JSON as a SQLite document artifact when
              document context exists.
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
                filename_data = {
                    **data, "id": str(context.get("document_id") or unique_id),
                }
                base_filename = self._build_safe_filename(filename_data)
            except Exception as e:
                raise TaskError(f"Failed to generate filename: {e}")

            name_without_ext, _ = os.path.splitext(base_filename)
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
                    # For scalar fields, keep the value as-is.
                    processed[alias] = value

            # Ensure data_dir exists
            try:
                Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise TaskError(f"Failed to create data directory '{self.data_dir}': {e}")

            try:
                reserved_path = reserve_unique_filepath(self.data_dir, name_without_ext, ".json")
                output_path = windows_long_path(str(reserved_path))
            except Exception as e:
                raise TaskError(f"Failed to reserve unique filepath in '{self.data_dir}': {e}")

            # Write JSON (use text write with utf-8)
            try:
                with open(output_path, "w", encoding="utf-8") as fh:
                    json.dump(processed, fh, indent=4, ensure_ascii=False)
                self.logger.info(f"Metadata for {unique_id} stored as JSON at {output_path}")
                # Put output path into context for downstream steps
                context["output_path"] = output_path
                register_document_artifact(
                    self.config_manager,
                    context,
                    file_type="export_json",
                    file_path=output_path,
                    metadata={"task_key": self.task_key(context)},
                )
            except Exception as e:
                if not release_reserved_filepath(reserved_path):
                    self.logger.warning("Failed to remove JSON output after a failed write")
                # On write failure, record and re-raise as TaskError
                # Update context with error for Railway pattern
                context["error"] = str(e)
                context["error_step"] = self.task_key(context)
                raise TaskError(f"Failed to write JSON to '{output_path}': {e}")

        except TaskError:
            # TaskError already meaningful; ensure context contains failure info and return
            if "error_step" not in context:
                context["error_step"] = self.task_key(context)
            return context
        except Exception as e:
            # Unexpected exceptions: capture in context and update status manager
            context["error"] = str(e)
            context["error_step"] = self.task_key(context)
            self.logger.exception("Unhandled exception in StoreMetadataAsJson")
            return context

        return context
