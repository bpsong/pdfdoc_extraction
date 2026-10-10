# Split task parameters and continuation contracts

| Item | Value |
| --- | --- |
| Audience | Developers, IT support and advanced configuration maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## split.llamacloud_split

- **type:** `"split.llamacloud_split"`
- **Purpose:** Optionally splits a source PDF into child PDF documents before downstream extraction and storage tasks run.
- **params:**
  - `enabled`: boolean. If `false`, the task records a skipped split result and the source document continues as a normal document.
  - `api_key`: required secret reference when the real LlamaCloud split adapter
    is used, for example `{ $secret: "llamacloud-primary" }`.
  - `configuration_id`: optional saved LlamaCloud split configuration ID.
  - `categories`: optional list of category definitions. Required when `configuration_id` is not provided.
  - `allow_uncategorized`: controls what LlamaCloud does with pages that do not match a configured category. The default is `"include"`; see the decision table below.
  - `fail_on_confidence_levels`: list of split confidence labels that cause the whole split task to fail before child documents are created. Default is `["low"]`.
  - `fail_on_unknown_category`: boolean. When `true`, blank, `other`, `uncategorized`, and disallowed category results fail the whole split task. Default is `true`.
  - `allowed_categories`: optional list of accepted category names. If omitted, inline `categories` are used as the allowed list.
  - `split_dir`: string, required. Destination for generated child PDFs. The
    task creates it when child PDFs are needed if the application account has
    the required filesystem permission. Whole-document continuation creates no
    split PDF.
  - `project_id` / `organization_id`: optional provider scoping values.
  - `poll_interval_seconds`: optional polling interval. Default is `1.0`.
  - `timeout_seconds`: optional timeout. Default is `7200.0`.
- **Behavior:**
  - Runs only for root/source documents; split child documents skip the split task.
  - Applies category/confidence policy and page validation before continuation or child creation.
  - When exactly one segment covers every source page once in source order,
    saves classification on the original document and continues at the next
    pipeline task, preserving its ID and PDF. Retries reuse a matching saved
    decision; review resume restores its classification.
  - Otherwise creates one child document record and one split PDF for each
    provider segment, including a single segment containing only some pages or
    changing page order.
  - Records split category, confidence, page range, and source metadata in SQLite.
  - When children are created, sets the parent/source document to
    `split_completed`, then child documents continue from the next pipeline task.
  - Fan-in recomputes the parent and batch status after child documents complete, fail, or enter review.
- **Ordering rules:**
  - Configure split before extraction, so child PDFs are extracted independently.
  - Configure the review gate after extraction, so it can evaluate extracted fields and confidence.

**Choosing how to handle unmatched pages:**

| Value | What LlamaCloud does | Effect in this application | When to use it |
|-------|----------------------|----------------------------|----------------|
| `"include"` | Returns unmatched pages in an `uncategorized` segment. | Pages are retained, but the default `fail_on_unknown_category: true` rejects that segment and fails the split before creating any children. | Use when retaining every page matters, after deciding whether uncategorized segments should fail or continue for review. |
| `"forbid"` | Forces every page into one of the defined categories. | No page is omitted, but a cover sheet, receipt, or other unexpected page may be assigned to the wrong category and processed as that document type. | Use only when the category list covers every page type you expect and has been tested with representative documents. |
| `"omit"` | Excludes unmatched pages from the split results. | Omitted pages do not become child documents and do not proceed to extraction, review, or export. | Use only when discarding unmatched pages is an explicit business decision. |

`"forbid"` does not mean “reject a document containing an unknown page.” For example, if `invoice` is the only category, every page must be labelled as an invoice even when a page is actually a cover sheet or supporting document.

Before enabling split processing for production documents:

1. Define categories in clear business language and include expected supporting pages.
2. Test all three policies with representative combined PDFs.
3. Decide whether low confidence or unknown categories should stop the whole source document.
4. Confirm in **Split Results** that every page that must be retained appears in a child document.
5. Configure the review gate to catch the split confidence levels that require an operator decision.

**Inline YAML configuration example:**

```yaml
tasks:
  split_documents:
    module: standard_step.split.llamacloud_split
    class: LlamaCloudSplitTask
    params:
      enabled: true
      api_key: { $secret: "llamacloud-primary" }
      categories:
        - name: "invoice"
          description: "Supplier invoice pages"
        - name: "supporting_document"
          description: "Delivery orders, receipts, or supporting pages"
      allow_uncategorized: "include"
      fail_on_confidence_levels:
        - "low"
      fail_on_unknown_category: true
      allowed_categories:
        - "invoice"
        - "supporting_document"
      split_dir: "data/app/split"
      poll_interval_seconds: 1.0
      timeout_seconds: 7200
    on_error: stop

pipeline:
  - split_documents
  - extract_document_data
  - store_metadata_json
```

