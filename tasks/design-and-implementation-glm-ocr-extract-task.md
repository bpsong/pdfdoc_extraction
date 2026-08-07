# Design and Implementation Plan: Local GLM-OCR Extraction Task

## Document status

| Item | Value |
| --- | --- |
| Purpose | Decision-complete, checkbox-based implementation plan |
| Audience | AI coding agents, reviewers, test owners, and maintainers |
| Governing standard | `tasks/standard_task_creation_guidelines.md` |
| Main outcome | Add a local Ollama/GLM-OCR structured extraction task without changing the existing LlamaCloud task's behavior |
| Completion rule | Complete only after all phases, live portal/watch-folder verification, documentation, and final audit pass |

## Strict provider isolation

- The existing LlamaCloud implementation remains independently owned by
  `standard_step/extraction/extract_pdf.py` and
  `standard_step/extraction/llama_cloud_v2.py`.
- The GLM-OCR implementation must not refactor, wrap, import into, or otherwise
  alter either existing LlamaCloud module.
- Provider-neutral in this plan means that GLM output follows the same external
  field/context contract; it does not mean that the two providers share runtime
  implementation code.
- Behavioral compatibility is proven by tests that compare outputs across the
  independent implementations.
- The new task remains `standard_step.extraction.glm_ocr_extract.GlmOcrExtractTask`
  and receives its own registry entry, validation, persistence orchestration,
  and visual properties editor.

## Execution rules

- Work phases in order and start from the next unchecked task.
- Mark a subtask `[x]` only after its code and required tests pass.
- Mark a phase `[x]` only after every subtask and its unit-test gate pass.
- Use `.\.venv\Scripts\python.exe` for every Python command.
- Preserve unrelated changes in the dirty worktree.
- Do not stage, commit, or discard changes unless explicitly requested.
- Keep the Relevant Files and Implementation Notes sections current.
- Mock Ollama in normal automated tests; run the live model only in the final visual phase.
- Follow `BaseTask`, `TaskError`, context preservation, SQLite persistence,
  approval-registry, and logging rules from the standard-task guideline.
- Do not log or persist raw PDF images, raw model responses, extracted customer
  values, or full prompts in task-run errors.

## Design decisions

### New task identity

- Module: `standard_step.extraction.glm_ocr_extract`
- Class: `GlmOcrExtractTask`
- Registry key: `glm_ocr_extract`
- Provider value: `glm_ocr_ollama`
- Display purpose: "Extract structured PDF data with local GLM-OCR"

### Task parameters

```yaml
module: standard_step.extraction.glm_ocr_extract
class: GlmOcrExtractTask
params:
  ollama_host: http://127.0.0.1:11434
  model: glm-ocr:latest
  document_instructions: ""
  dpi: 216
  num_ctx: 8192
  num_predict: 2048
  timeout_seconds: 300
  fields: {}
```

Rules:

- `fields` uses the existing extraction field contract.
- Scalar, scalar-array, flat object, and one array-of-objects table are supported.
- Field keys become JSON and context keys.
- Aliases and descriptions guide the prompt but do not replace field keys.
- `temperature` is fixed at zero and is not an administrator setting.
- The task does not start Ollama automatically.
- Ollama-unavailable and model-not-installed failures raise redacted `TaskError`
  messages with operator instructions.
- Full `glmocr[selfhosted]` and PP-DocLayout are out of scope for the first release.

### Extraction behavior

- Render PDF pages in memory with PyMuPDF.
- Make one scalar/object schema call per page when scalar or object fields exist.
- Make one separate table-focused schema call per page when a table field exists.
- Use permissive page schemas so absent page-level fields are not forced.
- Use a strict final schema with required fields after page results are merged.
- Use `additionalProperties: false` for configured objects.
- Embed the schema and configured extraction guidance in each prompt.
- Merge scalars and object children deterministically, retain the first non-empty
  value, and record later conflicts in safe metadata.
- Concatenate table rows across pages and deduplicate normalized identical rows.
- Preserve every configured top-level key in the final result; use `None` when no
  usable value was extracted so review corrections can update an existing SQLite
  field row.
- Treat model-shape or field-validation findings as reviewable extraction quality
  unless the response cannot be parsed at all.
- Runtime failures, PDF rendering failures, invalid JSON, or invalid response
  envelopes fail the task.

### Confidence and review behavior

- Persist `confidence = NULL` and `confidence_label = NULL`.
- Do not manufacture a numerical confidence or confidence threshold.
- The task adds a structured review flag:

```json
{
  "glm_ocr_unscored": {
    "reason": "unscored_extraction",
    "field_keys": ["all", "configured", "top_level_fields"]
  }
}
```

- The review gate consumes this provider-neutral structured flag, pauses the
  workflow, highlights all listed fields, and marks them as requiring review.
- If no review gate exists in the pipeline, the flag does not pause execution
  and downstream storage runs normally.
- The review gate continues supporting existing boolean/list business flags.
- The review form exposes all configured GLM-OCR fields, including missing values
  and arrays of objects, for correction.
- Review completion writes corrected `final_value_json` values and resumes at the
  next task.

### Persistence and downstream behavior

- Store the complete normalized object in `extraction_results.data_json`.
- Store one `extracted_fields` row for every configured top-level field.
- Store arrays and objects as JSON values in their top-level field rows.
- Store only safe execution metadata: model, host classification, page count,
  timings, call strategy, schema hash, prompt hash, source page numbers,
  validation findings, and conflicts.
- Update `context["data"]` without discarding existing values.
- Merge GLM metadata under its own `context["metadata"]` child instead of
  replacing unrelated metadata.
- CSV storage expands the configured object array to one row per item and repeats
  top-level scalar values.
- No database migration is required.

### Separate visual properties editor

- Add a dedicated `glmOcrExtractControls(step)` renderer.
- Dispatch `GlmOcrExtractTask` to that renderer before the generic
  extraction/LlamaCloud renderer.
- Leave `extractControls(step)` and its LlamaCloud modes unchanged.
- Reuse low-level UI helpers for text boxes, numeric controls, required toggles,
  type dropdowns, object children, and array-of-object row definitions.
- Do not share LlamaCloud provider-mode state, API-key fields, configuration IDs,
  tiers, citations, or confidence controls with GLM-OCR.
- Display a visible notice that GLM-OCR supplies no field confidence and that
  adding a review gate causes every configured field to require operator review.

## Acceptance criteria

- Administrators can add and configure the GLM-OCR task independently of
  LlamaCloud Extract.
- Existing LlamaCloud pipelines and visual editing behave exactly as before.
- A dynamically configured scalar/object/table schema is sent to local GLM-OCR.
- Extracted data uses configured field keys and types.
- Every configured top-level field is persisted, including missing values.
- A following review gate pauses and exposes every GLM-OCR field.
- Omitting the review gate allows direct downstream storage.
- Review corrections survive resume and are used by CSV/JSON storage.
- Portal upload and watch-folder ingestion both complete using different real
  SuperStore invoice PDFs.
