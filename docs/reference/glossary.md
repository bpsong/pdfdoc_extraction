# Shared terminology

| Item | Value |
| --- | --- |
| Audience | All documentation readers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

| Term | Meaning |
| --- | --- |
| Operator | Account used to submit documents, monitor work and complete review |
| Administrator | Account that also manages app configuration, forms, folders and passwords |
| IT support | Documentation audience responsible for deployment and recovery; not an additional app role |
| Batch | Group of documents accepted together |
| Document | One accepted PDF or a document created by splitting a source |
| Pipeline | Ordered processing steps for a document type |
| Task | One operation in a pipeline |
| Draft | Editable working copy of pipeline/form settings |
| Published version | Fixed numbered settings used by accepted work |
| Review form | Fields and controls an operator uses to check extracted data |
| Field key | Stable name connecting extraction, review and output |
| Watch-folder binding | Saved incoming-folder assignment to an exact pipeline version |
| Artifact | A retained source, split PDF, archive or export recorded for a document |
| Claim | Temporary ownership of an item being reviewed |
| Cleanup | Removal of eligible processing history; physical files are retained |

## Technical terms

| Term | Meaning |
| --- | --- |
| Lease | Time-bounded worker claim on a durable processing job |
| Fan-out | Creation of independently processed child documents from a split |
| Fan-in | Aggregation of child/leaf outcomes into their source's state |
| Pinned version | Exact recorded pipeline/form identity used without a latest-version fallback |
| Secret alias | Named reference to a deployment-owned credential |
| CSRF token | Request token paired with the authenticated browser cookie for protected writes |

Use the [architecture state model](../architecture/workflow-and-state.md) for
exact transitions and the [Operator guide](../operator/README.md) for everyday actions.
