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
agent to use the server API's Tailscale DNS name and a unique processor token and
agent name. Run the agent as a WSL systemd service (enable systemd in
`/etc/wsl.conf`); configure Windows Task Scheduler to start the distribution at
boot. Keep the three agents on the same shared mount paths.

Connect the server SMB export and managed raw/results shares over Tailscale.
Mount them inside WSL2 at stable Linux paths, for example `/data/raw`,
`/data/results`, and `/data/shared`. Set `RAW_FILE_STORAGE_ROOT`, `RESULTS_ROOT`,
and `PROCESSOR_SHARED_STORAGE_ROOT` to those paths. Ensure the processor
service identity can read inputs/references and write job results.

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
