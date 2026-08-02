# PDF Document Processing System

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139.2-green.svg)](https://fastapi.tiangolo.com/)

A sophisticated PDF document processing system that leverages AI-powered extraction to convert unstructured PDF documents into structured data. Built with modern Python technologies and designed for enterprise document processing workflows.

## Key Features

### AI-Powered Data Extraction
- **Llama Cloud Integration**: Advanced AI service for intelligent document understanding
- **Structured Data Extraction**: Converts PDF content into structured JSON/CSV format
- **Multi-format Support**: Handles invoices, receipts, forms, and various document types
- **Typed Scalar Lists**: Normalize lists of text, integers, numbers, and yes/no values
- **Typed Object Support**: Extract fixed flat objects whose properties mix text, integer, number, and yes/no values
- **Array-of-Objects Support**: Extract line items and tabular data from complex documents

### Multiple Input Methods
- **Watch Folder Monitoring**: Automated processing of dropped PDF files
- **Web Upload Interface**: User-friendly web portal for manual uploads
- **Polled Processing Status**: Browser pages refresh workflow progress at
  short intervals
- **Batch Uploads**: `/app/upload` supports multi-file upload and creates batch/document records for tracking

### Configurable Pipeline Architecture
- **Modular Design**: Pluggable processing steps (extraction, storage, archiving, rules)
- **Prefect Workflow Orchestration**: Reliable task execution and error handling
- **Versioned Configuration**: Named SQLite pipeline templates with editable
  drafts, immutable published versions, and exact review-form dependencies
- **Explicit Routing**: Uploads select one exact published version and each
  watch-folder binding pins one exact version
- **Deployment YAML**: `config.yaml` owns paths, web/auth/logging settings,
  custom-task approvals, and secret aliases—not new workflow definitions
- **Extensible Framework**: Easy to add new processing steps
- **SQLite-backed Workflow State**: Batches, documents, task runs, extracted fields, review items, artifacts, settings, and audit history are persisted in SQLite

### Flexible Data Storage
- **CSV Export**: Structured data in spreadsheet format
- **JSON Export**: Hierarchical data preservation
- **Table-Aware Storage**: Row-per-item expansion for tabular data
- **Local File Management**: Organized storage with metadata tracking
- **Artifact Registry**: Source originals, split working files, archives, PDFs, CSVs, and JSON exports are registered as durable document files

### Modern Web Interface
- **FastAPI Backend**: High-performance REST API
- **Operator App**: `/app/upload`, `/app/processing`, `/app/review`, `/app/reports`, and `/app/settings`
- **Admin App**: `/app/admin`, `/app/admin/users`, `/app/admin/pipeline`,
  `/app/schemas`, `/app/admin/tasks`, `/app/settings/validation`, and
  `/app/admin/audit`
- **Review Workflows**: Human review queues for low-confidence or policy-triggered extracted fields
- **Responsive Design**: Mobile-friendly interface

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Prerequisites
- Python 3.13+
- Llama Cloud API access

### Installation

1. **Clone the repository**
   ```powershell
   git clone <your-repo-url>
   cd pdfdoc_extraction
   ```

2. **Install dependencies**
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. **Configure the system**
   Open the ignored local `config.yaml` and set deployment paths, web/auth
   settings, and provider secret aliases. Do not place new `tasks` or
   `pipeline` blocks there. Create folders required by `watch_folder.dir` and
   `web.upload_dir` before startup.

4. **Run the application**
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

   Database migrations run automatically on startup when `database.run_migrations_on_startup` is enabled.

5. **Access the web interface**
   Open your browser and navigate to `http://localhost:8000/app/upload`

## Installation

### System Requirements
- **Operating System**: Windows 11 is the primary supported development/runtime
  environment
- **Python Version**: 3.13+
- **Memory and Storage**: Size for the PDF volume, provider workload, retained
  artifacts, and SQLite database; no fixed production capacity is enforced by
  the application

### Dependencies Installation
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Key dependencies:
- **FastAPI**: Modern web framework for the API and web interface
- **LlamaCloud SDK (`llama-cloud`)**: AI-powered document extraction through Extract v2
- **Prefect**: Workflow orchestration engine
- **Pandas**: Data manipulation and CSV processing
- **Uvicorn**: ASGI server for production deployment

## Configuration

### Basic Configuration Structure

```yaml
# config.yaml
web:
  host: "127.0.0.1"
  port: 8000
  secret_key: "your_secret_key"
  upload_dir: "web_upload"

database:
  path: "data/app_state.sqlite3"
  run_migrations_on_startup: true

review:
  default_queue_name: "default_review"
  lock_timeout_minutes: 60

watch_folder:
  dir: "watch_folder"  # required startup-compatibility path, not pipeline routing
  validate_pdf_header: true
  processing_dir: "processing_folder_default"

pipeline_secrets:
  llamacloud-primary: "SET-ONLY-IN-THIS-LOCAL-IGNORED-FILE"
```

Create review forms and pipelines visually after startup: publish and activate a
review-form version when schema-driven review is needed, add tasks to a pipeline
draft, reference secrets as `{ "$secret": "llamacloud-primary" }`, save,
validate, publish, and activate the pipeline. `config.yaml` does not need
top-level `tasks` or `pipeline` sections after migration.

Output folders are task-owned in the exact SQLite pipeline version. CSV/JSON
tasks use `data_dir`, local PDF storage uses `files_dir`, archive tasks use
`archive_dir`, and split tasks use `split_dir`. CSV/JSON/local-PDF/split tasks
create their output directory when execution begins if permissions allow;
`ArchivePdfTask` requires its configured archive directory to exist.
Deployment `_dir` keys are the paths that `ConfigManager` creates at startup,
except `watch_folder.dir`.

The current runtime uses the `llama-cloud` SDK and `LlamaCloud` client. New code should not use the legacy `llama-cloud-services` / `LlamaExtract` agent flow. `agent_id` is legacy; use `configuration_id` for saved Extract v2 configurations or omit it to build an inline schema from `fields`.

### Manual LlamaCloud Smoke Check

After validating a saved Extract v2 configuration in the LlamaCloud UI, you can
run a one-file SDK and workflow fit check against `sample_invoice.pdf`. The
manual tool reads a YAML task definition; it does not read SQLite or resolve
`pipeline_secrets`. Export/copy the selected pipeline definition to an ignored
local smoke file and provide the API key through the current process:

```powershell
$env:LLAMA_CLOUD_API_KEY = "set-locally"
.\.venv\Scripts\python.exe tools\llamacloud_extract_smoke.py --config smoke-pipeline.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
```

If `configuration_id` is already set in the smoke definition, omit the override
flag. Do not commit the smoke definition or output because they can contain
customer/provider data.

The script writes:

- `raw_extract_result.json`: raw `result.extract_result` from LlamaCloud.
- `workflow_normalized_data.json`: data after matching returned keys to workflow
  fields and applying configured types.
- `workflow_fit_report.json`: missing workflow fields, extra raw keys,
  validation errors, and pass/fail status.

To re-check a saved raw result without another LlamaCloud call:

```powershell
.\.venv\Scripts\python.exe tools\llamacloud_extract_smoke.py --config smoke-pipeline.yaml --raw-json test\data\llamacloud_smoke\raw_extract_result.json
```

### Environment Variables

- `CONFIG_PATH`: Custom path to configuration file
- `USE_RELOAD`: Enable auto-reload for development (`true`/`false`)

### Runtime State

SQLite is the primary workflow-state store. The application records:

- ingestion batches and documents
- task-run lifecycle and errors
- extraction results and field-level confidence/review state
- review queue items and decisions
- registered document artifacts
- admin settings versions and audit events

Text status files are not required for configured workflow state. `/api/files` and `/api/status/{file_id}` remain as legacy compatibility APIs, but they read from SQLite. Use `/app/*` pages for browser workflows.

## Usage

### Web Interface

Before first login, initialize the two fixed SQLite users:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml
```

For an upgrade from YAML credentials, preserve the existing admin hash while creating the operator account:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml --legacy-config config.yaml
```

After a successful import, remove the legacy `authentication` block. Passwords must contain uppercase, lowercase, numeric, and symbol characters and be 12–72 UTF-8 bytes.

1. **Login**: Access the app at `http://localhost:8000/app/upload` and select `admin` or `operator`
2. **Upload PDFs**: Use `/app/upload`, select one exact eligible published
   pipeline version for the whole batch, and submit one or more PDFs
3. **Monitor Progress**: Use `/app/processing` or `/app/batches/{batch_id}` to track splitting, extraction, review, and completion state
4. **Review Exceptions**: Use `/app/review` and `/app/review/{review_item_id}` for human review queues
5. **Inspect Results**: Use `/app/documents/{document_id}/extraction` for extracted fields and source PDF access
6. **Inspect Batch History**: Use `/app/reports` and click a recent batch row to view document task timelines and task-run details
7. **Administer Configuration**: Admin users create/version pipelines in
   `/app/admin/pipeline`, review forms in `/app/schemas`, inspect tasks and
   validation, manage users, and view the `admin_` audit subset

### Watch Folder

1. **Create a binding**: In the bottom of `/app/admin/pipeline`, bind an
   existing, non-overlapping incoming folder to one exact published version
2. **Drop PDFs** into that bound directory; `watch_folder.dir` alone is only a
   required startup-compatibility path and does not assign a workflow
3. **Automatic Processing**: Enabled bindings are scanned and files are pinned
   to their bound version before processing
4. **Status Updates**: Monitor progress through Reports and Processing Overview

### Command Line

```powershell
# Run with default configuration
.\.venv\Scripts\python.exe main.py

# Use custom configuration
.\.venv\Scripts\python.exe main.py --config-path custom_config.yaml

# Run without web server (watch folder only)
.\.venv\Scripts\python.exe main.py --no-web
```

## API Reference

### Authentication
- `POST /login`: User authentication
- `POST /logout`: Session termination
- `GET /api/admin/users`: List fixed accounts (admin only)
- `PUT /api/admin/users/{username}/password`: Change an account password (admin only)

Repeated failed login attempts are temporarily throttled and may return HTTP `429 Too Many Requests`.
The `admin` account has full access. The `operator` account cannot access administrative pages or APIs. Admins manage both passwords at `/app/admin/users`; changing a password revokes existing sessions for that account.

### File Operations
- `POST /upload`: Legacy single-PDF upload endpoint; redirects to `/app/processing` after scheduling
- `GET /api/pipelines/available`: List exact pipeline versions eligible for the current user
- `POST /api/batches/upload`: Upload a batch of PDFs with a required
  `pipeline_version_id` and create SQLite batch/document records
- `GET /api/batches`: List ingestion batches
- `GET /api/batches/{batch_id}`: Get batch details
- `GET /api/batches/{batch_id}/documents`: List batch documents
- `GET /api/batches/{batch_id}/split-results`: Show split source/child document relationships
- `GET /api/documents/{document_id}/task-runs`: List task runs for a document
- `GET /api/documents/{document_id}/extraction`: Read extraction result and normalized fields
- `GET /api/documents/{document_id}/fields`: Read extracted/reviewed fields
- `GET /api/documents/{document_id}/file/pdf`: Stream the source PDF or registered PDF artifact
- `POST /api/documents/{document_id}/resume`: Resume a document after review
- `GET /api/files`: Legacy compatibility list backed by SQLite documents
- `GET /api/status/{file_id}`: Legacy compatibility detail backed by SQLite documents, task runs, and artifacts

### Review, Reports, and Admin
- `GET /api/review/items`: List review queue items
- `POST /api/review/items/{review_item_id}/claim`: Claim a review item
- `POST /api/review/items/{review_item_id}/complete`: Complete review and persist corrected values
- `GET /api/reports/summary`: Processing and review activity summary
- `GET /api/settings`: Non-secret runtime settings for operators
- `GET /api/admin/settings`, `PUT /api/admin/settings`: Admin configuration state
- `GET /api/admin/audit`: Admin audit events
- `/api/admin/pipeline-templates`: Create/list named templates; per-template
  endpoints manage metadata, clone, draft save/validate/import/export/diff,
  immutable publish, and version history
- `/api/admin/review-schemas`: Create/list review forms; per-template endpoints
  manage metadata, draft save/validate/import/export, immutable publish,
  versions, and dependency usage
- `/api/admin/watch-folder-bindings`: List/create bindings; per-binding
  `PATCH` and `DELETE` update or remove eligible unreferenced bindings
- `GET /api/admin/pipeline`, `PUT /api/admin/pipeline/draft`,
  `POST /api/admin/pipeline/publish`, review-gate-rules, split-settings, and
  filesystem `/api/schemas` endpoints are legacy compatibility/configuration
  surfaces. New workflow authoring uses the versioned template endpoints.

## Project Structure

```
pdfdoc_extraction/
├── 📄 main.py                    # Application entry point
├── 📄 config.yaml               # Main configuration file
├── 📄 requirements.txt          # Python dependencies
├── 📁 modules/                  # Core application modules
│   ├── api_router.py           # API endpoint management
│   ├── config_manager.py       # Configuration management
│   ├── file_processor.py       # File processing logic
│   ├── db/                     # SQLite connection, migrations, repositories
│   ├── services/               # Batch, review, reports, audit, settings, artifact services
│   ├── status_manager.py       # Legacy text-status compatibility support
│   ├── services/watch_folder_coordinator.py # Multi-binding watch-folder routing
│   ├── watch_folder_monitor.py # Legacy single-folder compatibility component
│   └── workflow_manager.py     # Workflow orchestration
├── 📁 standard_step/           # Processing pipeline steps
│   ├── extraction/             # Data extraction tasks
│   │   └── extract_pdf.py      # Scalar, typed-object, and array-of-objects extraction
│   ├── storage/                # Data storage tasks
│   │   ├── store_metadata_as_csv.py
│   │   └── store_metadata_as_json.py
│   ├── rules/                  # Business rule tasks
│   ├── archiver/               # File archiving tasks
│   ├── context/                # Context management tasks
│   └── housekeeping/           # Cleanup and maintenance tasks
├── 📁 web/                     # Web interface
│   ├── server.py               # FastAPI application
│   ├── templates/              # HTML templates
│   └── static/                 # CSS, JavaScript, assets
├── 📁 test/                    # Test suites
│   ├── core/                   # Core component tests
│   ├── integration/            # Integration tests
│   ├── storage/                # Storage task tests
│   └── workflow/               # Workflow tests
├── 📁 docs/                    # Documentation
│   ├── design_architecture.md  # System architecture
│   ├── user_guide.md           # User manual
│   └── review_schema_admin_guide.md
└── 📁 tasks/                   # Engineering guidance and future designs
    ├── standard_task_creation_guidelines.md
    ├── future-lightweight-pipeline-visualization.md
    ├── future-multi-document-routing.md
    └── archive/                # Historical PRDs, completed task lists, and audits
```

## Development

### Setting Up Development Environment

1. **Clone and install**
   ```powershell
   git clone <repository-url>
   cd pdfdoc_extraction
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. **Run tests**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v
   ```

3. **Development mode**
   ```powershell
   $env:USE_RELOAD="true"
   .\.venv\Scripts\python.exe main.py
   ```

### Code Structure Guidelines

- **PEP 8 Compliance**: Follow Python style guidelines
- **Type Hints**: Use comprehensive type annotations
- **Documentation**: Concise Google-style docstrings for public and non-obvious
  modules, classes, and functions
- **Error Handling**: Structured error handling with custom exceptions
- **Testing**: Unit tests for all new features

## Testing

### Running Tests

```powershell
# Run all tests
.\.venv\Scripts\python.exe -m pytest -v

# Run specific test file
.\.venv\Scripts\python.exe -m pytest -v test/core/test_config_manager.py

# Run static type checking when Pyright is installed (it is not pinned in requirements.txt)
pyright
```

Example focused validation for SQLite-backed ingestion and operator state:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\integration\test_sqlite_only_workflow_state.py test\integration\test_batch_upload_api.py test\integration\test_reports_api.py test\integration\test_settings_api.py
```

Run the full suite before handing off broad or cross-cutting changes.

The end-to-end workflow fixture config also passes config-check:

```powershell
.\.venv\Scripts\python.exe -m tools.config_check validate --config test\data\config.yaml --import-checks
```

### Test Categories

- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end workflow validation
- **Third-party Tests**: External service integration testing

## Troubleshooting

### Common Issues

**Application won't start**
- Verify Python 3.13+ is installed
- Check configuration file syntax
- Ensure all required directories exist

**PDF processing fails**
- Verify Llama Cloud API credentials
- Check PDF file format and accessibility
- Review application logs for detailed errors

**Web interface issues**
- Confirm web server is running on correct port
- Check browser console for JavaScript errors
- Verify authentication credentials

### Logging

Application logs are written to the file specified in `config.yaml` under `logging.log_file`. Default location is `app.log`.

### Getting Help

1. Check the [User Guide](docs/user_guide.md) for detailed instructions
2. Review [Design Architecture](docs/design_architecture.md) for technical details
3. Examine application logs for error details
4. Check the repository's issue tracker for known problems

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add comprehensive type hints
- Include unit tests for new features
- Update documentation as needed
- Ensure backward compatibility

## License

No repository license file is currently present. Confirm the applicable usage
and distribution terms with the project owner before redistributing the code.

## Acknowledgments

- **Llama Cloud** for AI-powered document extraction
- **Prefect** for workflow orchestration
- **FastAPI** for the web framework
- Open source community for various tools and libraries

## Support

For support and questions:
- Create an issue in the repository's issue tracker
- Check existing documentation in the `docs/` folder
- Review the [User Guide](docs/user_guide.md) for detailed instructions

---

**Built with ❤️ for intelligent document processing**
