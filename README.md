# MSConnect

MSConnect is an on-prem SDMS/LIMS scaffold for LC-MS proteomics. The MVP tracks organizational structure, users, projects, experiments, samples, runs, raw files, and peptide/protein result data.

## Stack

- Django
- SQLite
- Docker Compose
- nginx
- Watched-share raw file ingestion

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

## Raw File Ingestion

The `ingest` service polls `INCOMING_RAW_ROOT` and imports recognized raw file paths into `RAW_FILE_STORAGE_ROOT`.

Default host paths are:

- `./incoming` for files from the MS computer or mounted network share
- `./raw-storage` for immutable managed raw file storage
- `./data` for SQLite

Run one import pass manually:

```sh
docker compose run --rm ingest python manage.py ingest_raw_files --recursive
```

Run a watcher loop:

```sh
docker compose run --rm ingest python manage.py ingest_raw_files --watch --recursive --interval 60
```

Try run-name matching from filename tokens (for example `SampleA_run07_20260701.raw`):

```sh
docker compose run --rm ingest python manage.py ingest_raw_files --recursive --match-run-by-name
```

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
2. Submit pre-acquisition project intake requests in the placeholder UI (`/ui/intake/new`), review in queue (`/ui/intake`), and promote approved requests to canonical `Project` records.
3. Import raw files from the watched share.
4. Link raw files to Runs.
5. Register processing pipelines and store peptide/protein IDs and quantification outputs.

## Placeholder UI Routes

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
- media uploads: `MSCONNECT_MEDIA_HOST_PATH`
