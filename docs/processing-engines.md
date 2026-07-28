# Processing Engines

MSConnect keeps the Django app image separate from heavy or licensed search engines. The default `processor` service remains a generic command runner. Engine-specific workers can be enabled with Compose profiles when the site has approved binaries and licenses.

## Reproducibility Contract

Every processor job writes `runtime-manifest.json` under `RESULTS_ROOT/jobs/<job id>/` and registers it as a processing artifact. The manifest captures:

- adapter name, executable path, declared version, and detected version output
- redacted command line
- job working directory and results directory
- shared storage roots visible to the processor
- host OS, CPU count, Python runtime, hostname, and selected environment variables
- raw input file size, mtime, and SHA-256 when the file is not larger than the hashing limit
- scrubbed pipeline parameters

The same runtime metadata is also stored in `ProcessingJob.stats.runtime` on successful completion. Failed jobs preserve `runtime_manifest_path` when the manifest was written before failure.

For best replication, pipeline definitions should set a pinned `software_version` and, when the default probe is not correct for a vendor CLI, a `version_command` array:

```json
{
  "software_version": "DIA-NN 1.9.2 site build 2026-07",
  "version_command": ["diann", "--version"]
}
```

## Shared Storage

Processors need the same logical paths for raw files, result outputs, references, workflows, libraries, and enterprise handoff folders. Configure these roots consistently across Linux containers and Windows workers:

- `RAW_FILE_STORAGE_ROOT`: immutable managed raw-file storage.
- `RESULTS_ROOT`: processor output root where logs, manifests, tables, reports, and exports are written.
- `PROCESSOR_SHARED_STORAGE_ROOT`: top-level shared mount used by processors for references and cross-engine handoff.

Linux containers normally mount these as `/data/raw`, `/data/results`, and `/data/shared`. Windows enterprise workers should mount the same shares at stable paths, for example `Z:\msconnect\raw`, `Z:\msconnect\results`, and `Z:\msconnect\shared`, and run the processor agent with matching environment variables.

## Boot Processor Nodes

Each processor node is a long-running Django management command with a processor token, a stable node name, shared storage roots, and an engine identity. The engine identity is reported in heartbeats and appears in `/app/admin` and `/app/processing/admin`.

Linux or container workers:

```sh
MSCONNECT_PROCESSOR_ENGINE=diann \
MSCONNECT_AGENT_NAME=diann-01 \
MSCONNECT_AGENT_TOKEN=<processor-token> \
MSCONNECT_API_BASE_URL=http://msconnect-server:8000/api \
RAW_FILE_STORAGE_ROOT=/mnt/msconnect/raw \
RESULTS_ROOT=/mnt/msconnect/results \
PROCESSOR_SHARED_STORAGE_ROOT=/mnt/msconnect \
.venv/bin/python manage.py run_processor_agent --engine diann
```

Windows enterprise workers:

```powershell
$env:MSCONNECT_PROCESSOR_ENGINE='proteome-discoverer'
$env:MSCONNECT_AGENT_NAME='pd-win-01'
$env:MSCONNECT_AGENT_TOKEN='<processor-token>'
$env:MSCONNECT_API_BASE_URL='http://msconnect-server:8000/api'
$env:RAW_FILE_STORAGE_ROOT='\\nas\msconnect\raw'
$env:RESULTS_ROOT='\\nas\msconnect\results'
$env:PROCESSOR_SHARED_STORAGE_ROOT='\\nas\msconnect'
.\.venv\Scripts\python manage.py run_processor_agent --engine proteome-discoverer
```

Use one node name per live process, such as `diann-01`, `fragpipe-01`, `skyline-win-01`, `spectronaut-win-01`, and `pd-win-01`. For persistent operations, wrap the same command in `systemd`, Docker Compose, Windows Task Scheduler, or a Windows service runner. `pause` and `drain` controls stop a node from claiming new jobs; `stop` and `restart` acknowledge the control and exit the process so the host supervisor can stop or restart it.

Before starting a long-running node, run preflight from that same host:

```sh
python manage.py check_agent_runtime --role processor --engine diann --write-test
```

For watcher hosts:

```sh
python manage.py check_agent_runtime --role watcher --write-test
```

The preflight checks DNS, TCP connectivity, web liveness, bearer-token role, API ping, and storage permissions. A running agent also writes a heartbeat marker under `MSCONNECT_AGENT_HEALTH_DIR`; supervisors can call:

```sh
python manage.py agent_healthcheck --role processor
```

## Runner Images

- `processor-diann`: DIA-NN worker. Build with `DIANN_LINUX_URL` pointing at the site-approved Linux DIA-NN archive.
- `processor-fragpipe`: FragPipe worker. Build with `FRAGPIPE_URL` pointing at the site-approved FragPipe archive.
- `processor-pwiz`: ProteoWizard conversion worker. This image derives from the ProteoWizard/Skyline vendor-license-acceptance container and exposes `msconvert`.
- `SkylineCmd`: can run as a Windows processor or a site-approved Wine/container runner. Use the `skyline` adapter.
- Enterprise tools such as Proteome Discoverer and Spectronaut should run as external licensed Windows workers. Configure their pipelines with `adapter` set to `proteome-discoverer`, `spectronaut`, or `enterprise-handoff` plus a site-specific `command` array.

