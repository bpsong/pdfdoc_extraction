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
| `agent.extract(file_path)` | upload with `client.files.create`, run with `client.extract.create` |
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
configuration from `fields`. Field `alias` values become JSON-schema property
names sent to LlamaCloud, so aliases must match the desired extracted output.

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

Status: pending.

- Create or verify saved Extract v2 configurations in the LlamaCloud UI.
- Add `configuration_id` to local/cloud configs when a saved configuration is
  preferred.
- Run a single cloud-backed extraction manually through the UI workflow.
- Compare extracted field names against configured aliases.

### Phase 3: Test and Legacy Cleanup

Status: pending.

- Run the full pytest suite.
- Update remaining tests to mock the v2 adapter rather than legacy agents.
- Remove any remaining `agent_id` examples and compatibility metadata after
  the cloud rollout is stable.
