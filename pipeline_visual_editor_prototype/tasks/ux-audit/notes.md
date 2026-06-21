# Property pane UX audit

Scope: task selection and property editing in the visual pipeline editor at a 1265 px viewport.

1. Initial editor — usable task selection, but the extraction API key was exposed and field rows were compressed. Evidence: `01-initial.png`.
2. Extraction credentials — API keys are now masked by default with an accessible show/hide control. The value and YAML model remain unchanged.
3. Extraction fields — each field key now gets a full row; alias and type remain readable below it, and the three-column app layout no longer overflows the viewport. Evidence: `05-field-layout-improved.png`.
4. Review configuration — confidence is now expressed as a synchronized percentage and slider with a sentence describing the outcome. Review scope and resume behavior use readable labels and helper text while retaining the original YAML values. Evidence: `04-review-improved.png`.
5. Storage filenames — filename templates now have a live preview and searchable token list, reducing scanning when many extraction fields exist. Evidence: `03-storage-improved.png`.

Accessibility checks: new controls have explicit accessible names; the credential visibility and confidence controls were exercised by role/name locators. Screenshot review cannot establish full keyboard, screen-reader, contrast, or zoom conformance.
