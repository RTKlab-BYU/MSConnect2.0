# DIA-NN Nextflow processing

For live-server upgrades and remote Windows/WSL2 processor setup, use
[DIA-NN processor node operations](diann-node-operations.md).

MSConnect uses the pinned DIA-NN 2.7.0 Main Release Channel build with Nextflow 26.10.6. The Linux archive URL and SHA-256 are recorded in `nextflow/diann/versions.json` and the processor image build. Each processor image contains the matching runtime, workflow, and FASTA prediction helper; the worker does not install engines dynamically.

## Analysis flow

1. Set the organism on the experiment/project metadata when importing or editing the worklist. Supported selections are Human + Yeast + *E. coli*, Human, Pig, Rat, and Mouse. The analysis view defaults to that metadata and offers an explicit override.
2. On reanalysis, MSConnect first checks registered shared FASTA references, then the known shared reference folders, and finally retrieves reviewed UniProt FASTA sequences for the selected taxa. Retrieved references are content addressed and registered under the shared `reference-assets/fasta` directory.
3. The default spectral-library choice reuses the project library when it matches the organism selection. If none exists, the first sample job generates it from the selected FASTA. Remaining sample jobs wait for that job and use its library. The completed library is copied into the project's shared reference directory for subsequent analyses.
4. DIA-NN settings use the configured defaults unless an operator supplies advanced JSON overrides. The processor defaults to two threads (capped at the CPU count); the administrator can tune this per node. Supported named settings include q-value, matrix q-value, mass accuracy, individual reports/windows, and extra command-line tokens. `extra_options` is an array of tokens, such as `["--peak-window", "0.7"]`.
5. Reanalysis creates a new immutable batch and jobs. The batch records its parameters, organisms, FASTA/library checksum, and engine version. Failed jobs and batches remain visible; a corrected rerun creates new records.

The project Analysis view exposes metadata/organism override, project library reuse, rebuild, or an explicit shared library path, plus advanced settings JSON. A custom library path must be visible to the server and every processor at the same mounted path.

## Development container

`docker-compose.diann-dev.yml` builds an isolated processor image without replacing the main MSConnect web, watcher, or processor services. It binds the existing raw, results, and shared host paths read-only for inputs/references and writable for results. The live shared reference directory must be mounted at `/data/shared` on both the API and processor.

Build and inspect the image:

```sh
docker compose -f docker-compose.diann-dev.yml build processor-diann-dev
docker compose -f docker-compose.diann-dev.yml run --rm --entrypoint nextflow processor-diann-dev -version
docker compose -f docker-compose.diann-dev.yml run --rm --entrypoint diann processor-diann-dev
```

For a real queue test, create a `diann` processor through **Admin → Agent setup**, mount the same raw/results/shared paths in WSL2, and use the one-time token and generated connection check. Clicking **Ready** immediately activates the database-backed key; the web server does not need a restart. Keep the image version/profile at `diann:2.7.0`. Do not place the service token in a shared file or commit it.

## Windows/WSL2 processor setup

The admin panel creates a processor row and per-machine key, then provides install/check and post-activation commands. Install Docker Desktop with WSL integration on the Windows processor host, mount the site raw, results, and shared file shares in the WSL distribution, run the generated checks, activate the key in the admin panel, and start the processor service. The service image includes Python, Java, .NET, Nextflow, and DIA-NN, so the host does not need a separate DIA-NN installation.

## Verification

Use `manage.py check`, `manage.py makemigrations --check --dry-run`, the processor and acquisition watcher tests, and the frontend build/lint/worklist tests after changes. Validate a representative mzML or vendor RAW acquisition against the intended full reference before enabling a processor for live work. The tiny repository demo FASTA is only a container-launch fixture and cannot validate biological identifications.