For a saved LlamaCloud split configuration, set `configuration_id` instead of `categories` and `allow_uncategorized`. The confidence policy, allowed-category checks, output directory, and advanced provider settings remain local task behavior.

After fan-out, each child document is a **leaf document** because it is processed independently. Fan-in summarizes those child statuses for the source document and batch:

- **Processing** (`processing`): at least one child is still running.
- **Review required** (`review_required`): at least one child is waiting for or undergoing operator review.
- **Completed** (`completed`): every child completed successfully.
- **Completed with errors** (`completed_with_errors`): all children finished, with a mixture of successful and failed children.
- **Failed** (`failed`): every child failed.

## Pipeline setup

Add **Manual Split** before extraction in the production Pipeline editor.
Configure `enabled` (default `true`), a local `split_dir`, and `queue_name`
(default `default_review`). Publish and activate the pipeline. A pipeline may
contain one split step, either manual or cloud. The manual step requires no
API key, category configuration, or extraction review schema.

Typical order: Manual Split → Field Extraction → Review Gate → JSON Export.
Use local extraction and a local Prefect runtime for an entirely local
deployment. Selecting a later cloud extraction step still sends documents to
that provider.

## Execution and skips

| Input or decision | Review pause | Children / fan-out | Continuation |
| --- | --- | --- | --- |
| One-page PDF | None | None | Original document, next task |
| Disabled task | None | None | Original document, next task |
| Operator selects no boundaries | Until approval | None | Original document, next task |
| Operator selects boundaries | Until approval | One child per contiguous range | Children start after manual split |

The original source remains unchanged. Real split children retain their exact
pipeline version and upstream business context. Their PDFs are registered as
artifacts; their split confidence is absent, because a manual decision has no
model confidence. Existing leaf-based fan-in aggregates child reviews,
successes, and failures. Skips count as one continuing original leaf.

## Persistence and recovery

Schema version 8 adds `review_items.review_kind` and
`manual_split_decisions`. Existing reviews migrate to `extraction`.
Decisions pin the document, pipeline version, task run/index, source SHA-256,
page count, bounded business-context checkpoint, draft revision, actor, and
application phase. Boundaries are strict ordered integers in `1..N-1`.
Draft saves require the current claim and revision. Approval rechecks the
source. The browser cannot submit output paths or child identities.
Renewing a claim preserves unsaved selections, but a newer draft from another
session disables saving and approval until the operator reloads.

Approval is committed before continuation. Repeating an identical approval
does not create another decision or child set. **Retry continuation** on a
completed plan can retry unapplied accepted work with no active task attempt,
or dispatch queued children with no task runs. It does not replay started,
failed downstream, or completed workflows. Active or inconsistent attempts
require operator repair. A crash after claiming a child but before its flow
starts is deliberately treated as ambiguous. This is not a durable
exactly-once dispatch queue. Ordinary materialization failures compensate
new files and queued child rows; abrupt process termination can leave orphan
files that require storage reconciliation.

A claimed original continuation is also treated as active before its first
task run exists. Child workflows are loaded before claiming their documents,
so a loader failure leaves unstarted children queued and retryable. A failed
split application can be retried after successful runner cleanup, provided
no downstream task has started. Failed cleanup still blocks retry. Failed
split attempts remain in task history, but an accepted retry does not pass
their errors to the recovered children or later review continuations.

Authenticated, CSRF-protected endpoints:

- `POST /api/review/items/{id}/split/draft`
- `POST /api/review/items/{id}/split/complete`
- `POST /api/review/items/{id}/split/retry`

The first two accept `boundaries` and `expected_revision`; completion also
requires `action` (`split` or `skip`). Extraction correction endpoints reject
manual items. Completion returns HTTP `202` after the decision commits, with
`resume_scheduled: true`. This acknowledges the decision, not completion of
downstream processing. Continuation runs as a server background task after
the response is sent. The form refreshes the application phase separately.
Background dispatch is in-process rather than a durable job queue; an accepted
decision survives restart and remains subject to the recovery rules above.


Operators use [manual splitting](../../operator/manual-splitting.md).
Admins configure the task in [Pipeline](../../admin/managing-pipelines.md).
For incident handling use [IT runbooks](../../it-support/incident-runbooks.md).
