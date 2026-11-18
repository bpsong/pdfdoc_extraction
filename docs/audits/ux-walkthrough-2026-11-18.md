# UX walkthrough: operator and admin journeys

| Item | Value |
| --- | --- |
| Date | 18 November 2026 |
| Method | Observation-only browser walkthrough with two synthetic invoices loaded through the UI |
| Environment | Local deployment, `http://127.0.0.1:8000`, `config.yaml`, `db_folder/app_state.sqlite3` |
| Passes | One per persona; no journey repeated |
| Evidence | Screenshots in the session temp folder `uxwalk/shots`; screenshot ids match the evidence ids below |
| Code changes | None. One new document (this file) |

## Owner corrections applied

Two interpretations in the first draft were corrected by the product owner on the same
day and are reflected throughout:

1. **The Review Queue is the work inbox.** No second queue is proposed. The remaining
   finding is only that the existing queue is not advertised on arrival (no count, no
   banner); whether the queue or the upload form should start the day is a product
   decision left open.
2. **Two roles (`admin`, `operator`) are the intended design.** Persona C, unmet need
   U-9, and ranked item 10 are withdrawn. Shared attribution and shared-password
   offboarding are recorded as consequences, not defects.

## Positioning used

No committed positioning statement exists in the repository. The personas below are
derived from the roadmap **Business aim**, the **one human user at a time** planning
assumption, the operator/admin split in `docs/operator` and `docs/admin`, and the
deployed configuration (self-hosted Windows, SQLite, 15 pipeline templates, 9 review
forms, 3 watch-folder bindings).

> Inferred positioning: a self-hosted, single-tenant application that turns business
> PDFs into reviewed, structured data and files for downstream systems. A small
> operations team submits documents with one shared operator account; an in-house
> administrator owns extraction quality, review-form design, and deployment.

This is an assumption, not an approved positioning. Confirm before the roadmap
conversation; every persona judgement below depends on it.

## Personas

### A. Mei - Document Operations Clerk (`operator`)

- Processes 30-80 supplier invoices, bills of lading, and claim documents a day during
  two busy windows. Measured on nothing sitting unreviewed for more than a working day.
- Works from a shared drive and an accounting system. No interest in extraction
  technology; cannot choose between "GLM-OCR", "LiteParse", "LlamaCloud", or "JSON".
- Mental models: an inbox that tells her what needs her; a spreadsheet she can scan;
  Docparser/Nanonets-style "upload, wait, download". She expects status to be visible
  without hunting and expects a recognisable name for her own batch.

### B. Arun - Application Admin / Pipeline Maintainer (`admin`)

- Owns extraction accuracy, review-form design, and the watch folders. Also de facto
  IT support for install, upgrade, backup, and access because no other account exists.
- Thinks in versioned templates, task order, and field schemas. Mental models: an
  n8n/Zapier-style builder, an Airtable-style schema editor, and Rossum/Docsumo-style
  field validation. Expects publish/rollback safety and an impact preview before a
  change reaches live documents.

### C. No third persona - the product has two roles by design

Only `admin` and `operator` exist, and the product owner confirms that is intended, not
an omission. An IT-support persona would therefore be persona B under a different title:
install, backup, runtime health, and pipeline design all sit inside `admin`.

Two consequences are recorded as observations rather than defects: every review and
audit event is attributed to the shared `operator` or `admin` identity, and removing a
person's access means rotating a shared password. They only become findings if
per-person accountability is a requirement. Nothing below argues for a third role.

## Journey map

### Persona A - Mei (operator)