- At least one CSV export contains one row per extracted invoice line item.
- No live GLM-OCR dependency is introduced into the default automated test suite.

## Phase dependency map

```text
1 -> 2 -> 3 -> 4 -> 5
4 + 5 -> 6
2 + 4 + 6 -> 7
5 + 6 + 7 -> 8
1-8 -> 9
9 -> 10
```

## Relevant Files

Keep this section updated during implementation.

### Expected new files

- `standard_step/extraction/structured_fields.py`
- `standard_step/extraction/glm_ocr_prompt.py`
- `standard_step/extraction/glm_ocr_adapter.py`
- `standard_step/extraction/glm_ocr_extract.py`
- `test/extraction/test_structured_fields.py`
- `test/extraction/test_glm_ocr_prompt_schema.py`
- `test/extraction/test_glm_ocr_adapter.py`
- `test/extraction/test_glm_ocr_extract.py`
- `test/integration/test_glm_ocr_pipeline.py`
- `test/visual/test_glm_ocr_pipeline_editor.py`
- `test/fixtures/glm_ocr_pipeline.yml`

### Expected existing areas

- `modules/db/connection.py` and `modules/db/repositories.py` for explicit-null
  extraction-field value persistence.
- `modules/services/task_registry_service.py` and task catalog tests.
- `modules/services/pipeline_template_service.py` and pipeline/config-check
  validation tests.
- `standard_step/review/review_gate.py`, review service tests, and resume tests.
- `modules/workflow_manager.py` and split-child preflight tests.
- `tools/config_check/parameter_validator.py`.
- `tasks/standard_task_creation_guidelines.md` for the structured review-flag
  context contract established in Phase 5.
- `web/static/js/pipeline_config.js` for the separate GLM-OCR renderer,
  dedicated defaults, and exact-class dispatch only.
- `web/static/css/app.css` and `web/static/css/vendor.css` for the GLM-only
  aligned, container-responsive field editor and rebuilt frontend utilities.
- `web/templates/pipeline_config.html` and
  `test/visual/test_schema_editor_regressions.py` for distinct template/publish
  guide grid rows and overlap regression coverage.
- `test/pipeline_visual_editor_prototype/test_production_parameter_parity.py`
  for GLM parameter coverage without changing existing renderer expectations.
- `test/integration/test_extraction_results_api.py` for safe GLM provider
  presentation through the extraction-results API.
- `test/integration/test_versioned_pipeline_api.py` for administrator-only GLM
  pipeline publication coverage.
- CSV storage and versioned workflow integration tests; the production CSV and
  JSON storage task implementations remain unchanged.
- Architecture, user, troubleshooting, and standard-task documentation.
- `tools/config_check/README.md` and
  `tools/config_check/examples/ERROR_CODES.md` for GLM parameter examples and
  actionable validation codes.
- `requirements.txt`.

### Protected existing LlamaCloud files

The following files must remain unmodified by the GLM-OCR implementation:

- `standard_step/extraction/extract_pdf.py`
- `standard_step/extraction/llama_cloud_v2.py`

---

## Phase 1 - Baseline, dependencies, and shared extraction contract

- [x] **Phase 1 complete**

**Main task:** Establish a regression baseline and provider-neutral
structured-field foundation.

**Prerequisites:** This plan is accepted for implementation.

**Exit criterion:** Shared helpers exist, Llama behavior is unchanged,
dependencies are healthy, and Phase 1 tests pass.

- [x] **1.1 Record the baseline**
  - [x] Capture `git status --short`.
  - [x] Record pre-existing failures under Implementation Notes.
  - [x] Confirm Ollama is not required for baseline tests.
  - [x] Confirm existing LlamaCloud schema, persistence, review, storage, and
    pipeline-editor tests pass.

- [x] **1.2 Add direct runtime dependencies**
  - [x] Add `ollama==0.6.2` to `requirements.txt`.
  - [x] Add `PyMuPDF==1.28.0` to `requirements.txt`.
  - [x] Add a direct compatible `jsonschema` dependency if final-schema
    validation uses it.
  - [x] Do not add `glmocr[selfhosted]`.
  - [x] Run `pip check` after installation.

- [x] **1.3 Introduce provider-neutral field helpers**
  - [x] Implement GLM-owned type parsing, schema construction, alias lookup,
    object normalization, and table normalization in `structured_fields.py`.
  - [x] Preserve existing LlamaCloud source code, schema output, and
    normalization behavior without importing the new helpers into LlamaCloud.
  - [x] Support strict-object generation as an opt-in GLM mode.
  - [x] Compare the independent GLM helpers with existing public LlamaCloud
    behavior in regression tests; do not add compatibility re-exports.
  - [x] Add typed result/finding structures for normalized fields.

- [x] **1.4 Complete Phase 1 unit-test gate**
  - [x] Add regression coverage proving LlamaCloud schema output is unchanged.
  - [x] Test scalar, optional, scalar-list, object, and object-array type parsing.
  - [x] Test alias-versus-key lookup and newline normalization.
  - [x] Test strict-object mode separately from LlamaCloud compatibility mode.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\extraction\test_llama_cloud_v2_schema.py `
  test\extraction\test_extract_pdf_edge_cases.py `
  test\extraction\test_structured_fields.py
```

---

## Phase 2 - Dynamic GLM schema and prompt generation

- [x] **Phase 2 complete**

**Main task:** Convert visual field configuration into deterministic GLM-OCR
schemas and prompts.

**Prerequisites:** Phase 1 complete.

**Exit criterion:** Every supported visual field definition produces stable,
valid GLM schemas and focused prompts.

- [x] **2.1 Build canonical and page schemas**
  - [x] Generate the final canonical schema with configured required fields.
  - [x] Generate per-page schemas without top-level required fields.
  - [x] Keep required child properties for emitted object/table rows.
  - [x] Add `additionalProperties: false` to configured objects.
  - [x] Generate a scalar/object schema and a separate table schema.
  - [x] Reject more than one configured table.

- [x] **2.2 Build scalar/object prompts**
  - [x] Include exact field keys, aliases, types, required state, and guidance.
  - [x] Include document-level instructions.
  - [x] Instruct the model not to invent values.
  - [x] Preserve leading zeros for string identifiers.
  - [x] Require numbers without currency symbols or separators.
  - [x] Include the schema text to ground structured output.

- [x] **2.3 Build table prompts**
  - [x] Describe the logical table and every item field.
  - [x] Require one object per logical row.
  - [x] Exclude headers, footers, subtotals, blank rows, and duplicates unless
    explicitly configured.
  - [x] Require values from one visual row to remain in the same object.
  - [x] Keep the configured table key as the response property.

- [x] **2.4 Complete Phase 2 unit-test gate**
  - [x] Test deterministic schema and prompt generation.
  - [x] Test required/optional top-level and child behavior.
  - [x] Test scalar-only, object-only, table-only, and mixed configurations.
  - [x] Test prompt escaping and Unicode guidance.
  - [x] Test that prompts contain no runtime document values.
  - [x] Test rejection of multiple tables and malformed field definitions.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\extraction\test_structured_fields.py `
  test\extraction\test_glm_ocr_prompt_schema.py
