"""Schema loading, normalization, and payload validation services."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from modules.config_manager import ConfigManager


SUPPORTED_FIELD_TYPES = {
    "string",
    "number",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "enum",
    "array",
    "object",
}

SCHEMA_SUFFIXES = {".yaml", ".yml", ".json"}


class SchemaService:
    """Load QA schema files and expose canonical validation helpers."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager

    def schema_directories(self) -> list[Path]:
        """Return configured schema directories, resolved relative to config."""
        configured = (
            self.config_manager.get("schema.directories")
            or self.config_manager.get("schema.dirs")
            or self.config_manager.get("schema.directory")
            or self.config_manager.get("schemas.directory")
            or "schemas"
        )
        raw_dirs = configured if isinstance(configured, list) else [configured]
        config_path = getattr(self.config_manager, "_config_path", None)
        base_dir = Path(config_path).parent if config_path else Path.cwd()
        directories: list[Path] = []
        for raw_dir in raw_dirs:
            path = Path(str(raw_dir))
            directories.append(path if path.is_absolute() else base_dir / path)
        return directories

    def list_schemas(self) -> list[dict[str, Any]]:
        """List available YAML and JSON schemas."""
        schemas: list[dict[str, Any]] = []
        for directory in self.schema_directories():
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*")):
                if path.suffix.lower() not in SCHEMA_SUFFIXES:
                    continue
                schema = self.load_schema(path.name)
                schemas.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "hash": self.schema_hash(path.name),
                        "title": schema.get("title", path.stem) if schema else path.stem,
                    }
                )
        return schemas

    def save_schema(
        self,
        schema_name: str,
        schema: dict[str, Any],
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Validate and save a schema file, returning normalized schema data."""
        findings = self.validate_schema(schema)
        if findings:
            raise ValueError(f"Schema validation failed: {findings}")

        path = self._writable_schema_path(schema_name)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Schema already exists: {path.name}")

        path.parent.mkdir(parents=True, exist_ok=True)
        content = self._serialize_schema(path, schema)
        path.write_text(content, encoding="utf-8")
        normalized = self.normalize_schema(path.name)
        return normalized or {}

    def duplicate_schema(self, schema_name: str, new_schema_name: str) -> dict[str, Any]:
        """Create a copy of one schema under a new name."""
        source_path = self._resolve_schema_path(schema_name)
        if source_path is None or not source_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_name}")
        schema = self.load_schema(schema_name)
        if schema is None:
            raise ValueError("Schema file could not be loaded.")
        return self.save_schema(new_schema_name, schema, overwrite=False)

    def load_schema(self, schema_name: str) -> dict[str, Any] | None:
        """Load a YAML or JSON schema by configured-relative name."""
        path = self._resolve_schema_path(schema_name)
        if path is None or not path.exists():
            return None
        with path.open("r", encoding="utf-8") as schema_file:
            if path.suffix.lower() == ".json":
                schema = json.load(schema_file)
            else:
                schema = yaml.safe_load(schema_file)
        if not isinstance(schema, dict):
            return None
        schema.setdefault("title", path.stem)
        schema.setdefault("description", "")
        schema.setdefault("fields", {})
        return schema

    def schema_content(self, schema_name: str) -> str | None:
        """Return the raw schema file text for editor previews."""
        path = self._resolve_schema_path(schema_name)
        if path is None or not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def normalize_schema(self, schema_name: str) -> dict[str, Any] | None:
        """Return schema metadata and canonical UI field definitions."""
        schema = self.load_schema(schema_name)
        if schema is None:
            return None
        return {
            "name": schema_name,
            "title": schema.get("title", schema_name),
            "description": schema.get("description", ""),
            "version": schema.get("version") or schema.get("schema_version") or self.schema_hash(schema_name),
            "hash": self.schema_hash(schema_name),
            "fields": self._normalize_fields(schema.get("fields", {})),
        }

    def validate_schema(self, schema: dict[str, Any]) -> list[dict[str, str]]:
        """Validate schema structure and return actionable findings."""
        findings: list[dict[str, str]] = []
        fields = schema.get("fields")
        if not isinstance(fields, dict):
            return [{"path": "fields", "message": "Schema fields must be a mapping."}]
        for field_key, field_config in fields.items():
            findings.extend(self._validate_field_config(str(field_key), field_config))
        return findings

    def validate_payload(
        self,
        payload: dict[str, Any],
        *,
        schema_name: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Validate corrected data against a schema."""
        active_schema = schema or (self.load_schema(schema_name) if schema_name else None)
        if active_schema is None:
            return [{"path": schema_name or "schema", "message": "Schema file could not be loaded."}]
        fields = active_schema.get("fields", {})
        if not isinstance(fields, dict):
            return [{"path": "fields", "message": "Schema fields must be a mapping."}]
        findings: list[dict[str, str]] = []
        for field_key, field_config in fields.items():
            value = payload.get(field_key)
            findings.extend(self._validate_value(str(field_key), value, field_config))
        return findings

    def schema_hash(self, schema_name: str) -> str | None:
        """Return a SHA-256 hash of a schema file for review traceability."""
        path = self._resolve_schema_path(schema_name)
        if path is None or not path.exists():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _resolve_schema_path(self, schema_name: str) -> Path | None:
        candidate = Path(schema_name)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        config_path = getattr(self.config_manager, "_config_path", None)
        base_dir = Path(config_path).parent if config_path else Path.cwd()
        config_relative = base_dir / candidate
        if config_relative.exists():
            return config_relative
        for directory in self.schema_directories():
            path = directory / schema_name
            if path.exists():
                return path
        return self.schema_directories()[0] / schema_name

    def _writable_schema_path(self, schema_name: str) -> Path:
        name = self._safe_schema_name(schema_name)
        return self.schema_directories()[0] / name

    @staticmethod
    def _safe_schema_name(schema_name: str) -> str:
        candidate = Path(schema_name)
        if candidate.name != schema_name or candidate.is_absolute() or not candidate.name:
            raise ValueError("Schema name must be a file name, not a path.")
        suffix = candidate.suffix.lower()
        if suffix not in SCHEMA_SUFFIXES:
            raise ValueError("Schema name must end with .yaml, .yml, or .json.")
        return candidate.name

    @staticmethod
    def _serialize_schema(path: Path, schema: dict[str, Any]) -> str:
        if path.suffix.lower() == ".json":
            return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        return yaml.safe_dump(schema, sort_keys=False, allow_unicode=True)

    def _normalize_fields(self, fields: dict[str, Any], parent_path: str = "") -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for key, config in fields.items():
            if not isinstance(config, dict):
                config = {"type": "string", "label": str(key), "unsupported_config": config}
            field_type = str(config.get("type", "string"))
            path = f"{parent_path}.{key}" if parent_path else str(key)
            field = {
                "key": str(key),
                "path": path,
                "label": config.get("label") or config.get("title") or str(key).replace("_", " ").title(),
                "type": field_type,
                "required": bool(config.get("required", False)),
                "description": config.get("description") or config.get("help"),
                "default": config.get("default"),
                "options": config.get("choices") or config.get("enum"),
                "editor": self._editor_for(config),
                "children": [],
                "item_schema": None,
                "metadata": {
                    key: value
                    for key, value in config.items()
                    if key
                    not in {
                        "type",
                        "label",
                        "title",
                        "required",
                        "description",
                        "help",
                        "default",
                        "choices",
                        "enum",
                        "properties",
                        "items",
                    }
                },
            }
            if field_type == "object":
                field["children"] = self._normalize_fields(config.get("properties", {}), path)
            elif field_type == "array":
                item_config = config.get("items", {"type": "string"})
                if isinstance(item_config, dict) and item_config.get("type") == "object":
                    field["item_schema"] = {
                        "type": "object",
                        "fields": self._normalize_fields(item_config.get("properties", {}), f"{path}[]"),
                    }
                    field["editor"] = "object_array"
                else:
                    field["item_schema"] = self._normalize_array_item(item_config)
                    field["editor"] = "scalar_array"
            normalized.append(field)
        return normalized

    @staticmethod
    def _normalize_array_item(item_config: Any) -> dict[str, Any]:
        if not isinstance(item_config, dict):
            return {"type": "string"}
        return {
            "type": item_config.get("type", "string"),
            "label": item_config.get("label"),
            "options": item_config.get("choices") or item_config.get("enum"),
        }

    @staticmethod
    def _editor_for(field_config: dict[str, Any]) -> str:
        field_type = field_config.get("type", "string")
        if field_type == "enum" or field_config.get("choices") or field_config.get("enum"):
            return "select"
        if field_type in {"number", "integer", "float"}:
            return "number"
        if field_type == "boolean":
            return "checkbox"
        if field_type in {"date", "datetime"}:
            return field_type
        if field_type == "object":
            return "object"
        if field_type == "array":
            return "array"
        if field_config.get("multiline"):
            return "textarea"
        return "text"

    def _validate_field_config(self, path: str, field_config: Any) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        if not isinstance(field_config, dict):
            return [{"path": path, "message": "Field configuration must be a mapping."}]
        field_type = field_config.get("type")
        if field_type not in SUPPORTED_FIELD_TYPES:
            findings.append({"path": f"{path}.type", "message": f"Unsupported field type: {field_type}."})
        if field_type == "enum" and not field_config.get("choices") and not field_config.get("enum"):
            findings.append({"path": f"{path}.choices", "message": "Enum fields require choices."})
        if field_type == "object":
            properties = field_config.get("properties")
            if not isinstance(properties, dict):
                findings.append({"path": f"{path}.properties", "message": "Object fields require properties."})
            else:
                for child_key, child_config in properties.items():
                    findings.extend(self._validate_field_config(f"{path}.{child_key}", child_config))
        if field_type == "array" and "items" not in field_config:
            findings.append({"path": f"{path}.items", "message": "Array fields require an items definition."})
        return findings

    def _validate_value(self, path: str, value: Any, field_config: Any) -> list[dict[str, str]]:
        if not isinstance(field_config, dict):
            return []
        findings: list[dict[str, str]] = []
        required = bool(field_config.get("required", False))
        if value is None or value == "":
            if required:
                findings.append({"path": path, "message": "Required field is missing."})
            return findings

        field_type = field_config.get("type", "string")
        if field_type == "string":
            if not isinstance(value, str):
                findings.append({"path": path, "message": "Value must be a string."})
            else:
                if field_config.get("min_length") is not None and len(value) < int(field_config["min_length"]):
                    findings.append({"path": path, "message": f"Value must be at least {field_config['min_length']} characters."})
                if field_config.get("max_length") is not None and len(value) > int(field_config["max_length"]):
                    findings.append({"path": path, "message": f"Value must be at most {field_config['max_length']} characters."})
                pattern = field_config.get("pattern")
                if pattern and not re.match(str(pattern), value):
                    findings.append({"path": path, "message": "Value does not match required pattern."})
        elif field_type in {"number", "integer", "float"}:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                findings.append({"path": path, "message": "Value must be numeric."})
            elif field_type == "integer" and not isinstance(value, int):
                findings.append({"path": path, "message": "Value must be an integer."})
            else:
                if field_config.get("min_value") is not None and value < field_config["min_value"]:
                    findings.append({"path": path, "message": f"Value must be at least {field_config['min_value']}."})
                if field_config.get("max_value") is not None and value > field_config["max_value"]:
                    findings.append({"path": path, "message": f"Value must be at most {field_config['max_value']}."})
        elif field_type == "boolean" and not isinstance(value, bool):
            findings.append({"path": path, "message": "Value must be a boolean."})
        elif field_type == "enum":
            choices = field_config.get("choices") or field_config.get("enum") or []
            if value not in choices:
                findings.append({"path": path, "message": f"Value must be one of: {choices}."})
        elif field_type == "object":
            if not isinstance(value, dict):
                findings.append({"path": path, "message": "Value must be an object."})
            else:
                for child_key, child_config in field_config.get("properties", {}).items():
                    findings.extend(self._validate_value(f"{path}.{child_key}", value.get(child_key), child_config))
        elif field_type == "array":
            if not isinstance(value, list):
                findings.append({"path": path, "message": "Value must be an array."})
            else:
                item_config = field_config.get("items", {"type": "string"})
                for index, item in enumerate(value):
                    findings.extend(self._validate_value(f"{path}[{index}]", item, item_config))
        return findings
