# Storage and archive task reference

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## storage.store_metadata_as_csv

- **Current module/class:** `standard_step.storage.store_metadata_as_csv` / `StoreMetadataAsCsv`
- **Purpose:** Stores extracted metadata as CSV and expands a configured table field into one row per item.
- **params:**
  - `data_dir`: string (required). Destination folder for CSV.
  - `filename`: string (required). Base filename template; `.csv` is auto-added.
  - Advanced compatibility parameters may use nested `storage.data_dir` /
    `storage.filename`. Add a task-specific `extraction.fields` mapping when
    CSV aliases or explicit table metadata are required; the extraction task's
    mapping is not inherited by a published versioned storage task.
- **Behavior:**
  - Uses task-specific configured field aliases for column names when present;
    otherwise it uses workflow data keys.
  - In a published versioned pipeline, columns come from that version's
    extracted data (or an explicit task-specific `extraction.fields` mapping);
    deployment-level YAML field mappings are not inherited.
  - If one extraction field has `is_table: true`, writes one row per item and repeats the document-level values.
  - Prefixes item columns with `item_` and falls back to one row when no table data is present.
  - Sanitizes values and generates a unique filename to avoid overwrites.

**YAML configuration example:**

```yaml
tasks:
  store_metadata_csv:
    module: standard_step.storage.store_metadata_as_csv
    class: StoreMetadataAsCsv
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

pipeline:
  - store_metadata_csv
```

## storage.store_metadata_as_json

- **Current module/class:** `standard_step.storage.store_metadata_as_json` / `StoreMetadataAsJson`
- **Purpose:** Stores extracted metadata as JSON while preserving arrays of objects such as invoice line items.
- **params:**
  - `data_dir`: string (required). Destination folder for JSON.
  - `filename`: string (required). Base filename template; `.json` is auto-added.
  - Optional task-specific `extraction.fields`: mapping used only when this JSON
    task should emit aliases or retain explicit table metadata. It is not
    inherited from another pipeline or deployment YAML.
- **Behavior:**
  - Reads `context["data"]` (dict).
  - Writes a JSON file with keys transformed to aliases when a task-specific
    `extraction.fields` mapping is configured.
  - In a published versioned pipeline, deployment-level YAML extraction fields
    are not inherited. Without a task-specific mapping, it writes the exact
    workflow data keys produced by that pipeline version, preventing unrelated
    columns or aliases from another workflow from leaking into the export.
  - Generates a unique filename to avoid overwrites.

**YAML configuration example:**

```yaml
tasks:
  store_metadata_json:
    module: standard_step.storage.store_metadata_as_json
    class: StoreMetadataAsJson
    params:
      data_dir: "data"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

pipeline:
  - store_metadata_json
```

These canonical CSV and JSON classes support both scalar fields and one configured array-of-objects table field.

## storage.store_file_to_localdrive

- **type:** `"storage.store_file_to_localdrive"`
- **Purpose:** Stores processed PDF files with descriptive filenames based on extracted data.
- **params:**
  - `files_dir`: string (required). Destination for processed PDFs.
  - `filename`: string (required). Template for filename; `.pdf` is auto-added.
    - Placeholders: extracted field keys (e.g., `{company}`, `{name}`) and context variables `{id}`, `{original_filename}`, `{timestamp}`.
- **Behavior:**
  - Copies the original PDF from processing into `files_dir` with a unique filename derived from `filename`.
  - Missing keys in the template raise a configuration error.

**YAML configuration example:**

```yaml
tasks:
  store_file_to_localdrive:
    module: standard_step.storage.store_file_to_localdrive
    class: StoreFileToLocaldrive
    params:
      files_dir: "files"
      filename: "{supplier_name}_{invoice_amount}_{policy_number}"
    on_error: continue

pipeline:
  - store_file_to_localdrive
```

## archiver.archive_pdf

- **type:** `"archiver.archive_pdf"`
- **Purpose:** Archives the original input PDF to a designated archive directory with a sanitized, unique filename.
- **params:**
  - `archive_dir`: string (required). Destination folder for archived PDFs.
- **Behavior:**
  - Copies the current `context["file_path"]` to the archive directory. After
    split fan-out this is a child PDF, not the original parent bundle. Place
    the archive task before splitting when a full incoming-bundle copy is needed.
  - Creates a unique filename to avoid overwrites using the original filename as a base.
  - Preserves file metadata during the copy operation.

The archive directory must already exist and be accessible to the application.
For screen instructions, see [Admin output and archiving](../../admin/task-guide.md#configure-output-files).

**YAML configuration example:**

```yaml
tasks:
  archive_pdf:
    module: standard_step.archiver.archive_pdf
    class: ArchivePdfTask
    params:
      archive_dir: "archive_folder"
    on_error: continue

pipeline:
  - archive_pdf
```


## History cleanup is a separate operation

The Archive PDF task creates a durable file. Pipeline archiving changes
configuration availability. Processing-history cleanup deletes eligible state
while retaining physical files; working-file housekeeping removes temporary
files according to task ownership. These operations have separate contracts.
See [persistence/artifacts](../../architecture/persistence-and-artifacts.md) and
[Admin retention](../../admin/archiving-and-retention.md).