```

---

## Phase 3 - Ollama/GLM-OCR adapter

- [x] **Phase 3 complete**

**Main task:** Implement a testable local inference adapter without workflow or
persistence responsibilities.

**Prerequisites:** Phase 2 complete.

**Exit criterion:** The adapter can render, call, parse, validate, and merge
documents using only mocked Ollama during automated testing.

- [x] **3.1 Implement in-memory PDF rendering**
  - [x] Open PDFs through PyMuPDF.
  - [x] Render pages at configured DPI into in-memory PNG bytes.
  - [x] Use Windows-long-path handling.
  - [x] Close documents and release page/image resources on success and failure.
  - [x] Reject missing, unreadable, empty, or invalid PDFs with safe errors.

- [x] **3.2 Implement native Ollama calls**
  - [x] Construct an injectable Ollama client using `ollama_host` and
    `timeout_seconds`.
  - [x] Use `model`, image bytes, prompt, `format=schema`, and `stream=False`.
  - [x] Use fixed temperature zero plus configured `num_ctx` and `num_predict`.
  - [x] Validate service availability and model presence.
  - [x] Do not start or stop Ollama from task code.
  - [x] Do not add provider-level retries; rely on the workflow runner's retry.

- [x] **3.3 Implement page orchestration**
  - [x] Run scalar/object calls only when those fields exist.
  - [x] Run separate table calls only when a table exists.
  - [x] Parse response JSON strictly.
  - [x] Detect incomplete/token-length responses.
  - [x] Record safe call timing, page number, call type, and completion reason.

- [x] **3.4 Implement deterministic merging**
  - [x] Merge scalar and object values by first non-empty value.
  - [x] Record conflicting later values without logging their raw contents.
  - [x] Concatenate and deduplicate table rows.
  - [x] Associate top-level fields with contributing source page numbers.
  - [x] Validate the merged object against the canonical schema.
  - [x] Return partial structured data plus findings when values are missing or
    type-invalid.
  - [x] Fail when no response can be parsed into a structured object.

- [x] **3.5 Complete Phase 3 unit-test gate**
  - [x] Mock the Ollama client; do not require a live server.
  - [x] Test request payloads for scalar and table calls.
  - [x] Test one-page and multi-page orchestration.
  - [x] Test service unavailable, missing model, timeout, malformed JSON,
    truncated output, and invalid PDF.
  - [x] Test scalar conflicts, object merging, table concatenation, and
    deduplication.
  - [x] Test resource cleanup after exceptions.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\extraction\test_glm_ocr_adapter.py
```

---

## Phase 4 - `GlmOcrExtractTask` and SQLite persistence

**Main task:** Create the approved `BaseTask` implementation and
provider-neutral output contract.

**Prerequisites:** Phase 3 complete.

**Exit criterion:** The task follows the standard-task contract and produces
complete provider-neutral SQLite/context output.

- [x] **4.1 Create the task class**
  - [x] Inherit directly from `BaseTask`.
  - [x] Keep `__init__` side-effect free.
  - [x] Load only constructor parameters supplied by the versioned pipeline.
  - [x] Implement `on_start`, `validate_required_fields`, and `run`.
  - [x] Validate field count, one-table limit, host, model, numeric options, and
    `context["file_path"]`.
  - [x] Preserve workflow-owned context keys.

- [x] **4.2 Normalize task output**
  - [x] Ensure every configured top-level key exists in `processed_data`.
  - [x] Use `None` for missing scalar, object, or table values.
  - [x] Update rather than replace `context["data"]`.
  - [x] Add GLM metadata under a dedicated metadata child.
  - [x] Append the structured `glm_ocr_unscored` review flag without
    overwriting existing flags.

- [x] **4.3 Persist extraction state**
  - [x] Save one `extraction_results` row with provider `glm_ocr_ollama`.
  - [x] Save one `extracted_fields` row per configured top-level field.
  - [x] Persist confidence and confidence label as `NULL`.
  - [x] Keep initial `requires_review` false; the review gate owns the transition.
  - [x] Store page/source evidence and safe validation details in `source_json`.
  - [x] Set `context["extraction_result_id"]`.
  - [x] Do not create an artifact because the task creates no durable file.

- [x] **4.4 Implement task failure behavior**
  - [x] Translate Ollama connection, missing-model, PDF, timeout, and protocol
    failures to redacted `TaskError`.
  - [x] Call `register_error` consistently.
  - [x] Add provider-specific but non-sensitive `fatal_failure` guidance.
  - [x] Never place raw responses, images, prompts, extracted values, or host
    credentials in errors.

- [x] **4.5 Complete Phase 4 unit-test gate**
  - [x] Test initialization and validation.
  - [x] Test success with scalar, object, table, missing, and conflicting values.
  - [x] Test context preservation and review-flag merging.
  - [x] Test SQLite result and field rows.
  - [x] Test null confidence and safe source metadata.
  - [x] Test expected and unexpected failures.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\extraction\test_glm_ocr_extract.py `
  test\extraction\test_extraction_sqlite_persistence.py
```

---

## Phase 5 - Mandatory all-field review integration

**Main task:** Make structured unscored review flags pause and expose all GLM
fields only when a review gate exists.

**Prerequisites:** Phase 4 complete.

**Exit criterion:** A downstream review gate reliably requires operator review
of every configured GLM field, while gate-free pipelines continue normally.

- [x] **5.1 Extend review-flag handling**
  - [x] Preserve existing list and boolean-map review flags.
  - [x] Accept structured flag entries containing a reason and field-key list.
  - [x] Add a business-rule reason for the unscored extraction.
  - [x] Add every listed field to `highlight_fields`.
  - [x] Mark every listed field `requires_review` when the gate runs.
  - [x] Ensure document and low-confidence review scopes allow all highlighted
    GLM fields to be edited.

- [x] **5.2 Preserve conditional gate behavior**
  - [x] Verify a pipeline without a review gate continues directly to storage.
  - [x] Verify no stale `requires_review` state is created without a gate.
  - [x] Verify a following gate pauses regardless of numeric threshold settings.
  - [x] Verify missing configured values appear and can be corrected.
  - [x] Verify corrected object arrays reconstruct correctly on resume.

- [x] **5.3 Complete Phase 5 unit-test gate**
  - [x] Test structured review flags alone and alongside legacy flags.
  - [x] Test all-field highlighting and persistence.
  - [x] Test a GLM result with required and optional fields.
  - [x] Test review correction and resume-context reconstruction.
  - [x] Test ordinary LlamaCloud confidence behavior is unchanged.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\standard_step\review\test_review_gate.py `
  test\services\test_review_service.py `
  test\services\test_resume_manager.py
