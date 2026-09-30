# Three-Machine Deployment

This is the first operational topology for MSConnect: one web server, one uploader/watcher host, and one processor host. All hosts must see the same raw and results storage paths logically, even if the host mount paths differ.

Compose services use `restart: unless-stopped`. Processor jobs use renewable API leases so outages do not leave work permanently assigned, and watchers wait for stable file or vendor-directory fingerprints before importing an acquisition.

For Linux hosts, `ops/install-msconnect-node.sh` installs a role-specific systemd
unit. Systemd owns boot ordering and starts the selected Compose services; Compose
owns container restart and health recovery. This keeps the server, watcher, and
processor independently rebootable without giving any node direct database access.

For a method-development lab or facility deployment, use the production
overlay and durable Postgres. SQLite is suitable only for local development
and single-process demonstrations.

## Roles

- `server`: runs `web` and `nginx`, owns migrations, admin UI, API, Postgres access, media, and static files.
- `uploader-watcher`: mounts the incoming vendor RAW share read-only, copies files into managed raw storage, and reports imports to the API.
- `processor`: claims queued jobs whose required engine matches its `MSCONNECT_PROCESSOR_ENGINE`, runs tools, writes results/artifacts, and reports completion.

Use `docs/env.server.example`, `docs/env.watcher.example`, and `docs/env.processor.example` as starting points. Replace tokens, hostnames, storage paths, and the signed-upload base URL before running long-lived services.

## Shared Storage Contract

- `INCOMING_RAW_ROOT`: drop zone for vendor RAW files or vendor directories, mounted read-only for watcher containers.
- `RAW_FILE_STORAGE_ROOT`: immutable managed raw-file storage. Watchers write here; processors read here.
- `RESULTS_ROOT`: job logs, tables, runtime manifests, reports, derivatives, and temporary job workspaces.
- `PROCESSOR_SHARED_STORAGE_ROOT`: shared references, workflows, libraries, and licensed-tool handoff folders.

Vendor RAW directories such as `.d` folders are imported as a single raw path. Archive/restore state is tracked through `RawFileArchive`; the archive worker and `verify_archives --restore-test` preserve the original storage path, archive path, checksum, compression, and status. Restore verification rejects unsafe ZIP traversal and symlink entries.

## Server

```sh
cp docs/env.server.example .env
docker compose up -d --build web nginx
curl -f http://localhost/readyz/
```

Before the first `up`, set `MSCONNECT_BOOTSTRAP_SUPERUSER_USERNAME`,
`MSCONNECT_BOOTSTRAP_SUPERUSER_EMAIL`, and
`MSCONNECT_BOOTSTRAP_SUPERUSER_PASSWORD` in `.env`. The web entrypoint creates
that account after migrations when the database has no superuser. It never
resets an existing account; use Django admin or `manage.py changepassword` for
later changes.

To make the server start automatically after a host reboot:

```sh
sudo ops/install-msconnect-node.sh --role server \
  --project-dir /opt/msconnect2 --env-file /opt/msconnect2/.env
```

Before starting the production overlay, run the environment preflight. It
requires Postgres, the explicit production flag, non-default agent secrets,
and absolute host paths for every persistent application and data mount:

```sh
./scripts/check-production-env.sh /opt/msconnect2/.env
```

Only the server should run migrations. The watcher and processor use the API and shared storage; they do not need direct database access.

### Production Postgres deployment

Create one independent deployment directory per site. The database path,
raw/results/archive/backup paths, Compose project name, tokens, and env file
must not be shared between the method-development lab and the facility pilot.

Set these values in the deployment env file:

```sh
DJANGO_DB_PASSWORD=<unique-long-secret>
DJANGO_SECRET_KEY=<unique-long-secret>
DJANGO_ALLOWED_HOSTS=msconnect-methodlab.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://msconnect-methodlab.example
MSCONNECT_PRODUCTION=1
# For method-lab validation, use the CI image for a reviewed main commit;
# production should use the promoted immutable digest or version tag.
MSCONNECT_IMAGE=docker.io/rtklabgroup/msconnect:main-<full-git-sha>
POSTGRES_DATA_HOST_PATH=/srv/msconnect-methodlab/postgres
MSCONNECT_DATA_HOST_PATH=/srv/msconnect-methodlab/data
MSCONNECT_MEDIA_HOST_PATH=/srv/msconnect-methodlab/media
INCOMING_RAW_HOST_PATH=/srv/msconnect-methodlab/incoming
RAW_STORAGE_HOST_PATH=/srv/msconnect-methodlab/raw
RESULTS_HOST_PATH=/srv/msconnect-methodlab/results
PROCESSOR_SHARED_HOST_PATH=/srv/msconnect-methodlab/shared
ARCHIVE_HOST_PATH=/srv/msconnect-methodlab/archive
BACKUP_HOST_PATH=/srv/msconnect-methodlab/backup
```

