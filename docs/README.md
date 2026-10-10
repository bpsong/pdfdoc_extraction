# PDF processing documentation

| Item | Value |
| --- | --- |
| Audience | Operators, administrators, architects, developers and IT support |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

Choose the reading path that matches your work. **Operator** and **admin** are
the application's two fixed accounts. Architect, developer and IT support are
documentation audiences, not additional application roles.

| I need to… | Start here |
| --- | --- |
| Submit PDFs, check results or complete reviews | [Operator guide](operator/README.md) |
| Configure processing, review forms, folders or passwords | [Application Admin guide](admin/README.md) |
| Understand boundaries, state and architectural tradeoffs | [Architecture overview](design_architecture.md) |
| Maintain or extend the source code | [Developer guide](developer/README.md) |
| Install, monitor, upgrade or recover a deployment | [IT Support guide](it-support/README.md) |
| Look up exact parameters, formats or API contracts | [Technical reference](reference/README.md) |
| Find earlier assessments, test evidence or documents | [Historical records](history/README.md) |

The [architecture reading path](architecture/README.md) indexes the detailed
architecture topics. Each audience guide links its own complete page set.

## Shared authoritative sources

- [Standard task creation guidelines](../tasks/standard_task_creation_guidelines.md)
- [Config-check CLI reference](../tools/config_check/README.md)
- [Config-check finding catalog](../tools/config_check/examples/ERROR_CODES.md)

## Maintain the documentation

Keep screen procedures with their audience and exact technical contracts in
Reference. Link shared definitions rather than copying them into each guide.
Explain app terms for operators/admins; keep code and deployment commands in
Developer, IT Support or Reference. Coordinate application-admin and support
handoffs for folder access, connections, maintenance and recovery.

Maintained pages identify audience, owner, status, applicability and last
verification basis. Update the verification date only after checking relevant
content against the implementation. A source review is distinct from a live
deployment/provider check. Ordinary text edits are recorded in Git. Record
behaviour changes, affected readers and required actions under `history/changes/`.
Significant architectural decisions include rationale and supersession links.
Historical evidence retains its original date, scope and assessed revision.

The [documentation map](documentation-map.json) inventories current pages,
original-source destinations and compatibility links. Verify navigation and
archive integrity from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -v test\tools\test_documentation_structure.py
```

The original mixed guides are retained in the
[2026-10-10 snapshot](history/archive/2026-10-10/README.md).
