# Earlier user-guide revision history

| Item | Value |
| --- | --- |
| Audience | Readers investigating historical evidence |
| Owner | Application maintainers |
| Status | Historical record |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Original checkpoint or snapshot documented below |

This table records revisions of the former combined guide. It was moved here
during the 2026-10-10 audience reorganisation. Version numbers identify that
guide's revisions, not independent application releases. See the
[exact original](../archive/2026-10-10/docs/user_guide.md).

## History of Changes

| Version | Date       | Author              | Description                                                                 |
|---------|------------|---------------------|-----------------------------------------------------------------------------|
| 1.0     | 2025-04-13 | PDF Processing System team | Initial user guide for fixed pipeline system                                |
| 2.0     | 2025-08-01 | PDF Processing System team | Redesigned to configurable task-based workflows via `config.yaml`; web TBD    |
| 2.1     | 2025-08-01 | PDF Processing System team | Added Quick Start guide, simplified explanations, expanded glossary, and improved configuration editing instructions for non-developers |
| 2.2     | 2025-08-01 | PDF Processing System team | Added YAML configuration examples to all 4.7.x subsections for clarity      |
| 2.3     | 2025-08-11 | PDF Processing System team | Implemented and documented web interface for PDF upload and status monitoring|
| 2.4     | 2025-08-20 | PDF Processing System team | Added config-check administrator overview and cross-references to validation docs |
| 2.5     | 2026-06-03 | PDF Processing System team | Updated for the unified operator and administrator interface, SQLite-backed workflow state, review, split, reports, settings, artifact registration, and legacy status endpoint compatibility |
| 2.6     | 2026-06-20 | PDF Processing System team | Updated role guidance, UI-led operator procedures, account recovery, failure handling, split policy explanations, v2 task examples, upload limits, and recovery guidance |
| 2.7     | 2026-06-21 | PDF Processing System team | Consolidated extraction and metadata storage under canonical module and class names while retaining Extract v2 array-of-objects behavior |
| 2.8     | 2026-06-28 | PDF Processing System team | Added typed scalar-list options and flat structured-object extraction with Pipeline editor, validation, review-schema mapping, and operator documentation |
| 2.9     | 2026-07-26 | PDF Processing System team | Documented SQLite-backed, immutable pipeline and review-schema versions, explicit upload selection, watch-folder bindings, exact-version execution, migration, recovery, and stored-definition validation |
| 3.0     | 2026-08-02 | PDF Processing System team | Completed the operator and administrator procedures for multi-pipeline routing, review forms, watch-folder bindings, outputs, validation, settings, audit visibility, and portable definitions; corrected remaining single-pipeline and task-behavior guidance |
| 3.1     | 2026-08-09 | PDF Processing System team | Documented GLM-OCR sensitivity to JSON Schema property order and prompt construction, with controlled-testing and review guidance |
| 3.2     | 2026-08-12 | PDF Processing System team | Documented generic multi-page GLM-OCR document resolution, resolver configuration, schema boundaries, and document-specific pipeline guidance |
| 3.3     | 2026-08-15 | PDF Processing System team | Added visual-editor guidance for multiline extraction values, labelled-block boundaries, adjacent-field exclusions, and focused regression testing |
| 3.4     | 2026-09-03 | PDF Processing System team | Documented the local PDF.js source viewer, provider-specific source-location behavior, and the GLM-OCR resolver context default of 18000 |
| 3.5     | 2026-09-03 | PDF Processing System team | Added upload transfer progress, text confidence bands, and concise screen-reader announcements for dynamic operator updates |
| 3.6     | 2026-09-04 | PDF Processing System team | Added keyboard-friendly upload activation, cancellable uploads, queue retry actions, consistent DaisyUI table styling, and lightweight contextual help |
| 3.7 | 2026-09-08 | PDF Processing System team | Added independent Watch folders management, lifecycle, explicit upgrades, diagnostics, and activity history. |
| 3.8 | 2026-09-27 | PDF Processing System team | Refreshed setup guidance, UI labels, logging, configuration references, and review-form administration instructions. |
| 3.9 | 2026-10-04 | PDF Processing System team | Added generic LiteParse + local Ollama extraction, nullable confidence, diagnostic citations, visual pipeline setup and six-invoice validation guidance. |
| 3.10 | 2026-10-07 | PDF Processing System team | Documented manual PDF splitting and its Review Queue workflow. |
| 3.11 | 2026-10-09 | PDF Processing System team | Retired the read-only Settings screen and documented application settings in Admin Overview and workflow configuration in Pipeline. |
| 3.12 | 2026-10-09 | PDF Processing System team | Documented independent pipeline archiving and processing-history cleanup, protected work, retained files/audits, SQLite space reuse, and draft-preserving metadata/availability saves. |
| 3.13 | 2026-10-09 | PDF Processing System team | Rewrote everyday work and administration around app screens; moved developer and IT instructions into a separate technical reference. |
