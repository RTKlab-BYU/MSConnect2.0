# MSConnect

MSConnect is an on-prem SDMS/LIMS scaffold for LC-MS proteomics. The MVP tracks organizational structure, users, projects, experiments, samples, runs, raw files, and peptide/protein result data.

## Stack

- Django
- SQLite
- Docker Compose
- nginx
- Watched-share raw file ingestion
- Repo-embedded watcher and processor agents

## Repository Layout

MSConnect follows a conventional Django project layout with a small extension layer for research tools:

```text
msconnect/              Django project settings, root URLs, WSGI/ASGI
core/                   Canonical LIMS/SDMS models, API, agent auth, processor job lifecycle
ingest/                 Raw-file discovery/import services and result-table import helpers
ui/                     Built React app mount and legacy compatibility URLs
frontend/               React/Vite source for /app/*
capabilities/           Optional researcher/tool Django apps
docker/                 Optional specialized processor image definitions
docs/                   Architecture notes and work logs
incoming/               Host-mounted watched-share input, ignored by git
raw-storage/            Host-mounted managed raw-file storage, ignored by git
results/                Host-mounted processing outputs/artifacts, ignored by git
```

The stable domain model lives in `core`: projects, samples, runs, raw files, processing jobs, derivatives, artifacts, protein/peptide IDs, and quants. New tools should integrate at that boundary instead of duplicating those concepts.

## Local On-Prem Run

1. Create the environment file:

```sh
cp .env.example .env
```

2. Build and start the stack:

```sh
docker compose up --build
```

The direct Django app is published at `http://localhost:8000/` by default. The nginx reverse proxy is published at `http://localhost:8080/` by default so local machines that already use port 80 do not block the stack.

3. Create an admin user:

```sh
docker compose run --rm web python manage.py createsuperuser
```

4. Open the Django admin:

```text
http://localhost/admin/
```

## Agent Services

The deployment now runs three repo-embedded application services from the same image:

- `web`: Django API/UI server
- `watcher`: watched-share raw-file ingestion agent
- `processor`: queued processing command runner

All three services stay in the same repo and can be deployed together from one tag and one image.

`watcher` and `processor` wait for the `web` healthcheck before starting, and their API client retries transient connection and HTTP 5xx errors. This keeps local three-container simulations from failing during Django migration/startup races.

Each component is a Django management command run from the same container image:

```sh
# Main API/UI server, normally run by docker compose service `web`
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn msconnect.wsgi:application --bind 0.0.0.0:8000

# Watched-share ingestion service, normally run by service `watcher`
python manage.py run_watcher_agent --match-run-by-name

# Processing worker service, normally run by service `processor`
python manage.py run_processor_agent

# One-shot utility examples
python manage.py index_mzml_spectra --project 6
python manage.py seed_pride_pxd053992 --import-now --limit 2
```

## Raw File Ingestion

The `watcher` service polls `INCOMING_RAW_ROOT`, copies recognized raw file paths into `RAW_FILE_STORAGE_ROOT`, and reports imports back to the main API.

Default host paths are:

- `./incoming` for files from the MS computer or mounted network share
- `./raw-storage` for immutable managed raw file storage
- `./data` for SQLite

Run one import pass manually:

```sh
docker compose run --rm watcher python manage.py run_watcher_agent --once --match-run-by-name
```

Run a watcher loop:

```sh
docker compose run --rm watcher python manage.py run_watcher_agent --match-run-by-name
```

The watcher can link files to runs by filename tokens (for example `SampleA_run07_20260701.raw`) when `--match-run-by-name` is enabled.

## Processing Agent

The `processor` service claims queued `ProcessingJob` records from the main API, runs the configured local command, writes logs under `RESULTS_ROOT`, and reports completion or failure back to the API.

V1 pipeline execution is driven by `ProcessingPipeline.parameters`:

```json
{
  "command": ["my-tool", "--input", "{raw_file_path}", "--out", "{results_dir}"],
  "env": {"PROJECT_CODE": "{run_name}"},
  "working_dir": "{results_dir}",
  "result_files": {
    "protein_table": "proteins.csv",
    "peptide_table": "peptides.tsv"
  }
}
```

Supported result declarations include:

- `protein_table`: CSV/TSV file imported into `ProteinQuant` and `ProteinIdentification`.
- `peptide_table`: CSV/TSV file imported into `PeptideQuant` and `PeptideIdentification`.
- `stats_json`: JSON object copied into `ProcessingJob.stats`.
- `artifact_files`: retained files recorded as `ProcessingJobArtifact` rows.
- `derivatives`: files such as mzML or spectrum indexes recorded as `RawFileDerivative` rows.

The demo showcase and PRIDE smoke utilities seed executable pipeline commands that write protein/peptide CSV artifacts under `RESULTS_ROOT`, so the `processor` container can exercise claim/start/complete/result-import behavior without a DIA-NN installation.

Run one processor pass manually:

```sh
docker compose run --rm processor python manage.py run_processor_agent --once
```

## Agent Auth

Watcher and processor containers authenticate to the main API with static bearer tokens:

- `MSCONNECT_WATCHER_TOKEN`
- `MSCONNECT_PROCESSOR_TOKEN`

