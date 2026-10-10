# Develop database migrations

| Item | Value |
| --- | --- |
| Audience | Developers and maintainers |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Migration development workflow

The canonical structural schema is [`modules/db/schema.sql`](../../modules/db/schema.sql).
Structural upgrade logic belongs in [`modules/db/migrations.py`](../../modules/db/migrations.py);
startup orchestration and legacy YAML import belong in
[`startup_migration_service.py`](../../modules/services/startup_migration_service.py).
The structural migration module must remain free of application-service imports.
There is no general downgrade chain. For a migration change, use a temporary
database, verify the exact supported version and required tables, run startup a
second time to prove idempotency, and exercise legacy-import compensation when
the change touches YAML cutover.

The [safe-change workflow](backend-development.md#safe-change-workflow) is the canonical checklist
for extensions too. For tasks, also follow the [standard task guidelines](../../tasks/standard_task_creation_guidelines.md).


## Verification and release checklist

Use temporary database/config fixtures. Cover fresh initialization, upgrades
from affected prior versions, constraint preservation, failed-upgrade rollback,
and a second startup proving idempotency. Verify that children reject a missing,
older, newer or incomplete schema before serving work. Add YAML cutover
compensation tests when changing legacy import.

Update schema, migration, repositories, owning services and integration tests
together. Keep structural migrations free of application-service imports.
The current [schema version](../../modules/db/schema_version.py) is 9.
There is no supported general downgrade chain; release notes must describe
artifact compatibility and recovery from a consistent backup.

See [deployment and upgrades](../it-support/deployment-and-upgrades.md) for the
operational handoff and [testing](testing-and-verification.md) for commands.
