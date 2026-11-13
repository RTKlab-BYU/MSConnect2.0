#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_FILE="${1:-$ROOT_DIR/data/processor-smoke/inputs/mzml/CW0615_Hela_250pg_rep240_ch2_G3_DIAex480.mzML}"
FASTA_FILE="${2:-$ROOT_DIR/data/processor-smoke/inputs/human-100.fasta}"
shift $(( $# >= 2 ? 2 : $# ))

if [[ ! -f "$INPUT_FILE" ]]; then
  echo "DIA-NN smoke input is missing: $INPUT_FILE" >&2
  exit 2
fi
if [[ ! -f "$FASTA_FILE" ]]; then
  echo "DIA-NN smoke FASTA is missing: $FASTA_FILE" >&2
  exit 2
fi

INPUT_FILE="$(cd "$(dirname "$INPUT_FILE")" && pwd)/$(basename "$INPUT_FILE")"
FASTA_FILE="$(cd "$(dirname "$FASTA_FILE")" && pwd)/$(basename "$FASTA_FILE")"

input_ext="${INPUT_FILE##*.}"
input_ext="$(printf '%s' "$input_ext" | tr '[:upper:]' '[:lower:]')"
if [[ "$input_ext" != "mzml" ]]; then
  echo "Use a centroided mzML input so each DIA-NN version receives the same cross-tool file: $INPUT_FILE" >&2
  exit 2
fi

if [[ $# -gt 0 ]]; then
  images=("$@")
else
  images=("msconnect-processor-diann:2.2.0-standalone-r2")
fi

OUTPUT_ROOT="${DIANN_SMOKE_OUTPUT_DIR:-$ROOT_DIR/data/processor-smoke/results/human-100}"
TIMEOUT_SECONDS="${DIANN_SMOKE_TIMEOUT_SECONDS:-240}"
mkdir -p "$OUTPUT_ROOT"
matrix_failed=0
input_sha="$(shasum -a 256 "$INPUT_FILE" | awk '{print $1}')"
fasta_sha="$(shasum -a 256 "$FASTA_FILE" | awk '{print $1}')"
printf 'Input: %s\nInput SHA-256: %s\nFASTA: %s\nFASTA SHA-256: %s\nTimeout: %ss per image\n' \
  "$INPUT_FILE" "$input_sha" "$FASTA_FILE" "$fasta_sha" "$TIMEOUT_SECONDS"

for image in "${images[@]}"; do
  label="${image//[^[:alnum:]_.-]/_}"
  output_dir="$(mktemp -d "$OUTPUT_ROOT/$label.XXXXXX")"
  printf '\n=== %s ===\nOutput: %s\n' "$image" "$output_dir"

  if ! docker image inspect "$image" >/dev/null 2>&1; then
    printf 'FAIL: image is not available locally\n' | tee "$output_dir/status.txt"
    matrix_failed=1
    continue
  fi

  if ! docker run --rm --entrypoint diann "$image" >"$output_dir/boot.log" 2>&1; then
    printf 'FAIL: image boot check failed (see boot.log)\n' | tee "$output_dir/status.txt"
    cat "$output_dir/boot.log"
    matrix_failed=1
    continue
  fi
  cat "$output_dir/boot.log"

  set +e
  docker run --rm --cpus="${DIANN_SMOKE_CPUS:-2}" \
    -v "$INPUT_FILE:/input.mzML:ro" \
    -v "$FASTA_FILE:/reference.fasta:ro" \
    -v "$output_dir:/out" \
    --entrypoint timeout "$image" \
    --signal=TERM "${TIMEOUT_SECONDS}s" python -m core.processing.diann_search diann \
    --f /input.mzML \
    --fasta /reference.fasta \
    --fasta-search \
    --matrices \
    --out /out/report.parquet \
    --threads "${DIANN_SMOKE_THREADS:-1}" \
    --verbose 1 2>&1 | tee "$output_dir/diann.log"
  run_status=$?
  set -e

  if [[ "$run_status" -eq 124 || "$run_status" -eq 137 ]]; then
    printf 'TIMEOUT: stopped after %ss; see diann.log\n' "$TIMEOUT_SECONDS" | tee "$output_dir/status.txt"
    matrix_failed=1
    continue
  fi
  if [[ "$run_status" -ne 0 ]]; then
    printf 'FAIL: DIA-NN exited with status %s; see diann.log\n' "$run_status" | tee "$output_dir/status.txt"
    matrix_failed=1
    continue
  fi
  if [[ ! -s "$output_dir/report.parquet" ]]; then
    printf 'FAIL: DIA-NN did not create a non-empty report\n' | tee "$output_dir/status.txt"
    matrix_failed=1
    continue
  fi
  if grep -Eqi 'DIA-NN tried but failed to load|cannot load the file|No MS2 spectra: aborting' "$output_dir/diann.log"; then
    printf 'FAIL: DIA-NN reported an input-load failure; see diann.log\n' | tee "$output_dir/status.txt"
    matrix_failed=1
    continue
  fi
  if ! docker run --rm -v "$output_dir:/out:ro" --entrypoint python "$image" -c '
import pyarrow.parquet as pq
p = pq.ParquetFile("/out/report.parquet")
required = {"Protein.Group", "Precursor.Id", "Q.Value", "Precursor.Quantity"}
missing = required - set(p.schema_arrow.names)
assert {"File.Name", "Run"} & set(p.schema_arrow.names), "Missing run identity"
assert not missing, f"Not a quantitative report: missing {sorted(missing)}"
assert p.metadata.num_rows > 0, "Report contains no identifications"
from pathlib import Path
assert Path("/out/report.stats.tsv").stat().st_size > 0, "Missing stats"
assert Path("/out/report.pg_matrix.tsv").stat().st_size > 0, "Missing protein matrix"
print(f"Validated quantitative report: {p.metadata.num_rows} rows")
'; then
    printf 'FAIL: quantitative output validation failed\n' | tee "$output_dir/status.txt"
    matrix_failed=1
    continue
  fi
  printf 'PASS: report.parquet created; see diann.log\n' | tee "$output_dir/status.txt"
done

if [[ "$matrix_failed" -ne 0 ]]; then
  echo "One or more images failed; see per-image status.txt and logs under $OUTPUT_ROOT" >&2
  exit 1
fi
