# R3 design — CSV reference lookup and enrichment

**Status** · Implemented and verified on 2026-11-25. Each lookup returns text into new document-level fields. Numeric comparison applies only to match inputs. The [archived implementation record](archive/tasks-r3-csv-reference-lookup.md) contains the release checks and sign-off. Use the [task reference](../docs/reference/tasks/rules-context-housekeeping.md#csv-reference-lookup) for current configuration.

## Operator outcome

A supplier invoice carries tax number `00123`. The receiving system needs supplier ID `00042`. A pipeline author configures a lookup from the extracted tax number to the supplier register. A unique match adds `supplier_id: "00042"` to the document data used for export. The original supplier name, tax number, and extraction evidence stay available. The lookup opens the reference file read-only.

The production pipeline is **extract → CSV lookup → review gate (when configured) → outputs**. SQLite holds the lookup decision for the current document or split child. [R3 roadmap scope](roadmap.md#r3-csv-reference-lookup-and-enrichment)

## Pipeline authoring

Offer **CSV reference lookup** as a separate built-in task in the production pipeline editor. The existing CSV update task can update multiple matching rows and replace its source file. Keeping its configuration and behavior intact lets authors add enrichment explicitly. [Current CSV update task](../standard_step/rules/update_reference.py)

| Editor setting | Contract | Invoice example |
| --- | --- | --- |
| Reference CSV | One administrator-configured reference file readable by the worker. Resolve it from trusted configuration, never from document or reviewer input. | `suppliers.csv` |
| Match clauses | One to five clauses joined by AND. For each clause, the administrator selects a document field, CSV column, and comparison mode. Choices are **Case-sensitive text** (default), **Case-insensitive text**, and **Numeric**. | Match the supplier name ignoring case and the tax number as case-sensitive text. |
| Returned fields | Map one or more CSV columns to distinct new top-level document field keys. Return strings in the first release so identifiers keep their formatting. | `SupplierCode` → `supplier_id` |
| Required for release | Applies to the entire lookup. Commit all mapped fields together. | Required |
| No match / multiple matches | Set a policy independently for each outcome. Offer **Review** or **Fail**, plus **Continue without enrichment** for optional lookups. | Review / Review |

Publication checks the pinned pipeline for invalid bindings, incompatible known input types, duplicate target keys, collisions with extraction fields or reserved filename/context keys, and task ordering. Reject collisions discovered only at runtime before writing any returned field. Consecutive independent lookups may use distinct targets. Match inputs must come from extraction fields. Line-item lookup, chaining, fuzzy matching, reference management, and database/API sources are outside this draft.

Place each lookup after its extraction source and before business release. This lets a reference or configuration error stop release even for an optional lookup. When either outcome can request review, require a downstream extraction review gate before release. That gate must allow the reviewer to correct the lookup input even under low-confidence-only editing. Any later gate that changes a match input must revalidate the affected lookup before accepting the edit.

Require `on_error: stop` for the lookup task. A configured optional miss is a successful evaluation with omitted fields. Check CSV headers in the editor when the file is accessible and always check the actual worker input at execution. A pipeline version pins the configuration and field mappings. New documents can use refreshed contents at the configured path.

## Matching contract

Read a comma-delimited UTF-8 CSV with a header, optional BOM, standard quoted fields, and exact, unique column names. Read cells as text before comparison. Invalid encoding, malformed rows, duplicate or missing configured headers, unreadable files, and files over the built-in 8 MiB limit are task errors. The evaluator counts all matches and retains up to 50 candidates.

| Mode | Equality rule | Consequence |
| --- | --- | --- |
| Case-sensitive text (default) | Trim surrounding whitespace from both strings and compare exactly. | `" Ab-001 "` matches `"Ab-001"`. Uppercase `"AB-001"` is a distinct key. |
| Case-insensitive text | Trim both strings and apply Unicode case folding (`str.casefold()`) to both comparison keys. | `" Ab-001 "` matches `"AB-001"`. Leading zeros still distinguish `"AB-001"` from `"AB-1"`. |
| Numeric (opt-in) | Compare finite decimals using a period as decimal separator and an optional sign. Reject booleans, grouping separators, currency, and exponent notation. | `"00123.00"` matches `123`. Choose text for tax numbers and account codes. |

Both text modes operate on string fields and preserve internal spaces and punctuation. Model identifiers as text upstream to retain leading zeros. Use numeric mode for numeric fields. Comparison transforms apply only to match keys. Review displays the original input and reference values, and exports preserve the case and formatting of the returned cells.

Numeric mode accepts a trailing decimal separator. For example, `"1."` matches
`1`. When clauses share a reference column, the review shows each comparison
with its own input field and mode.

A blank, absent, or invalid document input goes through the no-match policy with a distinct reason visible to the reviewer. A blank reference key cannot match. A nonblank malformed numeric key in a configured numeric column is a reference-data error. Count matching records before taking any returned values. Two matching records remain ambiguous even when they return the same ID. Each selected return cell must contain a nonblank value. An incomplete selected row is a reference-data error. Preserve returned strings, including leading zeros.

## Outcomes and release

| Result | Workflow behavior |
| --- | --- |
| Exactly one complete row | Persist the match and add all returned values to effective document data. The ordinary review gate and any R4 rules still apply. |
| No match or several matches, **Review** | Record a pending decision. Force a review at the configured gate even if confidence and business validation would otherwise pass. Hold downstream release. |
| No match or several matches, **Fail** | Stop the document with the lookup task and reason visible to the operator. |
| No match or several matches, **Continue without enrichment** | Persist the reason and omit all mapped keys. Allow only for an optional lookup. An output that requires those keys, such as a PDF filename template, needs a required lookup or a different template. |
| Reference or configuration error | Stop before output. Expose a diagnostic identifying the task and problem. Optional continuation applies only to a valid lookup outcome. |

With several lookups feeding one gate, every required decision must resolve before completion. A pending review state must survive interruption before the gate runs.

## What the reviewer sees and can change

In the existing extraction review, show the lookup label, matched fields and inputs, outcome, and proposed returned values. For ambiguous matches, show candidate rows from the evaluated file, limited to configured match and return columns, with a record number to distinguish duplicates. A bounded candidate view must disclose truncation. If there are too many matches to offer a complete choice, require a corrected input or register repair. Never select the first row automatically.

The reviewer can correct a match input and revalidate, or select a specific matching row and give a reason. Returned fields are derived and read-only. A required no-match can be resolved by correcting the source input to obtain a valid row. If the register itself is wrong, the document stays held for reference maintenance. An optional lookup in review may be explicitly skipped with an audited reason.

Revalidation previews the proposed decision for the current draft. Editing a match input invalidates a prior selection. At completion, the server checks claim ownership and the submitted revision, recomputes or verifies the decision for those values, then runs the pinned form's schema and R4 rules against the merged values. A lookup result has reference provenance and carries no OCR confidence. A rule can bind a returned key declared with the compatible type in the form. A stale preview, unresolved required lookup, or blocking validation finding keeps review open. The accepted corrections, lookup decisions, validation report, and review completion commit together before next-task resume. [Current review gate](../docs/reference/tasks/review-gate.md)

## Decision history, file changes, and recovery

SQLite owns the result through the service/repository boundary. Identify each decision by document, extraction result or input revision, exact pipeline version, and configured task key. Record the normalized match inputs and modes, a SHA-256 digest of the exact bytes parsed, outcome and count, bounded candidate evidence, selected record number, returned keys/values, and any reviewer, reason, and revision. Retain superseded decisions with their relationship to the replacement. Keep business values in access-controlled workflow records. General logs and audit summaries need only identifiers and reason codes.

- **Initial read.** Hash and parse the same bounded byte buffer. Reference-file maintainers should replace a complete file atomically. Saving the result and its evidence is one transaction. Retrying after that commit reuses the decision for the same input revision. A failure before the first commit has no recorded decision to replay.
- **Resume or retry with the same inputs.** Reconstruct accepted values from the recorded result. A pending ambiguous choice can use the recorded candidates for that revision. A later edit, rename, or removal of the CSV cannot silently alter either decision.
- **Corrected input during review.** Rematch against bytes with the recorded digest. If those bytes are unavailable, keep the item open. Show an explicit **Use current reference file** action for an authorized reviewer with a reason. This also permits deliberate reevaluation after a register repair. Record a new evaluation with the old and new digest and require fresh review. Concurrent saves or repeated submissions must produce at most one accepted revision.
- **Retention choice.** Store decision evidence and the digest, without copying the entire supplier register per document. This supports replay of the recorded result. Repeating a historical search with different inputs requires the corresponding reference bytes. A requirement for full historical rematching would change this design.

## Output and runtime boundaries

The new approved `standard_step.*` task follows `BaseTask` and the existing error contract. Repositories persist decisions and services coordinate lookup, review, and release. The web route validates the request and calls the service. SQLite-specific operations belong behind that boundary. [Task standards](standard_task_creation_guidelines.md) and [application architecture](../docs/design_architecture.md)

Use the same effective data for the uninterrupted path, the gate, and resumed outputs. Merge accepted lookup values into workflow `context["data"]` alongside the current extraction values and corrections. The gate currently reads persisted fields, and resume reconstructs data from SQLite. Both paths need the same persisted lookup projection. Preserve original extraction values and confidence separately. Omit an optional skipped key on both paths. Candidate rows and decision metadata are review evidence and stay out of ordinary business exports. [Resume behavior](../modules/resume_manager.py) and [output contracts](../docs/reference/tasks/storage-and-archiving.md)

## Acceptance examples

| Given | Observable result |
| --- | --- |
| Invoice tax number `00123`, one supplier row with code `00042` | JSON and CSV contain both strings. A PDF template using `{supplier_id}` includes `00042`. The CSV reference bytes and original extraction record are preserved. |
| Input `Acme`, reference names `Acme` and `ACME`, both rows satisfying the other clauses | The default mode selects the first name by exact equality. Case-insensitive mode finds both rows and applies the configured multiple-match policy. |
| Input `acme`, one matching reference name `Acme`, return code `SuP-007` | Case-insensitive matching returns `SuP-007` with the register's spelling and leading zeros. |
| Two rows for the same tax number | Review shows ambiguity. Selecting the second row records the actor, reason, candidate identity, and returned value. Reopening or retrying yields that selection. |
| Required match missing, then reviewer corrects tax number | No release with the missing ID. Revalidation shows the new match, and completion runs business rules on that revision. A stale submission cannot replace it. |
| Optional match missing, or malformed reference header | The optional miss yields an auditable omission. The malformed file stops processing even for an optional lookup. |
| Register replaced during review | Unedited inputs retain their recorded evidence. Changed inputs require matching bytes or explicit adoption of the replacement. Resumed output uses the accepted revision. |
| A mapping targets an existing field or two children use different supplier IDs | A collision is rejected before mutation. Each child's decision and exported ID belong to its own document. |

