# Three-Machine Deployment

This is the first operational topology for MSConnect: one web server, one uploader/watcher host, and one processor host. All hosts must see the same raw and results storage paths logically, even if the host mount paths differ.

## Roles

- `server`: runs `web` and `nginx`, owns migrations, admin UI, API, SQLite data, media, and static files.
- `uploader-watcher`: mounts the incoming vendor RAW share read-only, copies files into managed raw storage, and reports imports to the API.
- `processor`: claims queued jobs whose required engine matches its `MSCONNECT_PROCESSOR_ENGINE`, runs tools, writes results/artifacts, and reports completion.

Use `docs/env.server.example`, `docs/env.watcher.example`, and `docs/env.processor.example` as starting points. Replace tokens, hostnames, and storage paths before running long-lived services.

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

Only the server should run migrations. The watcher and processor use the API and shared storage; they do not need direct database access.

## Watcher

On the uploader/watcher host, mount the incoming instrument share and managed raw/results shares, then run either the Compose `watcher` service or the management command directly:

```sh
python manage.py check_agent_runtime --role watcher --write-test
python manage.py run_watcher_agent --match-run-by-name
```

Worklists are the queue source of truth. Upload/import the worklist before acquisition when possible so expected filenames exist before the watcher sees files. The watcher matches expected filename first through the API path and run-name fallback second.

## Processor

Start one processor per engine identity:

```sh
MSCONNECT_PROCESSOR_ENGINE=diann MSCONNECT_AGENT_NAME=diann-1 python manage.py check_agent_runtime --role processor --engine diann --write-test
MSCONNECT_PROCESSOR_ENGINE=diann MSCONNECT_AGENT_NAME=diann-1 python manage.py run_processor_agent --engine diann
```

Jobs with `parameters.adapter` or `parameters.required_engine` only claim on compatible nodes. Generic command pipelines without an adapter remain claimable by the default `processor` node for local smoke tests.

## Smoke Test

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

Back on the server:

```sh
docker compose exec web python manage.py verify_e2e_smoke_fixture --code E2E-THREE-MACHINE
```
