# Windows DIA-NN processors with Nextflow

This deployment runs the MSConnect processor agent and Nextflow inside WSL2 on
each Windows processor. Windows remains the host OS; the agent, Nextflow, and
pinned DIA-NN Conda environments run in Linux. The server, watchers, and job
queue are unchanged.

## Shared deployment files

Keep the workflow and version catalog in the server-owned shared directory,
for example `/srv/msconnect/shared/nextflow/diann/`:

- `main.nf` and `nextflow.config` from `nextflow/diann/` in this repository.
- `envs/diann-<version>.yml` for each approved, pinned Python helper runtime.
- `versions.json`, maintained by the operator, listing version, approved
  DIA-NN executable path, Conda environment path, and upstream distribution.
- `diann_search.py`, copied from `core/processing/diann_search.py`. This helper
  performs the separate FASTA library-prediction and quantitative-search passes
  used by MSConnect.
- Approved FASTA files, spectral libraries, and the headless DIA-NN CLI script
  under the shared reference directory.

The Linux DIA-NN executable is a separately downloaded, approved distribution,
not a Conda package. The Conda environment supplies the Python runtime for the
helper; install the .NET 8 SDK and Linux runtime dependencies required by the
selected DIA-NN release in WSL. The starter catalog contains DIA-NN 2.2.0, the
version already used by the repository's worker configuration. Its binary must
be installed at the catalog path on each node, and the env must be provisioned
on all nodes before enabling that version in a pipeline. Add other versions by
adding their approved distribution, environment file, and catalog entry.
Workers should not modify shared references.

## Windows processor setup

Install WSL2 with a supported Linux distribution on all three machines. In each
distribution install Python and Java (Nextflow runtime requirements), Conda or
Mamba, Nextflow, and the MSConnect checkout/agent dependencies. Configure the
agent to use the server API's Tailscale DNS name, the server's processor token,
and a unique agent name. The current server configuration accepts one shared
processor token for all three nodes. Use the Windows Task Scheduler helper below to start the WSL agent
at user logon. Keep the three agents on the same shared mount paths.

Install and sign in to Tailscale on the server, each Windows processor host, and
the watcher hosts. Keep Tailscale on the Windows host only; Tailscale documents
that running it both on Windows and inside WSL2 can break nested encrypted
traffic. Enable MagicDNS or use the server's Tailscale IP in the API URL. Confirm
from Windows with `tailscale ping <server-name>` and from WSL with
`getent hosts <server-name>`. Permit only the required API HTTPS port and SMB
TCP 445 from the processor devices in the tailnet access policy and host
firewall. [Tailscale's WSL2 guidance](https://tailscale.com/docs/install/windows/wsl2)
recommends Windows-host installation for this topology; [MagicDNS](https://tailscale.com/docs/features/magicdns)
provides tailnet hostnames.

Connect the server SMB export and managed raw/results shares over Tailscale.
Mount them inside WSL2 at the same absolute paths the server uses:
`/data/raw`, `/data/results`, and `/data/shared`. Use `cifs-utils` and a
root-owned credentials file for the SMB mount; do not place SMB credentials in
the processor `.env`. Set `RAW_FILE_STORAGE_ROOT`, `RESULTS_ROOT`, and
`PROCESSOR_SHARED_STORAGE_ROOT` to those paths. Ensure the processor identity
can read inputs/references and write job results.

## Simple per-node setup

Use the same Windows repository path and shared Linux mount paths on all three
workers. In each WSL2 distribution install Python 3.12, Java 17 or newer,
Miniforge/Conda, and Nextflow. Keep Python environments and Nextflow work/cache
under the Linux home directory; then in WSL run:

```bash
python3 -m venv "$HOME/.venvs/msconnect"
"$HOME/.venvs/msconnect/bin/python" -m pip install -r /mnt/c/MSConnect/requirements.txt
```

Copy `docs/env.processor.wsl2.example` to `C:\MSConnect\.env` and edit the
unique agent name and shared server processor token for that machine. Keep values unquoted unless they
contain spaces. Set `MSCONNECT_PYTHON` to the venv Python path, replacing
`<wsl-user>` with the Linux account name. The configured API host must resolve
over Tailscale, and the three storage roots must already be mounted inside WSL2.
The WSL project path for `C:\MSConnect` is `/mnt/c/MSConnect`.

From an elevated PowerShell prompt in the Windows checkout, verify then start
the node:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\ops\run-msconnect-diann-processor.ps1 -ProjectDir C:\MSConnect -EnvFile C:\MSConnect\.env -WslProjectDir /mnt/c/MSConnect -Distro Ubuntu -Action check
.\ops\run-msconnect-diann-processor.ps1 -ProjectDir C:\MSConnect -EnvFile C:\MSConnect\.env -WslProjectDir /mnt/c/MSConnect -Distro Ubuntu -Action once
.\ops\install-msconnect-diann-processor.ps1 -ProjectDir C:\MSConnect -EnvFile C:\MSConnect\.env -WslProjectDir /mnt/c/MSConnect -Distro Ubuntu
```

`check` verifies required environment values, WSL mount paths, Python,
Nextflow, Conda, catalog entries, DIA-NN executable presence, and Tailscale DNS
resolution. `once` claims at most one queued job for a smoke run. `run` keeps the
agent polling. The installer registers a per-user Scheduled Task at logon and
restarts it after failure; the Windows account must be signed in for its WSL2
distribution to run. Logs are written by the processor agent under
`RESULTS_ROOT/jobs/<job-id>/process.log`.

Install the DIA-NN Linux archive at `/opt/diann/<version>/diann-linux` on each
WSL2 worker, matching the executable path in `versions.json`. DIA-NN's Linux distribution requires .NET SDK 8 and system
libraries; the Conda file only pins the helper's Python runtime. The first
Nextflow run creates the Conda cache. To prime it before production, run the
`once` action with an eligible smoke job after confirming the CLI and reference
paths. Server-side pipelines must also specify `execution_mode: "nextflow"`,
the workflow/catalog paths, selected `diann_version`, and FASTA or speclib path.

## MSConnect pipeline configuration

Create a DIA-NN `ProcessingPipeline` whose parameters include:

```json
{
  "adapter": "diann",
  "execution_mode": "nextflow",
  "nextflow_workflow": "/data/shared/nextflow/diann/main.nf",
  "nextflow_version_catalog": "/data/shared/nextflow/diann/versions.json",
  "nextflow_profile": "conda",
  "diann_version": "2.2.0",
  "fasta": "/data/shared/reference/human.fasta",
  "cli_script": "/data/shared/nextflow/diann/diann_search.py"
}
```

Use `library` instead of `fasta` for spectral-library reuse. The agent passes the
selected version, input, results directory, and configured reference paths to
Nextflow. A completed job publishes `report.parquet` as a DIA-NN report artifact
and `diann.log` as a log artifact, matching the server's report importer.
`nextflow_executable` may override `nextflow` when it is not on the service
PATH. The workflow currently runs one task at a time per node.

## Operator procedure

1. Add a version-specific Conda environment file and register the version in
   the shared operator catalog.
2. Provision the environment cache on all three WSL2 workers and verify the
   DIA-NN CLI resolves to the expected version.
3. Make that version selectable in the MSConnect pipeline configuration.
4. Submit jobs through the existing MSConnect UI/API/queue and inspect status,
   logs, and artifacts through the existing job views. The processor agent
   invokes Nextflow and reports completion using the current lease protocol.

The generic `run_processor_agent` remains the worker entrypoint; no Docker
image is needed on processor machines. The MSConnect server deployment may
continue using its existing Compose setup.
