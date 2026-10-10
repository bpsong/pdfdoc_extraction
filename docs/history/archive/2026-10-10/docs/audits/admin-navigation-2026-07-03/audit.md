# Admin Navigation Information Architecture Audit

Date: 2026-07-03

## Scope

Review the administrator sidebar grouping and naming of the review-schema editor, task catalog, and pipeline configuration links.

## Step 1 — Admin navigation

Evidence: [01-admin-navigation.png](01-admin-navigation.png)

Health: Needs revision.

- Strength: The sidebar separates administrative links from the operator workflow and uses visible group labels.
- UX issue: `Quality` contains both schema authoring and configuration validation, while `Configuration` contains the pipeline editor and task catalog. This splits closely related configuration work across two groups.
- UX issue: `Schemas` describes the storage/implementation concept rather than the administrator's outcome: defining the operator review form.
- UX issue: `Tasks` sounds configurable beside `Pipeline`, even though the destination is primarily a catalog and metadata view.
- Accessibility risk: The group labels are generic text rather than semantic headings or labelled navigation groups. Their relationships may be less clear to screen-reader users than they are visually.

## Step 2 — Schema editor

Evidence: [02-review-schema-editor.png](02-review-schema-editor.png)

Health: Functional, but the navigation label undersells and obscures its purpose.

- Strength: The page clearly supports creation, editing, duplication, validation, and saving of schema-backed forms.
- UX issue: The page title `Schema Editor`, sidebar label `Schemas`, and internal `Schemas` heading all expose implementation language. The actual user-facing outcome is configuring fields, labels, requirements, help text, and controls used during review.
- UX issue: The subtitle `Manage schemas used by extraction review workflows` can be read as extraction configuration, even though the repository documentation states that review schemas do not define what the extraction service extracts.
- Naming direction: Prefer `Review Forms` in navigation and `Review Form Editor` as the page title. Retain `schema` terminology in technical details such as filenames, validation messages, and documentation for advanced administrators.
- Accessibility risk: Several controls rely on dense visual grouping. Keyboard order, focus visibility, and zoom/reflow need interactive testing and cannot be confirmed from this screenshot alone.

## Step 3 — Task catalog

Evidence: [03-task-catalog.png](03-task-catalog.png)

Health: The destination is clear; the sidebar label is ambiguous.

- Strength: The page title and subtitle already use the accurate mental model: this is a catalog for inspecting available workflow task classes.
- UX issue: The shorter sidebar label `Tasks` drops the key qualifier and sits beside a truly configurable `Pipeline` page. Administrators can reasonably expect `Tasks` to create or edit task instances.
- Naming direction: Prefer `Task Catalog`. It is shorter, more conventional, and more specific than `Tasks Info`. The noun `Catalog` signals browse/inspect behavior without the awkwardness of `Info`.
- Scope caveat: The catalog is not strictly read-only: importable rows can expose an `Add in Pipeline` action. `Task Reference` would therefore be too passive, while `Task Library` could imply installable or user-managed task definitions that do not exist here.
- Accessibility risk: The two filter controls have no visible labels in the screenshot, and the accessibility snapshot exposes both as unnamed comboboxes. Add persistent labels or explicit accessible names; placeholder/options alone are not a robust label.

## Step 4 — Pipeline configuration

Evidence: [04-pipeline-configuration.png](04-pipeline-configuration.png)

Health: Correctly categorized as configuration.

- Strength: The page clearly creates and edits configured task instances: order, enablement, error behavior, and task-specific parameters.
- Strength: The `Open Task Catalog` link already expresses the distinction between configuring a task instance here and inspecting available task classes in the catalog.
- UX implication: Keeping `Pipeline` and `Task Catalog` adjacent is useful because they are two views of the same domain. Their labels must make the action/reference distinction explicit.
- UX issue: `Pipeline` is serviceable but `Pipeline Configuration` would be more self-explanatory if sidebar width permits. The current page subtitle already supplies that context, so changing this label is lower priority.
- Accessibility risk: The task editor is dense and vertically long. Responsive reflow, keyboard reordering, focus movement after selecting a task, and status announcements require interactive testing beyond this screenshot.

## Step 5 — Validation center

Evidence: [05-validation-center.png](05-validation-center.png)

Health: Useful page, incorrectly narrowed by the `Quality` group.

- Strength: The page accurately presents a cross-cutting check across the runtime config, pipeline, and schema files.
- UX issue: Grouping it under `Quality` suggests output/data-quality validation, but the page is configuration governance and readiness checking.
- Naming direction: Keep `Validation` if space is constrained, or use the existing page name `Validation Center`. Place it last under `Configuration` as the verification step after edits.
- Accessibility risk: The current screenshot does not show a clear programmatic relationship between the warning count and its finding row. Live updates, focus management, table semantics, and announcement behavior require interactive testing.

## Recommendation

The proposed diagnosis is correct, with two naming adjustments:

1. Move schema administration into `Configuration`.
2. Rename the navigation item to `Review Forms` (plural), not `Review Form`, because the destination manages a collection. Rename the page to `Review Form Editor` while keeping technical `schema` language where filenames and validation require it.
3. Rename `Tasks` to `Task Catalog`, not `Tasks Info`. `Catalog` is conventional browse-and-inspect language and matches the existing page title. `Info` is vague and makes the navigation read like helper documentation.
4. Move `Validation` into `Configuration` too. It validates config, pipeline, and review-schema files, so leaving it in `Quality` preserves the same category split the schema move is intended to fix.

Recommended sidebar:

```text
Admin
  Overview
  Users

Configuration
  Pipeline
  Review Forms
  Task Catalog
  Validation

Compliance
  Audit Log
```

`Pipeline` remains first because it is the primary place where task instances are configured. `Review Forms` is a separate configuration artifact. `Task Catalog` is the supporting reference/library, and `Validation` is the final verification step.

If the administration surface grows substantially, a later structure could split `Configuration` into `Workflow Setup` (`Pipeline`, `Review Forms`) and `Reference & Assurance` (`Task Catalog`, `Validation`). With only four links, that extra hierarchy would add visual noise without improving findability.

## Accessibility and evidence limits

- The screenshots and accessibility snapshots support the naming, grouping, and missing-label findings above.
- The group dividers are visually styled text nodes rather than semantic headings or separately labelled navigation regions. Use headings or `aria-labelledby` relationships if the visual groups remain.
- Full keyboard operation, focus visibility, responsive behavior, zoom reflow, contrast, and screen-reader announcements were not exhaustively tested.
- This audit did not modify production code.
