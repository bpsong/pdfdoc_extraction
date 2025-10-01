"""
Write v2 extracted metadata to CSV with row-per-item expansion for table fields.

This implements the v2 CSV storage task as described in PRD section 9.5 / task 8.3.2.
It supports:
- Backwards-compatible scalar-only behavior (single-row CSV).
- Table-field expansion: when a field is marked is_table: true in extraction
  configuration, it will create one CSV row per item in that table, repeating
  top-level scalar fields and prefixing item columns with 'item_'.
- Aliases from extraction config are used for CSV headers where available.

Behavior:
- Reads configuration (data_dir, filename template) from ConfigManager.
- Uses StatusManager to report start/completion/failure using task_slug.
- Cleans strings for CSV (newlines -> spaces).
- Ensures unique filenames by appending _1, _2, ... if necessary.
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
from modules.status_manager import StatusManager
from modules.utils import windows_long_path, sanitize_filename, preprocess_filename_value

TASK_SLUG = "store_metadata_csv_v2"


class StoreMetadataAsCsvV2(BaseTask):
    """
    Task to store normalized v2 extraction metadata as CSV.

    Expects context["data"] to be a dict (normalized extraction). Table fields
    (arrays of objects) are preserved under their normalized names when the
    extraction configuration marks them with is_table: true.
    """

    def __init__(self, config_manager: ConfigManager, **params: Any) -> None:
        """
        Initialize task and read configuration.

        Args:
            config_manager: ConfigManager singleton instance.
            **params: Task parameters provided by workflow loader.
        """
        super().__init__(config_manager=config_manager, **params)
        logging.getLogger(__name__)  # ensure logging config has been applied
        self.logger = logging.getLogger(__name__)
        # load storage-specific params from the central config or params
        storage_cfg = self.params.get("storage", {}) or {}
        # support top-level params compat
        self.data_dir_template = storage_cfg.get("data_dir") or self.params.get("data_dir")
        self.filename_template = storage_cfg.get("filename") or self.params.get("filename")

        # If not found in params, try to get from config_manager (try both direct keys and nested paths)
        if not self.data_dir_template:
            self.data_dir_template = self.config_manager.get("data_dir")
        if not self.filename_template:
            self.filename_template = self.config_manager.get("filename")

        # extraction fields config (if present) - mapping of field_name -> config
        # expect structure similar to extract_pdf_v2 fields
        self.extraction_fields = self.params.get("extraction", {}).get("fields", {}) or {}

        # If not found in params, try to get from config_manager
        if not self.extraction_fields:
            # Try direct extraction config first
            extraction_config = self.config_manager.get("extraction")
            if extraction_config and isinstance(extraction_config, dict):
                self.extraction_fields = extraction_config.get("fields", {})
            else:
                # Fallback: try to locate extraction.fields config from extract task
                tasks_config = self.config_manager.get_all().get("tasks", {})
                extract_task_def = (
                    tasks_config.get("extract_document_data")
                    or tasks_config.get("extract_document")
                    or tasks_config.get("extract_document_data_v2")
                    or {}
                )
                extraction_params = extract_task_def.get("params", {}) if isinstance(extract_task_def, dict) else {}
                self.extraction_fields = extraction_params.get("fields", {})

        # task slug used in status updates
        self.task_slug = self.params.get("task_slug", TASK_SLUG)

        # Initialize logger
        self.logger = logging.getLogger(__name__)

    def on_start(self, context: Dict[str, Any]) -> None:
        """Log and update status that the task has started."""
        unique_id = str(context.get("id", "unknown"))
        self.logger.info("Starting StoreMetadataAsCsvV2 for id=%s", unique_id)
        try:
            StatusManager(self.config_manager).update_status(unique_id, f"Task Started: {self.task_slug}", step=f"Task Started: {self.task_slug}")
        except Exception:
            self.logger.debug("Status update (started) failed", exc_info=True)

    def validate_required_fields(self, context: Dict[str, Any]) -> None:
        """
        Validate that required configuration and context are available.

        Raises:
            TaskError: if required fields are missing.
        """
        self.logger.debug(f"Validating fields: data_dir={self.data_dir_template}, filename={self.filename_template}, has_data={'data' in context}")
        if not self.data_dir_template:
            raise TaskError("Missing 'data_dir' parameter in configuration for StoreMetadataAsCsvV2 task.")
        if not self.filename_template:
            raise TaskError("Missing 'filename' parameter in configuration for StoreMetadataAsCsvV2 task.")
        if "data" not in context:
            self.logger.debug("Validation failed: 'data' not in context")
            raise TaskError("Missing 'data' in context for StoreMetadataAsCsvV2 task.")

    def _detect_table_field(self, context: Dict[str, Any]) -> Optional[str]:
        """
        Detect the normalized table field name from extraction_fields config.

        Returns:
            Normalized field name (key in context['data']) marked as is_table: true,
            or None if none found.
        """
        # extraction_fields may be dict of field_name -> metadata dict
        for field_key, cfg in self.extraction_fields.items():
            try:
                if isinstance(cfg, dict) and cfg.get("is_table"):
                    # normalized name could be provided via cfg.get("normalized_name") or cfg.get("name")
                    normalized = cfg.get("normalized_name") or cfg.get("name") or field_key
                    return normalized
            except Exception:
                continue
        # Fallback: inspect context data for list-of-dicts fields
        data = context.get("data", {})
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list) and v and all(isinstance(it, dict) for it in v):
                    return k
        return None

    def _generate_unique_filepath(self, data_dir: Path, base_name: str, ext: str = ".csv") -> Path:
        """
        Generate a unique filepath in data_dir by appending numeric suffixes.

        Args:
            data_dir: target directory Path
            base_name: filename without extension
            ext: file extension (including dot)

        Returns:
            Path to a non-existing file (unique).
        """
        attempt = 0
        candidate = data_dir / f"{base_name}{ext}"
        while candidate.exists():
            attempt += 1
            candidate = data_dir / f"{base_name}_{attempt}{ext}"
        return candidate

    @staticmethod
    def _clean_value(val: Any) -> str:
        """
        Convert a value to a CSV-safe string: replace newlines with spaces.

        Lists become comma-separated strings.
        """
        if val is None:
            return ""
        if isinstance(val, list):
            # join list elements with comma, flatten nested primitives
            cleaned = []
            for it in val:
                if it is None:
                    continue
                if isinstance(it, (dict, list)):
                    cleaned.append(str(it))
                else:
                    cleaned.append(str(it))
            return ",".join(cleaned)
        if isinstance(val, dict):
            return str(val)
        s = str(val)
        # Replace Windows line endings first, then individual line ending characters
        s = s.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        return s

    def _map_alias(self, field_key: str, is_item: bool = False) -> str:
        """
        Return alias for a field key from extraction_fields if available.
        For item-level fields, the alias will be prefixed with 'item_' by the caller.
        """
        cfg = self.extraction_fields.get(field_key, {}) or {}
        alias = cfg.get("alias") or cfg.get("name") or field_key
        return alias

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the CSV storage task.

        Returns:
            context (possibly updated with output_path or error information).
        """
        try:
            self.validate_required_fields(context)
            unique_id = str(context.get("id", "unknown"))
            data = context.get("data", {})
            self.logger.debug(f"Starting CSV task for {unique_id}, data keys: {list(data.keys()) if data else 'None'}")
            if data is None:
                self.logger.warning("No extracted data found for %s. Skipping CSV storage.", unique_id)
                return context

            if data is not None and not isinstance(data, dict):
                raise TaskError("Extracted data must be a dict for CSV storage (v2).")

            if isinstance(data, dict) and not data:  # Empty dict
                self.logger.warning(f"Empty data dict found for {unique_id}. Creating minimal CSV file.")
                # Handle empty dict case by creating a minimal row
                data = {"_message": "No data extracted"}

            # Resolve data_dir and filename template via ConfigManager
            data_dir_str = self.data_dir_template

            data_dir = Path(windows_long_path(str(data_dir_str)))
            data_dir.mkdir(parents=True, exist_ok=True)

            # Build base filename using template and available scalar values from data
            # Template may contain placeholders like {nanoid}, {supplier_name}, etc.
            # Use context["data"] (a dict) for formatting.
            filename_template = self.filename_template or "{id}"
            # Prepare format mapping with preprocessing and sanitization for consistency
            format_map: Dict[str, Any] = {}
            if isinstance(data, dict):
                # Use the same preprocessing and sanitization as v1 CSV and v2 JSON for consistency
                format_map = {
                    k: sanitize_filename(preprocess_filename_value(v)) if not isinstance(v, list) else sanitize_filename(",".join(map(preprocess_filename_value, v)))
                    for k, v in data.items()
                }
            # Add the unique_id to format_map for fallback templates
            format_map["id"] = unique_id
            try:
                base_filename = filename_template.format(**format_map)
            except Exception:
                # Graceful fallback: join some known keys or use unique id
                base_filename = f"{unique_id}"

            # sanitize base_filename for filesystem (remove path separators)
            base_filename = base_filename.replace(os.sep, "_").replace("/", "_").strip()
            if not base_filename:
                base_filename = unique_id

            # Detect table field (if any)
            table_field = self._detect_table_field(context)
            # Build rows and headers
            rows: List[Dict[str, Any]] = []
            headers: List[str] = []

            # Validate table field structure
            table_items = None
            if table_field:
                table_value = data.get(table_field)
                if not isinstance(table_value, list):
                    self.logger.warning(f"Table field '{table_field}' is not a list: {type(table_value)}. Treating as scalar.")
                    table_field = None
                else:
                    # Validate and convert all items to dicts
                    validated_items = []
                    for i, item in enumerate(table_value):
                        if isinstance(item, dict):
                            validated_items.append(item)
                        elif item is not None:
                            self.logger.warning(f"Non-dict item at index {i} in table field '{table_field}': {item}. Converting to string.")
                            validated_items.append({"value": str(item)})
                        else:
                            # Handle None items
                            validated_items.append({"_null": True})
                    table_items = validated_items

            # If no table field or table is empty, fall back to v1 behavior:
            if not table_field or not table_items:
                # Single row representing scalar fields. Lists become joined strings.
                row: Dict[str, Any] = {}
                # use extraction_fields order where possible, but include all data fields for v1 compatibility
                processed_fields = set()

                # First, process fields defined in extraction_fields
                if self.extraction_fields:
                    for field_key, cfg in self.extraction_fields.items():
                        # skip fields that are marked as table in v2 (they might be lists of objects)
                        if isinstance(cfg, dict) and cfg.get("is_table"):
                            continue
                        alias = cfg.get("alias") if isinstance(cfg, dict) else None
                        alias = alias or cfg.get("name") if isinstance(cfg, dict) else alias
                        header = alias or field_key
                        value = data.get(field_key)
                        row[header] = self._clean_value(value)
                        processed_fields.add(field_key)

                # Then add any remaining fields from data that weren't in extraction_fields
                for k, v in data.items():
                    if k in processed_fields:
                        continue
                    if isinstance(v, list) and v and all(isinstance(it, dict) for it in v):
                        # skip table-like fields in this mode
                        continue
                    row[k] = self._clean_value(v)
                rows.append(row)
                # headers in deterministic order
                headers = list(rows[0].keys()) if rows else []
            else:
                # Table field present and non-empty -> expand rows per item
                # table_items is already validated above
                # scalar top-level fields are those not equal to table_field and not lists-of-dicts
                scalar_fields: List[str] = []
                if isinstance(data, dict):
                    for k, v in data.items():
                        if k == table_field:
                            continue
                        # treat list-of-primitives as scalar to be repeated
                        if isinstance(v, list) and v and all(not isinstance(it, dict) for it in v):
                            scalar_fields.append(k)
                        elif isinstance(v, dict):
                            # nested dict as scalar: stringify and repeat
                            scalar_fields.append(k)
                        elif isinstance(v, list) and not v:
                            # empty list -> include
                            scalar_fields.append(k)
                        else:
                            scalar_fields.append(k)

                # item fields: union of keys in all items (preserve order from first item)
                item_fields_ordered: List[str] = []
                if table_items:
                    first_item = table_items[0]
                    if isinstance(first_item, dict):
                        for k in first_item.keys():
                            item_fields_ordered.append(k)
                    else:
                        # Handle non-dict first item (shouldn't happen after validation, but being safe)
                        self.logger.warning(f"First table item is not a dict: {type(first_item)}. Using 'value' as field name.")
                        item_fields_ordered.append("value")

                    # ensure we include any other keys that appear later
                    for it in table_items[1:]:
                        if isinstance(it, dict):
                            for k in it.keys():
                                if k not in item_fields_ordered:
                                    item_fields_ordered.append(k)
                        else:
                            # Handle non-dict items
                            if "value" not in item_fields_ordered:
                                item_fields_ordered.append("value")

                # Build headers: scalar aliases first, then item aliases prefixed with item_
                headers = []
                scalar_aliases: Dict[str, str] = {}
                for sf in scalar_fields:
                    # get alias from extraction_fields if present
                    alias = None
                    cfg = self.extraction_fields.get(sf, {}) or {}
                    alias = cfg.get("alias") if isinstance(cfg, dict) else None
                    alias = alias or cfg.get("name") if isinstance(cfg, dict) else alias
                    header = alias or sf
                    scalar_aliases[sf] = header
                    headers.append(header)

                item_aliases: Dict[str, str] = {}
                for itf in item_fields_ordered:
                    # item-level config may be nested under the table field config
                    # e.g. extraction_fields may contain an entry for the table with subfields
                    alias = None
                    # check top-level fields mapping first
                    cfg_top = self.extraction_fields.get(itf, {}) or {}
                    if isinstance(cfg_top, dict):
                        alias = cfg_top.get("alias") or cfg_top.get("name")
                    # check table-specific subfield mapping if available
                    table_cfg = self.extraction_fields.get(table_field, {}) or {}
                    if isinstance(table_cfg, dict):
                        # Prefer item_fields over fields for the schema used in tests
                        subfields = table_cfg.get("item_fields") or table_cfg.get("fields") or {}
                        if isinstance(subfields, dict):
                            sf_cfg = subfields.get(itf, {}) or {}
                            if isinstance(sf_cfg, dict):
                                alias = alias or sf_cfg.get("alias") or sf_cfg.get("name")
                    header = (alias or itf)
                    prefixed = f"item_{header}"
                    item_aliases[itf] = prefixed
                    headers.append(prefixed)

                # Build rows by combining scalar fields and each item
                for item in table_items:
                    row: Dict[str, Any] = {}
                    for sf in scalar_fields:
                        header = scalar_aliases.get(sf, sf)
                        row[header] = self._clean_value(data.get(sf))
                    for itf in item_fields_ordered:
                        prefixed_header = item_aliases.get(itf, f"item_{itf}")
                        row[prefixed_header] = self._clean_value(item.get(itf))
                    rows.append(row)

            # Ensure headers include any keys present in rows (in case of missing extraction_fields)
            if rows and not headers:
                headers = list(rows[0].keys())
            # unify header ordering across all rows: ensure every row has all headers
            for r in rows:
                for h in headers:
                    if h not in r:
                        r[h] = ""

            # Create unique file path
            output_path = self._generate_unique_filepath(data_dir, base_filename, ".csv")
            output_path = Path(windows_long_path(str(output_path)))

            # Write CSV
            try:
                with open(output_path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=headers)
                    writer.writeheader()
                    # status update while writing rows (best-effort)
                    try:
                        StatusManager(self.config_manager).update_status(unique_id, "Writing CSV rows", step="Writing CSV rows")
                    except Exception:
                        self.logger.debug("Status update (writing rows) failed", exc_info=True)
                    writer.writerows(rows)
            except Exception as e:
                # capture error and update status manager, but follow Railway pattern: return context with error info
                context["error"] = str(e)
                context["error_step"] = "StoreMetadataAsCsvV2"
                try:
                    StatusManager(self.config_manager).update_status(unique_id, f"Task Failed: {self.task_slug}", step=f"Task Failed: {self.task_slug}", error=str(e))
                except Exception:
                    self.logger.debug("Status update (failed) failed", exc_info=True)
                self.logger.exception("Failed writing CSV for %s", unique_id)
                return context

            # Success updates
            self.logger.info("Metadata for %s stored as CSV at %s", unique_id, output_path)
            try:
                StatusManager(self.config_manager).update_status(unique_id, f"Task Completed: {self.task_slug}", step=f"Task Completed: {self.task_slug}", details={"output_path": str(output_path), "rows": len(rows)})
            except Exception:
                self.logger.debug("Status update (completed) failed", exc_info=True)

            # Attach output path to context
            context["output_path"] = str(output_path)
            context["rows_written"] = len(rows)
            return context

        except TaskError as e:
            # Known validation/task errors - ensure context populated and returned
            context["error"] = str(e)
            if "error_step" not in context:
                context["error_step"] = "StoreMetadataAsCsvV2"
            try:
                StatusManager(self.config_manager).update_status(str(context.get("id", "unknown")), f"Task Failed: {self.task_slug}", step=f"Task Failed: {self.task_slug}", error=str(e))
            except Exception:
                self.logger.debug("Status update (failed outer) failed", exc_info=True)
            return context
        except Exception as e:
            # Unexpected exceptions: capture and return context
            context["error"] = str(e)
            context["error_step"] = "StoreMetadataAsCsvV2"
            try:
                StatusManager(self.config_manager).update_status(str(context.get("id", "unknown")), f"Task Failed: {self.task_slug}", step=f"Task Failed: {self.task_slug}", error=str(e))
            except Exception:
                self.logger.debug("Status update (failed unexpected) failed", exc_info=True)
            self.logger.exception("Unhandled exception in StoreMetadataAsCsvV2")
            return context