| Stage | What she expected | What actually happened | Judgement |
| --- | --- | --- | --- |
| Landing | A product page or, at worst, a sign-in page that names the application and says what to do first | `/` redirects straight to `/login`. Header "Sign In"; card "Welcome Back - Use your configured DocFlow account." There is no signup, no reset, no help link, and an empty 220px sidebar rail | Friction: "Welcome Back" to a first-time visitor; no orientation, but acceptable for an internally deployed tool |
| Signup / first access | An invitation or a way to get an account | None. Username is a dropdown with the two designed roles, and it **defaults to `admin`** | Friction: the operator must notice and switch accounts; the two-option list itself is correct for this product |
| Core workflow - choose pipeline | "Which pipeline is for a supplier invoice? Pick the obvious one." | Ten equal-weight radio cards in alphabetical order: `Bill of Lading - GLM OCR`, `FTS GLM-OCR Review JSON`, `LlamaCloud Invoice Live`, `LiteParse Invoice Review JSON`, `Superstore GLM-OCR Review JSON`, `glm-ocr insurance invoice pipeline`... Each shows a `Version N` badge; details disclose `liteparse-invoice-review-json`, step count, publish date, and one free-text line | High friction: internal product names and version numbers, no document-type grouping, no recommendation, no "use this for invoices" |
| Core workflow - upload | Drag PDFs, be told the limits | Limits are stated up front (PDF only, 50 MB/file, 20 files, 200 MB/batch). Dropping a `.txt` produces an inline "Only PDF files are accepted", marks the row Invalid, and disables Start | Delight: honest limits and a clear, non-blocking invalid-file state |
| Core workflow - monitor | "Is it working, how long, can I leave?" | Batch page is titled "Processing Overview" but the nav highlights "Upload & Process" and no Processing entry exists. Stepper shows `Lite Parse Extract / review_gate / store_metadata_as_json` with a pipeline hash. Queued rows already show 25% progress. One invoice took 2.5 minutes; no elapsed time, no estimate, no "safe to close this page" | Friction: internal identifiers and misleading progress; uncertainty about whether it is safe to navigate away |
| Core workflow - review | A queue of what needs her, then one screen to fix values against the source | Queue rows repeat the queued timestamp twice, label the signal "Missing confidence", and render the status badge as `Pendin g`. Claiming opens a split PDF/fields screen. Every field and every table cell carries its own "Missing confidence" badge; all fields are amber-bordered | Friction: alarm fatigue; no distinction between "unverified" and "suspect" |
| Core workflow - verify against source | Click a field, see where the value came from on the PDF | Field selection replaces the pane hint with "Customer name has diagnostic citations on page 1. Verify against the PDF; field highlights are unavailable." No highlight is drawn | Acceptable compromise, poorly framed: the promise ("Select a field to locate its source") is withdrawn after the click instead of being provider-aware up front |
| Core workflow - finish | "Saved - what next?" | Completing review returns her to the queue with no confirmation, no summary, and no statement of what the pipeline will do next. A deliberately wrong total (400 against line items summing to 397) was accepted and stored as `Corrected` | Friction: no completion feedback. Validation gap is expected for this form (R4 is opt-in) but is invisible to her |
| Core workflow - results | A record she can check and hand on | Extraction page shows Extracted vs Final per field (good), then dumps line items as raw JSON in a single cell, prefixes each label with its snake_case key, writes "No model confidence" in five consecutive rows, and offers no download, export, or "where is my file" action. Artifacts are listed by UUID filename | High friction: the payoff moment is developer-shaped and has no delivery action |
| Secondary - Reports | "Find my batch from this morning" | Recent Batches lists `Batch ID` as a raw UUID; no filename, pipeline, or document count. Status chip and "Workflow state" restate each other in different words. The sixth KPI card is clipped at 1264px. Average processing time reads 11.4h | High friction: she cannot recognise her own batch |
| Secondary - Failures | "Something failed - what do I do?" | Table of raw task errors (`TaskError: Ollama returned HTTP 500; check the local runtime and memory capacity`), class names, and a red "Open Failure" per row whose detail pane opens far below the fold. Real guidance exists only inside a JSON blob: `"operator_action": "Inspect the source PDF or task configuration outside this failed workflow, then re-ingest as a new document if appropriate."` No retry. Page count says 20, Reports says 19 failed | High friction: no triage, no action, feedback off-screen |
| Limits | "What am I not allowed to do, and who do I ask?" | Visiting `/app/admin` renders a raw JSON document: `{"detail":"Admin role required"}`, with no branding, no back link, no contact | Friction: a permission boundary reached as a broken page |
| Return visit | "What needs me today?" | Login again, land on an empty upload form. The Review Queue holds 2 pending items, but the nav shows no count, the landing page no banner, and neither the last batch nor the last pipeline is remembered | Friction: the queue is the inbox, but nothing on arrival says there is work in it |
| Offboarding | Sign out, be told it worked | Account menu contains only Logout. Logout drops straight to `/login`, which resets the account selector to `admin`. No "signed out" confirmation, no session summary | Friction: ambiguous exit; small risk of the next password attempt going to the wrong account |

