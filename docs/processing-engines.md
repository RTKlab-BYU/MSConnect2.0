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
  "version_command": ["diann"]
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

- `processor-diann`: DIA-NN worker. Build one private-registry image per site-approved DIA-NN version, with `DIANN_LINUX_URL` pointing at the approved Linux DIA-NN archive. For a Linux Docker worker, use the Linux ZIP, not the Windows MSI.
- `processor-fragpipe`: FragPipe worker. Build one private-registry image per site-approved FragPipe version, with `FRAGPIPE_URL` pointing at the approved FragPipe archive.
- `processor-pwiz`: ProteoWizard conversion worker. This image derives from the ProteoWizard/Skyline vendor-license-acceptance container and exposes `msconvert`.
- `SkylineCmd`: can run as a Windows processor or a site-approved Wine/container runner. Build or point to a site-approved image and use the `skyline` adapter.
- Enterprise tools such as Proteome Discoverer and Spectronaut should run as external licensed Windows workers. Configure their pipelines with `adapter` set to `proteome-discoverer`, `spectronaut`, or `enterprise-handoff` plus a site-specific `command` array.

MSConnect does not redistribute vendor binaries or licenses. The recommended operating model is:

1. Obtain and approve vendor installers or archives according to site policy.
2. Build engine worker images locally or in CI.
3. Push approved images to a private registry with immutable version tags and, where possible, deploy by digest.
4. Register each engine profile in `PROCESSOR_SHARED_STORAGE_ROOT/config/processor-registry.json`.
5. Create pipelines that target a specific engine profile/version.

Example DIA-NN 2.0 image build and registration:

```sh
docker build \
  -f docker/processor/diann.Dockerfile \
  --build-arg DIANN_VERSION=2.0 \
  --build-arg DIANN_LINUX_URL=https://github.com/vdemichev/DiaNN/releases/download/2.0/DIA-NN-2.0-Academia-Linux.zip \
  -t registry.example.org/msconnect/processor-diann:2.0 .

docker run --rm registry.example.org/msconnect/processor-diann:2.0 diann

docker push registry.example.org/msconnect/processor-diann:2.0

python manage.py processor_registry add-engine \
  --engine diann \
  --version 2.0 \
  --install-type image \
  --image registry.example.org/msconnect/processor-diann:2.0 \
  --executable diann \
  --version-command-json '["diann"]' \
  --license-note "Site-approved DIA-NN academic installation"
```

The public DIA-NN release assets are academic-use binaries under the DIA-NN license. In regulated or multi-user environments, mirror the approved ZIP into internal artifact storage and replace `DIANN_LINUX_URL` with that internal URL before building.

Example FragPipe image profile:

```sh
python manage.py processor_registry add-engine \
  --engine fragpipe \
  --version 23.0 \
  --install-type image \
  --image registry.example.org/msconnect/processor-fragpipe:23.0 \
  --executable fragpipe
```

Example Skyline 26.1 image build and PRTC registration:

```sh
docker build \
  -f docker/processor/skyline.Dockerfile \
  --build-arg SKYLINE_BASE_IMAGE=proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:skyline_26.1.0.057-c07debd \
  -t registry.example.org/msconnect/processor-skyline:26.1 .

docker run --rm registry.example.org/msconnect/processor-skyline:26.1 SkylineCmd --help

docker push registry.example.org/msconnect/processor-skyline:26.1

python manage.py processor_registry add-engine \
  --engine skyline \
  --version 26.1.0 \
  --install-type image \
  --image registry.example.org/msconnect/processor-skyline:26.1 \
  --executable SkylineCmd \
  --version-command-json '["SkylineCmd", "--version"]' \
  --license-note "Site-approved ProteoWizard/Skyline vendor-license container"

python manage.py processor_registry add-reference \
  --kind skyline_document \
  --key prtc-15 \
  --path /data/shared/skyline/prtc-15.sky
```

