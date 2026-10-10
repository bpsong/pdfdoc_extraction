# Install the application and extraction providers

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Prepare the Windows deployment

Obtain the approved application artifact and Python 3.13. Run PowerShell from
the repository root under the intended deployment account. Create the runtime
environment and install pinned dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use `requirements-dev.txt` instead when preparing a development/test machine.
Committed frontend assets are sufficient for runtime; install Node/npm and run
`npm ci` when building them. The separate prototype is not part of deployment.

Create an ignored deployment YAML, prepare the required watch/upload roots and
configure the database, logs, permissions and secure browser access using
[configuration and access](configuration-and-access.md). Provision accounts
using [account setup](account-recovery.md). Follow [startup](starting-and-stopping.md)
so normal migration and child verification happen in the supported order.
Ask the application admin to publish a form/pipeline and test representative
documents before enabling intake. Installation alone creates no usable routing.

## LlamaCloud

Obtain authorised provider credentials through the approved secret channel.
Configure a named alias in deployment `pipeline_secrets`; admins select that
alias in their pipeline. Arrange outbound access to the provider and check
quotas. A live smoke check consumes provider resources and requires explicit
authorisation; ordinary installation and synthetic tests do not need one.

See [LlamaCloud task parameters](../reference/tasks/llamacloud-extraction.md).

## GLM-OCR with Ollama

Install Ollama separately. The app does not install/start Ollama or download
models. Confirm the pipeline's configured vision and resolver model names;
typical current choices are:

```powershell
ollama pull glm-ocr:latest
ollama pull qwen3.5:9b-q4_K_M
ollama list
```

Start Ollama through its desktop application or `ollama serve` if no service is
already running. Verify the configured endpoint is reachable from the worker's
account. GLM-OCR document resolution needs its resolver model as well as the
vision model. Check RAM/GPU capacity with a representative synthetic workload;
large documents can take substantially longer than small ones.

See [GLM-OCR parameters and limits](../reference/tasks/glm-ocr-extraction.md).

## LiteParse with Ollama

The runtime requirements include the parser integration. Prepare a local
Ollama model and working Tesseract OCR with the language data named by the
pipeline's `ocr_language`. Embedded text uses parsing; scanned pages need OCR.
Check the parser/OCR from the deployment account with a synthetic scanned PDF.
Missing language data needs installation through the approved local OCR setup.

```powershell
ollama pull qwen3.5:9b-q4_K_M
ollama list
```

Downloads may require internet access during setup. LiteParse runtime accepts
only credential-free HTTP loopback Ollama endpoints and local GGUF models;
cloud-backed models, redirects, remote OCR servers and environment proxies are
rejected. It cannot use a remote Ollama host just because GLM-OCR can.
See [LiteParse parameters](../reference/tasks/liteparse-extraction.md).

## Verify the handoff

Confirm readiness, both account logins, provider/model availability, an approved
pipeline version, review completion and readable registered outputs. Record
the deployment revision and environment without capturing credentials or raw
document content. Use synthetic documents for routine checks.
