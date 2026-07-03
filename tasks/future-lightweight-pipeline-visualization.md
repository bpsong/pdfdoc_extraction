# Future Design: Lightweight Pipeline Visualization

## Status

Deferred. This document records optional presentation improvements, not a
commitment to replace the production Pipeline editor.

## Product Decision

The production serial-list editor under `web/` is the accepted pipeline
authoring experience. It already supports the important workflow operations:

- add, reorder, enable, disable, duplicate, and remove tasks;
- edit common task parameters through task-specific forms;
- retain advanced JSON as an escape hatch;
- save and compare drafts;
- validate before publishing;
- compile and publish the existing `tasks` and `pipeline` YAML model; and
- redact secrets and audit administrative changes.

The React/Vite prototype is not a production dependency and should not be
ported wholesale. Its node canvas and richer visual effects do not currently
provide enough additional value for an ordered serial pipeline to justify the
extra runtime, frontend architecture, testing, and maintenance cost.

## Performance Position

A React or node-editor implementation is not inherently slow. Performance
depends on the number of mounted elements, rerender scope, event handlers,
layout work, effects, and library behavior. A carefully virtualized canvas can
perform well, while an inefficient vanilla-JavaScript page can perform poorly.

The decision to retain the current editor is therefore based on proportionality,
not an assumption that React is always slower. The present pipeline is an
ordered list, which the existing server-rendered page expresses directly with
fewer moving parts. A node library becomes easier to justify only if future
workflow semantics require graph navigation, branching, or route mapping.

Any future visualization work must measure production-page behavior before and
after the change. Visual polish alone is not sufficient justification for a
new frontend runtime or a large increase in DOM and event-handling complexity.

## Deferred Lightweight Improvements

These improvements may be implemented independently when operator feedback
shows that the current list is unclear:

1. **Split boundary cue**
   - Mark a configured split task as the fan-out boundary.
   - Explain that the source workflow stops at that point and child workflows
     resume at the next enabled task.

2. **Downstream child scope**
   - Add a lightweight divider or label after the split row.
   - Indicate that downstream tasks run once for each split child document.

3. **Implicit fan-in explanation**
   - Show fan-in as an informational status note, not an editable task.
   - Preserve `FanInService` as the runtime aggregation mechanism.

4. **Existing warning placement**
   - Surface the existing final-split validation warning close to the split
     task, in addition to the general validation panel.

5. **Optional serial-flow styling**
   - Consider simple CSS connectors or a compact horizontal read-only preview
     if they materially improve comprehension.
   - Keep the editable list and keyboard-accessible move controls authoritative.

These changes should normally use the existing Jinja, CSS, and vanilla-
JavaScript production stack. They do not require the prototype or a graph
editing library.

## Deferred Full Canvas Option

The following prototype concepts remain available for reconsideration, but are
not approved implementation work:

- a task palette grouped by task category;
- connected nodes showing the configured serial order;
- drag reordering backed by equivalent keyboard controls;
- selection of a node to open the existing task-specific properties forms;
- validation findings attached to the affected node; and
- split-aware scope cues for downstream child processing and implicit fan-in.

If approved later, the implementation should reuse the production API and
properties behavior rather than porting the prototype wholesale. Technology
selection must follow a measured proof of concept comparing initial load,
interaction latency, DOM size, memory use, accessibility, and bundle cost with
the production list editor.

## Full Canvas Reconsideration Triggers

Reconsider a node canvas only when at least one of these becomes approved
product scope:

- conditional branches or user-authored edges;
- multiple named pipeline templates that require visual route mapping;
- explicit graph fan-out and fan-in nodes;
- run-state inspection where graph position is materially clearer than a list;
- usability evidence showing that the current list causes significant operator
  errors that lightweight cues cannot resolve.

Such work requires a separate PRD covering graph schema, validation, execution,
resume behavior, accessibility, performance budgets, and migration from the
ordered `pipeline` list.

## Non-Goals

- Porting the React/Vite prototype wholesale.
- Adding a React island solely for visual polish.
- Replacing the current YAML-backed runtime model.
- Implementing arbitrary graph execution through UI changes alone.
- Making fan-in an administrator-configurable task.
- Removing the advanced JSON or read-only YAML inspection surfaces.

## Acceptance Criteria for Any Lightweight Change

- The production serial-list editor remains fully usable without a canvas.
- Split scope and child processing are described accurately.
- Fan-in remains informational and cannot be added, removed, or reordered.
- Keyboard controls and screen-reader labels remain available.
- Existing authentication, CSRF, role, redaction, validation, publishing, and
  audit behavior is preserved.
- Tests cover the added UI behavior and the existing pipeline compilation
  contract.
- A before-and-after browser measurement demonstrates no material regression
  for the supported pipeline size and target browsers.

## Related Documents

- [Current architecture](../docs/design_architecture.md)
- [Archived visual pipeline builder direction](archive/future-design-visual-pipeline-builder.md)
- [Future multiple pipeline templates](future-multi-document-routing.md)
- [Future mixed-document pipeline routing](future-mixed-document-routing.md)