```

---

## Phase 6 - Registration, validation, and workflow-provider separation

**Main task:** Make the new task publishable and remove LlamaCloud assumptions
from provider-neutral extraction classification.

**Prerequisites:** Phases 4 and 5 complete.

**Exit criterion:** GLM is an approved, publishable extraction task with
provider-correct validation and preflight behavior.

- [x] **6.1 Register the task**
  - [x] Add the exact module/class pair to `BUILTIN_TASKS`.
  - [x] Ensure the task catalog imports and displays it.
  - [x] Add registry-coverage tests for the new `BaseTask` subclass.
  - [x] Confirm custom-task approval rules remain unchanged.

- [x] **6.2 Add GLM parameter validation**
  - [x] Validate non-empty model and well-formed HTTP(S) Ollama host.
  - [x] Reject URLs with embedded credentials.
  - [x] Validate positive DPI, context, prediction, and timeout settings.
  - [x] Reuse shared extraction-field validation.
  - [x] Do not require `api_key` or `configuration_id`.
  - [x] Reject or report LlamaCloud-only parameters on the GLM task.
  - [x] Keep LlamaCloud credential validation unchanged for `ExtractPdfTask`.

- [x] **6.3 Generalize pipeline extraction-field discovery**
  - [x] Allow review-schema compatibility checks to obtain fields from either
    approved extraction class.
  - [x] Keep singleton extraction-task ordering rules.
  - [x] Ensure CSV's field-reuse behavior recognizes the GLM task.
  - [x] Preserve exact published task parameters.

- [x] **6.4 Correct split-child preflight**
  - [x] Restrict LlamaCloud access preflight to its exact task module/class.
  - [x] Ensure GLM extraction after a split does not call LlamaCloud preflight.
  - [x] Let the GLM task validate its own runtime availability.
  - [x] Keep existing source-level LlamaCloud failure behavior unchanged.

- [x] **6.5 Complete Phase 6 unit-test gate**
  - [x] Test task registry and catalog entries.
  - [x] Test valid and invalid GLM parameters.
  - [x] Test GLM fields satisfy review-schema compatibility checks.
  - [x] Test Llama credentials remain mandatory only for Llama tasks.
  - [x] Test split-child dispatch for Llama and GLM extractors.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\services\test_task_registry_service.py `
  test\services\test_task_catalog_service.py `
  test\services\test_pipeline_template_service.py `
  test\tools\config_check\test_parameter_validator.py `
  test\workflow\test_workflow_manager.py
```

---

## Phase 7 - Separate production visual properties editor

**Main task:** Add an independent GLM-OCR properties form while reusing only
neutral field-editor primitives.

**Prerequisites:** Phases 2, 4, and 6 complete.

**Exit criterion:** GLM has a distinct, testable properties form and the
existing LlamaCloud form is unaffected.

- [x] **7.1 Add dedicated task dispatch**
  - [x] Dispatch `GlmOcrExtractTask` to `glmOcrExtractControls`.
  - [x] Perform this check before generic `.extraction.` dispatch.
  - [x] Leave `extractControls` unchanged.
  - [x] Keep GLM out of `providerModes` and saved/inline Llama state.

- [x] **7.2 Build GLM runtime controls**
  - [x] Add Ollama host and model controls.
  - [x] Add document instructions.
  - [x] Add DPI, context length, prediction length, and timeout controls.
  - [x] Add inline validation findings.
  - [x] Add the unscored/all-field-review explanatory notice.
  - [x] Do not show API key, Llama configuration ID, tier, citations, project,
    organization, or confidence controls.

- [x] **7.3 Reuse structured-field controls**
  - [x] Reuse field key, alias, guidance, type, and required controls.
  - [x] Reuse object-child editing.
  - [x] Reuse array-of-object row editing.
  - [x] Preserve the one-table constraint.
  - [x] Ensure changing GLM fields does not mutate a Llama task or another task.
  - [x] Ensure CSV field override can copy definitions from GLM.

- [x] **7.4 Add editor defaults and summaries**
  - [x] Add default GLM parameters.
  - [x] Display model, host, field count, and table status without exposing
    sensitive data.
  - [x] Keep existing Llama defaults and summaries unchanged.
  - [x] Use production files under `web/`; do not implement only in the prototype.

- [x] **7.5 Complete Phase 7 unit-test gate**
  - [x] Add source/DOM regression tests proving separate renderer dispatch.
  - [x] Test the absence of Llama controls in the GLM form.
  - [x] Test the presence of scalar, object, and table controls.
  - [x] Test task parameter parity.
  - [x] Test existing Llama editor markup and defaults remain unchanged.
  - [x] Rebuild CSS only if Tailwind classes or CSS sources change.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\pipeline_visual_editor_prototype\test_production_parameter_parity.py `
  test\visual\test_schema_editor_regressions.py `
  test\visual\test_glm_ocr_pipeline_editor.py `
  test\services\test_task_catalog_service.py
```

- [x] If frontend utility classes or CSS changed, run: (not applicable; no CSS changed)

```powershell
npm run build:css
```

---

## Phase 8 - Workflow, review, resume, and CSV integration

**Main task:** Prove the complete provider-neutral lifecycle with mocked Ollama.

**Prerequisites:** Phases 5, 6, and 7 complete.

**Exit criterion:** Mocked upload and watch-folder workflows both complete
through mandatory review and CSV resume, and gate-free execution also works.

- [x] **8.1 Add a representative pipeline fixture**
  - [x] Configure GLM extraction with SuperStore invoice scalar fields.
  - [x] Configure one `line_items` object array.
  - [x] Attach a pinned review-schema version with matching keys and types.
  - [x] Add `ReviewGateTask`.
  - [x] Add `StoreMetadataAsCsv`.
  - [x] Ensure the CSV task obtains the GLM field definitions.

- [x] **8.2 Test upload-path execution**
  - [x] Ingest a synthetic PDF through the upload service.
  - [x] Mock GLM structured output.
  - [x] Verify task-run completion and SQLite provider metadata.
  - [x] Verify every field reaches review with null confidence.
  - [x] Apply corrections and complete review.
  - [x] Verify resume starts at CSV storage.
  - [x] Verify one CSV row per line item and registered `export_csv` artifact.

- [x] **8.3 Test watch-folder execution**
  - [x] Bind a temporary watch folder to the published pipeline version.
  - [x] Ingest a different synthetic PDF through `WatchFolderCoordinator`.
  - [x] Verify assignment and pinned pipeline identity.
  - [x] Verify review, correction, resume, and CSV output.
  - [x] Verify upload and watch runs do not share context or output paths.

- [x] **8.4 Test gate-free execution**
  - [x] Publish a GLM-to-CSV pipeline without a review gate.
  - [x] Verify the unscored flag does not pause execution.
  - [x] Verify CSV uses extracted values directly.
  - [x] Verify no review item or stale review requirement is created.

- [x] **8.5 Complete Phase 8 unit/integration gate**
  - [x] Test extraction-results API redaction and provider presentation.
  - [x] Test CSV array expansion with GLM field aliases.
  - [x] Test pinned version execution.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\integration\test_glm_ocr_pipeline.py `
  test\integration\test_extraction_results_api.py `
  test\storage\test_storage_csv.py `
  test\workflow\test_versioned_workflow_execution.py `
  test\services\test_watch_folder_coordinator.py
