# Property pane UX audit — round 3

Scope: remaining task-property opportunities and the newly added Split task.

The existing panes did not provide five additional task-specific improvements without repeating earlier work. Split was therefore added through the task palette, moved to pipeline position 1, validated, and published to `public/config_sample_invoice.yaml`.

1. Uncategorized-page policy — replaced raw `include`/`forbid`/`omit` values with outcome-based labels and a sentence explaining the selected behavior.
2. Confidence failure policy — replaced three bare checkboxes with a grouped policy control that explains why a selected confidence level stops the split.
3. Unknown-category policy — renamed the switch and added live accepted/allowed-category guidance.
4. Category definition — grouped category inputs, clarified what the description controls, and added a live classification target preview.
5. Output path scope — added project-relative/absolute path feedback and explained that generated child PDFs are written to the selected directory.

Visual evidence: `01-split-before.png`, `02-split-after.png`, and `03-split-after-top.png`.

Interaction checks: the uncategorized policy, low-confidence policy, unknown-category switch, category preview, and path-scope indicator were each changed and restored. The final draft matches the published eight-step YAML and validation is ready.

Accessibility limits: the controls expose labels and state in the browser accessibility tree, but screenshot and browser inspection do not establish full keyboard, screen-reader, contrast, or zoom conformance.
