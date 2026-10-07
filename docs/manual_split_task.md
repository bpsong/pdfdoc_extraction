# Manual PDF split task

`standard_step.split.manual_split.ManualSplitTask` splits a PDF locally using
page boundaries chosen in the existing Review Queue. The PDF.js library and
worker are served by this application; page selection and splitting require
no cloud document service.

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

## Operator workflow

The queue retains its existing layout. Manual items show a **Manual split**
badge, page count, **Manual task** review signal, and **Claim & split** action.
Extraction rows continue to show confidence under **Review signal**.

The split form shows every page in vertical source order. Check the box
between two pages to split after the first page. Numbered purple markers
match the selected boundary in the split plan. Click a plan boundary to jump
to its checkbox. Pages render lazily to avoid keeping every large canvas in
memory. Zoom does not change the decision.

Claim before editing. **Save draft** persists selections without continuing
processing. **Confirm split** saves an immutable decision and applies it.
After the decision is saved, the form shows **Decision saved** and a
**View processing** link. You can leave the form while child workflows run;
submission does not wait for their extraction or subsequent review steps.
With no boundaries selected, **Continue without splitting** continues the
original document. Completed plans are available through queue History.

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
