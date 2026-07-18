# MSConnect

MSConnect is an on-prem SDMS/LIMS scaffold for LC-MS proteomics. The MVP tracks organizational structure, users, projects, experiments, samples, runs, raw files, and peptide/protein result data.

## Stack

- Django
- SQLite
- Docker Compose
- nginx
- Watched-share raw file ingestion
- Repo-embedded watcher and processor agents

## Local On-Prem Run

1. Create the environment file:

```sh
cp .env.example .env
```

2. Build and start the stack:

```sh
docker compose up --build
```

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

## Core Workflow

1. Configure University, Facility, Lab, Instruments, and Instrument Configurations.
2. Submit pre-acquisition project intake requests, review them, and promote approved requests to canonical `Project` records.
3. Import raw files from the watched share.
4. Link raw files to Runs.
5. Register processing pipelines and store peptide/protein IDs and quantification outputs.

## React App Review

The new React application is mounted at `/app/*` while the legacy Django-template UI remains available at `/ui/*`.

Start review at:

```text
http://localhost/app/projects
```

Use `docs/app-review-guide.md` for the full review flow, demo data setup, acceptance criteria, and the planned migration steps for making `/app/` the only user-facing interface.

## Legacy UI Routes

- `/ui/intake/new`: create intake request
- `/ui/intake`: pre-acquisition queue with filters
- `/ui/intake/<id>`: intake detail and timeline
- `/ui/intake/<id>/review`: review transitions and promotion action
- `/ui/projects/pre-acq`: approved intake planning list

See handoff contract in `docs/ui-handoff.md`.

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
