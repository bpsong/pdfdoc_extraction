# Pipeline cleanup options

Status: historical options proposal. The approved implementation is archive and
hide plus independent processing-data cleanup. Permanent pipeline deletion,
physical-file deletion, and compaction remain deferred. See
[implementation tasks](tasks-pipeline-archive-cleanup.md), the current
[retention and API reference](../docs/pipeline_retention_admin_guide.md), and the maintained
[administrator guide](../docs/user_guide.md#433-pipeline-configuration).

## Behavior when options were proposed

The pipeline administration page supports active, inactive, and archived
templates. It has no permanent-delete endpoint or button. Inactive templates
are unavailable for new uploads and watch-folder ingestion, but their versions
remain available to documents already assigned to them.

Archiving requires an inactive template and no enabled watch-folder bindings.
It is terminal: the template cannot be restored or published again. Published
versions, historical records, and pinned execution remain available. The
editor currently includes archived templates in its selector, so archiving
does not yet remove visual clutter there.

Published versions and their review-schema dependencies have database triggers
that prohibit deletion. Batches, documents, task runs, manual-split decisions,
and watch-folder bindings also reference exact pipeline versions. Clearing or
reassigning historical references would change processing attribution and can
break review resume or queued work.

## Options

| Option | Suitable pipelines | Watch folders | Existing documents and files |
| --- | --- | --- | --- |
| Archive and hide by default (recommended) | Inactive templates, including ones with published versions or history | Require explicit pause, reassignment, unbind, or retirement of enabled bindings first | Keep versions, history, review resume, queued work, and all files |
| Permanently delete an unused draft | Inactive templates with no published versions and no references | Block if any binding still references the template | Remove only the draft and template; keep the audit event; no filesystem deletion |
| Separate retention cleanup | A future, explicitly scoped data-retention requirement | Resolve bindings before any removal | Requires its own rules for history, reviews, jobs, exports, and shared files; changes the current version-immutability policy if published definitions are removed |

Keeping a pipeline inactive remains the reversible choice when it may be used
again. Archive should explicitly explain its terminal behavior. A reversible
archive would require a separate lifecycle decision and tests.

## Recommended admin interaction

1. Add an **Archive pipeline** action for inactive templates and exclude
   archived entries from the ordinary selector. Add **Show archived** so an
   administrator can inspect old definitions or clone their published versions.
2. Before archiving, show an impact preview with published-version count,
   enabled/paused/retired binding counts, document and batch counts, queued or
   running jobs, and pending reviews. Explain that existing work continues on
   its pinned version and that no source or output files are deleted.
3. List blocking watch folders with links to their settings. Let the admin
   explicitly pause, reassign, unbind, or retire them. Reassignment affects
   future intake only. Pausing/unbinding keeps the path reserved; retirement
   permits a new binding to reuse it while preserving earlier batch references.
   Explain that incoming PDFs accumulate when a folder is paused.
4. Offer **Delete unused draft** only for an inactive template with zero
   published versions and zero references. When blocked, show the reason and
   offer archiving for templates with versions. Do not silently remove bindings,
   historical documents, review schemas, or business artifacts.
5. Require a final confirmation naming the pipeline and the operation. Record
   the operation in the existing audit log. Preserve historical template keys
   on archived templates; define key-reuse behavior explicitly for deleted
   drafts rather than implying that a new template restores an old identity.

The impact preview is advisory. Services must recheck lifecycle and references
within the same immediate SQLite transaction as the mutation, so another admin
cannot publish, activate, or create a dependency between the preview and delete.
Use repositories for table mutations, a service for the cross-table policy,
admin-only authenticated/CSRF-protected APIs, and the production `web/` UI.

No pipeline cleanup action should delete physical directories or PDFs. A
separate retention feature must account for shared paths and registered artifact
ownership before it can remove files. Existing audit history is retained.

## Verification required for implementation

- Unused inactive draft deletion succeeds and writes an audit event atomically.
- Active, published, bound, and historically referenced templates cannot be
  permanently deleted; failure leaves all records unchanged.
- Archiving is blocked by enabled bindings; paused and retired bindings retain
  their identity and historical batch links.
- Documents, reports, queued execution, and review resume still resolve their
  original versions after archiving. No historical assignment is rewritten.
- Preview/delete races are rejected; operator access and missing CSRF tokens
  cannot mutate lifecycle state.
- Browser tests cover confirmations, blockers, empty selectors, archive filters,
  preserved unsaved edits, and clear success/failure feedback.

## Relevant implementation references

- `modules/services/pipeline_template_service.py`: lifecycle and publication.
- `modules/services/pipeline_definition_service.py`: pinned execution after archival.
- `modules/services/ingress_binding_service.py`: binding lifecycle and references.
- `modules/db/repositories.py`: persistence and binding reference checks.
- `modules/db/schema.sql`: immutable versions and foreign-key constraints.
- `modules/api_router.py`: versioned admin API and admin authorization.
- `web/templates/pipeline_config.html`: production pipeline administration controls.
- `web/static/js/pipeline_config.js`: metadata saving and editor orchestration.
- `docs/watch_folder_admin_reference.md`: path reservation and retirement behavior.

## Related rename fix delivered

Metadata saves previously committed the change and then reloaded the full
editor. A failed follow-up request could display an error after a successful
save, and a successful reload discarded unsaved task edits. Metadata now
patches only the edited field, updates the selector from the save response,
and shows success without reloading the editor.

Changed files:

- `web/static/js/pipeline_config.js`: save metadata without resetting draft state.
- `web/static/js/pipeline-config/index.js` and
  `web/templates/pipeline_config.html`: advance the pipeline module asset version.
- `test/visual/test_pipeline_metadata_visual.py`: browser regressions for
  retained edits/selection and unavailable auxiliary resources.
- `test/integration/test_versioned_pipeline_api.py`: verify renaming preserves
  identity, the draft, and immutable versions.
- `test/integration/test_versioned_admin_pages.py` and
  `test/visual/test_pipeline_controller_modules.py`: verify current module wiring.
- `docs/user_guide.md`: document metadata autosave and draft preservation.
- This proposal: describe cleanup options and their consequences.

Verification from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\integration\test_versioned_pipeline_api.py test\integration\test_versioned_admin_pages.py test\visual\test_pipeline_controller_modules.py test\visual\test_pipeline_metadata_visual.py test\services\test_pipeline_template_service.py --tb=short
git diff --check
```

Result: 30 tests passed; diff whitespace checks passed. A separate
agent-browser check against a temporary synthetic app confirmed that renaming
updates the selector and preserves an unsaved task label. No live provider
requests or developer runtime data were used. The full pytest suite and
Pyright were not run for this scoped frontend fix. No CSS build was required
because utility classes, Tailwind input, and frontend packages did not change.
