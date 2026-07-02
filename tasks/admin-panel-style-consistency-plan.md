# Shared Admin Panel Style Consistency Plan

## Objective

Create one reusable panel surface and header treatment for the production
Schema Editor (`/app/schemas`) and Pipeline editor
(`/app/admin/pipeline`). The change should align their visual hierarchy without
altering either workflow, API contract, persisted data, or page-specific
layout.

## Current Inconsistencies

- Schema panels use explicit borders and 8 px corners, while Pipeline panels
  use DaisyUI cards with shadows and larger default corners.
- Schema panel headings are explicitly `text-sm`; Pipeline panel headings use
  the larger inherited size.
- The two pages duplicate effectively identical header layout rules through
  `.schema-panel-header` and `.panel-header`.
- Header action groups do not share one wrapping and responsive contract.

## Design Standard

### Shared panel surface

Introduce `.admin-panel` in `web/static/css/app.css` with:

- flex-column layout;
- `min-width: 0` and `min-height: 0`;
- `1px` `--b3` border;
- `0.5rem` corner radius;
- `--b1` background;
- subtle `0 1px 2px` shadow using low-opacity `--bc`;
- no forced `overflow: hidden`, so focus rings, menus, and popovers are not
  clipped.

The shared surface controls only the outer container. Each page continues to
own its grid placement, body padding, scrolling, selected states, and preview
backgrounds.

### Shared panel header

Introduce these classes:

- `.admin-panel-header`: 56 px minimum height, flex layout, 16 px padding,
  12 px gap, bottom border, and space-between alignment.
- `.admin-panel-heading`: shrink-safe heading container with `min-width: 0`.
- `.admin-panel-title`: truncated 14 px semibold panel title.
- `.admin-panel-subtitle`: truncated 12 px muted supporting text.
- `.admin-panel-actions`: non-shrinking, wrapping action group with 8 px gaps.

Keep the application page title as the larger `h1`. The shared titles are
subordinate workspace headings and remain semantic `h2` elements.

### Responsive behavior

At the existing mobile breakpoint:

- allow `.admin-panel-header` to wrap and align content to the start;
- make `.admin-panel-actions` occupy the available row width;
- let buttons wrap naturally without forcing every button to full width;
- preserve the existing no-horizontal-overflow behavior at 390 px.

## Implementation Steps

1. Add the shared classes to `web/static/css/app.css` using the existing DaisyUI
   color variables; do not introduce a separate token system.
2. Migrate the three Schema Editor surfaces: schema list, schema detail, and
   YAML preview.
3. Migrate the Pipeline active, draft, editor, YAML preview, validation, and
   diff surfaces.
4. Apply `.admin-panel` to the Pipeline publish-sequence guide, but retain its
   compact body-only structure without adding a panel header.
5. Remove repeated surface utility classes from the migrated templates and
   remove `card` where it only supplied the old Pipeline surface treatment.
6. Retire `.schema-panel-header` after migration. Keep generic `.panel-header`
   for unrelated pages until they are reviewed separately.
7. Rebuild `web/static/css/vendor.css` with `npm run build:css` if template
   utility-class usage changes.

Do not create a Jinja macro in this change. The panels have different internal
structures, and shared CSS classes provide consistency without making template
composition harder.

## Out of Scope

- Workspace grid layouts and breakpoints beyond header wrapping.
- Schema field-card and Pipeline task-card designs.
- Reorder and destructive-action terminology or confirmation behavior.
- YAML preview heights and validation-result layouts.
- API, database, configuration, or persisted YAML changes.
- Prototype-only files under `pipeline_visual_editor_prototype/`.

## Testing

Add or update production UI regression coverage to verify:

- both pages use `.admin-panel` and `.admin-panel-header`;
- panel titles and subtitles use the shared classes;
- the old Schema-specific header class is no longer used by the Schema Editor;
- Pipeline page behavior and controls remain unchanged;
- desktop and 390 px layouts have no horizontal overflow;
- header actions wrap cleanly;
- focus outlines, drawers, menus, and validation content are not clipped;
- screenshots remain nonblank at desktop and mobile sizes.

Run:

```powershell
npm run build:css
.\.venv\Scripts\python.exe -m pytest -v test\visual\test_schema_editor_regressions.py test\visual\test_schema_review_visual.py
.\.venv\Scripts\python.exe -m pytest -v
```

## Acceptance Criteria

- Schema and Pipeline panels have identical computed background, border,
  radius, shadow, header height, and header padding.
- All migrated panel titles use the same font size, weight, and line height.
- Subtitles use the same muted treatment.
- Header actions do not overflow at 390 px.
- Existing keyboard order and focus visibility remain intact.
- No menus, drawers, popovers, or focus rings are clipped.
- No functional behavior or API contract changes.
- Focused visual tests and the full pytest suite pass.

