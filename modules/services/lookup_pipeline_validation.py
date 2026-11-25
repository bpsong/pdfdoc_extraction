"""Validate CSV lookup bindings and release order in explicit definitions."""

from collections.abc import Mapping
from pathlib import Path
from string import Formatter
from typing import Any, NamedTuple

from pydantic import ValidationError

from modules.services.csv_reference_lookup import (
    CSV_LOOKUP_TASK,
    LookupConfig,
    ReferenceDataError,
    ReferenceUnavailableError,
    validate_reference_header,
)


class LookupIssue(NamedTuple):
    """A validation finding without reference contents or raw parameters."""

    path: str
    message: str
    code: str


def lookup_parameters(task_key: str, task: Mapping[str, Any]) -> tuple[LookupConfig | None, list[LookupIssue]]:
    """Parse the lookup task and enforce the stopping error policy."""
    path = f"tasks.{task_key}"
    issues: list[LookupIssue] = []
    if task.get("on_error", "stop") != "stop":
        issues.append(LookupIssue(f"{path}.on_error", "CSV lookup requires on_error: stop.", "lookup-on-error"))
    try:
        config = LookupConfig.model_validate(task.get("params"))
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_context=False, include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            issues.append(LookupIssue(
                f"{path}.params" + (f".{location}" if location else ""),
                error["msg"], "lookup-invalid-parameters",
            ))
        return None, issues
    return config, issues


def active_lookup_configs(definition: Mapping[str, Any]) -> dict[str, LookupConfig]:
    """Collect well-formed configured lookups in the executable order."""
    return {
        key: settings for _, key, task in _steps(definition)
        if (task.get("module"), task.get("class")) == CSV_LOOKUP_TASK
        and (settings := lookup_parameters(key, task)[0]) is not None
    }


def lookup_fields_before(definition: Mapping[str, Any], task_key: str) -> set[str]:
    """Return lookup fields available to a particular downstream task."""
    steps = definition.get("pipeline")
    if not isinstance(steps, list) or task_key not in steps:
        return set()
    earlier = {key for key in steps[:steps.index(task_key)] if isinstance(key, str)}
    return {
        mapping.field for key, lookup in active_lookup_configs(definition).items() if key in earlier
        for mapping in lookup.returns
    }


def _steps(definition: Mapping[str, Any]) -> list[tuple[int, str, dict[str, Any]]]:
    tasks = definition.get("tasks")
    order = definition.get("pipeline")
    if not isinstance(tasks, dict) or not isinstance(order, list):
        return []
    return [
        (index, key, task) for index, key in enumerate(order)
        if isinstance(key, str) and isinstance(task := tasks.get(key), dict)
    ]


def _params(task: Mapping[str, Any]) -> dict[str, Any]:
    value = task.get("params")
    return value if isinstance(value, dict) else {}


def _release_task(task: Mapping[str, Any]) -> bool:
    module = str(task.get("module", ""))
    return ".storage." in module or ".archiver." in module or (
        ".rules." in module and (module, task.get("class")) != CSV_LOOKUP_TASK
    )


