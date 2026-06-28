# Pipeline editor visual QA

## Scope

- Surface: `http://localhost:8000/app/admin/pipeline`
- Coverage: task creation/removal/reordering, task-specific controls, extraction
  field modeling, validation, draft persistence, diff, publish, YAML parsing, and
  rollback.
- Baseline backup: `config.yaml.safe-copy`
- Baseline SHA-256: `7CD8B758AFED80B46892F928CF25F60DD7ACBD784F35A607D7B0247FEC377F29`

## Outcome

- The published nine-task QA configuration parsed successfully as YAML.
- `tools.config_check --import-checks` reported 0 errors and one existing warning:
  `schema: Unknown key not defined by schema` (warning-only exit code 2).
- The published extraction model contained all ten supported top-level field types,
  required and optional variants, a four-property object, and a four-column table.
- The original `config.yaml` was restored byte-for-byte and the application was
  restarted. The runtime now shows the original seven-task active and draft model.
- The temporary archive directory created through the UI was removed.
- Nineteen focused pipeline API/service/validation tests passed.

## Findings

### 1. High - YAML Preview is not valid YAML

The browser preview uses a hand-written serializer. Empty nested mappings are emitted
without indentation. For example:

```yaml
      per_document_type_thresholds:
{}
      queue_name: default_review
```

PyYAML rejected the saved client preview with `could not find expected ':'`. The
server-generated draft and published `config.yaml` both remained valid. The preview
should use the server serializer or the same serialization library and test fixtures.

### 2. High - one-table constraint is client-only

The normal type selectors disable a second `List[Any]` field and the page displays
`Only one table field is supported`. Advanced Params JSON can still introduce a
second table. Validate then reports `0 blocking, 0 warnings` and enables Publish.
Server validation must enforce the same maximum-one-table invariant.

### 3. High - Nano ID range is not enforced server-side

The Nano ID length control advertises `min=5` and `max=21`. Setting `length: 4`
through Advanced Params JSON rendered the invalid value, but Validate reported
success and enabled Publish. Central validation must enforce every UI range.

### 4. Medium - extraction fields reorder after refresh

The initial and saved model retained insertion order. After Refresh, the field editor
displayed fields alphabetically. Field order may affect readability and downstream
schema expectations. Preserve model order or explicitly document/surface sorting.

### 5. Medium - Diff contains normalization noise

The active-vs-draft diff included large key-order-only changes and numeric
normalization such as `1.0` to `1`. This makes material changes harder to review.
Canonicalize both sides before diffing, or add a semantic diff view.

### 6. Medium - compact-width overflow

At a 1024px viewport the workspace client width was 737px while its scroll width was
912px. The task editor requires horizontal scrolling and key controls can be clipped.
Use a stacked/two-column breakpoint or a collapsible active-pipeline panel.

### 7. Medium - repeated controls lack unique accessible names

Task cards expose repeated `Up`, `Down`, `Enabled`, and `Remove` names. Extraction
fields repeat `Field key`, `Alias`, `Type`, and `Remove`. Structured-schema type
selects have no accessible name in the DOM snapshot. Include the task or field name
in accessible labels and associate drawer column headers with their controls.

### 8. Low - Validate remains enabled for malformed Advanced JSON

Malformed JSON disables Save Draft but leaves Validate enabled. Clicking Validate
only produces a warning toast. Disable both actions while Params JSON is malformed.

## Confirmed strengths

- Invalid split configuration and out-of-range review confidence produced blocking,
  path-specific findings.
- Invalid Advanced JSON was retained in the editor with a precise parse error and
  did not replace the last valid params object.
- The object/table drawer blocks empty schemas, supports required/optional scalar
  children, previews sample values, and preserves Cancel semantics.
- File and directory browsers stayed inside project paths; CSV metadata populated
  field selectors; directory creation/navigation/selection worked.
- Add, enable/disable, error policy, duplicate, confirmed remove, Up/Down, token
  insertion, nested CSV storage, rule-clause limits, and provider-mode switching
  behaved correctly.
- Save, reload, Validate, Diff, and Publish completed. The generated YAML preserved
  multiline and YAML-sensitive guidance safely.

## Step health

1. Sign in and open Pipeline - healthy.
2. Initial hierarchy and responsive layout - attention needed below 1024px.
3. Split task modes, policies, categories, and validation - healthy.
4. Extraction scalar/list type matrix - healthy.
5. Object and row-schema drawers - healthy with server-validation gap.
6. Advanced JSON valid/invalid handling - mostly healthy.
7. Duplicate-table bypass - unhealthy.
8. Generic task enable/order/error/duplicate/remove controls - healthy.
9. Update Reference CSV browser and clauses - healthy.
10. Review Gate thresholds, triggers, schema browser, and validation - healthy.
11. CSV/JSON/local-file storage controls - healthy.
12. Archive directory create/select - healthy.
13. Draft save/reload and validation - healthy.
14. Diff - functional but noisy.
15. Publish and generated YAML validation - healthy.
16. Config and runtime rollback - healthy.

## Evidence files

- `01-start-viewport.png` - initial workspace.
- `02-object-draft.png` - structured object editor.
- `03-extraction-validation-passed.png` - validated extraction matrix.
- `04-invalid-advanced-json.png` - invalid Advanced JSON state.
- `05-duplicate-table-validation-gap.png` - UI table warning that server validation missed.
- `06-published-valid-yaml.png` - published nine-task QA state before rollback.
- `client-yaml-preview.yaml` - client preview that fails YAML parsing.