```

---

## Phase 9 - Security, regression, and live-readiness gate

**Main task:** Establish that the change is safe, backward-compatible, and
ready for live visual testing.

**Prerequisites:** Phases 1-8 complete.

**Exit criterion:** The full automated suite passes or only documented
pre-existing failures remain, and the implementation is cleared for live testing.

- [x] **9.1 Review security and operational behavior**
  - [x] Confirm Ollama URLs cannot contain embedded credentials.
  - [x] Confirm no API key is required or persisted for GLM.
  - [x] Confirm raw images, prompts, responses, and extracted values are absent
    from errors and task-run summaries.
  - [x] Confirm task parameters are not copied wholesale into context or SQLite.
  - [x] Confirm only administrators can publish the new task configuration.
  - [x] Confirm same-origin PDF preview and existing security headers are unchanged.

- [x] **9.2 Run configuration validation**
  - [x] Validate a representative GLM pipeline through config-check.
  - [x] Validate a published GLM pipeline through the shared validator.
  - [x] Verify missing model, malformed URL, invalid fields, and multiple tables
    produce actionable findings.
  - [x] Verify a LlamaCloud pipeline still requires its API key.

- [x] **9.3 Run focused regression suites**
  - [x] Run all extraction tests.
  - [x] Run review, storage, workflow, registry, catalog, and config-check tests.
  - [x] Run production editor visual/static tests.
  - [x] Run `pip check`.

- [x] **9.4 Run full regression**
  - [x] Run the complete pytest suite.
  - [x] Record unrelated/pre-existing failures.
  - [x] Review the diff for accidental files, credentials, raw extraction output,
    local databases, PDFs, screenshots, and generated runtime state.
  - [x] Confirm no live GLM call occurs during the full suite.

- [x] **9.5 Complete Phase 9 test gate**
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\extraction
.\.venv\Scripts\python.exe -m pytest -v `
  test\standard_step\review `
  test\storage `
  test\services\test_task_registry_service.py `
  test\services\test_task_catalog_service.py `
  test\tools\config_check\test_parameter_validator.py `
  test\workflow\test_workflow_manager.py
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pip check
```

---

## Phase 10 - Live administrator visual testing, documentation, and final audit

**Main task:** Use the real application and local GLM-OCR as an administrator,
then document verified behavior.

**Prerequisites:** Phase 9 complete.

**Exit criterion:** An administrator has visually created and published the
pipeline, processed two different real invoices through portal and watch-folder
ingestion, reviewed every field, produced two CSV artifacts, and the final
documentation matches verified behavior.

- [x] **10.1 Prepare the live environment**
  - [x] Confirm `glm-ocr:latest` is installed.
  - [x] Start Ollama if it is not already running.
  - [x] Verify the native API and one harmless model request.
  - [x] Start the application with isolated test paths and a dedicated SQLite
    database.
  - [x] Use an unused local port and synthetic administrator account.
  - [x] Keep evidence in an ignored test-output directory.
  - [x] Do not use or modify a customer/runtime production database.

- [x] **10.2 Create the review form visually**
  - [x] Sign in as administrator.
  - [x] Create and publish a SuperStore invoice review form containing:
    - [x] `row_id` - string, required.
    - [x] `order_date` - string, required.
    - [x] `ship_mode` - string, required.
    - [x] `customer_name` - string, required.
    - [x] `ship_to_address` - string, required.
    - [x] `order_id` - string, required.
    - [x] `invoice_subtotal` - number, required.
    - [x] `discount_percent` - number, optional.
    - [x] `shipping_fee` - number, required.
    - [x] `total_amount_payable` - number, required.
    - [x] `line_items` - required array of objects.
    - [x] Row properties: `product_name`, `sub_category`, `category`,
      `product_id`, `quantity`, `unit_cost`, and `subtotal`.

- [x] **10.3 Create and publish the pipeline visually**
  - [x] Create a new pipeline template.
  - [x] Add `GlmOcrExtractTask`.
  - [x] Confirm its properties form is separate from LlamaCloud Extract.
  - [x] Configure Ollama host, model, instructions, runtime settings, scalar
    fields, and `line_items`.
  - [x] Confirm array-of-object editing uses the reused row-field editor.
  - [x] Add `ReviewGateTask` and select the exact review-form version.
  - [x] Set review scope to the entire document.
  - [x] Add `StoreMetadataAsCsv` with an isolated output directory and
    collision-safe filename.
  - [x] Validate and publish the pipeline.
  - [x] Capture desktop and narrow-width GLM properties screenshots.
  - [x] Capture the published GLM Extract -> Review Gate -> CSV pipeline.

- [x] **10.4 Run the portal-upload live trigger**

  Use:

  ```text
  sample stock invoices from internet\invoice_Steven Ward_9240.pdf
  ```

  - [x] Select the newly published pipeline in the upload portal.
  - [x] Upload the PDF.
  - [x] Follow processing until it enters the review queue.
  - [x] Open and claim the review item.
  - [x] Confirm all configured fields are highlighted/editable despite missing
    confidence.
  - [x] Compare every scalar and line-item value with the PDF preview.
  - [x] Correct inaccurate or missing values.
  - [x] Complete review and confirm pipeline resume.
  - [x] Confirm CSV output is created and registered.
  - [x] Verify one CSV row per line item with repeated invoice-level values.
  - [x] Confirm provider `glm_ocr_ollama` and null confidence in SQLite.
  - [x] Capture upload, processing, review, and export evidence.

- [x] **10.5 Run the watch-folder live trigger**

  Use a different invoice:

  ```text
  sample stock invoices from internet\invoice_Tamara Chand_41648.pdf
  ```

  - [x] Create a dedicated watch-folder binding visually against the exact
    published pipeline version.
  - [x] Copy the invoice into the bound watch folder.
  - [x] Observe the document through the administration and processing UI.
  - [x] Confirm watch-folder assignment and pinned pipeline version.
  - [x] Open and claim its separate review item.
  - [x] Review every scalar and line-item value.
  - [x] Correct values if necessary and complete review.
  - [x] Confirm a separate CSV artifact is produced.
  - [x] Confirm no context, extraction rows, review item, or CSV path was reused
    from the portal upload.
  - [x] Capture watch binding, ingestion, review, and CSV evidence.

- [x] **10.6 Enforce the unique-invoice rule for retries**
  - [x] Never trigger a previously used PDF again during this visual run.
  - [x] Do not use a file whose name begins with `random_merged`.
  - [x] If another trigger is required, use the next unused file in this order:
    1. `invoice_Sue Ann Reed_10365.pdf`
    2. `invoice_Suzanne McNair_2725.pdf`
    3. `invoice_Tamara Chand_25931.pdf`
    4. `invoice_Steven Roelle_14184.pdf`
  - [x] Record every triggered filename and outcome under Implementation Notes.