### Persona B - Arun (admin)

| Stage | What he expected | What actually happened | Judgement |
| --- | --- | --- | --- |
| Landing | An admin home showing health and work in progress | Login lands on `/app/upload`, the operator upload form. Admin links appear as a second nav block under the operator links | Friction: no role-aware landing; config work starts two clicks away |
| Signup / access | Nothing to do: accounts are fixed at two roles | User Management offers exactly two password-change forms (admin, operator). No create, disable, role, last-login, or active-session view - as designed | Neutral by design; the consequence is a shared credential and unattributed actions, noted at persona C |
| Core workflow - health | "Is the system healthy?" | Overview says **Config Health: Blocked - 2 errors, 0 warnings**, but nothing on the card is clickable and nothing says which errors. Validation Center shows two migration-era findings (`tasks section must be a mapping`, `pipeline section must be a list of task identifiers`) with an empty Suggestion column and no remediation link | High friction: a red state with no path forward, while documents process normally |
| Core workflow - template work | Find the template, change it, publish safely | The Pipeline page opens empty with `Select a template` and disabled buttons; all 15 templates live in one dropdown labelled `Name · key · status`. Selecting one reveals a three-column editor | Friction: no list, no search, no status/publish/usage overview |
| Core workflow - edit | Understand a step and its parameters at a glance | Step rows mix three naming systems (`Glm Ocr Extract`, `glm_ocr_extract`, badge `Extract`, badge `Optional`). Parameters form one very long column (16 fields plus prompt, resolver, and prompt-mode selectors); YAML preview and diff repeat the same content further down | Friction: high density, no summary, easy to lose place |
| Core workflow - publish | See who is affected before publishing | Sequence guidance is clear (`1 Edit draft - 2 Save Draft - 3 Validate - 4 Publish`) and drafts are explicitly immutable-on-publish. No impact preview (which bindings, which versions, how many documents) | Mixed: strong safety model, missing pre-flight impact |
| Retention / destructive | Confirmation that explains consequences | "Clean up processing data" explains protected work, retained definitions/audit/files, and SQLite compaction in plain language before a Preview step | Delight: one of the best-written screens in the product |
| Secondary - review forms | Design a form and know what depends on it | Three-pane editor; version history shows `Version 1 2026-10-05T06:30:20.105139+00:00 445c72839257`; the impact panel lists "Used by 7 published pipeline task(s)" with exact pipeline and step versions | Mixed: excellent dependency transparency, raw timestamps and hashes |
| Secondary - watch folders | See bindings, drift, and health at a glance | Filters and a summary row ("3 shown - 3 current bindings - 3 enabled - 1 updates available") are genuinely useful. Status badges wrap to `enabl ed`; one binding shows `v3 / Update available: v5` with no upgrade action; dates use `09/09/2026, 10:20:36` while other pages use `18 Nov 2026, 15:51` | Mixed: good operational signal, no drift remediation, inconsistent formatting |
| Secondary - audit | Answer "who changed what" | Event chips and before/after JSON. Event Type is free text, Target always reads `admin`, and the only detail is raw JSON. No export | Friction: read-only forensic view needs a developer to interpret |
| Limits | Know what the account cannot separate | One admin identity covers pipeline design, user access, audit, and deployment support | High friction: no separation of duties, no attributable actions |
| Return visit | Resume where he left off | Bookmarking `/app/admin/pipeline` while signed out and then signing in lands on `/app/upload`; the requested page is dropped. No "unsaved draft" or "since you were away" signal | Friction: deep links do not survive login |
| Offboarding | Sign out cleanly | Same as persona A: immediate redirect, no confirmation | Friction |

## Evidence log

