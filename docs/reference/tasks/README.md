# Pipeline task reference

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

These pages describe exact task parameters, value shapes and failure contracts.
For task selection and setup through the app, start with the
[Admin task guide](../../admin/task-guide.md), which covers all approved
built-ins and their normal ordering.
Examples show portable task-definition content, not new runtime deployment YAML.
Use an app export for the complete transfer wrapper and select exact published
dependencies before execution. Common error/context/approval rules live in the
[canonical task standards](../../../tasks/standard_task_creation_guidelines.md).


Read in this order, or choose the task you need:

1. [LlamaCloud extraction](llamacloud-extraction.md)
2. [GLM-OCR extraction](glm-ocr-extraction.md)
3. [LiteParse extraction](liteparse-extraction.md)
4. [Cloud/manual split and continuation](splitting.md)
5. [Review gate](review-gate.md)
6. [Storage and archiving](storage-and-archiving.md)
7. [Rules, context and housekeeping](rules-context-housekeeping.md)

[All documentation](../../README.md)