Register PRTC Skyline settings with the lab-approved 15 peptide definitions. Use `docs/skyline-prtc-15-settings.example.json` as the starting template:

```json
{
  "document_ref": "prtc-15",
  "report_name": "PRTC Results",
  "report": "skyline-prtc-report.csv",
  "report_format": "csv",
  "report_invariant": true,
  "report_conflict_resolution": "overwrite",
  "postprocess": "skyline_prtc",
  "result_files": {
    "peptide_table": "skyline-prtc-peptides.csv",
    "stats_json": "skyline-prtc-stats.json"
  },
  "expected_peptides": [
    {"sequence": "PRTC01", "charge": 2},
    {"sequence": "PRTC02", "charge": 2}
  ]
}
```

Then create the PRTC pipeline and configure upload-time routing:

```sh
python manage.py processor_registry add-settings \
  --engine skyline \
  --key prtc-15 \
  --json-file /data/shared/settings/skyline/prtc-15.json

python manage.py processor_registry create-pipeline \
  --engine skyline \
  --version "Skyline PRTC 26.1" \
  --engine-version 26.1.0 \
  --settings-key prtc-15 \
  --name "Skyline PRTC"

MSCONNECT_PRTC_SKYLINE_PIPELINE_ID=<created pipeline id>
```

Example external enterprise profiles:

```sh
python manage.py processor_registry add-engine \
  --engine proteome-discoverer \
  --version 3.1 \
  --install-type external \
  --executable "C:\\Program Files\\Thermo\\Proteome Discoverer 3.1\\ProteomeDiscoverer.exe"

python manage.py processor_registry add-engine \
  --engine spectronaut \
  --version site-current \
  --install-type external \
  --executable "C:\\Program Files\\Biognosys\\Spectronaut\\Spectronaut.exe"
```

Register shared settings and create a version-pinned pipeline:

```sh
python manage.py processor_registry add-settings \
  --engine diann \
  --key plasma-standard \
  --json-file /data/shared/settings/diann/plasma-standard.json

python manage.py processor_registry create-pipeline \
  --engine diann \
  --version "DIA-NN plasma 2.0" \
  --engine-version 2.0 \
  --settings-key plasma-standard
```

Start workers with matching engine profile metadata:

```sh
MSCONNECT_PROCESSOR_ENGINE=diann \
MSCONNECT_PROCESSOR_ENGINE_VERSION=2.0 \
MSCONNECT_PROCESSOR_ENGINE_PROFILE=diann:2.0 \
MSCONNECT_IMAGE=registry.example.org/msconnect/processor-diann:2.0 \
python manage.py run_processor_agent --engine diann
```

For Compose deployments, use `compose.engines.example.yml` as a template for one service per engine version of interest.

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
docker compose --profile engines build processor-skyline
docker compose --profile conversion build processor-pwiz
```

For a local DIA-NN 2.0 Compose build, set:

```sh
MSCONNECT_DIANN_IMAGE=msconnect-processor-diann:2.0
DIANN_ENGINE_VERSION=2.0
DIANN_ENGINE_PROFILE=diann:2.0
DIANN_LINUX_URL=https://github.com/vdemichev/DiaNN/releases/download/2.0/DIA-NN-2.0-Academia-Linux.zip
```

For a local Skyline 26.1 Compose build, set:

```sh
SKYLINE_BASE_IMAGE=proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:skyline_26.1.0.057-c07debd
MSCONNECT_SKYLINE_IMAGE=msconnect-processor-skyline:26.1
SKYLINE_ENGINE_VERSION=26.1.0
SKYLINE_ENGINE_PROFILE=skyline:26.1.0
MSCONNECT_PRTC_SKYLINE_PIPELINE_ID=<created pipeline id>
```

Example runtime:

```sh
docker compose --profile engines --profile conversion up -d web watcher processor-diann processor-skyline processor-fragpipe processor-pwiz nginx
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
