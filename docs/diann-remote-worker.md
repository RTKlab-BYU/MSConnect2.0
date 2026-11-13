# Dedicated DIA-NN worker

The DIA-NN Dockerfile builds independently of `msconnect:local` and does not
include the frontend, Wine, or ProteoWizard. Vendor conversion remains a separate
service. Use centroided mzML for the initial validation.

For a remote API, use `docker-compose.diann-worker.yml`. Create a private env file
with the live processor token, engine version/profile, approved Linux archive URL,
and these site values:

```dotenv
MSCONNECT_API_BASE_URL=http://100.111.228.0:8083/api
MSCONNECT_PROCESSOR_TOKEN=replace-with-live-token
DIANN_AGENT_NAME=diann-remote-1
DIANN_ENGINE_VERSION=2.2.0
DIANN_ENGINE_PROFILE=diann:2.2.0
DIANN_SOURCE_IMAGE=msconnect-processor-diann:2.2.0
DOTNET_SDK_IMAGE=msconnect-processor-diann:2.2.0
MSCONNECT_DIANN_IMAGE=msconnect-processor-diann:2.2.0-standalone
RAW_STORAGE_HOST_PATH=/mnt/msconnect/raw
RESULTS_HOST_PATH=/mnt/msconnect/results
PROCESSOR_SHARED_HOST_PATH=/mnt/msconnect/shared
```

The example reuses the approved 2.2.0 engine and .NET runtime already present on
the live server; only those runtime directories enter the new image. For a clean
build elsewhere, omit these two source-image overrides and set `DIANN_LINUX_URL`
to the approved archive for exactly the configured version. A missing engine
fails the build.

Tailscale provides network connectivity. Mount the server's storage on the worker
host separately (for example via the site's existing SMB/NFS shares). The API
server must see outputs at the same `/data/results` paths sent by the worker.
Before starting a worker, verify those mounts expose the actual raw data and
references and that an output written by the worker is readable on the server.

```sh
docker compose --env-file /path/to/worker.env -f docker-compose.diann-worker.yml build
docker compose --env-file /path/to/worker.env -f docker-compose.diann-worker.yml run --rm processor-diann python manage.py check_agent_runtime --role processor --engine diann --write-test
docker compose --env-file /path/to/worker.env -f docker-compose.diann-worker.yml up -d
```

A FASTA search now uses separate prediction and quantitative-search invocations,
with `search-library.predicted.speclib` retained in the job directory. Providing an
existing library skips prediction. Every invocation must succeed. The importer
rejects library-shaped Parquet before processing rows. Renewals occur during the
engine run and immediately before output handling and completion.

Run `scripts/run-diann-smoke.sh INPUT.mzML REFERENCE.fasta IMAGE` for local engine
validation. It requires a quantitative report with identification rows, stats,
and a protein matrix. The tiny 100-record fixture is a launcher/search fixture;
its identifications cannot validate a production biological analysis. Keep the
image digest, command, input/reference hashes, logs and complete output directory.

Live acceptance also requires an isolated job to complete and import results on
the target API. Health/readiness checks alone do not establish worker integration.

## Validation recorded 2026-11-12

Built on `rtklab@100.111.228.0` as
`msconnect-processor-diann:2.2.0-standalone` (approximately 1.66 GB).
Final image ID:
`sha256:6780ff31deb541649fd660b10b7847314bd8d09a1a41e0172a5963c9b88d68c9`.
The build reused the existing approved 2.2.0 engine and .NET directories; it did
not rebuild or overwrite the server's modified source checkout.

The final image passed engine/runtime preflight, authenticated API ping, and
shared raw/reference/results storage checks. Health and readiness endpoints and
an authenticated API ping also passed from this workstation over Tailscale.

Live project `DIANN-IMAGE-VALIDATION`, job 41, completed through the new worker's
start, execution, renewal, artifact collection and completion methods. The job
was assigned explicitly to a validation node, without consuming the production
queue. The API recorded 13 artifacts and imported a quantitative Parquet report.
The test used a short centroided HeLa fixture and 15 protein FASTA entries;
the assigned diagnostic job explicitly disabled the neural-network classifier.
Its report contained zero accepted identifications. A separate direct container
run with default classification also completed with a valid empty report.
A second validation used the complete 338,785,647-byte Thermo RAW acquisition
`LL2110_Hela_P1_250pgWet_blo4_rep1_ch1_R1_DIA250pg.raw`, with default classification,
four threads, and the same small reference. Native RAW loading succeeded and the
search finished in about 12 seconds, producing 142 quantitative rows. Assigned
job 42 then exercised start, execution, renewal, artifact collection, API
completion, and real database import: complete status, 13 artifacts, 142 peptide
quantities and 15 protein abundance records. These are import counts, not a
claim of 15 proteins passing a protein-level FDR threshold. The test harness
explicitly used the dedicated validation pipeline rather than the acquisition
worklist's full-proteome processing plan. Original failed jobs were preserved.

This validates packaging, native RAW reading, file production, shared storage,
and nonempty quantitative import. It does not benchmark full-proteome coverage
or import throughput on very large reports. The strict smoke runner continues
to require nonempty output; the tiny arbitrary 100-record reference is unsuitable
for that acceptance condition.

44 local regression tests passed across result import, processing and operations.
The existing production worker service remains on its prior image; no failed
production batch was requeued. The candidate image and isolated evidence remain
on the server under `/tmp/msconnect-diann-validation/`, with job outputs retained
under `/data/results/jobs/41/` and source files under the isolated validation
build directory. Use a pilot with the approved full reference/library and pinned acquisition
settings before broadly requeuing the failed production batch.

The worker fixes also distinguish reference dependencies from MS inputs, use an
absolute helper path when executing from job directories, create DIA-NN scratch
directories, and register predicted libraries for subsequent reuse. An exhausted
initial-build count cannot trigger reuse until a preferred library actually
exists. The importer accepts both `Run` and `File.Name`, including the managed
storage basename containing the checksum prefix.
