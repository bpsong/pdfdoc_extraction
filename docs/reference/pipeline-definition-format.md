# Portable pipeline definition format

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Stored versus portable configuration

SQLite stores editable drafts and immutable executable versions. Import/export
transfers definitions; importing changes a draft and never publishes it. The
deployment YAML contains paths/security/provider aliases, not new workflows.
Use an app-generated export as the wrapper for transfer between environments.
The snippets below describe task-definition content, not a complete export bundle.

## Definition content

```yaml
tasks:
  extract_fields:
    module: standard_step.extraction.extract_pdf
    class: ExtractPdfTask
    params:
      api_key: { $secret: "llamacloud-primary" }
      fields:
        document_number: { alias: "Document number", type: str }
    on_error: stop
pipeline:
  - extract_fields
```

`pipeline` is an ordered list of task keys. Each key selects one entry in
`tasks`, containing `module`, `class`, `params` and error behaviour. The configured
key is the authoritative task identity in task runs, errors and artifact metadata.
Legacy `task_slug` is accepted only for compatibility, ignored and warned about.
`cleanup_task` is reserved for automatic internal housekeeping; do not add it
to the registry/order or treat it as a configured pipeline position.

## Dependencies and approvals

A review gate selects an exact published `schema_version_id`. Import/publish
must resolve the corresponding immutable form dependency; there is no latest
draft/file fallback during execution. Secret parameters use `$secret` aliases
resolved by deployment configuration. Built-in module/class pairs are approved;
custom implementations use `custom_step.*` and explicit deployment approval.
Importing a file does not approve a new implementation.

## Ordering and validation

A pipeline can contain at most one split, extraction and review-gate task.
Split precedes extraction, and the review gate follows extraction. Extraction
supports at most one table field. Task-specific parameter, shape and approval
rules are checked before atomic publication; a failed publish creates no version.

Validate in the Pipeline editor or select an imported stored draft:

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config path\to\config.yaml --pipeline invoices --draft --import-checks
```

The CLI currently accepts `validate-file --kind pipeline` but its validator
expects an incompatible `pipeline-bundle` wrapper. Use the editor/stored-draft
path for pipeline bundles. The structural checker and complete publish/business
validation are distinct; see [CLI reference](../../tools/config_check/README.md).

## Lifecycle and routing

Inactive templates can hold published versions. Active templates expose eligible
published versions for explicit uploads and exact watch-folder assignments.
Archived templates cannot be reactivated or republished. Archiving preserves
assigned work; independent processing-history cleanup retains physical files.
Publication never silently upgrades accepted documents or folder assignments.
Automatic classification, mixed child-pipeline routing and conditional graphs
are not implemented by this pipeline model.

See [task parameters](tasks/README.md), [form format](review-schema-format.md),
[configuration/versioning](../architecture/configuration-and-versioning.md), and
the [Admin pipeline procedure](../admin/managing-pipelines.md).