Before starting the stack, run the preflight. It validates the deployment
secrets and storage paths without printing their values:

```sh
scripts/check-production-env.sh /opt/msconnect-methodlab/.env
```

Create a custom-format database backup from the Postgres service. The helper
writes to a temporary file first and only publishes it after `pg_dump` succeeds:

```sh
sudo ops/backup-msconnect-postgres.sh \
  --project-dir /opt/msconnect-methodlab \
  --env-file /opt/msconnect-methodlab/.env \
  --project-name msconnect-methodlab \
  --output /srv/msconnect-methodlab/backup/database/msconnect-$(date +%Y%m%dT%H%M%S).dump
```

For a restore drill, provision an isolated Postgres database or temporary
deployment, then use the safe restore helper. It creates a new target database
and refuses to restore over the configured live database:

```sh
sudo ops/restore-msconnect-postgres.sh \
  --project-dir /opt/msconnect-methodlab \
  --env-file /opt/msconnect-methodlab/.env \
  --project-name msconnect-methodlab \
  --input /srv/msconnect-methodlab/backup/database/msconnect-latest.dump \
  --target-database msconnect_restore_20260917
```

Point an isolated validation web service at the new database, run
`python manage.py migrate --check`, and record the resulting readiness response.
The helper never uses `--clean` against the live facility database.

Start the stack with an explicit Compose project name:

```sh
docker compose -p msconnect-methodlab \
  -f docker-compose.msconnect2.server.yml \
  -f docker-compose.production.yml up -d web nginx postgres
docker compose -p msconnect-methodlab \
  -f docker-compose.msconnect2.server.yml \
  -f docker-compose.production.yml exec web python manage.py migrate
```

Use a different project name and a completely different set of storage paths
for the facility deployment. Only the server runs migrations; watcher and
processor nodes communicate through the API and shared storage.

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

For direct upload from a completed acquisition folder, set
`MSCONNECT_UPLOAD_PROJECT_ID` and `MSCONNECT_UPLOAD_SOURCE_ROOT` in the agent
environment and install the same task in direct-upload mode:

```powershell
.\ops\install-msconnect-watcher.ps1 `
  -ProjectDir C:\MSConnect `
  -EnvFile C:\MSConnect\.env `
  -PythonExe C:\MSConnect\.venv\Scripts\python.exe `
  -Mode direct-upload `
  -TaskName "MSConnect Direct Uploader"
```

The direct uploader waits for stable `.raw` files and `.d` directories, uploads
in resumable chunks, verifies a SHA-256 checksum, and lets the server match the
basename to the frozen worklist. It does not delete or modify the instrument
acquisition source.

For multiple direct-upload instruments, configure a distinct token for each
agent using `MSCONNECT_WATCHER_TOKENS=instrument-label=token,...` on the server
and put only that instrument's token in its Windows `.env`. The server records
the token label in the watcher heartbeat and upload metadata; rotating one
instrument token does not require changing the others.

The task starts at boot, runs as `SYSTEM`, retries after process failure, and
writes timestamped logs under `C:\ProgramData\MSConnect\logs`. Keep the incoming
instrument share read-only and grant the service account write access only to the
managed raw/results roots. The same API lease and file-stability safeguards apply
regardless of whether the watcher runs in Linux Compose or Windows Python.

For a host-side Compose rollout, use the provided release command. It updates
only `MSCONNECT_IMAGE`, pins a supplied digest, pulls the selected services,
runs migrations on a server, waits for `/readyz/`, and restores the previous
environment/configuration if the rollout fails:

```sh
MSCONNECT_PROJECT_DIR=/opt/msconnect-methodlab \
MSCONNECT_ENV_FILE=/opt/msconnect-methodlab/.env \
MSCONNECT_COMPOSE_PROJECT=msconnect-methodlab \
MSCONNECT_COMPOSE_SERVICES="web nginx" \
  /opt/msconnect-methodlab/ops/apply-msconnect-release.sh \
  2026.09.17 registry.example.org/msconnect/msconnect \
  sha256:<64-hex-digest>
```

The command is intentionally host-side; do not mount the Docker socket into
application containers just to enable upgrades. `MSCONNECT_UPGRADE_HOOK` is
available only for agents that run directly on the host (including a native
Windows watcher). The hook receives release version, image, and digest as
three positional arguments, is invoked without a shell, and has a 15-minute
timeout. A non-zero result leaves the node in `error` for operator review.

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
