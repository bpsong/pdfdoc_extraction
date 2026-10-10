# Develop and change pipeline tasks

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

Read the [canonical standard task creation guidelines](../../tasks/standard_task_creation_guidelines.md)
before adding or substantially changing a task. This page is an entry checklist;
the canonical guidelines remain authoritative.

## Task and context contract

Tasks share a mutable context dictionary and preserve identity,
position, outputs, and failure/review signals. State needed after a process
restart or for operator/audit use must also be persisted in SQLite.

Standard tasks inherit from `BaseTask` and implement `on_start`, `run`, and
`validate_required_fields`. Expected failures use `TaskError` and
`register_error`. New tasks must not write workflow status through
filesystem status files. Tasks use their injected parameters and must not
reload their own parameters from a fixed `tasks.<name>` configuration path,
because one implementation may be configured under different pipeline keys.

The mutable context is the internal task protocol:

| Category | Representative keys |
| --- | --- |
| Identity | `id`, `batch_id`, `document_id` |
| Input | `file_path`, `original_filename`, `source` |
| Position | `current_task_index`, `current_task_key`, `task_run_id` |
| Output | `data`, `metadata` |
| Failure | `error`, `error_step`, `fatal_failure`, `continued_failures` |
| Review | `review_required`, `review_item_id`, `pipeline_state` |
| Split | `parent_document_id`, `split_children`, `fan_out_start_task_index` |

The context is extensible but weakly typed. State required for resume,
operator visibility, or audit must also be persisted in SQLite. Detailed task
rules are in the
[standard task creation guidelines](../../tasks/standard_task_creation_guidelines.md).
`pipeline_template_id` and `pipeline_version_id` are cached execution identity
in context; tasks must preserve them, while SQLite remains authoritative.


## Change checklist

1. Inherit [BaseTask](../../modules/base_task.py), implement its hooks and keep
   construction free of external side effects.
2. Follow the shared mutable context, identity, pause and error contracts.
   Use `TaskError` and `register_error` rather than swallowing failures.
3. Use an approved built-in `standard_step.*` module/class pair. Custom tasks
   use `custom_step.*` and explicit deployment approval; approval alone does
   not add a task to a pipeline.
4. Register durable output through
   [artifact_service](../../modules/services/artifact_service.py) when a document
   ID is present. Compensate partial files/rows at the owning transaction boundary.
5. Update task catalog/editor/validation surfaces when parameters change.
6. Test task behaviour and the pinned workflow path, including failures,
   retries, human review and split continuation where affected.
7. Update the relevant [task reference](../reference/tasks/README.md).
   If a shared standard changes, update the canonical task guidelines in the
   same change.

For manual split, an accepted decision and downstream dispatch are distinct.
Preserve the bounded retry rules in [splitting](../reference/tasks/splitting.md).