- [x] **10.7 Complete visual and accessibility checks**
  - [x] Verify the GLM form at desktop, tablet, and mobile widths.
  - [x] Verify labels, help text, validation, focus order, keyboard navigation,
    and accessible control names.
  - [x] Verify long model/host values do not overflow.
  - [x] Verify object-array editing remains usable on narrow screens.
  - [x] Verify review represents missing confidence without a fake percentage.
  - [x] Verify no secret or raw provider payload appears in the UI.
  - [x] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v `
  test\visual\test_glm_ocr_pipeline_editor.py `
  test\visual\test_schema_editor_regressions.py `
  test\visual\test_schema_review_visual.py
```

- [x] **10.8 Update maintained documentation**
  - [x] Update `docs/design_architecture.md` with the provider-neutral
    extraction flow, structured review flag, and local runtime boundary.
  - [x] Update `docs/user_guide.md` with Ollama prerequisites, task parameters,
    visual configuration, no-confidence review behavior, portal/watch operation,
    and CSV expansion.
  - [x] Update `docs/config_check_troubleshooting.md` with local-provider errors.
  - [x] Update `tools/config_check/README.md` and examples for GLM parameters.
  - [x] Update `tasks/standard_task_creation_guidelines.md` because structured
    review flags establish a shared task/review contract.
  - [x] Keep this plan's Relevant Files and Implementation Notes accurate.
  - [x] Do not document PP-DocLayout, confidence, citations, or automatic Ollama
    startup as implemented.

- [x] **10.9 Perform the final verification and audit**
  - [x] Rerun GLM, review, storage, registry, config, and visual unit tests.
  - [x] Rerun the full suite if code changed while resolving visual findings.
  - [x] Review the final diff for secrets, raw output, sample-PDF copies,
    databases, generated CSV files, logs, and misplaced screenshots.
  - [x] Confirm both live documents reached terminal completion after review and
    produced distinct CSV artifacts.
  - [x] Confirm the LlamaCloud editor and extraction tests remain passing.
  - [x] Mark Phase 10 and the overall plan complete only after evidence is recorded.

## Phase 11 - Generic scalar-completeness correction and insurance regression

**Main task:** Correct the GLM-only per-page schema contract discovered during
live testing, then prove the generic behavior against both SuperStore and
insurance invoices without adding template-specific extraction code.

**Prerequisites:** Phase 10 complete and local Ollama running.

**Exit criterion:** Required scalar values are populated by live GLM-OCR for
both document formats, every page response has a consistent required-nullable
contract, review remains mandatory when configured, and downstream metadata
export completes after review.

- [x] **11.1 Correct GLM page-schema and prompt semantics**
  - [x] Require every configured scalar/object key in each page response.
  - [x] Allow every page-level value to be null because a value may be located
    on another page.
  - [x] Preserve nested object and table-row shape while allowing page absence.
  - [x] Require the table property and use an empty array when no rows are visible.
  - [x] Replace omit-if-absent instructions with return-every-key/null-if-absent.
  - [x] Keep the shared LlamaCloud schema implementation unchanged.

- [x] **11.2 Add automated regression coverage**
  - [x] Test required-nullable scalar, object, list, and table page schemas.
  - [x] Test prompt/schema consistency for missing values and empty tables.
  - [x] Test multi-page null merging and the existing two-calls-per-page contract.
  - [x] Run focused extraction/integration tests, the full suite, and Pyright.

- [x] **11.3 Retest the SuperStore GLM pipeline visually**
  - [x] Trigger a new unused, non-merged SuperStore invoice through the portal.
  - [x] Confirm header values and totals are populated before operator edits.
  - [x] Complete review and confirm downstream CSV output.

- [x] **11.4 Create and test a separate insurance GLM pipeline visually**
  - [x] Replace the native-prompt review-form creation flow with an accessible
    in-page dialog, add a focused regression test, and visually verify it.
  - [x] Create and publish an insurance review schema for `sample_invoice.pdf`.
  - [x] Create and publish a separate GLM pipeline with review, JSON metadata
    export, and local-PDF storage after review.
  - [x] Configure scalar-only visual field definitions and generic guidance for
    insurer, policy number, debit/credit note type, total premium, and coverage
    start/end dates; do not configure an object or table field.
  - [x] Require `YYYY-MM-DD` coverage dates and a numeric premium. Include the
    requested Liberty-specific rule that strips leading asterisks from a masked
    premium such as `SGD ********100.00` before returning `100`.
  - [x] Configure collision-safe local filenames as
    `insurance_{policy_number}_{insurance_start_date}_{id}.pdf`, preserving the
    original upload separately as the document source.
  - [x] Confirm the insurance extraction makes one initial scalar structured
    Ollama call per page and no table call. If a required scalar is null, record
    the adapter's conditional focused-recovery call rather than misreporting it
    as a second table/structure pass.
  - [x] Upload `sample_invoice.pdf`, inspect the unedited extraction, complete
    review, and confirm the downstream JSON and renamed-PDF artifacts.

- [x] **11.5 Record evidence and complete the remediation audit**
  - [x] Save ignored screenshots for configuration, unedited extraction,
    completed review, and export artifacts.
  - [x] Add generic GLM-only allowed-value constraints for scalar text fields,
    including nested object and table-row properties.
  - [x] Add opt-in deterministic ISO-date normalization after source-date
    transcription; do not add insurance-template-specific parsing.
  - [x] Expose both options only in the separate GLM visual properties editor
    and preserve the LlamaCloud editor byte contract.
  - [x] Retest `sample_invoice.pdf` with the customer object, debit/credit
    choices, ISO-date normalizers, and the experimental script's runtime sizes.
  - [x] Update maintained documentation and these implementation notes.
  - [x] Audit the diff for credentials, customer content, runtime databases,
    generated exports, logs, and screenshots.

## Final requirement audit

- [x] New GLM task follows the standard-task creation guideline.
- [x] Direct Ollama only; no full GLM SDK dependency.
- [x] Dynamic scalar, object, and array-of-object schemas work.
- [x] Table extraction uses a separate schema-directed VLM call.
- [x] No fake confidence is produced.
- [x] A downstream review gate requires review of every configured GLM field.
- [x] No review gate means no pause.
- [x] Structured JSON is available in context and SQLite.
- [x] Review corrections reconstruct correctly on resume.
- [x] CSV output expands line items correctly.
- [x] GLM and Llama visual property editors are separate.
- [x] Existing LlamaCloud behavior remains compatible.
- [x] Portal and watch-folder live tests use different non-merged invoices.
- [x] Documentation and visual evidence are complete.
- [x] Full automated regression is complete.

## Implementation Notes

Record during execution:

- Baseline commit/worktree state: Commit
  `356a8603215bbdd3fa7702a11475730fc9261cad`; dirty worktree recorded before implementation;
  pre-existing user changes were limited to `security_best_practices_report.md`,
  `security_remediation_checklist.md`, `tools/config_check/README.md`, and
  `tools/config_check/examples/ERROR_CODES.md`, plus this untracked plan.
- Pre-existing test failures: None. The 64-test baseline covering LlamaCloud
  schema/persistence, review, CSV/JSON storage, and visual-editor compatibility
  passed in 6.27 seconds without Ollama running.
