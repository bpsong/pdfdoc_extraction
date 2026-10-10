# PDF processing system architecture

| Item | Value |
| --- | --- |
| Audience | Software architects, technical leads and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

This is the stable architecture entry point for the current production app.
It describes implemented boundaries; proposed work remains in explicitly
labelled design/task documents. The normal topology is a Windows supervisor,
web subprocess, durable processing worker and watch-folder coordinator sharing
one SQLite database and configured filesystem paths.

## Architecture at a glance

- SQLite owns workflow state, configuration templates, drafts and exact published versions.
- The filesystem holds large artifacts; database records identify their role and path.
- The parent process owns normal migration and supervises web and worker startup.
- Only the worker normally executes queued root workflows. Review continuations
  have their own application-managed dispatch and recovery boundaries.
- Documents, children and reviews retain their selected pipeline/form versions.
- Routes handle HTTP concerns, services coordinate business operations, and
  repositories own table-specific persistence.
- Production UI lives under `web/`; prototypes are separate from runtime behaviour.

## Reading path

1. [Runtime topology and boundaries](architecture/runtime-and-boundaries.md)
2. [Workflow execution and state](architecture/workflow-and-state.md)
3. [Persistence and artifacts](architecture/persistence-and-artifacts.md)
4. [Configuration and versioning](architecture/configuration-and-versioning.md)
5. [Security and trust](architecture/security-and-trust.md)
6. [Decisions and constraints](architecture/decisions-and-constraints.md)

For source-level changes, use the [Developer guide](developer/README.md) and
[canonical task standards](../tasks/standard_task_creation_guidelines.md).
For deployment recovery, use [IT Support](it-support/README.md). Screen-based
instructions are in [Operator](operator/README.md) and [Admin](admin/README.md).
The pre-reorganisation document is preserved in the
[2026-10-10 snapshot](history/archive/2026-10-10/docs/design_architecture.md).

## Previous section links

<a id="document-status"></a>

[Document status](design_architecture.md)

<a id="contents-and-reading-paths"></a>

[Contents and reading paths](design_architecture.md)

<a id="start-here-for-a-codebase-takeover"></a>

[Start here for a codebase takeover](design_architecture.md)

<a id="key-architectural-decisions"></a>

[Key architectural decisions](architecture/decisions-and-constraints.md#key-architectural-decisions)

<a id="invariants-to-preserve"></a>

[Invariants to preserve](architecture/decisions-and-constraints.md#invariants-to-preserve)

<a id="runtime-topology"></a>

[Runtime topology](architecture/runtime-and-boundaries.md#runtime-topology)

<a id="component-boundaries"></a>

[Component boundaries](developer/codebase-map.md#component-boundaries)

<a id="frontend-module-boundaries"></a>

[Frontend module boundaries](architecture/runtime-and-boundaries.md#frontend-module-boundaries)

<a id="service-ownership-map"></a>

[Service ownership map](developer/codebase-map.md#service-ownership-map)

<a id="representative-request-traces"></a>

[Representative request traces](developer/execution-walkthroughs.md#representative-request-traces)

<a id="ingestion-and-workflow-execution"></a>

[Ingestion and workflow execution](architecture/workflow-and-state.md#ingestion-and-workflow-execution)

<a id="ingestion-paths"></a>

[Ingestion paths](architecture/workflow-and-state.md#ingestion-paths)

<a id="watch-folder-administration"></a>

[Watch-folder administration](architecture/configuration-and-versioning.md#watch-folder-administration)

<a id="pipeline-construction"></a>

[Pipeline construction](architecture/configuration-and-versioning.md#pipeline-construction)

<a id="task-and-context-contract"></a>

[Task and context contract](developer/task-development.md#task-and-context-contract)

<a id="glossary"></a>

[Glossary](reference/glossary.md)

<a id="state-model"></a>

[State model](architecture/workflow-and-state.md#state-model)

<a id="human-review"></a>

[Human review](architecture/workflow-and-state.md#human-review)

<a id="split-fan-out-and-fan-in"></a>

[Split fan-out and fan-in](architecture/workflow-and-state.md#split-fan-out-and-fan-in)

<a id="persistence-and-artifacts"></a>

[Persistence and artifacts](architecture/persistence-and-artifacts.md#persistence-and-artifacts)

<a id="configuration-architecture"></a>

[Configuration architecture](architecture/configuration-and-versioning.md#configuration-architecture)

<a id="frontend-and-ui-architecture"></a>

[Frontend and UI architecture](developer/frontend-development.md#frontend-and-ui-architecture)

<a id="rendering-and-data-flow"></a>

[Rendering and data flow](developer/frontend-development.md#rendering-and-data-flow)

<a id="frontend-layers"></a>

[Frontend layers](developer/frontend-development.md#frontend-layers)

<a id="browser-security"></a>

[Browser security](developer/frontend-development.md#browser-security)

<a id="frontend-constraints"></a>

[Frontend constraints](developer/frontend-development.md#frontend-constraints)

<a id="api-authentication-and-trust-boundaries"></a>

[API, authentication, and trust boundaries](architecture/security-and-trust.md#api-authentication-and-trust-boundaries)

<a id="errors-recovery-and-observability"></a>

[Errors, recovery, and observability](architecture/workflow-and-state.md#errors-recovery-and-observability)

<a id="testing-and-verification"></a>

[Testing and verification](developer/testing-and-verification.md#testing-and-verification)

<a id="known-architectural-debt"></a>

[Known architectural debt](architecture/decisions-and-constraints.md#known-architectural-debt)

<a id="debugging-checklist"></a>

[Debugging checklist](developer/execution-walkthroughs.md#debugging-checklist)

<a id="safe-change-workflow"></a>

[Safe-change workflow](developer/backend-development.md#safe-change-workflow)

<a id="migration-development-workflow"></a>

[Migration development workflow](developer/database-migrations.md#migration-development-workflow)

<a id="related-documentation"></a>

[Related documentation](design_architecture.md)
