# PDF Document Processing System

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136.3-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A sophisticated PDF document processing system that leverages AI-powered extraction to convert unstructured PDF documents into structured data. Built with modern Python technologies and designed for enterprise document processing workflows.

## Key Features

### AI-Powered Data Extraction
- **Llama Cloud Integration**: Advanced AI service for intelligent document understanding
- **Structured Data Extraction**: Converts PDF content into structured JSON/CSV format
- **Multi-format Support**: Handles invoices, receipts, forms, and various document types
- **v2 Array-of-Objects Support**: Extract line items and tabular data from complex documents

### Multiple Input Methods
- **Watch Folder Monitoring**: Automated processing of dropped PDF files
- **Web Upload Interface**: User-friendly web portal for manual uploads
- **Real-time Processing**: Live status updates and progress tracking
- **Batch Uploads**: `/app/upload` supports multi-file upload and creates batch/document records for tracking

### Configurable Pipeline Architecture
- **Modular Design**: Pluggable processing steps (extraction, storage, archiving, rules)
- **Prefect Workflow Orchestration**: Reliable task execution and error handling
- **Dynamic Configuration**: YAML-based pipeline definition
- **Extensible Framework**: Easy to add new processing steps
- **SQLite-backed Workflow State**: Batches, documents, task runs, extracted fields, review items, artifacts, settings, and audit history are persisted in SQLite

### Flexible Data Storage
- **CSV Export**: Structured data in spreadsheet format
- **JSON Export**: Hierarchical data preservation
- **v2 Enhanced Storage**: Row-per-item expansion for tabular data
- **Local File Management**: Organized storage with metadata tracking
- **Artifact Registry**: Source originals, split working files, archives, PDFs, CSVs, and JSON exports are registered as durable document files

### Modern Web Interface
- **FastAPI Backend**: High-performance REST API
- **Operator App**: `/app/upload`, `/app/processing`, `/app/review`, `/app/reports`, and `/app/settings`
- **Admin App**: `/app/admin`, `/app/admin/pipeline`, `/app/admin/tasks`, `/app/admin/review-gate`, `/app/admin/split`, `/app/admin/audit`, and `/app/admin/dry-run` (Review Gate Simulator)
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
   C:\Python313\python.exe -m pip install -r requirements.txt
   ```

3. **Configure the system**
   Open `config.yaml` in the project root and set your host, credentials, and task parameters.

4. **Run the application**
   ```powershell
   C:\Python313\python.exe main.py
   ```

   Database migrations run automatically on startup when `database.run_migrations_on_startup` is enabled.

5. **Access the web interface**
   Open your browser and navigate to `http://localhost:8000/app/upload`

## Installation

### System Requirements
- **Operating System**: Windows 11 (primary), cross-platform compatibility
- **Python Version**: 3.13+
- **Memory**: 4GB minimum, 8GB recommended
- **Storage**: 2GB free space for application + document storage

### Dependencies Installation
```bash
C:\Python313\python.exe -m pip install -r requirements.txt
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
  enabled: true
  default_queue_name: "default_review"
  lock_timeout_minutes: 60

watch_folder:
  dir: "watch_folder"
  validate_pdf_header: true
  processing_dir: "processing_folder_default"

tasks:
  extract_document_data:
    module: standard_step.extraction.extract_pdf_v2
    class: ExtractPdfV2Task
    params:
      api_key: "your_llama_cloud_api_key"
      # Optional: use a saved Extract v2 configuration from the LlamaCloud UI.
      # If omitted, the task builds an inline schema from fields.
      configuration_id: "your_extract_v2_configuration_id"
      tier: "agentic"
      extraction_target: "per_doc"
      fields:
        supplier_name:
          alias: "Supplier name"
          type: "str"
        items:
          alias: "Items"
          type: "List[Any]"
          is_table: true
          item_fields:
            description:
              alias: "description"
              type: "str"
            quantity:
              alias: "quantity"
              type: "str"

pipeline:
  - extract_document_data
```

Output folders are task-owned. For example, CSV/JSON tasks use `params.data_dir`, local PDF storage uses `params.files_dir`, archive tasks use `params.archive_dir`, and split tasks use required `params.split_dir`; `_dir` paths are auto-created at startup except `watch_folder.dir`.

The current runtime uses the `llama-cloud` SDK and `LlamaCloud` client. New code should not use the legacy `llama-cloud-services` / `LlamaExtract` agent flow. `agent_id` is legacy; use `configuration_id` for saved Extract v2 configurations or omit it to build an inline schema from `fields`.

### Manual LlamaCloud Smoke Check

After validating a saved Extract v2 configuration in the LlamaCloud UI, you can
run a one-file SDK and workflow fit check against `sample_invoice.pdf`:

```powershell
C:\Python313\python.exe tools\llamacloud_extract_smoke.py --config dev_config.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
```

If `configuration_id` is already set in `dev_config.yaml`, omit the override
flag.

The script writes:

- `raw_extract_result.json`: raw `result.extract_result` from LlamaCloud.
- `workflow_normalized_data.json`: data after matching returned keys to workflow
  fields and applying configured types.
- `workflow_fit_report.json`: missing workflow fields, extra raw keys,
  validation errors, and pass/fail status.

To re-check a saved raw result without another LlamaCloud call:

