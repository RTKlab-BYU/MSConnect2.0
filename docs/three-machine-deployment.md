# Three-Machine Deployment

This is the first operational topology for MSConnect: one web server, one uploader/watcher host, and one processor host. All hosts must see the same raw and results storage paths logically, even if the host mount paths differ.

Compose services use `restart: unless-stopped`. Processor jobs use renewable API leases so outages do not leave work permanently assigned, and watchers wait for stable file or vendor-directory fingerprints before importing an acquisition.

For Linux hosts, `ops/install-msconnect-node.sh` installs a role-specific systemd
unit. Systemd owns boot ordering and starts the selected Compose services; Compose
owns container restart and health recovery. This keeps the server, watcher, and
processor independently rebootable without giving any node direct database access.

SQLite is the default database for the lightweight deployment. Use Postgres only if you need a multi-process or higher-concurrency upgrade.

## Roles

- `server`: runs `web` and `nginx`, owns migrations, admin UI, API, SQLite data, media, and static files.
- `uploader-watcher`: mounts the incoming vendor RAW share read-only, copies files into managed raw storage, and reports imports to the API.
- `processor`: claims queued jobs whose required engine matches its `MSCONNECT_PROCESSOR_ENGINE`, runs tools, writes results/artifacts, and reports completion.

Use `docs/env.server.example`, `docs/env.watcher.example`, and `docs/env.processor.example` as starting points. Replace tokens, hostnames, storage paths, and the signed-upload base URL before running long-lived services.

## Shared Storage Contract

- `INCOMING_RAW_ROOT`: drop zone for vendor RAW files or vendor directories, mounted read-only for watcher containers.
- `RAW_FILE_STORAGE_ROOT`: immutable managed raw-file storage. Watchers write here; processors read here.
- `RESULTS_ROOT`: job logs, tables, runtime manifests, reports, derivatives, and temporary job workspaces.
- `PROCESSOR_SHARED_STORAGE_ROOT`: shared references, workflows, libraries, and licensed-tool handoff folders.

Vendor RAW directories such as `.d` folders are imported as a single raw path. Archive/restore state is tracked through `RawFileArchive`; actual zip/restore automation should preserve the original storage path, archive path, checksum, compression, and status.

## Server

```sh
cp docs/env.server.example .env
docker compose up -d --build web nginx
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
curl -f http://localhost/readyz/
```

To make the server start automatically after a host reboot:

```sh
sudo ops/install-msconnect-node.sh --role server \
  --project-dir /opt/msconnect2 --env-file /opt/msconnect2/.env
```

Only the server should run migrations. The watcher and processor use the API and shared storage; they do not need direct database access.

### Optional Postgres upgrade

If you later need a true multi-host or higher-concurrency setup, set `DJANGO_DB_ENGINE=django.db.backends.postgresql` and the related DB credentials in the server env, then run the same migrations against Postgres. Keep the rest of the deployment unchanged.

## Watcher

On the uploader/watcher host, mount the incoming instrument share and managed raw/results shares, then run either the Compose `watcher` service or the management command directly:

```sh
python manage.py check_agent_runtime --role watcher --write-test
python manage.py run_watcher_agent --match-run-by-name
```

On a Linux watcher host, install its boot service with the same script and use an
env file containing the watcher paths and API token:

```sh
sudo ops/install-msconnect-node.sh --role watcher \
  --project-dir /opt/msconnect2 --env-file /opt/msconnect2/.env
```

For the intended Windows instrument computer, install the watcher as a built-in
Scheduled Task. Run PowerShell as Administrator from the repository checkout:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\ops\install-msconnect-watcher.ps1 `
  -ProjectDir C:\MSConnect `
  -EnvFile C:\MSConnect\.env `
  -PythonExe C:\MSConnect\.venv\Scripts\python.exe
```

The task starts at boot, runs as `SYSTEM`, retries after process failure, and
writes timestamped logs under `C:\ProgramData\MSConnect\logs`. Keep the incoming
instrument share read-only and grant the service account write access only to the
managed raw/results roots. The same API lease and file-stability safeguards apply
regardless of whether the watcher runs in Linux Compose or Windows Python.

Set `MSCONNECT_UPGRADE_HOOK` on any node that should apply releases automatically.
The executable receives three positional arguments: release version, image, and
digest. It should pull/replace the local service and return zero only after the
new runtime is ready; non-zero results leave the node in `error` for operator
review. The hook is invoked without a shell and has a 15-minute timeout.

Schedule the outage check on the server (for example every five minutes):

```sh
docker compose exec -T web python manage.py notify_stale_nodes
```

Use `--stale-seconds` and `--cooldown-seconds` to tune sensitivity. Alerts are
aggregated and recorded per node, so repeated scheduler runs do not flood email.

For a reboot-safe scheduler, install the provided systemd timer on the server:

```sh
sudo ops/install-msconnect-alerts.sh /opt/msconnect2 /opt/msconnect2/.env
systemctl list-timers msconnect-alerts.timer
```

The timer starts after boot and invokes the check through the web container every
five minutes.

Worklists are the queue source of truth. Upload/import the worklist before acquisition when possible so expected filenames exist before the watcher sees files. The watcher matches expected filename first through the API path and only falls back to run-name matching for compatibility.
When no worklist exists, the watcher stores the raw file and records a match exception for later classification instead of discarding it.
If the Django URL is not known in advance, set `MSCONNECT_API_DISCOVERY_HOSTS` so the agent can keep searching common hostnames until it finds the API.

## Processor

Start one processor per engine identity:

```sh
MSCONNECT_PROCESSOR_ENGINE=diann MSCONNECT_AGENT_NAME=diann-1 python manage.py check_agent_runtime --role processor --engine diann --write-test
MSCONNECT_PROCESSOR_ENGINE=diann MSCONNECT_AGENT_NAME=diann-1 python manage.py run_processor_agent --engine diann
```

Jobs with `parameters.adapter` or `parameters.required_engine` only claim on compatible nodes. Generic command pipelines without an adapter remain claimable by the default `processor` node for local smoke tests.
As with the watcher, processors can search common Django hostnames via `MSCONNECT_API_DISCOVERY_HOSTS` when the exact API URL is not fixed at deployment time.

## Smoke Test

For a fuller live-stack checklist that includes DIA-NN pickup, dashboard verification, and archive validation, see [docs/live-stack-smoke-runbook.md](live-stack-smoke-runbook.md).

From the server clone:

```sh
docker compose up -d --build web nginx
docker compose exec web python manage.py create_e2e_smoke_fixture --code E2E-THREE-MACHINE
```

From the watcher host:

```sh
python manage.py check_agent_runtime --role watcher --write-test
python manage.py run_watcher_agent --once --match-run-by-name
```

From the processor host:

```sh
python manage.py check_agent_runtime --role processor --engine processor --write-test
python manage.py run_processor_agent --once --engine processor
```

For a processor host, use `--role processor`; use `MSCONNECT_COMPOSE_SERVICES` in
the env file when the node should run a specific engine service (for example
`processor-diann`) instead of the default processor service. The archive worker
can be installed independently with `--role archive`.

Back on the server:

```sh
docker compose exec web python manage.py verify_e2e_smoke_fixture --code E2E-THREE-MACHINE
```