| ID | Page | Action | Observation | Screenshot |
| --- | --- | --- | --- | --- |
| E-01 | `/` -> `/login` | First visit | Straight redirect; "Welcome Back"; username dropdown defaults to `admin`; no signup/reset/help; empty sidebar rail | `A01-login.png` |
| E-02 | `/app/upload` | Inspect chooser | 10 radio cards, alphabetical, no descriptions visible, `Version N` on each; details show `default-processing`, 6 steps, publish date, one free-text line | `A02-upload-empty.png` |
| E-03 | `/app/upload` | Expand help | "What happens next?" refers to "the processing page"; `/app/processing` exists in the router but has no navigation entry | - |
| E-04 | `/app/batches/{id}` | After upload | Heading "Processing Overview", nav still marks Upload & Process, no breadcrumb, raw batch UUID, pipeline hash, snake_case step names | `A04-batch-initial.png` |
| E-05 | Queue table | Measure | `Review` action link sits at x=1245 in a 1264px window; scroll wrapper 1088 wide inside 975 | `A06-batch-review-required.png`, `A07-review-link-clipped.png` |
| E-06 | Queue table | Read rows | Queued documents show 25% progress; Action column empty until review is required | `A04-batch-initial.png` |
| E-07 | `/app/review` | Empty state then populated | "No review items" with no guidance; then duplicate timestamp per row, `Missing confidence`, badge renders `Pendin g` | `A05-review-empty.png`, `A08-review-queue-2items.png` |
| E-08 | `/app/review` | Compare filters | 11 pipeline options plus `All pipelines`, including inactive `Superstore Invoice Business Validation`; upload page lists 10 | - |
| E-09 | `/app/review/{id}` | Claim and inspect | Every field and each table cell carries "Missing confidence"; `Source: Review only`; Release sits beside Complete Review without confirmation | `A09-review-item.png` |
| E-10 | Review page | Select field | Hint changes to "diagnostic citations... field highlights are unavailable"; highlight layer has 0 positioned children | `A10-review-locate.png` |
| E-11 | Review page | Set total 400, complete | Accepted; extraction page shows Extracted 397 / Final 400 / `Corrected`; no cross-field validation on this form | `A12-extraction.png` |
| E-12 | `/app/documents/{id}/extraction` | Read results | Line items rendered as raw JSON in one cell; snake_case keys beside labels; all six fields show "No model confidence"; artifacts listed as UUID filenames; no download/export/delivery action | `A12-extraction.png` |
| E-13 | `/app/reports` | Read dashboard | 6 KPI cards overflow: document width 1298 vs 1264; "Average processing time 11.4h" clipped; Recent Batches keyed on UUID; Status and Workflow state restate each other | `A13-reports.png`, `A14-reports-state.png` |
| E-14 | Reports dialog | Open batch details | Task table exposes class names, snake_case ids, per-task `Raw JSON`; Current step and Last Completed duplicate the same value | `A15-batch-details-dialog.png` |
| E-15 | `/app/failures` | Inspect | Raw infrastructure errors; red per-row CTA; detail pane 2000px below; `operator_action` only inside JSON; no retry; badged 20 while Reports says 19 failed | `A16-failures.png`, `A17-failure-detail.png`, `A18-failure-detail-bottom.png` |
| E-16 | `/app/admin` as operator | Navigate | Raw JSON page `{"detail":"Admin role required"}`, no chrome or exit | `A19-admin-blocked.png` |
| E-17 | `/app/upload` | Return visit | No nav badges, no pending counts, no recent work, no remembered pipeline | `A20-return-visit.png` |
| E-18 | `/app/upload` | Drop `.txt` | Inline "Only PDF files are accepted", Invalid row, Start disabled | `A21-invalid-file.png` |
| E-19 | Account menu | Open, log out | Menu contains only Logout; redirect to `/login`; selector resets to `admin`; no signed-out message | `A22-account-menu.png` |
| E-20 | Admin login | Land | Lands on `/app/upload`; admin nav is a second block under operator nav | - |
| E-21 | `/app/admin` | Read | "Config Health: Blocked" is not interactive; Configuration Health reports 1 published version while 35 published versions exist across 15 templates; Admin Workspaces duplicates nav | `B01-admin-overview.png` |
| E-22 | `/app/settings/validation` | Read | 2 errors, empty Suggestion column, no remediation link, fourth KPI card clipped | `B02-validation.png` |
| E-23 | `/app/admin/pipeline` | First open | Empty editor, disabled actions, `Loading selected pipeline...` shown with nothing loading, clipped button in draft header | `B03-pipeline.png` |
| E-24 | Pipeline editor | Inspect step | Three naming systems per step, `Optional` badge beside an enabled step, 1500px parameter column, YAML/raw duplication, no usage impact | `B04-pipeline-loaded.png` |
| E-25 | Pipeline | Open cleanup dialog, cancel | Clear protection/retention/compaction copy; `dd/mm/yyyy` input against a UTC-exclusive rule | `B05-cleanup-dialog.png` |
| E-26 | `/app/admin/users` | Read | Two fixed password forms; no create, disable, role, last login, or sessions | `B06-users.png` |
| E-27 | `/app/schemas` | Read | Truncated form names, vertical `activ e` badge, raw ISO timestamp plus hash, "Used by 7 published pipeline task(s)" dependency list | `B07-review-forms.png` |
| E-28 | `/app/admin/watch-folders` | Read | `enabl ed` badges, `v3 / Update available: v5` without upgrade action, `09/09/2026` vs `18 Nov 2026`, stacked action links | `B08-watch-folders.png` |
| E-29 | `/app/admin/audit` | Read | Free-text Event Type, Target always `admin`, raw JSON detail, no export | `B09-audit.png` |
| E-30 | Deep link | Sign out, open `/app/admin/pipeline`, sign in | Lands on `/app/upload`; requested page dropped | - |
| E-31 | Stylesheet | Verify badge wrapping | `main .badge:not(#failure-notification-badge) { white-space: normal }` allows the observed `Pendin g` / `enabl ed` / `activ e` breaks | `web/static/css/app.css` lines 25-31 |
| E-32 | Database | Read-only counts | 211 completed, 19 failed, 3 review required, 1 queued; 20 failed task runs across 20 documents (one failure did not become a failed document) | - |

