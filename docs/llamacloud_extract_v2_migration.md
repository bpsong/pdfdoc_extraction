# LlamaCloud Extract v2 Migration Plan

This project is migrating from the legacy `llama-cloud-services` package and
agent-based Extract flow to the current `llama-cloud` Python SDK and Extract v2
job flow.

## Target SDK Contract

Install the current SDK:

```powershell
C:\Python313\python.exe -m pip install "llama-cloud>=2.1"
```

The runtime should use:

```python
from llama_cloud import LlamaCloud
```

Legacy code should no longer import:

```python
from llama_cloud_services import LlamaExtract
```

## Runtime Mapping

| Legacy Extract flow | Extract v2 flow |
| --- | --- |
| `llama-cloud-services` | `llama-cloud>=2.1` |
| `LlamaExtract(api_key=...)` | `LlamaCloud(api_key=...)` |
| `client.get_agent(id=agent_id)` | saved `configuration_id` or inline `configuration` |
| `agent.extract(file_path)` | upload with `client.files.create`, run with `client.extract.run` |
| agent result `.data` | job `.extract_result` |
| `extraction_metadata` on result | `client.extract.get(job.id, expand=["extract_metadata"])` |

## Configuration Contract

Required:

```yaml
params:
  api_key: "llx-..."
  fields:
    supplier_name:
      alias: "Supplier name"
      type: "str"
```

Optional saved cloud configuration:

```yaml
params:
  configuration_id: "cfg-..."
```

If `configuration_id` is absent, the extraction task builds an inline Extract v2
configuration from `fields`. Workflow field keys, such as `supplier_name`,
become JSON-schema property names sent to LlamaCloud; aliases are kept as
descriptions and output labels for storage.

Saved LlamaCloud configurations may return either workflow field keys
(`supplier_name`) or aliases (`Supplier name`). The extraction tasks accept both
and normalize output to workflow field keys before downstream steps run.

Optional runtime tuning:

```yaml
params:
  tier: "agentic"
  parse_tier: "agentic"
  extraction_target: "per_doc"
  cite_sources: true
  poll_interval_seconds: 2
  timeout_seconds: 1800
```

`agent_id` is legacy and should not be used for new Extract v2 configuration.

## Phased Rollout

### Phase 1: SDK Cutover and Configuration Readiness

Status: completed in the current working tree.

- Replace documented dependency references with `llama-cloud>=2.1`.
- Remove runtime imports of `llama-cloud-services`.
- Route extraction through an Extract v2 adapter that uploads files, creates
  jobs, polls terminal status, and normalizes results.
- Document the v2 configuration contract.
- Update examples to use `configuration_id` or inline `fields`.
- Keep cloud validation and test execution out of this phase.

### Phase 2: LlamaCloud UI Validation

Status: in progress.

- Create or verify saved Extract v2 configurations in the LlamaCloud UI.
- Add `configuration_id` to local/cloud configs when a saved configuration is
  preferred.
- Run a single cloud-backed extraction manually through the UI workflow.
- Compare extracted field names against configured workflow field keys and aliases.

Manual SDK and workflow fit check, using `sample_invoice.pdf` by default:

```powershell
C:\Python313\python.exe tools\llamacloud_extract_smoke.py --config dev_config.yaml --file sample_invoice.pdf --configuration-id "cfg-..."
```

If `configuration_id` is already set in the selected config file, omit the
`--configuration-id` flag.

The script saves:

- `raw_extract_result.json`: raw LlamaCloud `extract_result`.
- `workflow_normalized_data.json`: payload after matching returned keys to
  workflow fields and applying configured types.
- `workflow_fit_report.json`: missing workflow fields, extra raw keys,
  validation errors, and `fits_workflow`.

To re-check a saved raw result without another LlamaCloud call:

```powershell
C:\Python313\python.exe tools\llamacloud_extract_smoke.py --config dev_config.yaml --raw-json test\data\llamacloud_smoke\raw_extract_result.json
```

### Phase 3: Test and Legacy Cleanup

Status: pending.

- Run the full pytest suite.
- Update remaining tests to mock the v2 adapter rather than legacy agents.
- Remove any remaining legacy examples after the cloud rollout is stable.