def _filename_tokens(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    try:
        return {
            field.split(".", 1)[0].split("[", 1)[0]
            for _, field, _, _ in Formatter().parse(value) if field
        }
    except ValueError:
        return set()


def lookup_order_issues(
    definition: Mapping[str, Any], lookups: Mapping[str, LookupConfig],
) -> list[LookupIssue]:
    """Check known extraction fields and consumers of the lookup outputs."""
    if not lookups:
        return []
    steps = _steps(definition)
    releases = [index for index, _, task in steps if _release_task(task)]
    gates = [index for index, _, task in steps
             if (task.get("module"), task.get("class")) == ("standard_step.review.review_gate", "ReviewGateTask")]
    source_fields: dict[str, Any] = {}
    for _, _, task in steps:
        fields = _params(task).get("fields")
        if ".extraction." in str(task.get("module", "")) and isinstance(fields, dict):
            source_fields.update(fields)
    targets: dict[str, tuple[int, LookupConfig]] = {}
    seen: set[str] = set()
    extraction_seen = False
    issues: list[LookupIssue] = []

    for index, key, task in steps:
        if ".extraction." in str(task.get("module", "")):
            extraction_seen = True
        settings = lookups.get(key)
        if settings is None:
            continue
        path = f"tasks.{key}.params"
        if key in seen:
            issues.append(LookupIssue(f"pipeline[{index}]", "A lookup task key can run only once.", "lookup-duplicate-step"))
            continue
        seen.add(key)
        if not extraction_seen:
            issues.append(LookupIssue(f"pipeline[{index}]", "CSV lookup must follow extraction.", "lookup-before-extraction"))
        needs_review = "review" in (settings.on_no_match, settings.on_multiple_matches)
        if any(release < index for release in releases):
            issues.append(LookupIssue(f"pipeline[{index}]", "CSV lookup must precede business outputs.", "lookup-after-release"))
        if needs_review and not any(
            index < gate and all(gate < release for release in releases) for gate in gates
        ):
            issues.append(LookupIssue(f"pipeline[{index}]", "Place a review gate after CSV lookup and before business outputs.", "lookup-review-gate-order"))
        for position, mapping in enumerate(settings.returns):
            if mapping.field in targets or mapping.field in source_fields:
                issues.append(LookupIssue(
                    f"{path}.returns.{position}.field", "Return field conflicts with an extraction or lookup field.", "lookup-field-collision",
                ))
            targets[mapping.field] = (index, settings)

    for key, settings in lookups.items():
        for position, clause in enumerate(settings.clauses):
            path = f"tasks.{key}.params.clauses.{position}.field"
            if clause.field in targets or (source_fields and clause.field not in source_fields):
                issues.append(LookupIssue(path, "Match inputs must name extraction fields.", "lookup-source-field"))
                continue
            spec = source_fields.get(clause.field)
            field_type = spec.get("type") if isinstance(spec, dict) else spec
            scalar_types = {"str", "string", "Any"} | ({"int", "float", "Decimal", "number", "integer"} if clause.mode == "numeric" else set())
            if (isinstance(spec, dict) and spec.get("is_table")) or (
                isinstance(field_type, str) and field_type not in scalar_types
            ):
                issues.append(LookupIssue(path, "Match input type is incompatible with its comparison mode.", "lookup-source-type"))

    for index, key, task in steps:
        if not _release_task(task):
            continue
        params = _params(task)
        storage = params.get("storage")
        filenames = [("filename", params.get("filename"))]
        if isinstance(storage, dict):
            filenames.append(("storage.filename", storage.get("filename")))
        for suffix, filename in filenames:
            for token in sorted(_filename_tokens(filename) & targets.keys()):
                producer, settings = targets[token]
                path = f"tasks.{key}.params.{suffix}"
                if producer >= index or not settings.required:
                    issues.append(LookupIssue(path, f"Filename field '{token}' requires an earlier required CSV lookup.", "lookup-filename-dependency"))
    return issues


def lookup_file_issues(
    definition: Mapping[str, Any], config_path: str | Path,
) -> list[tuple[str, LookupIssue]]:
    """Check locally accessible headers while allowing a worker-only register."""
    issues: list[tuple[str, LookupIssue]] = []
    for key, settings in active_lookup_configs(definition).items():
        path = f"tasks.{key}.params.reference_file"
        try:
            validate_reference_header(settings, config_path=config_path)
        except ReferenceUnavailableError:
            issues.append(("warning", LookupIssue(
                path, "Reference file is unavailable here. The worker will validate it before execution.",
                "lookup-reference-unavailable",
            )))
        except ReferenceDataError as exc:
            issues.append(("error", LookupIssue(path, str(exc), "lookup-reference-invalid")))
    return issues