## Findings

### Usability friction

| ID | Moment | Finding |
| --- | --- | --- |
| F-1 | Operator: choose pipeline | Ten pipelines with internal vocabulary and version numbers, no description, grouping, or recommendation. Selecting the right one is guesswork |
| F-2 | Operator: monitor | Batch pages expose hashes, keys, and class names, show 25% for queued work, hide elapsed/remaining time, and drop the navigation context. Onboarding copy points at a "processing page" that is not in the navigation |
| F-3 | Operator: review queue | Two timestamps per row, "Missing confidence" as a signal, duplicated filter concepts, and a status badge that breaks mid-word |
| F-4 | Operator: review item | Every field is equally alarming; `Release` sits beside `Complete Review`; "Source: Review only" is unexplained |
| F-5 | Operator: results | Line items are JSON; keys repeat labels; there is no download, export, or delivery action at the moment of payoff |
| F-6 | Operator: reports | Batches are identified only by UUID; two status vocabularies coexist; the KPI row overflows and truncates its own values |
| F-7 | Operator: failures | Infrastructure wording, no retry, actionable guidance buried in JSON, and the detail pane opens far below the click |
| F-8 | Operator: permission limit | A denied admin page is a raw JSON document |
| F-9 | Both: layout | Horizontal clipping recurs at 1264px: queue Action column, Reports KPI row, Validation KPI row, draft-header button |
| F-10 | Both: formatting | Date formats mix `18 Nov 2026, 15:51`, `09/09/2026, 10:20:36`, and `16 Sept 2026`; ISO timestamps appear in version history |
| F-11 | Admin: overview | "Blocked" with two errors that cannot be opened from the card, and legacy metrics that contradict the template model |
| F-12 | Admin: pipeline page | Empty default state, templates hidden in a dropdown, stale "Loading..." status text, and a 1500px parameter column |
| F-13 | Admin: watch folders | Drift is detected ("Update available: v5") but not actionable; badges wrap mid-word |

