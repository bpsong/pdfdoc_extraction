# Validate settings and inspect administrative history

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

## Validate the draft you are changing

Use **Validate** inside **Pipeline** or **Review Forms** to check that draft.
Read each finding, select the affected field where offered, correct it and
validate again. Save and publish after resolving blocking findings. In both
editors, Validate saves unsaved draft edits before checking the saved revision.
Validation does not repair the draft, publish it or run a sample PDF.

| Finding or outcome | What an Admin should do |
| --- | --- |
| Blocking error | Correct the indicated task/field or missing dependency; save and validate again. Publication remains blocked. |
| Warning | Decide whether the reported situation is intentional. For example, duplicate output tasks may be deliberate; a questionable task order still needs checking. |
| No blocking findings | Proceed to publication and controlled document testing. This does not establish extraction accuracy, provider reachability or usable output. |
| Missing/inactive review form | Publish and activate the form, then choose its exact published version in Review Gate. |
| Input/output/runtime-limit finding | Read the extraction guide's limits. Change only settings that preserve required evidence and fit the deployment; ask IT about memory/model capacity. |

After any draft edit, save/check that revision again. Record the published
pipeline and form versions used in acceptance so later results can be compared.
For a complete acceptance matrix, see
[Verify before routine use](managing-pipelines.md#verify-before-routine-use).

The separate **Validation** page provides additional checks for IT/support.
Its **Check config.yaml** action checks deployment configuration; it does not
perform the same complete check as validating every pipeline draft. Leave
advanced options at their defaults unless support gives you specific instructions.

## Inspect the task catalog

**Task Catalog** lists available processing steps. Search for a step and check
whether it is **Importable**. **Add in Pipeline** opens the editor; you still
need to add and configure the task in the draft. Give support the task name if
the app cannot load it. **Importable** does not check whether Ollama is running,
a model is installed or a cloud connection accepts a document. Compare the
catalog with [the Admin task guide](task-guide.md) for selection, prerequisites,
ordering and concrete setup steps. Custom task availability depends on deployment
approval; arrange that with maintainers rather than adding implementation names.

## Inspect administrative changes

1. Open **Audit Log**.
2. Filter by **Event Type**, **User**, **From** or **To** and select **Apply**.
3. Select **Details** on the relevant entry.
4. Use **Previous**, **Next**, **Clear** or **Refresh** as needed.

This screen displays selected administrative events. An empty result does not
prove that no change occurred; ask support for a fuller investigation when
needed. Use **Reports** for document-processing history.

Record the affected pipeline/form/folder, its version, the action, time and
message when requesting help. Use an approved channel for any sensitive details.
