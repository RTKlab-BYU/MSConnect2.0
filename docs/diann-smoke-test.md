# Standalone DIA-NN smoke test

This local smoke test runs DIA-NN images directly with Docker. It does not call
the MSConnect API, enqueue a job, or place the test input in the watcher’s
`incoming/` directory.

## Local test fixture

- Source file: `CW0615_Hela_250pg_rep240_ch2_G3_DIAex480.raw` from
  `/Volumes/T7_Shield/tempDataMS/` (24 MB).
- Shared engine input: centroided mzML made from that source with the
  ProteoWizard `peakPicking vendor` filter (14 MB).
- mzML SHA-256:
  `6d7438928b225338fbc1c6305ed4ac03d38f67e2459c2e90f0054914be0db8c9`
- Reference: first 100 records from the local human FASTA, used to keep the
  predictor memory below the local Docker limit.
- FASTA SHA-256:
  `01a933c9cf1394bc9ab56833535d23cce315c5f103dff951f923f85a22aabaf9`

The source RAW and mzML are local smoke data and are ignored by Git under
`data/`. Keep this mzML as the shared input when comparing DIA-NN versions or
adding another tool that accepts mzML. Use the same FASTA and recorded command
for each comparison.

## Run the installed DIA-NN versions

```sh
./scripts/run-diann-smoke.sh
```

The default matrix is:

- `msconnect-processor-diann:1.8.1`
- `msconnect-processor-diann:1.9.2`
- `msconnect-processor-diann:2.0`
- `msconnect-processor-diann:2.6.1`

Run only one version, or add a later version, by passing image tags after the
two input paths:

```sh
./scripts/run-diann-smoke.sh \
  data/processor-smoke/inputs/mzml/CW0615_Hela_250pg_rep240_ch2_G3_DIAex480.mzML \
  data/processor-smoke/inputs/human-100.fasta \
  msconnect-processor-diann:2.0
```

Set `DIANN_SMOKE_OUTPUT_DIR` to save results elsewhere,
`DIANN_SMOKE_THREADS` to change the DIA-NN thread count, and
`DIANN_SMOKE_CPUS` to change Docker’s CPU limit. `DIANN_SMOKE_TIMEOUT_SECONDS`
sets the per-image run limit (default 240 seconds). Each image gets its own
output directory under `data/processor-smoke/results/human-100/`, with a boot
log, full run log, report when generated, and `status.txt`. A timeout or failure
is recorded and the runner continues to the next image; the script exits
non-zero if any image fails.

## What this validates

This is an engine and input-reader smoke test: it checks that the binary starts,
loads the shared mzML and FASTA, and writes a DIA-NN report. It runs library-free
search with predicted spectral-library generation. It does not validate
MSConnect queueing, agent health, project metadata, or scientific equivalence
between software versions. The small FASTA is intentionally a memory-limited
smoke reference, not a production search database.

The local DIA-NN 2.0 image did not read the original Thermo RAW in the initial
check (`Thermo RAW file format not supported`). The mzML conversion therefore
also makes the fixture usable with older DIA-NN images and other engines that
accept mzML.

A first run with 500 FASTA records exceeded local container memory. DIA-NN 2.0
also stalled during neural-network training with the 100-record reference, so
the runner applies a timeout and records the result before continuing. Earlier
1.8.1 and 1.9.2 reports remain under
`data/processor-smoke/results/human-100/msconnect-processor-diann_1.8.1/` and
`data/processor-smoke/results/human-100/msconnect-processor-diann_1.9.2/`.