### Unmet needs

| ID | Moment | Need |
| --- | --- | --- |
| U-1 | Daily start | **Visibility of the queue that already exists**, not another queue. The Review Queue is the work inbox and is well formed once reached; nothing announces it: no count on the nav item, no waiting-work banner on the landing page, and failed work lives on a separate page. Whether the queue or the upload form should be the day's starting point is a product decision, not a fact established here |
| U-2 | Return visit | Recognition: my batches identified by filename, pipeline, and count; my last screen restored; deep links surviving login |
| U-3 | Pipeline choice | Approved, business-language guidance per pipeline ("use for supplier invoices; requires Ollama") surfaced on the card, plus a document-type first chooser |
| U-4 | Review | A confidence model that distinguishes "provider supplies no confidence" from "low confidence", and a way to mark a field verified |
| U-5 | Results | Data delivery: item lines as a table, CSV/JSON download, and a link to the durable file, not just a UUID |
| U-6 | Failure handling | Triage by "needs action vs historical", the operator action shown as prose, and re-ingest/retry from the row |
| U-7 | Admin health | A truthful, actionable health state: what is broken, what it affects, and the fix; legacy-vs-template metrics reconciled or labelled |
| U-8 | Admin change safety | Pre-publish impact: which bindings and pipeline versions use this template, how many documents would be affected, and who last published |
| U-9 | Not a need | Removed. Two roles are the intended design, so this is not an unmet need. The observations that remain: reviews and audit events carry only `operator` or `admin`, and offboarding means rotating a shared password. Revisit only if per-person accountability becomes a requirement |

### Feature suggestions, by journey moment

| ID | Moment | Suggestion |
| --- | --- | --- |
| S-1 | Landing | Replace "Welcome Back" with a first-run panel: what this tool does, where documents go, who to ask; keep the account selector off `admin` by default. Separately, if the queue is meant to start the day, put its pending count on the nav item and a waiting-work banner on the landing page - reuse the queue, do not build a second one |
| S-2 | Choose pipeline | Group cards by document type; show `operator_instructions` as the card description; add a `Recommended` marker; demote version numbers to a tooltip |
| S-3 | Monitor | Add elapsed time, a coarse estimate from recent documents of the same pipeline, and an explicit "safe to close this page" line |
| S-4 | Queue | Provide one filter set with plain labels ("Waiting for me", "Unclaimed", "Done"); show a single timestamp; replace "Missing confidence" with "Not scored by this pipeline" |
| S-5 | Review item | Collapse repeated badges into one banner ("This pipeline does not report confidence; all 21 values need checking"); set currency formatting and reorder supplier identity above line items |
| S-6 | Results | Render line items as an editable table and add Download CSV/JSON plus Open file, next to the extraction summary |
| S-7 | Failures | Lead with the recorded operator action, add "Needs action / History" tabs, and offer re-ingest from the row; keep the detail pane adjacent to the selected row |
| S-8 | Reports | Replace Batch ID with filename plus document count and pipeline; add date and pipeline filters; split "average processing time" into machine time and review wait |
| S-9 | Admin | Make the health card open the exact findings and link each finding to the page that fixes it; label or retire legacy config metrics |
| S-10 | Admin | Add a template list view with status, latest version, publish date, usage count, and last publisher, with a "used by" preview before publish |
| S-11 | Admin | Surface binding drift as an action ("Move to v5"), not only a warning |
| S-12 | Cross-cutting | One formatting and vocabulary pass: badge `nowrap`, one date format, one status vocabulary, human labels before keys |

## Ranked suggestions

Ordered by user impact against implementation effort, with the journey moment each one repairs.

