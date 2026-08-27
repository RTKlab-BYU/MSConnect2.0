# Live Stack Smoke Runbook

Use this runbook to verify the minimum live path for MSConnect:

- web/API is reachable
- watcher can pick up files from an instrument share
- raw files are copied into managed storage
- worklist filenames are used to link files to runs and projects
- DIA-NN jobs are queued and completed
- QC and project dashboards reflect the imported data
- archive/backup can be run afterward if retention coverage is needed

This assumes a single local or lab deployment with the repo's Docker Compose services.

## 0. Clear The Live State

Before a new manual pass, stop the worker containers that are holding old queue state and clear transient processing rows:

```sh
docker compose stop watcher processor processor-diann processor-pwiz
docker compose exec web python manage.py cleanup_processing_state
```

Use `--project-code <code>` if you only want to clear one project's transient jobs. The command preserves completed and failed job history.

## 1. Bring Up the Core Services

Start the API stack first:

```sh
docker compose up -d --build web nginx
```

For a real DIA-NN run, bring up the watcher and DIANN worker together:

```sh
make diann-up
```

Verify the stack is actually up:

```sh
docker compose ps
curl -f http://localhost:8080/readyz/
```

If `readyz` fails, stop here and fix the runtime before testing file ingest.

## 2. Confirm Agent Preconditions

Run the agent preflight checks from the agent containers themselves:

```sh
docker compose run --rm watcher python manage.py check_agent_runtime --role watcher --write-test
docker compose run --rm processor python manage.py check_agent_runtime --role processor --engine diann --write-test
```

If you want archive coverage in the same pass, confirm archive roots are mounted and writable from the host that runs `archive-worker`.

## 3. Create the Test Project and Worklist

For a pure end-to-end smoke test, create the repository's minimal fixture:

```sh
docker compose exec web python manage.py create_e2e_smoke_fixture --code E2E-SMOKE
```

To stage a real verified raw into the watcher input root for the same one-file path, point the smoke fixture at the source file directly:

```sh
docker compose exec web python manage.py create_e2e_smoke_fixture \
  --code E2E-REAL \
  --source-file /Volumes/T7_Shield/tempDataMS/JM1025_DigestMix_other_RK9_rep5_ch1_DIA100win_dry_run77.raw
```

For a real DIA-NN path, create an engine-specific project and worklist from filenames already present in `INCOMING_RAW_ROOT`:

```sh
docker compose exec web python manage.py create_engine_operations_fixture \
  --code OPS-DIANN \
  --diann-file SampleA.mzML \
  --diann-fasta /data/shared/reference/human.fasta \
  --diann-library /data/shared/reference/project.speclib
```

Replace the filenames and shared-asset paths with the lab's real filenames and references when running against production-like data. Add `--create-placeholders` only when you want the command to synthesize local test files under `INCOMING_RAW_ROOT`.

Use the `DIA-NN speclib build` preset when the project is creating a new library for a new chemistry, FASTA, or instrument setup. Use the `DIA-NN speclib reuse` preset once the project already has a generated speclib and you want later samples processed against it.

If you already know the exact filenames in your test folder, the more deterministic option is to create a filename-matched worklist first:

```sh
docker compose exec web python manage.py create_filename_worklist \
  --code OPS-DIANN \
  --filename SampleA.mzML \
  --filename SampleB.mzML
```

Then copy or mount the real files into `INCOMING_RAW_ROOT` so the watcher can match them without guessing.

## 4. Test Watcher Pickup

Run the watcher once to process the current incoming queue:

```sh
docker compose run --rm watcher python manage.py run_watcher_agent --once --match-run-by-name
```

Expected results:

- the watcher reports created or reused imports
- raw files are copied into `RAW_FILE_STORAGE_ROOT`
- imported raw files are linked to the matching run
- the run and project become visible in the project workspace

If you are testing a real folder from an MS computer, start with one folder from one instrument. After the first folder is working, bulk-drop the remaining files from that same instrument.

## 5. Test DIA-NN Processing

Leave the DIANN worker running and watch it claim queued jobs after the watcher import:

```sh
docker compose logs -f processor-diann
```

Expected results:

- a DIA-NN-compatible job is claimed
- job status moves through start and completion
- result tables are written under `RESULTS_ROOT`
- the job imports protein and peptide outputs
- the raw file status moves to processed

If the DIA-NN engine image is not available yet, you can still validate the wrapper contract with the generic smoke processor, but that does not replace a real DIA-NN run. The smoke case is only a launcher check and is not the production search path.

## 6. Verify UI and Metrics

Open these views after the run:

- `/app/projects`
- `/app/projects/<project_id>`
- `/app/qc?program=hye`
- `/app/qc?program=prtc`
- `/app/monitoring`
- `/app/processing`

What to confirm:

- the project page shows the imported runs and raw files
- the monitoring view shows live nodes and recent job state
- HYE metrics show up if the fixture contains HYE runs
- PRTC metrics appear once a PRTC worklist and Skyline pipeline exist

If you need the QC views to show useful data immediately, seed or import HYE and PRTC runs before testing the dashboard.

## 7. Optional Archive Pass

If archive/retention is part of the smoke test, run:

```sh
docker compose run --rm archive-worker python manage.py archive_raw_files --limit 50
docker compose exec web python manage.py verify_archives --restore-test
```

Expected results:

- archive records are created
- archive and backup copies are verified
- raw files remain available in managed storage

## 8. Quick Failure Triage

Use these checks when something fails:

```sh
docker compose ps -a
docker compose logs --tail=100 web watcher processor nginx archive-worker
docker compose exec web python manage.py check
docker compose exec web python manage.py generate_operations_report --output /tmp/msconnect-operations.txt
```

Common failure causes:

- the API container is not running or not reachable at the configured base URL
- watcher or processor tokens are missing or mismatched
- `INCOMING_RAW_ROOT`, `RAW_FILE_STORAGE_ROOT`, or `RESULTS_ROOT` do not point to mounted directories
- the worklist was not created before the files were dropped
- the expected filename in the worklist does not match the actual file name
