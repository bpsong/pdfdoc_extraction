# Start, stop and restart the application

| Item | Value |
| --- | --- |
| Audience | IT support and deployment owners |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Production application; SQLite schema 9 |

## Before planned maintenance

Ask admins to pause incoming folders and operators to stop new submissions.
Record current batches, pending reviews and active work. A paused folder stops
new intake; it does not cancel accepted work. Agree the maintenance window and
recovery plan, including any provider call that may already be running.

## Starting and Stopping Services

**Starting the main processing service (Windows):**

1. Open PowerShell.
2. Navigate to the project root folder.
3. Run the following command to start the system:

    ```
    .\.venv\Scripts\python.exe main.py
    ```

4. The system will begin scanning enabled SQLite watch-folder bindings and
   processing files. By default, this command also starts the web interface,
   which will be accessible at `http://localhost:8000` (or the host/port
   configured in `config.yaml`).

**Starting only watch-folder processing (without Web Interface):**

If you only need the watch folder functionality and do not wish to run the web interface, use the `--no-web` argument:

    ```
    .\.venv\Scripts\python.exe main.py --no-web
    ```

This mode still starts the supervised processing worker and watch-folder
coordinator, but browser upload, review, reports, and administration are
unavailable. A web-only process cannot scan watch folders.

**Stopping the service:**

To stop the coordinator and web interface, press `Ctrl+C` in the terminal where
`main.py` is running. This requests an orderly shutdown but does not guarantee
that an in-progress provider job finishes first; follow the recovery checks afterward.


## Select a non-default configuration

```powershell
.\.venv\Scripts\python.exe main.py --config-path path\to\config.yaml
```

Start through `main.py` for the normal topology. The parent migrates and then
starts web and worker children. A web-only process does not scan folders or
execute queued root work. A directly launched web process verifies schema by
default; it is not a substitute for the normal migration owner.

## Graceful Shutdown and Error Recovery

To stop the system, press `Ctrl+C` in the terminal where `main.py` is running.
This asks the watch-folder coordinator, web server, and durable worker to stop,
then runs registered cleanup handlers. It does not guarantee that every
in-progress document finishes before the processes exit. An unexpected web,
worker, or coordinator exit stops the remaining components and returns a
nonzero process exit code. On Windows, the supervisor gives child processes a
bounded graceful-stop period before force-terminating their process trees.

For service monitoring, `GET /health/live` confirms that the web process can
respond and `GET /health/ready` returns `503` until the current supervised run
is ready. Administrators can use `GET /api/admin/runtime-health` for component,
heartbeat, watch-folder degradation, and database details.

After stopping or restarting:

1. Check the final shutdown messages in `app.supervisor.log` when using the
   default log base path.
2. Sign in and open **Processing Overview** and **Failures**.
3. Inspect any document that was processing when shutdown began.
4. Confirm whether its outputs were created before deciding to re-upload it.
5. Do not delete processing files or database records unless the document state and recovery need are understood.

If the system fails to start, check the supervisor and component logs, validate
`config.yaml`, confirm that the required watch and upload folders exist, and
verify folder permissions and provider connectivity. The Config Check tool
described in the config-check troubleshooting guide should be the first configuration diagnostic.


Use [incident runbooks](incident-runbooks.md) if accepted work does not continue.
Resume intake only after checking the intended configuration, component
readiness, relevant reviews, completed outputs and folder health.