| Rank | Suggestion | Journey moment | Impact | Effort | Approval needed from |
| --- | --- | --- | --- | --- | --- |
| 1 | Make the existing Review Queue advertise itself: pending count on the nav item, waiting-work banner on the landing page (U-1, S-1). No new queue, no new page | Daily start, return visit | Medium | Low | Product owner (decide queue-first vs upload-first) |
| 2 | Recognisable batch identity and restoring deep links (U-2, S-8) | Reports, return visit | High | Low | Product owner |
| 3 | Fix horizontal clipping and badge wrapping (F-9, F-3, E-31) | Queue, Reports, Validation, Watch folders | High | Low | Frontend owner |
| 4 | Business-language pipeline chooser with recommendations (F-1, S-2) | Choose pipeline | High | Low | Product owner + admin |
| 5 | Honest health state that links to its findings (F-11, U-7, S-9) | Admin overview, validation | High | Medium | Admin owner |
| 6 | Surface failure guidance and triage, add re-ingest (F-7, U-6, S-7) | Failures | High | Medium | Admin owner + operator input |
| 7 | Review signal semantics and badge de-duplication (F-4, U-4, S-5) | Review item | Medium | Medium | Product owner |
| 8 | Results as data with download/delivery (F-5, U-5, S-6) | Results | Medium | Medium | Product owner; ties to roadmap R5 |
| 9 | Template list view with usage and publish impact (U-8, S-10) | Admin pipeline | Medium | Medium | Admin owner |
| 10 | ~~Named users and roles~~ withdrawn: two roles are the intended design, not a gap | - | - | - | Not proposed |
| 11 | Formatting and vocabulary pass (F-10, S-12) | Everywhere | Medium | Low | Frontend owner |
| 12 | Binding drift upgrade action (F-13, S-11) | Watch folders | Low | Low | Admin owner |

Not suggested: adding features because comparable products have them, a second work queue
alongside the Review Queue, or additional roles. Item 8 is roadmap R5; items 1-7, 9, 11
and 12 come from observed breakdowns in this deployment.

## Approval boundaries

### What this pass did and did not touch

- No application code, configuration, template, schema, or committed asset was changed.
- No pipeline was published, activated, archived, deleted, or cleaned up. The cleanup
  dialog was opened and cancelled before the preview step, so no preview record exists.
- No draft was saved, no setting saved, no password or user changed.
- No retention, migration, or provider call was executed. The LlamaCloud path was
  avoided deliberately to prevent external cost.
- Database access was read-only (`mode=ro`) and only for counts, schema, and status
  facts cited above.

### Residual state that needs a decision

- Two test batches with four synthetic invoice documents were created through the UI,
  with three now in `review_required` and one completed.
- One completed review stores a deliberately inconsistent total (400 against line items
  summing to 397) to test validation. It is synthetic data in a development database,
  but it must not be used for accuracy or metric reporting.
- The local application was left running on `http://127.0.0.1:8000` for inspection.
- Cleaning up the two test batches uses "Clean up processing data" or direct SQL. Either
  is a destructive action and needs explicit approval; nothing was deleted.

### Decisions that must not be made from this document

This is observation evidence, not a roadmap. Each of these needs an owner decision
before any implementation:

1. Any change to pipeline selection defaults, availability, or operator guidance
   affects who can process what; product owner and admin must agree.
2. Any change to review-completion behaviour touches a path the 18 November codebase
   audit already flags as running downstream work on the web event loop. Re-check that
   audit before altering it.
3. Any change to status vocabulary, confidence display, or metric definitions changes
   reported numbers. Finance and operations may be reading those numbers.
4. Additional roles are not proposed here. If per-person attribution ever becomes a
   requirement, that is roadmap R6 with a documented dependency on R1, not a UI change.
5. Retention, cleanup, archive, and audit changes have recovery limits documented in the
   retention guide; they need the same review as a data-deletion feature.
6. Anything touching delivery (download/export/webhook) overlaps roadmap R5 and should
   be specified there rather than bolted onto the extraction page.

### Not covered by this pass

- Mobile and tablet widths, keyboard-only traversal, screen-reader behaviour, and
  non-Chromium browsers.
- Manual split, the LlamaCloud extraction path, watch-folder ingestion, and the
  retention execution itself. These need their own passes with appropriate fixtures.
- Any behaviour requiring two people at once; the deployment assumes one human user.

### Method caveat

Three early "click did nothing" observations were tool artifacts: the target element
was outside the viewport or the page was scrolled. Each was retested and the product
behaved correctly; only findings confirmed after retest are recorded above.