```powershell
C:\Python313\python.exe tools\llamacloud_extract_smoke.py --config dev_config.yaml --raw-json test\data\llamacloud_smoke\raw_extract_result.json
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

Text status files are not required for configured workflow state. `/api/files` and `/api/status/{file_id}` remain as legacy compatibility APIs, but they read from SQLite. Legacy HTML dashboard/upload pages are retired; use `/app/*` pages for browser workflows.

## Usage

### Web Interface

Before first login, initialize the two fixed SQLite users:

```powershell
C:\Python313\python.exe tools\setup_users.py --config config.yaml
```

For an upgrade from YAML credentials, preserve the existing admin hash while creating the operator account:

```powershell
C:\Python313\python.exe tools\setup_users.py --config config.yaml --legacy-config config.yaml
```

After a successful import, remove the legacy `authentication` block. Passwords must contain uppercase, lowercase, numeric, and symbol characters and be 12–72 UTF-8 bytes.

1. **Login**: Access the app at `http://localhost:8000/app/upload` and select `admin` or `operator`
2. **Upload PDFs**: Use `/app/upload` to submit one or more PDFs as a batch
3. **Monitor Progress**: Use `/app/processing` or `/app/batches/{batch_id}` to track splitting, extraction, review, and completion state
4. **Review Exceptions**: Use `/app/review` and `/app/review/{review_item_id}` for human review queues
5. **Inspect Results**: Use `/app/documents/{document_id}/extraction` for extracted fields and source PDF access
6. **Inspect Batch History**: Use `/app/reports` and click a recent batch row to view document task timelines and task-run details
7. **Administer Configuration**: Admin users use `/app/admin/*` pages for pipeline, task catalog, review-gate, split, audit, review-gate simulation, and schema workflows

### Watch Folder

1. **Drop PDFs** into the `watch_folder` directory
2. **Automatic Processing**: Files are automatically detected and processed
3. **Status Updates**: Monitor progress through the web interface

### Command Line

```powershell
# Run with default configuration
C:\Python313\python.exe main.py

# Use custom configuration
C:\Python313\python.exe main.py --config-path custom_config.yaml

# Run without web server (watch folder only)
C:\Python313\python.exe main.py --no-web
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
- `POST /api/batches/upload`: Upload a batch of PDFs and create SQLite batch/document records
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
- `GET /api/admin/pipeline`, `PUT /api/admin/pipeline/draft`, `POST /api/admin/pipeline/publish`: Pipeline editing flow
- `GET /api/admin/review-gate-rules`, `PUT /api/admin/review-gate-rules`: Review gate configuration
- `GET /api/admin/split-settings`, `PUT /api/admin/split-settings`: Split settings configuration

## 📁 Project Structure

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
│   ├── watch_folder_monitor.py # File system monitoring
│   └── workflow_manager.py     # Workflow orchestration
├── 📁 standard_step/           # Processing pipeline steps
│   ├── extraction/             # Data extraction tasks
│   │   ├── extract_pdf.py      # Basic extraction
│   │   └── extract_pdf_v2.py   # Enhanced extraction with arrays
│   ├── storage/                # Data storage tasks
│   │   ├── store_metadata_as_csv.py
│   │   ├── store_metadata_as_json.py
│   │   ├── store_metadata_as_csv_v2.py
│   │   └── store_metadata_as_json_v2.py
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
│   └── user_guide.md           # User manual
└── 📁 tasks/                   # Project management
    ├── prd-*.md                # Product requirements
    └── future_todos.md         # Development roadmap
```

## 🛠️ Development

### Setting Up Development Environment

1. **Clone and install**
   ```powershell
   git clone <repository-url>
   cd pdfdoc_extraction
   C:\Python313\python.exe -m venv .venv
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
- **Documentation**: Google-style docstrings for all modules
- **Error Handling**: Structured error handling with custom exceptions
- **Testing**: Unit tests for all new features

## Testing

### Running Tests

```powershell
# Run all tests
.\.venv\Scripts\python.exe -m pytest -v

# Run specific test file
.\.venv\Scripts\python.exe -m pytest -v test/core/test_config_manager.py

# Run with coverage
.\.venv\Scripts\python.exe -m pytest -v --cov=modules

# Run static type checking (uses .venv from pyrightconfig.json)
pyright
```

Current focused validation for the SQLite-only workflow-state cleanup:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\integration\test_sqlite_only_workflow_state.py test\integration\test_batch_upload_api.py test\integration\test_reports_api.py test\integration\test_settings_api.py
```

The broader full-suite run remains part of the migration cleanup checklist.

The end-to-end workflow fixture config also passes config-check:

```powershell
C:\Python313\python.exe -m tools.config_check validate --config test\data\config.yaml --import-checks
```

### Test Categories

- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end workflow validation
- **Third-party Tests**: External service integration testing

## 🔧 Troubleshooting

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
4. Check the [Issues](../../issues) page for known problems

## 🤝 Contributing

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

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Llama Cloud** for AI-powered document extraction
- **Prefect** for workflow orchestration
- **FastAPI** for the web framework
- Open source community for various tools and libraries

## 📞 Support

For support and questions:
- Create an issue in the [Issues](../../issues) section
- Check existing documentation in the `docs/` folder
- Review the [User Guide](docs/user_guide.md) for detailed instructions

---

**Built with ❤️ for intelligent document processing**
