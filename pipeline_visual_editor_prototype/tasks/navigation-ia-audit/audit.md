# Task inspector scope and navigation audit

## Verdict

The current tab model should be reworked before this editor is treated as production-ready. `Properties` is task-scoped, while `Validate`, `YAML`, and `Diff` are pipeline/config-scoped. Placing all four beneath the selected task's name communicates that they share the same scope, which they do not.

This is an information-architecture problem, not primarily a labeling or visual-style problem.

## Evidence walkthrough

1. **Open YAML while `Store JSON metadata` is selected** — **Needs attention**
   - The selected task remains the panel heading, but the YAML contains unrelated tasks and global configuration.
   - Users can reasonably infer that this is the selected task's YAML because it sits inside that task's inspector.
   - Evidence: `01-task-selected-global-yaml.png`

2. **Select `Extract document data` without leaving YAML** — **Needs attention**
   - The task heading changes, while the YAML content remains the whole configuration.
   - This makes the task selection appear ineffective and reinforces ambiguity about what the tab belongs to.
   - Evidence: `02-another-task-same-global-yaml.png`

3. **Open Validate beneath `Extract document data`** — **Needs attention**
   - The message says the draft can be written to the prototype YAML file. This is pipeline-level publish readiness, not validation of the selected extract task.
   - A green result can create false confidence that the selected task and its fields have specifically passed validation.
   - Evidence: `03-task-selected-global-validation.png`

4. **Open Diff beneath `Extract document data`** — **Needs attention**
   - The diff begins with unrelated global sections and spans the whole configuration.
   - A narrow task inspector is also a poor reading surface for a long, global line diff.
   - Evidence: `04-task-selected-global-diff.png`

5. **Return to Properties** — **Healthy in isolation**
   - Properties correctly reflects the selected task and establishes the local scope users expect from this panel.
   - This makes the global scope of the adjacent tabs more surprising, not less.
   - Evidence: `05-task-properties.png`

## Why the current model is tempting

- It is compact and avoids adding another navigation surface.
- It keeps configuration diagnostics close to editing.
- It can be acceptable in a throwaway prototype whose users already understand that one YAML document backs the entire page.

Those benefits do not compensate for misleading ownership once users rely on the editor. Adjacent tabs under one object heading are expected to be alternate views of that object.

## Recommended information architecture

### Task inspector

Keep this panel task-scoped:

- `Properties`
- `Issues (n)` — only findings belonging to the selected task, with controls linked to the affected field
- Optional `Task YAML` — only if the application can produce a genuine selected-task snippet
- Optional `Task changes` — only if the application can filter changes to the selected task

If true task-level YAML and diff views cannot be produced reliably, omit them here.

### Pipeline workspace

Move whole-document actions to the pipeline/page level:

- `Validate pipeline` near Simulate/Publish
- `Pipeline YAML` near the editable source filename or as a page-level view
- `Review changes` beside Publish and the unsaved-draft status

Open YAML and diff in a wide drawer, modal workspace, or full-width page view. Their content density is not suited to the narrow task inspector.

### Validation hierarchy

Use two levels:

1. Inline or task-level issues while editing the selected task.
2. A global validation summary grouped by task, with links that select the relevant task and field.

This preserves local feedback while making pipeline readiness explicit.

## Lower-cost interim option

If the structure cannot be changed immediately, rename and visually separate the tabs:

- Local group: `Properties`
- Pipeline group: `Pipeline validation`, `Pipeline YAML`, `Pipeline diff`

This is safer than the current labels, but still makes one panel switch between two ownership levels. Treat it as an interim fix rather than the target design.

## Implementation priority

1. Move global Validate/YAML/Diff out of the task tab set.
2. Add task-filtered issue counts and navigation.
3. Give global YAML and Diff a wider workspace.
4. Add task-scoped YAML/changes only if the data model can define them unambiguously.