Supported raw-like extensions are `.raw`, `.RAW`, `.mzML`, `.mzXML`, `.wiff`, `.scan`, and vendor directory suffixes such as `.d`.

Ingestion failures are persisted in the `IngestionFailure` model (visible in Django admin) with source path, reason, and repeat count.

## Result Table Import

Import protein and peptide result tables and attach them to a `ProcessingJob`:

```sh
docker compose run --rm web python manage.py import_result_tables \
  --job-id 1 \
  --protein-table /app/media/results/proteins.csv \
  --peptide-table /app/media/results/peptides.tsv
```

Expected columns:

- Protein table: `accession` and a quant column (`value`/`abundance`/`intensity`/`quantity`), plus optional `label`, `unit`, `score`, `q_value`, `coverage_percent`, `peptide_count`, `organism`.
- Peptide table: `sequence` and a quant column (`value`/`abundance`/`intensity`/`quantity`), plus optional `modified_sequence`, `charge`, `label`, `unit`, `score`, `q_value`, `retention_time_seconds`, `mz`.

## Adding Researcher Tool Capabilities

Use a Django app for each new tool or service. This keeps experiments modular while preserving one deployment image and one canonical data model.

Create a capability app:

```sh
docker compose run --rm web python manage.py start_capability spectral_library
```

This creates:

```text
capabilities/spectral_library/
  __init__.py
  apps.py
  models.py
  services.py
  api_urls.py
  management/commands/run_spectral_library.py
  tests.py
  README.md
```

Capability apps under `capabilities/` are auto-discovered when they contain `apps.py` and `__init__.py`. You can disable discovery with:

```sh
MSCONNECT_AUTO_DISCOVER_CAPABILITIES=0
```

You can also explicitly install apps with:

```sh
MSCONNECT_EXTRA_APPS=capabilities.spectral_library,capabilities.custom_tool
```

When manually dropping in a Django app folder, make sure its `apps.py` uses the full package path:

```py
class SpectralLibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "capabilities.spectral_library"
    label = "spectral_library"
```

If a capability exposes `api_urls.py`, MSConnect mounts it at:

```text
/api/capabilities/<capability-slug>/
```

If it exposes `urls.py`, MSConnect mounts it at:

```text
/capabilities/<capability-slug>/
```

Development rules for capability apps:

- Put tool-specific wrappers, parsers, and command builders in `services.py`.
- Put long-running or one-shot work in `management/commands/`.
- Store new persisted tool data in the capability app only when it is truly tool-specific.
- Reuse `core` records for shared concepts: `Project`, `Sample`, `Run`, `RawFile`, `ProcessingPipeline`, `ProcessingJob`, `RawFileDerivative`, `ProcessingJobArtifact`, `ProteinQuant`, and `PeptideQuant`.
- For processor integration, create or update a `ProcessingPipeline` whose `parameters.command` calls a management command, writes outputs under `{results_dir}`, and declares `result_files`/`artifact_files`.
- Add migrations with `python manage.py makemigrations <capability_app>` and tests with `python manage.py test <capability_app>`.
- Rebuild/restart Docker after adding a new app so Django settings can discover it.

Minimal processor-capability pattern:

```json
{
  "command": [
    "python",
    "manage.py",
    "run_spectral_library",
    "{job_id}",
    "{results_dir}",
    "--raw-file",
    "{raw_file_path}"
  ],
  "working_dir": "/app",
  "result_files": {
    "protein_table": "proteins.csv",
    "peptide_table": "peptides.csv",
    "stats_json": "stats.json",
    "delimiter": ","
  },
  "artifact_files": [
    {"artifact_type": "raw_output", "path": "tool-report.json", "format": "json"}
  ]
}
```

This lets a researcher drop in a normal Django app, add commands/services for their tool, and wire it through `ProcessingPipeline` without changing the stable `core` workflow.

## Core Workflow

1. Configure University, Facility, Lab, Instruments, and Instrument Configurations.
2. Submit pre-acquisition project intake requests, review them, and promote approved requests to canonical `Project` records.
3. Import raw files from the watched share.
4. Link raw files to Runs.
5. Register processing pipelines and store peptide/protein IDs and quantification outputs.

## React App

The React application is the user-facing UI and is mounted at `/app/*`.

Open the app at:

```text
http://localhost:8000/app/projects
```

Legacy `/ui/*` URLs now redirect to their closest `/app/*` route for bookmark compatibility.

## Retired Legacy UI

The old Django-template UI under `ui/templates/ui/**` and `ui/static/ui/**` has been removed. Django admin, API routes, auth routes, and `/app/*` remain available.

## Backups

Back up these paths together so database records and raw files stay consistent:

- SQLite database: `MSCONNECT_DATA_HOST_PATH`
- raw file storage: `RAW_STORAGE_HOST_PATH`
- processing logs and results: `RESULTS_HOST_PATH`
- media uploads: `MSCONNECT_MEDIA_HOST_PATH`

## Tagged Deployments

Git tags matching `v*.*.*` publish the shared application image to Docker Hub.

Deploy a tagged release by setting:

```sh
MSCONNECT_IMAGE=docker.io/<your-dockerhub-user>/msconnect:vX.Y.Z
```

Then run:

```sh
docker compose pull
docker compose up -d
```
