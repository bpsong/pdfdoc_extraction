# Provision accounts and recover administrator access

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Account provisioning and recovery

#### First-Time Account Setup

Before the first login, open PowerShell in the project folder and run:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml
```

The tool asks for an administrator password and an operator password, then asks you to confirm each one. Setup stops if the accounts already exist; do not use the reset option for routine setup.

For an upgrade from an older installation, an administrator may import the existing administrator bcrypt hash while setting a new operator password:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml --legacy-config config.yaml
```

After a successful migration, remove the obsolete `authentication` section from the runtime YAML.

#### Recover Access When the Administrator Cannot Sign In

Use the setup tool's reset option only when the administrator password is unavailable:

```powershell
.\.venv\Scripts\python.exe tools\setup_users.py --config config.yaml --reset
```

The tool asks for new passwords and replaces the credentials for **both** fixed accounts. Run it against the same configuration file, and therefore the same `database.path`, used by the application. After the reset, test both accounts before returning the system to normal use.


## Verify and hand back access

The tool operates on the configured SQLite database. Confirm the intended YAML
and database before provisioning or resetting. Use secure interactive prompts;
keep passwords/hashes out of command arguments, logs, screenshots and commits.

After recovery, test admin and operator login and arrange secure distribution
of both new passwords. Existing sessions for changed users are invalidated.
Routine changes belong in the admin **Users** screen, described in
[accounts and settings](../admin/accounts-and-settings.md).
