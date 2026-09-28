# MSConnect staged launch acceptance

This is the operational gate for the method-development lab and the facility
pilot. It separates application behavior that can be verified in CI from site
evidence that requires real instruments, storage, and processor runtimes.

## Stage 1: method-development lab

Deploy one independent MSConnect stack with:

- Postgres, not SQLite, for the shared deployment;
- durable storage for incoming, immutable raw, results, archive, backup, and
  processor references/libraries;
- one watcher agent connected to the instrument acquisition directory;
- one ProteoWizard conversion node for Thermo RAW;
- one DIA-NN node for Thermo mzML and timsTOF `.d` direct input;
- TLS, non-default agent tokens, SMTP, allowed hosts, and public signup disabled.

Acceptance evidence:

1. Create a project and experiment, generate a worklist from the approved
   workbook, download both generated MS/LC CSVs, and freeze the worklist.
2. Acquire and ingest a 20-run Thermo experiment. Confirm every file matches
   the expected run, conversion jobs complete before DIA-NN jobs claim, and
   errors create visible exceptions rather than silently completing.
3. Acquire and ingest a 20-run timsTOF experiment. Confirm `.d` is not sent
   through ProteoWizard and DIA-NN runs after the directory is stable.
4. Confirm researchers can follow project → experiment → sample → files and
   see runs, processing state, QC, and result artifacts.
5. Confirm QC is advisory: raw-signal, identification, and experiment-level
   warnings are visible without falsely converting a warning into completion.
6. Stop/restart the watcher and processor hosts and verify leases recover,
   duplicate files remain idempotent, and no run is marked processed before
   its analysis job completes.
7. Archive one completed experiment, verify the copy, remove only the test
   working result, and perform a restore test.

After the real-data run and restore test, record the machine-readable gate
result from the server:

```sh
docker compose -p msconnect-methodlab \
  -f docker-compose.msconnect2.server.yml \
  -f docker-compose.production.yml exec -T web \
  python manage.py verify_launch_acceptance \
  --project-code METHOD-2026-01 \
  --experiment-id 42 \
  --json > methodlab-acceptance.json
```

The verifier checks the frozen worklist, minimum run count, raw-file matching,
processing completion, fresh watcher/processor heartbeats, indexed
visualization data, QC runs, and verified archive/restore evidence. Use
`--skip-qc` or `--skip-archive` only for a documented intermediate checkpoint;
they are not release sign-off results.

## Stage 2: facility pilot

Deploy a second independent stack with its own:

- Postgres database and credentials;
- raw/results/archive/backup/reference storage;
- agent names and tokens;
- TLS hostname and SMTP configuration.

Repeat the 20-run Thermo and 20-run timsTOF acceptance on the second stack.
Confirm that project, run, result, and QC data cannot cross the two
deployments. Add processor capacity only after the first node passes the
single-node acceptance.

## Release evidence to retain

For each stack, retain the release version and image digests, migration output,
Compose configuration, database backup/restore result, storage mount checks,
agent heartbeat screenshots or API responses, representative raw/result
checksums, QC output, and incident/recovery logs.

## Explicitly deferred

AI-agent integration, Slurm scheduling, and Windows-enterprise processing are
not prerequisites for the first method-lab acceptance. Windows-enterprise is a
separately provisioned Windows worker and must not be represented by a Linux
placeholder image. FragPipe and Skyline remain disabled until their licensed
runtime and result-schema acceptance evidence is recorded.