On Windows machines, run the same Django management command from a Python environment that can reach the MSConnect API and shared storage:

```powershell
$env:MSCONNECT_API_BASE_URL = "https://msconnect.example.org/api"
$env:MSCONNECT_AGENT_TOKEN = "<processor token>"
$env:MSCONNECT_AGENT_NAME = "win-pd-01"
$env:RAW_FILE_STORAGE_ROOT = "Z:\msconnect\raw"
$env:RESULTS_ROOT = "Z:\msconnect\results"
$env:PROCESSOR_SHARED_STORAGE_ROOT = "Z:\msconnect\shared"
python manage.py run_processor_agent
```

Example builds:

```sh
docker compose --profile engines build processor-diann processor-fragpipe
docker compose --profile conversion build processor-pwiz
```

Example runtime:

```sh
docker compose --profile engines --profile conversion up -d web watcher processor processor-diann processor-fragpipe processor-pwiz nginx
```

## Pipeline Adapter Parameters

Legacy pipelines can continue using `parameters.command`. New pipelines should prefer `parameters.adapter`.

```json
{
  "adapter": "msconvert",
  "executable": "msconvert",
  "output_format": "mzML",
  "filters": ["peakPicking true 1-"]
}
```

```json
{
  "adapter": "fragpipe",
  "workflow": "/data/reference/workflows/fragpipe.workflow",
  "threads": 8,
  "ram_gb": 32,
  "data_type": "DDA"
}
```

```json
{
  "adapter": "diann",
  "executable": "diann",
  "software_version": "DIA-NN 1.9.2",
  "library": "/data/reference/project.speclib",
  "fasta": "/data/reference/project.fasta",
  "options": ["--threads", "8"]
}
```

```json
{
  "adapter": "skyline",
  "executable": "SkylineCmd",
  "software_version": "Skyline 24.1",
  "document": "Z:\\msconnect\\shared\\skyline\\project.sky",
  "report": "skyline-report.csv",
  "report_name": "Transition Results",
  "options": ["--save"]
}
```

```json
{
  "adapter": "spectronaut",
  "executable": "Spectronaut.exe",
  "software_version": "Spectronaut site-pinned version",
  "version_command": ["Spectronaut.exe", "--version"],
  "command": [
    "Spectronaut.exe",
    "-i",
    "{raw_file_path}",
    "-o",
    "{results_dir}"
  ],
  "handoff_manifest": "spectronaut-handoff.json",
  "artifact_files": [
    {
      "artifact_type": "enterprise_export",
      "path": "{results_dir}/spectronaut-output.tsv",
      "format": "tsv"
    }
  ]
}
```

```json
{
  "adapter": "proteome-discoverer",
  "executable": "ProteomeDiscoverer.exe",
  "software_version": "Proteome Discoverer site-pinned version",
  "command": [
    "ProteomeDiscoverer.exe",
    "/RunWorkflow",
    "Z:\\msconnect\\shared\\pd\\workflow.pdProcessingWF",
    "/Input",
    "{raw_file_path}",
    "/Output",
    "{results_dir}"
  ],
  "handoff_manifest": "proteome-discoverer-handoff.json"
}
```

Enterprise adapters deliberately require site-specific command arrays because vendor CLIs and license setups vary between versions and installations. The generated handoff manifest records the exact command and paths that were presented to the licensed tool.

## Local Smoke Test

Use the smoke command to verify the MSConnect adapter layer, logging, declared artifacts, runtime manifests, and input fingerprinting without requiring licensed vendor binaries:

```sh
python manage.py smoke_test_processors \
  --raw-file incoming/public-ms/1min.mzML \
  --results-root results/processor-smoke
```

This runs mock DIA-NN, FragPipe, Skyline, Spectronaut, and Proteome Discoverer commands against one file. It is not a scientific validation of the vendor engines; it validates the processor wrapper contract. On machines with real engine binaries, create real queued jobs with site-pinned pipeline definitions and confirm each `runtime-manifest.json` captures the vendor version output and shared storage paths.

## Spectra Viewing

The web viewer reads spectrum index derivatives, not vendor RAW files directly. A conversion worker should create an mzML or mzMLb derivative and an index JSON derivative for the raw file.

Index JSON shape:

```json
{
  "spectra": [
    {
      "id": "scan=1",
      "index": 0,
      "scan_number": 1,
      "ms_level": 2,
      "retention_time_seconds": 42.5,
      "precursor_mz": 678.9,
      "base_peak_mz": 445.2,
      "base_peak_intensity": 12000,
      "tic": 45000,
      "peaks": [[445.2, 12000], [500.1, 3000]]
    }
  ],
  "chromatograms": {
    "tic": [[42.5, 45000]],
    "bpc": [[42.5, 12000]]
  }
}
```

Set `MSCONNECT_AUTO_QUEUE_SPECTRA_CONVERSION=1` only after a working conversion runner is available.
