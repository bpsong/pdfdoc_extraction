# PDF Document Processing System

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.12-green.svg)](https://fastapi.tiangolo.com/)
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

### Configurable Pipeline Architecture
- **Modular Design**: Pluggable processing steps (extraction, storage, archiving, rules)
- **Prefect Workflow Orchestration**: Reliable task execution and error handling
- **Dynamic Configuration**: YAML-based pipeline definition
- **Extensible Framework**: Easy to add new processing steps

### Flexible Data Storage
- **CSV Export**: Structured data in spreadsheet format
- **JSON Export**: Hierarchical data preservation
- **v2 Enhanced Storage**: Row-per-item expansion for tabular data
- **Local File Management**: Organized storage with metadata tracking

### Modern Web Interface
- **FastAPI Backend**: High-performance REST API
- **Interactive Dashboard**: Real-time processing status
- **Enhanced Modal Dialogs**: Detailed progress visualization with timeline
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
   ```bash
   C:\Python313\python.exe main.py
   ```

5. **Access the web interface**
   Open your browser and navigate to `http://localhost:8000`

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

watch_folder:
  dir: "watch_folder"
  validate_pdf_header: true
  processing_dir: "processing_folder_default"

authentication:
  username: "admin"
  password_hash: "$2b$12$example_hash_for_secure_password"

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

For the phased SDK migration details, see
[LlamaCloud Extract v2 Migration Plan](docs/llamacloud_extract_v2_migration.md).

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

## Usage

### Web Interface

1. **Login**: Access the dashboard at `http://localhost:8000`
2. **Upload PDFs**: Use the upload form to submit documents
3. **Monitor Progress**: View real-time processing status
4. **Download Results**: Access processed data in CSV/JSON format

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

### File Operations
- `POST /upload`: Upload PDF for processing
- `GET /api/files`: List processed files
- `GET /api/status/{file_id}`: Detailed processing status

### Status Monitoring
- Real-time status updates via WebSocket
- Comprehensive error reporting
- Processing timeline visualization

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
│   ├── status_manager.py       # Status tracking
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
   C:\Python313\python.exe -m pip install -r requirements.txt
   ```

2. **Run tests**
   ```powershell
   C:\Python313\python.exe -m pytest -v
   ```

3. **Development mode**
   ```powershell
   $env:USE_RELOAD="true"
   C:\Python313\python.exe main.py
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
C:\Python313\python.exe -m pytest -v

# Run specific test file
C:\Python313\python.exe -m pytest -v test/core/test_config_manager.py

# Run with coverage
C:\Python313\python.exe -m pytest -v --cov=modules
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
