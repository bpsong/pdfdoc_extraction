# Change backend behaviour

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Choose the owning layer

Routes in [api_router.py](../../modules/api_router.py) handle authentication,
request validation, service calls and response construction. Put cross-table
business invariants in the relevant service. Keep table-specific persistence
in [repositories.py](../../modules/db/repositories.py). Preserve transactions
when related state and audit events must commit together.

Add type hints, focused functions and concise Google-style docstrings for
non-obvious public behaviour. Use `Path` for filesystem work, preserve Windows
semantics, and catch specific exceptions with useful safe context.

## Preserve contracts

Use exact recorded pipeline/form versions for execution and resume. Do not
infer workflow state from filenames, status text files, `StatusManager` or the
compatibility `/api/files` and `/api/status/{file_id}` response shapes.
Register durable files through the artifact service when a document ID exists.
Keep secrets and document contents out of error responses and audit payloads.

When changing an API, update the service and browser caller together. Preserve
role checks, cookie/CSRF behaviour, security headers and same-origin PDF
preview restrictions. Test denied access as well as the successful path.

## Safe-change workflow

Update this architecture reference when a change alters process ownership,
state transitions, persistence boundaries, or trust contracts. For a new task,
also update the [task creation guidelines](../../tasks/standard_task_creation_guidelines.md)
when the shared task standard changes. Keep detailed operator procedures in a
focused guide and link it here rather than duplicating them.

- **New task:** inherit `BaseTask`, register the exact module/class pair, follow
  the [standard task guidelines](../../tasks/standard_task_creation_guidelines.md),
  and add task plus workflow tests.
- **Persistence:** update the schema/migration, repository, service, and
  integration tests together.
- **API:** keep request parsing and authorization in the router, put invariants
  in a service, and add API/security tests.
- **Production UI:** update the route, template, controller, and API contract
  together; run the focused visual test when rendering or interaction changes.
- **Pipeline behavior:** test the pinned-version path, review gate, resume, and
  split/fan-in behavior as applicable.
- **Configuration semantics:** test relative paths, malformed configuration,
  process-entry failures, and config-check behavior.
- **Startup or migration:** test idempotency, rollback/compensation, schema
  verification, and a fresh application startup.


For schema changes, follow [database migrations](database-migrations.md).
For new tasks, follow [task development](task-development.md).
Select meaningful neighbouring tests using [testing guidance](testing-and-verification.md).
