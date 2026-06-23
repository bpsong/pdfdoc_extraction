# Pipeline Merge IA/UX Audit

## Scope

- Current primary admin configuration route: `/app/admin/pipeline`.
- Former standalone review and split admin pages were reviewed before demotion.
- Prototype: `pipeline_visual_editor_prototype/` rendered at `http://127.0.0.1:5174`.
- Goal: decide whether `review-gate` and `split` are useful when merging the prototype into `/app/admin/pipeline`.

## Evidence

1. `01-current-pipeline.png` - Current production Pipeline page.
2. `02-current-review-gate-full.png` - Former Review Gate settings page.
3. `03-current-split-full.png` - Former split task settings page.
4. `04-prototype-split-properties-full.png` - Prototype Split task inspector.
5. `05-prototype-review-gate-properties-full.png` - Prototype Review Gate task inspector.
6. `06-prototype-pipeline-yaml-workspace.png` - Prototype global Pipeline YAML workspace.

## Verdict

Review gate and split controls are useful, but their best role changes after the prototype is merged. They should not remain equally prominent standalone admin destinations beside `/app/admin/pipeline`. Their domain-specific controls should be folded into the selected task inspector inside the Pipeline editor.

## Why They Are Useful

- They translate raw task params into safer controls: sliders, toggles, selects, category rows, field threshold rows, status summaries, and connection feedback.
- They expose task semantics that the current Pipeline page hides inside raw `Params JSON`.
- Split task settings safely summarize adapter state and API-key presence without exposing the key.
- Review Gate clarifies threshold precedence, triggers, queue behavior, schema linkage, and field overrides.

## Current IA Risks

- Production Pipeline, Review Gate, and split settings were siblings in the Admin navigation, but the review and split controls are really configuration views for specific pipeline tasks.
- The current Pipeline page requires editing selected task params as JSON. This is fragile for high-impact controls such as thresholds, queue behavior, split category policy, and provider settings.
- At the tested desktop viewport, the current Pipeline page has horizontal overflow and a cramped task property panel. A visual editor merge will increase the pressure on this layout.
- The current Pipeline task Params JSON can expose secret-looking values. The prototype's secret input pattern is a better UX and trust model.

## Prototype IA Strengths

- The selected task inspector owns task-scoped views only: `Properties` and `Issues`.
- Pipeline-wide views are moved to page-level tools: `Validate pipeline`, `Pipeline YAML`, and `Review changes`.
- Split and Review Gate are modeled as normal pipeline nodes with specialized controls in the right context.
- Advanced JSON remains available as progressive disclosure instead of being the primary editing mode.

## Recommendation

1. Make `/app/admin/pipeline` the primary configuration destination.
2. Move the review and split control groups into task-specific property panels for `ReviewGateTask` and `LlamaCloudSplitTask`.
3. Keep global actions at the page level: validate, YAML preview, diff, simulate, save draft, publish.
4. Keep the former standalone review and split admin destinations demoted from primary navigation and redirect them to Pipeline.
5. Preserve Split's connection/status affordances, but place them inside the Split task panel or a task-scoped status drawer.
6. Replace raw secret-bearing JSON as the default editor with typed controls and masked secret fields. Keep advanced JSON behind disclosure for recovery and power users.

## Accessibility And Verification Limits

- Screenshots and DOM snapshots confirmed visible labels, task ownership, route structure, and native control use.
- This audit did not run a full keyboard, screen-reader, contrast, or zoom audit.
- Current app screenshots were captured through a temporary local admin session for read-only review.