- Dependency-resolution notes: Installed direct dependencies `ollama==0.6.2`,
  `PyMuPDF==1.28.0`, and `jsonschema>=4.26,<5`; `pip check` reported no broken
  requirements. `glmocr[selfhosted]` was intentionally not added.
- Phase 1 verification: Required gate passed (18 tests); the broader 64-test
  LlamaCloud/persistence/review/storage/editor compatibility matrix also passed.
- Phase 2 verification: Required gate passed (23 tests).
- Phase 3 verification: Required gate passed (14 tests), all with mocked Ollama;
  the complete extraction test directory passed with 86 tests.
- Phase 4 verification: Required task/persistence gate passed with 26 tests.
  The new task persists provider `glm_ocr_ollama`, explicit JSON null values,
  null confidence, safe source evidence, and no task-created artifact.
- Phase 5 verification: Required review/service/resume gate passed with 16
  tests. A broader GLM/review run passed with 36 tests, including gate-free
  storage, structured and legacy flags, missing-value correction, and corrected
  object-array resume reconstruction.
- Phase 6 verification: Required registry/catalog/pipeline/config/workflow gate
  passed with 70 tests. An additional 22 workflow and LlamaCloud extraction
  regression tests passed after provider-specific split preflight changes.
- Phase 7 verification: The separate production GLM-OCR renderer, defaults,
  runtime controls, structured-field reuse, summary, and exact-class dispatch
  passed the prescribed 23-test gate. A byte-level renderer snapshot proves the
  existing LlamaCloud extraction editor was not changed. No CSS changed, so a
  Tailwind rebuild was not applicable.
- Phase 8 verification: Mocked upload and watch-folder workflows both pinned an
  exact published GLM pipeline version, persisted null-confidence extraction
  rows, paused every field for review, applied corrections, resumed at CSV, and
  registered separate `export_csv` artifacts. The gate-free GLM-to-CSV path
  completed without review state. The prescribed gate passed with 30 tests.
- Phase 7-8 repository regression: `node --check` passed for the production
  pipeline editor, and the complete pytest suite passed with 971 tests and 4
  skips in 131.42 seconds.
- Production-task isolation audit: `store_metadata_as_csv.py`,
  `store_metadata_as_json.py`, `extract_pdf.py`, and `llama_cloud_v2.py` have no
  Phase 7-8 diff. The protected storage hashes remained
  `2A279E8D13C572F9542266A3F173748BDC66BA508CAAA4982CC8CD78F018F59E`
  (CSV) and
  `88E146F744EA3169AD59145DE23789D5D2E5F16F13DF460CCCC8203675C5E884`
  (JSON).
- Phase 4-6 repository regression: The final complete pytest suite passed with
  963 tests and 4 skips in 123.44 seconds.
- Provider-isolation correction: The initial Phase 1 implementation temporarily
  delegated LlamaCloud schema/normalization methods to the new helper. At the
  operator's request, both existing LlamaCloud modules were restored exactly to
  their committed content, and this plan was amended to prohibit that coupling.
  The complete extraction test directory passed again after restoration (86
  tests in 10.17 seconds).
- Existing-provider isolation regression (2026-08-05): Both published
  LlamaCloud pipelines were exercised through the production UI after the
  restoration. `LlamaCloud Invoice Live` completed invoice `36259` without
  review; `Insurance Invoice` extracted `sample_invoice.pdf`, paused for the
  configured low-confidence review, and completed after the visually verified
  amount of SGD 70.00 was accepted. Both batches completed with zero failed
  documents and successful CSV, JSON, local-file, and archive task runs.
- Existing-provider watch-folder regression (2026-08-05): The enabled binding
  for `D:\python_code\pdfdoc_extraction\watch_folder` selected exact published
  version 1 of `LlamaCloud Invoice Live`. A new copy of
  `invoice_Aaron Bergman_36258.pdf` created watch-folder batch
  `daf060d2-f9a1-4045-b110-4f87442c08ed`. LlamaCloud returned invoice number
  36258, date 2012-03-06, one line item for 48.71, and total 50.10. The review
  gate paused because the total's 94.8% confidence was just below its 95%
  override. The displayed value was visually verified and accepted without
  correction; the batch then completed with zero failures. CSV, JSON, stored
  PDF, and archived PDF artifacts were all present.
- Existing-provider visual evidence directory:
  `C:\Users\bpson\.codex\visualizations\2026\07\24\019f92a8-52b2-7542-a9bd-b43f8aa09eaf\llamacloud-isolation-test`.
- Phase 9 security/configuration verification: The focused security matrix passed
  with 9 tests. It covers credential-bearing URL rejection, absence of a GLM API
  key, safe task-run summaries and context persistence, administrator-only
  publication, unchanged security headers and same-origin preview behavior,
  actionable malformed-configuration findings, published-pipeline validation,
  and the unchanged LlamaCloud API-key requirement. The portable
  `test/fixtures/glm_ocr_pipeline.yml` bundle passed config-check validation.
- Phase 9 focused regression: Extraction passed with 107 tests; review, storage,
  workflow, registry, catalog, and config-check passed with 100 tests; production
  editor visual/static coverage passed with 36 tests. `node --check` passed and
  `pip check` reported no broken requirements. A non-failing Prefect temporary
  server teardown message attempted to write to a closed log stream after the
  visual run; the test process exited successfully.
- Phase 9 full regression and type gate: The complete suite passed with 973 tests
  and 4 skips in 126.28 seconds. Pyright, using the repository Pylance-compatible
  configuration, reported 0 errors, 0 warnings, and 0 informational findings.
  No live Ollama/GLM call was made by the automated suite.
- Phase 9 repository audit: No credentials, PDFs, databases, CSVs, logs,
  screenshots, or runtime extraction artifacts were added. The existing
  LlamaCloud extract implementations and production CSV/JSON storage tasks have
  no diff. The protected storage hashes remain
  `2A279E8D13C572F9542266A3F173748BDC66BA508CAAA4982CC8CD78F018F59E`
  (CSV) and
  `88E146F744EA3169AD59145DE23789D5D2E5F16F13DF460CCCC8203675C5E884`
  (JSON).
- Phase 10 live environment: Ollama 0.32.6 exposed its native API at
  `http://127.0.0.1:11434`, `glm-ocr:latest` was installed, and a harmless model
  request completed. The application ran on isolated port 8765 with an ignored
  SQLite database and runtime tree under
  `output/playwright/phase10_glm_live`; no customer/runtime database was used.
- Phase 10 visual configuration: Administrator UI creation published review
  form `superstore-glm-phase10` v1 (schema version
  `82774063-af10-4b6a-b310-a31ec07231d6`) and pipeline
  `glm-phase10-superstore` v1 (pipeline version
  `1d74ae7e-1173-4ad9-9b75-ba7ba921a645`). The pipeline is
  `GlmOcrExtractTask -> ReviewGateTask -> StoreMetadataAsCsv`, with whole-document
  review and a dedicated watch binding pinned to that exact version.
