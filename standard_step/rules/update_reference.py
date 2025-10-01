"""Update fields in a CSV reference file based on values from the pipeline context.

This module implements UpdateReferenceTask, which selects rows from a reference
CSV using up to five ANDed equality clauses (column_equals_all) and updates a
single target column to a configured value. Matching is type-aware: each clause
can force numeric or string comparison, or auto-detect based on the context
value. The update is written atomically with an optional backup.

Notes:
    - Reads parameters via injected BaseTask params:
      reference_file, update_field, write_value, backup, task_slug, csv_match.
    - Uses StatusManager for standardized start/success/failure updates.
    - Reads/writes a CSV file on disk; atomic replace with optional .backup.
    - Follows Railway pattern: errors registered in context and surfaced as TaskError.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from modules.base_task import BaseTask
from modules.config_manager import ConfigManager
from modules.exceptions import TaskError
from modules.status_manager import StatusManager
from modules.utils import normalize_field_path, resolve_field


def _normalize_string(value: Any) -> str:
    """Normalize a value to a lowercased string, treating None as empty.

    Args:
        value (Any): Value to normalize.

    Returns:
        str: Lowercased string form of the value.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.lower()


def _strip_number_formatting(s: str) -> str:
    """Remove commas and spaces from a numeric-looking string.

    Args:
        s (str): Input string.

    Returns:
        str: String without commas/spaces.
    """
    return s.replace(",", "").replace(" ", "")


