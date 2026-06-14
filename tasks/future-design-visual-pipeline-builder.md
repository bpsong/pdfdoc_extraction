# Future Design Direction: Visual Pipeline Builder

## Background

Today the application is configured primarily through `config.yaml`, with some UI support for safer edits. The admin pipeline page can add, remove, reorder, enable, validate, diff, and publish pipeline steps, but generic task parameters are still edited as raw JSON in a text area. The UI also still exposes YAML previews and the publish path writes generated YAML back to the active config file.

This makes workflow configuration error-prone for administrators who are not comfortable editing structured YAML or JSON. A visual pipeline builder should reduce that risk by turning the current YAML-backed task pipeline into an editable node-based UI with a task-specific properties panel.

## Verified Current Behavior

- The runtime pipeline is currently a serial ordered pipeline loaded from `pipeline` in `config.yaml`.
- `WorkflowLoader` executes the configured task keys in order inside one Prefect flow.
- The split task is a special fan-out boundary:
  - `LlamaCloudSplitTask` creates child PDFs and child document records.
  - It sets `split_children`, `fan_out_start_task_index`, and `pipeline_state: fan_out`.
  - The parent flow returns at that boundary.
  - `WorkflowManager` starts child workflows from the next configured task index.
- Fan-in already exists as an aggregation service, not as a configurable visual join node:
  - `FanInService.finalize_leaf()` recomputes leaf, root document, and batch status.
  - It emits a `fan_in_completed` audit event when all leaf documents reach terminal states.
- Child workflows are started in a loop, so the current implementation has fan-out semantics, but not necessarily parallel execution.
- The current pipeline editor is a safer wrapper around the YAML model, not a fully separate workflow-definition system.

## UX Problem

Administrators should not need to edit YAML snippets or raw JSON blobs for normal workflow changes. The highest-friction areas are:

- Task parameters, especially nested extraction fields, storage filename templates, split categories, and review-gate rules.
- Understanding the effective task order and where split fan-out occurs.
- Knowing whether edits are valid before publishing.
- Avoiding accidental edits to secret-like values inside config files.

## Recommended Direction

Build a visual pipeline builder that compiles back to the existing `tasks` plus `pipeline` config model.

The first version should not attempt to replace the workflow engine. It should preserve the current serial pipeline semantics and use visual editing only as a safer authoring layer.

Suggested first-screen structure:

```text
Task Palette -> Visual Serial Canvas -> Properties Panel -> Validate -> YAML Preview -> Publish
```

The canvas should represent each configured task as a node. Normal nodes should have one input and one output. The split node can visually indicate fan-out, but should still compile to the existing serial config and rely on the backend split task to create child workflows.

## Candidate Open-Source JS Libraries

### Recommended for Product Direction: React Flow / XYFlow

- Website: https://reactflow.dev/
- License: MIT
- Strengths:
  - Mature node-based editor foundation.
  - Good fit for custom nodes, selection, drag/drop, pan/zoom, and side-panel editing.
  - Strong ecosystem and examples.
- Tradeoff:
  - The current app is server-rendered templates plus vanilla JS, so this likely means adding a small React island to the admin pipeline page.

### Recommended for Quick Prototype: Drawflow

- GitHub: https://github.com/jerosoler/Drawflow
- License: MIT
- Strengths:
  - Simple vanilla-JS setup.
  - Lower integration cost for a proof of concept.
- Tradeoff:
  - Less robust as a long-term foundation for a polished workflow builder.

### Other Options

- Rete.js: https://retejs.org/docs/
  - Good if the product eventually needs true graph/dataflow programming.
- LogicFlow: https://github.com/didi/LogicFlow
  - Good if the desired interaction model is closer to a flowchart/process editor.
- JointJS Community: https://www.jointjs.com/license
  - Strong diagramming foundation, but advanced application-builder features are commercial in JointJS+.

## Proposed Phases

### Phase 1: Task-Specific Properties Forms

Replace the generic `Params JSON` editor with task-specific forms where possible.

Examples:

- Extraction task:
  - API key status, configuration ID, tier, extraction target.
  - Field table with key, alias, type, required, and table settings.
- Review gate:
  - Reuse or embed the existing review-gate form controls.
- Split:
  - Reuse or embed the existing split settings form controls.
- Storage tasks:
  - Data/files directory, filename template, format-specific options.
- Archive task:
  - Archive directory and retention-related settings if added later.

Keep raw JSON/YAML as an advanced escape hatch, not the primary editing mode.

### Phase 2: Visual Serial Pipeline Canvas

Add a node canvas for the current ordered pipeline.

Expected behavior:

- Render active and draft pipeline as nodes connected left-to-right.
- Add tasks from the task catalog.
- Reorder tasks by dragging or using keyboard-accessible move controls.
- Enable, disable, remove, and duplicate nodes.
- Selecting a node opens the properties panel.
- Validate before publish using the existing backend validation service.
- Compile the visual model into the existing `PipelineConfigService` model.

The published output remains the current YAML-backed config shape.

### Phase 3: Split-Aware Visualization

Make split behavior understandable without changing execution semantics.

Expected behavior:

- Mark `LlamaCloudSplitTask` as a fan-out boundary.
- Show downstream nodes as applying to split child documents when split is enabled.
- Display warning states when split is the final pipeline step.
- Show fan-in as an implicit aggregate/status operation, not as a user-editable node initially.

### Phase 4: True Graph Workflow Evaluation

Only consider this after the serial visual builder is stable.

This would require backend architecture changes:

- Graph schema instead of ordered `pipeline` list.
- Edge conditions and branch validation.
- Workflow loader support for DAG traversal.
- Resume logic based on graph position rather than next list index.
- Fan-out and fan-in as explicit graph concepts.
- More complex UI validation and run-state visualization.

This should be treated as a separate PRD, not an incremental UI-only change.

## Non-Goals For First Version

- Do not implement arbitrary branching or conditional edges.
- Do not replace Prefect workflow execution semantics.
- Do not remove YAML export/preview immediately.
- Do not expose secret values in the properties panel.
- Do not require users to understand internal module/class paths for standard tasks.
- Do not make the visual builder responsible for runtime fan-in aggregation.

## Security And Governance Considerations

- Secrets should not be edited as plain YAML/JSON in the browser.
- Secret-like fields should be redacted in read APIs.
- The UI should show whether a secret is configured, not its value.
- Publishing should continue to require validation with no blocking findings.
- Audit events should record pipeline draft save, validation, and publish events.
- Config diffs should redact secret-like values.

## Acceptance Criteria For A Future Implementation

- An admin can reorder the serial pipeline without editing YAML.
- An admin can edit common task parameters through form controls.
- The builder validates drafts before publishing.
- The builder publishes to the same runtime config model used today.
- Existing upload, split fan-out, review pause/resume, fan-in finalization, and reports keep working.
- YAML/JSON editing is optional and clearly marked as advanced.
- Tests prove visual model compilation preserves the expected `tasks` and `pipeline` output.

