# Typography audit

## Audit scope

The visual pipeline editor overview, task properties, and pipeline YAML workspace at `http://127.0.0.1:5173/`.

## User goal and accessibility target

Match the production application's compact system-sans typography while improving hierarchy, control consistency, helper-text legibility, and code readability. The review checks visible UX and likely accessibility risks; it does not claim full WCAG compliance.

## Steps

1. **Before — editor overview** (`01-before.png`): Needs refinement. Page, section, and task text are too close in scale; essential metadata is frequently 11px.
2. **After — editor overview**: Implementation and DOM typography checks pass. Updated screenshot capture is pending because the in-app browser capture service timed out repeatedly.
3. **After — Pipeline YAML workspace**: DOM checks confirm a 16px workspace title, 14px tabs, 13px code, and approximately 20px code line-height. Updated screenshot capture is pending for the same reason.

## Strengths

- The editor now uses the same portable system-sans family as production.
- Page title, section titles, body text, labels, and helpers have distinct roles.
- Inputs, selects, and textareas consistently render at 14px with 20px line-height.
- YAML and diff content render at 13px with approximately 20px line-height.
- Meaningful interface text no longer uses the previous 11px treatment.

## UX risks addressed

- Raised section headings from 14px to 16px where stronger grouping is needed.
- Normalized inconsistent 12px, 14px, and 16px form-control text to 14px.
- Increased task metadata and grouping-label contrast.
- Increased the pipeline workspace footer to the 12px minimum.

## Accessibility risks and evidence limits

- Small supporting text now starts at 12px, but browser zoom and responsive reflow still require manual testing.
- Contrast was strengthened for small labels and metadata, but exact WCAG contrast ratios were not calculated in this pass.
- Keyboard semantics remain present in the inspected DOM, but this audit is scoped to typography rather than a complete keyboard-flow test.
- Final screenshot-based visual acceptance remains pending because the preferred capture surface could not save updated screenshots.
