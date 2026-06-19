"""Discovery service for workflow task classes used by admin UI."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any, cast

from modules.base_task import BaseTask
from modules.config_protocol import ConfigProvider as ConfigManager, get_all_config
from modules.services.task_registry_service import ApprovedTaskRegistry


SECRET_KEY_PARTS = ("api_key", "password", "secret", "token", "credential")


class TaskCatalogService:
    """Discover configured and available workflow task classes."""

    def __init__(self, config_manager: ConfigManager, *, project_root: Path | None = None) -> None:
        """Initialize the catalog service.

        Args:
            config_manager: Application configuration provider.
            project_root: Optional root override for tests.
        """
        self.config_manager = config_manager
        config_path = getattr(config_manager, "_config_path", None)
        candidate_root = Path(config_path).parent if config_path else Path.cwd()
        if not (candidate_root / "standard_step").exists():
            candidate_root = Path.cwd()
        self.project_root = project_root or candidate_root
        self.task_registry = ApprovedTaskRegistry(config_manager)

    def catalog(self) -> dict[str, Any]:
        """Return UI-ready task catalog entries and summary counts."""
        configured_entries = self._configured_entries()
        entries_by_id = self._discover_standard_step_entries()

        for configured in configured_entries:
            entry_id = self._entry_id(configured["module"], configured["class_name"])
            existing = entries_by_id.get(entry_id)
            if existing is None:
                entries_by_id[entry_id] = self._configured_only_entry(configured)
            else:
                self._merge_configured(existing, configured)

        entries = sorted(
            entries_by_id.values(),
            key=lambda entry: (
                not entry["is_configured"],
                entry["category"],
                entry["label"].lower(),
                entry["module"],
            ),
        )
        summary = {
            "total": len(entries),
            "configured": sum(1 for entry in entries if entry["is_configured"]),
            "available": sum(1 for entry in entries if entry["import_status"] == "ok"),
            "failed": sum(1 for entry in entries if entry["import_status"] != "ok"),
        }
        return {"summary": summary, "tasks": entries}

    def _discover_standard_step_entries(self) -> dict[str, dict[str, Any]]:
        """Discover importable BaseTask subclasses under standard_step."""
        entries: dict[str, dict[str, Any]] = {}
        standard_step_dir = self.project_root / "standard_step"
        if not standard_step_dir.exists():
            return entries

        for path in sorted(standard_step_dir.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            module_name = self._module_name(path)
            class_names = [
                class_name
                for class_name in self._class_names(path)
                if self.task_registry.is_approved(module_name, class_name)
            ]
            if not class_names:
                continue

            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                for class_name in class_names:
                    entries[self._entry_id(module_name, class_name)] = self._failed_entry(
                        module_name=module_name,
                        class_name=class_name,
                        import_error=str(exc),
                    )
                continue

            for class_name in class_names:
                task_class = getattr(module, class_name, None)
                if not inspect.isclass(task_class):
                    continue
                try:
                    is_task_class = issubclass(task_class, BaseTask) and task_class is not BaseTask
                except TypeError:
                    is_task_class = False
                if not is_task_class:
                    continue
                entry = self._class_entry(
                    module_name, cast(type[BaseTask], task_class)
                )
                entries[entry["id"]] = entry
        return entries

    def _configured_entries(self) -> list[dict[str, Any]]:
        """Return normalized configured task definitions."""
        config = get_all_config(self.config_manager)
        tasks = config.get("tasks") if isinstance(config, dict) else {}
        pipeline = config.get("pipeline") if isinstance(config, dict) else []
        if not isinstance(tasks, dict):
            return []
        pipeline_positions = {
            str(task_key): index
            for index, task_key in enumerate(pipeline if isinstance(pipeline, list) else [])
        }

        configured: list[dict[str, Any]] = []
        for task_key, task_config in tasks.items():
            if not isinstance(task_config, dict):
                continue
            module_name = str(task_config.get("module") or "")
            class_name = str(task_config.get("class") or "")
            if not module_name or not class_name:
                continue
            params = task_config.get("params", {})
            configured.append(
                {
                    "task_key": str(task_key),
                    "module": module_name,
                    "class_name": class_name,
                    "params": self._redact(params if isinstance(params, dict) else {}),
                    "on_error": task_config.get("on_error"),
                    "pipeline_index": pipeline_positions.get(str(task_key)),
                }
            )
        return configured

    def _class_entry(self, module_name: str, task_class: type[BaseTask]) -> dict[str, Any]:
        """Build one catalog entry from an imported task class."""
        class_name = task_class.__name__
        return {
            "id": self._entry_id(module_name, class_name),
            "label": self._label_for(class_name),
            "category": self._category_for(module_name),
            "module": module_name,
            "class_name": class_name,
            "docstring_summary": self._summary(task_class.__doc__),
            "import_status": "ok",
            "import_error": None,
            "is_configured": False,
            "configured_keys": [],
            "pipeline_positions": [],
            "configured_params": {},
            "on_error": None,
            "parameters": self._signature_parameters(task_class),
            "expected_inputs": self._expected_inputs_for(task_class),
            "expected_outputs": self._expected_outputs_for(task_class),
        }

    def _configured_only_entry(self, configured: dict[str, Any]) -> dict[str, Any]:
        """Build an entry for a configured task outside standard_step discovery."""
        module_name = configured["module"]
        class_name = configured["class_name"]
        if not self.task_registry.is_approved(module_name, class_name):
            entry = self._failed_entry(
                module_name=module_name,
                class_name=class_name,
                import_error=(
                    "Task class is not approved for import. Add a deployment-controlled "
                    "custom_steps.registry entry using the custom_step. module prefix."
                ),
            )
            self._merge_configured(entry, configured)
            return entry

        try:
            module = importlib.import_module(module_name)
            task_class = getattr(module, class_name)
            import_status = "ok"
            import_error = None
            parameters = self._signature_parameters(task_class) if inspect.isclass(task_class) else []
            docstring_summary = self._summary(task_class.__doc__) if inspect.isclass(task_class) else ""
        except Exception as exc:
            import_status = "failed"
            import_error = str(exc)
            parameters = []
            docstring_summary = ""

        entry = {
            "id": self._entry_id(module_name, class_name),
            "label": self._label_for(class_name),
            "category": self._category_for(module_name),
            "module": module_name,
            "class_name": class_name,
            "docstring_summary": docstring_summary,
            "import_status": import_status,
            "import_error": import_error,
            "is_configured": False,
            "configured_keys": [],
            "pipeline_positions": [],
            "configured_params": {},
            "on_error": None,
            "parameters": parameters,
            "expected_inputs": [],
            "expected_outputs": [],
        }
        self._merge_configured(entry, configured)
        return entry

    def _failed_entry(self, *, module_name: str, class_name: str, import_error: str) -> dict[str, Any]:
        """Build an entry for a class in a module that failed import."""
        return {
            "id": self._entry_id(module_name, class_name),
            "label": self._label_for(class_name),
            "category": self._category_for(module_name),
            "module": module_name,
            "class_name": class_name,
            "docstring_summary": "",
            "import_status": "failed",
            "import_error": import_error,
            "is_configured": False,
            "configured_keys": [],
            "pipeline_positions": [],
            "configured_params": {},
            "on_error": None,
            "parameters": [],
            "expected_inputs": [],
            "expected_outputs": [],
        }

    @staticmethod
    def _merge_configured(entry: dict[str, Any], configured: dict[str, Any]) -> None:
        """Annotate a catalog entry with configured task details."""
        entry["is_configured"] = True
        entry.setdefault("configured_keys", []).append(configured["task_key"])
        if configured.get("pipeline_index") is not None:
            entry.setdefault("pipeline_positions", []).append(configured["pipeline_index"])
        entry.setdefault("configured_params", {})[configured["task_key"]] = configured["params"]
        entry["on_error"] = configured.get("on_error")

    def _module_name(self, path: Path) -> str:
        """Convert a project file path into a Python module name."""
        relative = path.relative_to(self.project_root).with_suffix("")
        return ".".join(relative.parts)

    @staticmethod
    def _class_names(path: Path) -> list[str]:
        """Return class names declared in a Python source file."""
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            return []
        return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]

    @staticmethod
    def _signature_parameters(task_class: type[Any]) -> list[dict[str, Any]]:
        """Return constructor parameters excluding framework-provided arguments."""
        try:
            signature = inspect.signature(task_class.__init__)
        except (TypeError, ValueError):
            return []
        parameters: list[dict[str, Any]] = []
        for name, parameter in signature.parameters.items():
            if name in {"self", "config_manager"}:
                continue
            default = None if parameter.default is inspect.Parameter.empty else parameter.default
            parameters.append(
                {
                    "name": name,
                    "kind": str(parameter.kind).replace("_", " ").lower(),
                    "required": parameter.default is inspect.Parameter.empty
                    and parameter.kind
                    not in {inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL},
                    "default": default if _is_json_safe(default) else str(default),
                }
            )
        return parameters

    @staticmethod
    def _redact(value: Any) -> Any:
        """Redact secret-like keys while preserving non-secret shape."""
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if any(part in key_text for part in SECRET_KEY_PARTS):
                    redacted[str(key)] = "***REDACTED***"
                else:
                    redacted[str(key)] = TaskCatalogService._redact(item)
            return redacted
        if isinstance(value, list):
            return [TaskCatalogService._redact(item) for item in value]
        return value

    @staticmethod
    def _entry_id(module_name: str, class_name: str) -> str:
        return f"{module_name}.{class_name}"

    @staticmethod
    def _category_for(module_name: str) -> str:
        parts = module_name.split(".")
        if len(parts) >= 2 and parts[0] == "standard_step":
            return parts[1]
        return "configured"

    @staticmethod
    def _label_for(class_name: str) -> str:
        label = class_name
        for suffix in ("Task", "V2"):
            if label.endswith(suffix):
                label = label[: -len(suffix)]
        words: list[str] = []
        current = ""
        for char in label:
            if current and char.isupper() and not current[-1].isupper():
                words.append(current)
                current = char
            else:
                current += char
        if current:
            words.append(current)
        return " ".join(words) or class_name

    @staticmethod
    def _summary(docstring: str | None) -> str:
        if not docstring:
            return ""
        return docstring.strip().splitlines()[0].strip()

    @staticmethod
    def _expected_inputs_for(task_class: type[Any]) -> list[str]:
        name = task_class.__name__.lower()
        if "extract" in name or "split" in name or "archive" in name or "cleanup" in name:
            return ["file_path", "document_id", "batch_id"]
        if "store" in name or "reference" in name or "review" in name:
            return ["data", "document_id", "batch_id"]
        return ["context"]

    @staticmethod
    def _expected_outputs_for(task_class: type[Any]) -> list[str]:
        name = task_class.__name__.lower()
        if "extract" in name:
            return ["data", "extraction_result_id", "extracted_fields"]
        if "split" in name:
            return ["split_children", "pipeline_state"]
        if "review" in name:
            return ["review_required", "review_item_id", "pipeline_state"]
        if "store" in name:
            return ["output_path"]
        if "nanoid" in name:
            return ["data.nanoid"]
        if "reference" in name:
            return ["data.update_reference"]
        return ["context"]


def _is_json_safe(value: Any) -> bool:
    """Return whether a value is safe to return directly in JSON responses."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_safe(item) for key, item in value.items())
    return False