- Triggered GLM visual-test PDFs and outcomes: Portal upload triggered
  `invoice_Steven Ward_9240.pdf` once and completed; watch-folder ingestion
  triggered `invoice_Tamara Chand_41648.pdf` once and completed. No retry invoice
  and no filename beginning with `random_merged` was used.
- GLM portal result: Batch `b9c46e1a-7331-41a9-88bb-84fee7afc63f` and document
  `fc22644b-4979-437d-94b2-b4b2663b94a3` persisted provider
  `glm_ocr_ollama`, 11 null-confidence top-level fields, and a distinct review
  item. The operator corrected the scalar and line-item values against invoice
  9240 and completed review. Resume completed CSV and cleanup; registered CSV
  artifact `e7c5788c-98d0-4d72-8a85-d2c1d5ed639e` contains one line-item row
  with repeated document values.
- GLM watch-folder result: Batch `3ffd98d2-ffdb-4c55-9c52-7bad02963170` and
  document `fa02e006-e7f2-4590-839e-5864b8bec468` used ingestion source
  `watch_folder`, the same pinned pipeline version, and independent extraction,
  review, context, and task-run records. The operator corrected invoice 41648
  and completed review. Registered CSV artifact
  `7f188f96-c70b-4240-9b88-9c65a7e89def` is separate from the portal artifact.
- Live model quality observation: GLM used separate scalar/object and table
  calls as designed, but the raw outputs for both sample invoices needed
  operator corrections. This does not block the design: confidence stayed null,
  the review gate exposed every configured field, and only corrected SQLite
  values flowed to CSV.
- GLM visual evidence directory:
  `D:\python_code\pdfdoc_extraction\output\playwright\phase10_glm_live\evidence\screenshots`.
  Evidence covers review-form and pipeline publication, portal and watch runs,
  completed reviews and CSV artifacts, desktop/tablet/mobile layouts, long-value
  containment, and the mobile object-array editor. Keyboard focus followed host,
  model, instructions, and runtime settings; accessible names were present and
  missing confidence appeared without a fabricated percentage.
- Phase 10 verification: The prescribed visual gate passed with 23 tests. The
  final focused GLM, LlamaCloud, review, storage, registry, catalog, workflow,
  config, and visual matrix passed with 230 tests in 72.89 seconds. Pyright
  reported 0 errors, 0 warnings, and 0 informational findings; `pip check`
  reported no broken requirements. The non-failing Prefect temporary-server
  teardown logging message appeared after pytest exited successfully.
- Final full-suite result: Phase 9 passed the complete suite with 973 tests and
  4 skips in 126.28 seconds. Phase 10 made documentation and checklist changes
  only after live testing, so the conditional full-suite rerun for visual code
  fixes was not required.
- Final repository audit: No credentials, sample PDFs, databases, CSVs, logs,
  screenshots, or raw provider output are tracked. Live artifacts remain under
  ignored test output. Existing LlamaCloud extraction and production CSV/JSON
  storage files have no diff; the CSV and JSON hashes remain
  `2A279E8D13C572F9542266A3F173748BDC66BA508CAAA4982CC8CD78F018F59E`
  and `88E146F744EA3169AD59145DE23789D5D2E5F16F13DF460CCCC8203675C5E884`.
- Final post-refinement full-suite result: The complete suite passed with 974
  tests and 4 skips in 138.24 seconds after the production UI refinement.
  Pyright remained clean with 0 errors, 0 warnings, and 0 informational
  findings.
- Post-Phase 10 visual refinement (2026-08-06): The GLM extraction-field row now
  aligns Field key, Alias, and Type labels/controls; presents Remove as an
  outlined destructive action; balances Required field and Extraction guidance;
  suppresses the repeated one-table note; and responds to both viewport and
  editor-container width. Browser measurements confirmed identical label and
  input top coordinates and a solid 1px Remove border. Desktop and mobile
  screenshots are under the ignored `evidence/alignment-fix` directory. The
  prescribed visual matrix passed with 24 tests, the final GLM editor check
  passed with 6 tests, `node --check` passed, `npm run build:css` rebuilt the
  committed frontend CSS, and the byte-level LlamaCloud renderer regression
  remained unchanged.
- Pipeline header overlap correction (2026-08-06): The template metadata and
  Publish sequence panels previously shared the `guide` CSS grid area and could
  cover each other while scrolling. The template now owns a distinct `template`
  row at desktop, tablet, and mobile breakpoints. Live browser measurements at
  1224px, 900px, and 375px reported zero overlap with a 16px inter-panel gap;
  the focused visual regression matrix passed with 25 tests.
- Phase 11 insurance visual result (2026-08-06): Review schema
  `insurance-glm-phase11` v1 and separate pipeline `glm-phase11-insurance` v1
  were published visually. Portal batch `cb696222-1348-4bcd-9fb5-5054fc75644b`
  paused for review, accepted corrected insurer, ISO coverage dates, note type,
  policy number, and premium, then completed JSON and renamed-PDF storage. The
  exported PDF SHA-256 matched `sample_invoice.pdf` exactly. The GLM metadata
  recorded one `scalar_object` call and no recovery or table call.
- Phase 11 prompt comparison (2026-08-06): The original prompt already said not
  to use the invoice issue date. A visually imported and validated v2 added
  prioritized spatial rules for the insurer header and the `Period of
  Insurance` `FROM`/`TO` block. Portal batch
  `92945900-7d22-4918-93fc-175f886f81a8` still returned the insured company,
  issue date as start date, non-ISO end date, and full document title as note
  type; policy number and premium were correct. The prompt hash changed from
  v1, proving the revised prompt was sent, but the raw values were otherwise
  identical. The v2 run is intentionally paused at Review Gate so the unedited
  result remains inspectable.
- The specialized experimental script differs in more than prompt wording: its
  schema includes a customer object that anchors the insured name/address block,
  constrains debit/credit with an enum, and applies Python date/value validation
  after the model response. Those generic capabilities should be designed as
  field constraints and normalizers in the GLM task rather than copied as
  insurance-template-specific code. Prompting alone is not a reliable semantic
  validator for this sample.
- The JSON storage task does not expose the context-only `{id}` token to its
  filename formatter and therefore rendered it as `unknown` in the v1 artifact.
  Pipeline v2 removes `{id}` from the JSON filename while retaining it for the
  PDF storage task, which supports the document id. Both storage tasks reserve
  collision-safe output paths.
- Phase 11.5 insurance visual result (2026-08-07): Pipeline v5 was configured,
  validated, published, and submitted through the portal. The customer object
  kept the insured name and address together and separate from the insurer;
  allowed values reduced the note heading to `debit`; and the end date was
  normalized to ISO. GLM-OCR still selected the invoice issue date for the
  coverage start despite explicit guidance, so the administrator corrected that
  one value in Review Gate. JSON and renamed-PDF storage then completed. The
  extraction provenance recorded exactly one `scalar_object` call and no table
  or focused-recovery call.