def _coerce_to_float(value: Any) -> Optional[float]:
    """Attempt to coerce a value to float after normalization.

    Args:
        value (Any): Input value.

    Returns:
        Optional[float]: Float value or None on failure.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = _strip_number_formatting(s)
    try:
        return float(s)
    except ValueError:
        return None


def _keywords_all_match(haystack: str, keywords: List[str]) -> bool:
    """Return True if all keywords appear in haystack (case-insensitive).

    Args:
        haystack (str): Source string.
        keywords (List[str]): Keywords to check.

    Returns:
        bool: True if every keyword is present.
    """
    hs = _normalize_string(haystack)
    for kw in keywords:
        if _normalize_string(kw) not in hs:
            return False
    return True


@dataclass
class Clause:
    """Selection clause definition.

    Attributes:
        column (str): CSV column to compare.
        from_context (str): Dotted context path to the comparison value.
        number (Optional[bool]): If True, force numeric compare; if False, force
            string compare; if None, auto-detect based on context value.
    """
    column: str
    from_context: str
    number: Optional[bool] = None  # True=force numeric, False=force string, None=auto


class UpdateReferenceTask(BaseTask):
    """CSV reference updater using type-aware equality selection.

    Responsibilities:
        - Validate required params and CSV structure.
        - Build a combined selection mask from up to five clauses.
        - Update a single column with a configured value for matched rows.
        - Write results atomically and report status via StatusManager.

    Integration:
        Obtains params through WorkflowLoader/BaseTask. Emits standardized
        status events. Returns updated context with operation summary.

    Args:
        config_manager (ConfigManager): Project configuration manager.
        **params: Expected keys include:
            - reference_file (str): Path to CSV file to update.
            - update_field (str): Column to write.
            - write_value (str): Value to write for matched rows.
            - backup (bool): Whether to write a .backup before replacement.
            - task_slug (str): Slug used in status events.
            - csv_match (dict): With 'type' and 'clauses' definitions.

    Notes:
        - Side effects: File I/O, status updates.
        - Errors are reported as TaskError and registered in context.
    """
    
    def __init__(self, config_manager: ConfigManager, **params):
        """Initialize UpdateReferenceTask and capture parameters.

        Args:
            config_manager (ConfigManager): Configuration manager.
            **params: Task parameters; see class docstring for keys.

        Raises:
            TaskError: If csv_match is invalid (type or clause definitions).
        """
        super().__init__(config_manager, **params)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.status_manager = StatusManager(config_manager)
    
        # Extract parameters (ConfigManager validation of *_file paths occurs at startup)
        self.reference_file: str = params.get("reference_file", "") or ""
        self.update_field: str = params.get("update_field", "") or ""
        self.write_value: str = params.get("write_value", "Updated")
        self.backup: bool = bool(params.get("backup", True))
    
        # Standardized task slug for status events (lowercase underscore)
        self.task_slug: str = params.get("task_slug", "update_csv_reference")
    
        # csv_match: column_equals_all with up to 5 clauses
        csv_match: Dict[str, Any] = params.get("csv_match", {}) or {}
        csv_match_type = csv_match.get("type", "column_equals_all")
        if csv_match_type != "column_equals_all":
            raise TaskError("csv_match.type must be 'column_equals_all' for this implementation.")
        clauses_cfg = csv_match.get("clauses", [])
        if not isinstance(clauses_cfg, list) or not (1 <= len(clauses_cfg) <= 5):
            raise TaskError("csv_match.clauses must be a list with 1 to 5 items")
        self.clauses: List[Clause] = []
        for idx, c in enumerate(clauses_cfg):
            col = (c or {}).get("column")
            from_ctx = (c or {}).get("from_context")
            number = (c or {}).get("number", None)
            if not col or not from_ctx:
                raise TaskError(f"csv_match.clauses[{idx}] requires 'column' and 'from_context'")
            if number is not None and not isinstance(number, bool):
                raise TaskError(f"csv_match.clauses[{idx}].number must be boolean if provided")

            # Normalize field path and check for deprecation warning
            normalized_path, was_bare_name = normalize_field_path(from_ctx)
            self.clauses.append(Clause(column=col, from_context=normalized_path, number=number))

            # Emit deprecation warning for explicit "data." prefix usage
            if not was_bare_name and from_ctx.startswith("data."):
                self.logger.warning(
                    'DeprecationWarning: "data."prefixed field paths are deprecated; use bare field names like "purchase_order_number" instead. Provided: "%s"',
                    from_ctx
                )
    
    def on_start(self, context: dict):
        """Mark the task as started using StatusManager.

        Args:
            context (dict): Pipeline context containing 'id'.

        Notes:
            Status update failures are ignored to avoid blocking progress.
        """
        self.initialize_context(context)
        uid = str(context.get("id", "unknown"))
        try:
            self.status_manager.update_status(
                unique_id=uid,
                status=f"Task Started: {self.task_slug}",
                step=f"Task Started: {self.task_slug}",
                details={"task": self.__class__.__name__}
            )
        except Exception as e:
            self.logger.debug(f"Failed to update status on start: {e}")
    
    def validate_required_fields(self, context: dict):
        """Validate presence and structure of CSV and parameters.

        Args:
            context (dict): Unused; provided for BaseTask compatibility.

        Raises:
            TaskError: If reference_file is missing or not a file; if
                update_field is missing or not in CSV; or if any clause
                column is absent in the CSV header.
        """
        if not self.reference_file:
            raise TaskError("Missing required parameter: reference_file")
        ref_path = Path(self.reference_file)
        if not ref_path.exists() or not ref_path.is_file():
            raise TaskError(f"Reference CSV does not exist: {ref_path}")
    
        if not self.update_field:
            raise TaskError("Missing required parameter: update_field")
    
        # Verify CSV has required columns
        try:
            # Load only headers efficiently
            df_head = pd.read_csv(self.reference_file, nrows=0, dtype=str, keep_default_na=False)
            header = list(df_head.columns)
        except Exception as e:
            raise TaskError(f"Failed to read CSV header: {e}")
    
        if self.update_field not in header:
            raise TaskError(f"CSV missing required update_field column: '{self.update_field}'")
        # All clause columns must exist
        for cl in self.clauses:
            if cl.column not in header:
                raise TaskError(f"CSV missing required selection column: '{cl.column}'")
    
    # Removed keyword-based behavior
    
    def _build_selection_mask(self, df: pd.DataFrame, context: dict) -> "pd.Series[bool]":
        """Build a boolean mask combining all clauses with logical AND.

        Each clause compares a CSV column against a value resolved from the
        context, using numeric or string comparison rules per clause settings.

        Args:
            df (pd.DataFrame): The loaded CSV as a DataFrame.
            context (dict): Pipeline context used to resolve values.

        Returns:
            pd.Series: Boolean mask aligned to df.index marking matching rows.
        """
        if len(df) == 0:
            return pd.Series([], dtype=bool)
    
        combined = pd.Series([True] * len(df), index=df.index)
        unique_id = str(context.get("id", "unknown"))
        for cl in self.clauses:
            ctx_val, exists = resolve_field(context, cl.from_context)
            if not exists:
                self.logger.warning(f"Missing context value for clause '{cl.from_context}' in UpdateReferenceTask for {unique_id}; no rows will match this clause.")
            if cl.number is True:
                # Forced numeric
                ctx_num = _coerce_to_float(ctx_val)
                if ctx_num is None:
                    clause_mask = pd.Series([False] * len(df), index=df.index)
                else:
                    col_str = df[cl.column].astype(str).fillna("")
                    col_num = col_str.str.replace(",", "", regex=False).str.replace(" ", "", regex=False)
                    col_num = pd.to_numeric(col_num, errors="coerce")
                    clause_mask = ((col_num - ctx_num).abs() < 1e-9).fillna(False)
            elif cl.number is False:
                # Forced string (case-insensitive exact)
                left = df[cl.column].astype(str).fillna("").str.lower()
                right = _normalize_string(ctx_val)
                clause_mask = (left == right)
            else:
                # Auto: numeric if context numeric, else string
                ctx_num = _coerce_to_float(ctx_val)
                if ctx_num is not None:
                    col_str = df[cl.column].astype(str).fillna("")
                    col_num = col_str.str.replace(",", "", regex=False).str.replace(" ", "", regex=False)
                    col_num = pd.to_numeric(col_num, errors="coerce")
                    clause_mask = ((col_num - ctx_num).abs() < 1e-9).fillna(False)
                else:
                    left = df[cl.column].astype(str).fillna("").str.lower()
                    right = _normalize_string(ctx_val)
                    clause_mask = (left == right)

            combined &= clause_mask
    
        return combined
    
    def _atomic_write_df(self, path: Path, df: pd.DataFrame) -> None:
        """Write a DataFrame atomically to path with optional backup.

        Args:
            path (Path): Target CSV path.
            df (pd.DataFrame): DataFrame to write.
        """
        temp_path = Path(str(path) + ".tmp")
        try:
            # Optional backup
            if self.backup and path.exists():
                backup_path = Path(str(path) + ".backup")
                try:
                    with open(path, "r", encoding="utf-8", newline="") as src, open(backup_path, "w", encoding="utf-8", newline="") as dst:
                        dst.write(src.read())
                except Exception as e:
                    self.logger.warning(f"Failed to create CSV backup: {e}")
    
            # Write to temp then replace
            df.to_csv(temp_path, index=False, encoding="utf-8")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    
    def run(self, context: dict) -> dict:
        """Execute the CSV update and return an updated context summary.

        Validates inputs, loads the CSV, creates a selection mask from the
        configured clauses, writes the update atomically, reports status, and
        records a brief summary into context['data']['update_reference'].

        Args:
            context (dict): Pipeline context containing 'id' and other values
                required by clauses (resolved via dotted paths).

        Returns:
            dict: Updated context including an 'update_reference' summary.

        Notes:
            - Side effects: CSV read/write, optional backup creation, status updates.
        """
        self.on_start(context)
        uid = str(context.get("id", "unknown"))
        try:
            self.validate_required_fields(context)
    
            # Read full CSV as strings to preserve original formatting; we handle numeric normalization ourselves
            df = pd.read_csv(self.reference_file, dtype=str, keep_default_na=False)
    
            # Ensure update_field exists; if not, add it as empty string column for robustness
            if self.update_field not in df.columns:
                df[self.update_field] = ""
    
            mask = self._build_selection_mask(df, context)
    
            update_value = self.write_value
            before_values = df.loc[mask, self.update_field].copy()
            df.loc[mask, self.update_field] = update_value
            updated_count = int((before_values != df.loc[mask, self.update_field]).sum())
            selected_rows = int(mask.sum())
    
            self._atomic_write_df(Path(self.reference_file), df)
    
            # Standardized success per guidelines
            try:
                self.status_manager.update_status(
                    unique_id=uid,
                    status=f"Task Completed: {self.task_slug}",
                    step=f"Task Completed: {self.task_slug}",
                    details={
                        "task": self.__class__.__name__,
                        "updated_rows": updated_count,
                        "selected_rows": selected_rows,
                        "update_field": self.update_field,
                        "update_value": update_value,
                    }
                )
            except Exception as e:
                self.logger.debug(f"Failed to update status on success: {e}")
    
            context.setdefault("data", {})
            context["data"]["update_reference"] = {
                "updated_rows": updated_count,
                "selected_rows": selected_rows,
                "update_field": self.update_field,
                "update_value": update_value,
            }
            return context
    
        except TaskError as e:
            self.logger.error(f"TaskError: {e}")
            self.register_error(context, e)
            # Standardized failure per guidelines
            try:
                self.status_manager.update_status(
                    unique_id=uid,
                    status=f"Task Failed: {self.task_slug}",
                    step=f"Task Failed: {self.task_slug}",
                    error=str(e),
                    details={"task": self.__class__.__name__}
                )
            except Exception as e:
                self.logger.debug(f"Failed to update status on failure: {e}")
            return context
        except Exception as e:
            self.logger.exception("Unexpected error in UpdateReferenceTask")
            self.register_error(context, TaskError(f"Unexpected error: {e}"))
            try:
                self.status_manager.update_status(
                    unique_id=uid,
                    status=f"Task Failed: {self.task_slug}",
                    step=f"Task Failed: {self.task_slug}",
                    error=str(e),
                    details={"task": self.__class__.__name__}
                )
            except Exception as e:
                self.logger.debug(f"Failed to update status on unexpected failure: {e}")
            return context