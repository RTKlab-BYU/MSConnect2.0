from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


class WorklistGenerationError(Exception):
    """Raised when a generator workbook cannot be converted safely."""


@dataclass(frozen=True)
class GeneratedWorklist:
    input_path: Path
    output_directory: Path
    ms_path: Path
    lc_path: Path
    filenames: tuple[str, ...]
    condition_names: tuple[str, ...]
    replicate_numbers: tuple[int, ...]


def generated_worklist_rows(generated: GeneratedWorklist) -> list[dict[str, object]]:
    """Translate the MS CSV into the application's run-ground-truth rows."""
    rows: list[dict[str, object]] = []
    hye_pair_occurrences: dict[tuple[str, str], int] = {}
    with generated.ms_path.open(newline="", encoding="utf-8-sig") as handle:
        records = list(csv.reader(handle))
    for position, record in enumerate(records[2:], start=1):
        if len(record) < 6 or not record[1].strip():
            continue
        filename = record[1].strip()
        condition = generated.condition_names[position - 1] if position <= len(generated.condition_names) else ""
        replicate = generated.replicate_numbers[position - 1] if position <= len(generated.replicate_numbers) else position
        hye_match = re.search(r"(?:^|[_\-\s])HYE[_\-\s]?([AB])(?:[_\-\s]|$)", filename, re.IGNORECASE)
        file_role = "hye" if hye_match else "sample"
        qc_program = "hye" if hye_match else ""
        sample_name = f"HYE-{hye_match.group(1).upper()}" if hye_match else filename
        pair_label = ""
        if hye_match:
            context = re.sub(r"(?:^|[_\-\s])HYE[_\-\s]?[AB](?=[_\-\s]|$)", "_HYE_", filename, count=1, flags=re.IGNORECASE)
            context = re.sub(r"(?:^|[_-])B[A-Z]\d+", "_", context, flags=re.IGNORECASE)
            context = re.sub(r"(?:^|[_-])Run\d+", "_", context, flags=re.IGNORECASE)
            replicate_match = re.search(r"(?:^|[_-])Rep(?:licate)?[_-]?(\d+)", context, re.IGNORECASE)
            base_context = re.sub(r"(?:^|[_-])Rep(?:licate)?[_-]?\d*", "_", context, flags=re.IGNORECASE)
            base_context = re.sub(r"[_-]+", "_", base_context).strip("_")
            mix = hye_match.group(1).upper()
            if replicate_match:
                pair_replicate = replicate_match.group(1)
            else:
                occurrence_key = (base_context, mix)
                hye_pair_occurrences[occurrence_key] = hye_pair_occurrences.get(occurrence_key, 0) + 1
                pair_replicate = str(hye_pair_occurrences[occurrence_key])
            compact_context = re.sub(r"[^A-Za-z0-9_-]", "_", base_context)[:42]
            pair_label = f"HYE-{compact_context}-Rep{pair_replicate}"[:64]
        rows.append(
            {
                "position": position,
                "run_name": filename,
                "sample_name": sample_name,
                "expected_filename": filename,
                "file_role": file_role,
                "qc_program": qc_program,
                "hye_pair_label": pair_label,
                "condition": condition,
                "metadata": {
                    "source": "worklist_generation",
                    "sample_type": record[0].strip(),
                    "ms_path": record[2].strip(),
                    "ms_method": record[3].strip(),
                    "instrument_position": record[4].strip(),
                    "replicate": replicate,
                    "source_sample_name": filename,
                    "hye_mix": hye_match.group(1).upper() if hye_match else "",
                },
            }
        )
    if not rows:
        raise WorklistGenerationError("The generated MS worklist did not contain any usable runs.")
    return rows


def validate_generated_hye_pairs(rows: list[dict[str, object]]) -> None:
    """Reject generated HYE controls that cannot be queried as exact A/B pairs."""
    grouped: dict[str, list[str]] = {}
    for row in rows:
        if row.get("file_role") != "hye" and row.get("qc_program") != "hye":
            continue
        label = str(row.get("hye_pair_label") or "").strip()
        sample = str(row.get("sample_name") or "").strip().upper()
        if not label or sample not in {"HYE-A", "HYE-B"}:
            raise WorklistGenerationError("Detected HYE controls must have a pair label and map to HYE-A or HYE-B.")
        grouped.setdefault(label, []).append(sample)
    for label, mixes in grouped.items():
        if len(mixes) != 2 or mixes.count("HYE-A") != 1 or mixes.count("HYE-B") != 1:
            raise WorklistGenerationError(f"Generated HYE pair {label} must contain exactly one A and one B injection.")


def generate_vendor_worklists(input_path: Path, output_directory: Path) -> GeneratedWorklist:
    """Run the deterministic upstream algorithm without its SQLite/CLI layers."""
    input_path = Path(input_path).resolve()
    output_directory = Path(output_directory).resolve()
    if not input_path.is_file():
        raise WorklistGenerationError(f"Worklist workbook does not exist: {input_path}")
    output_directory.mkdir(parents=True, exist_ok=True)

    try:
        from core.worklist_generator.vendor.worklist_classes.main import main
    except ImportError as exc:
        raise WorklistGenerationError(
            "Worklist generation requires pandas, numpy, and openpyxl in the application environment."
        ) from exc

    try:
        ms_frame, lc_frame, ms_name, lc_name, filenames, condition_names, replicate_numbers = main(str(input_path))
        ms_path = output_directory / Path(ms_name).name
        lc_path = output_directory / Path(lc_name).name
        ms_frame.to_csv(ms_path, index=False, header=False, encoding="utf-8-sig")
        lc_frame.to_csv(lc_path, index=False, header=False, encoding="utf-8-sig")
    except Exception as exc:
        raise WorklistGenerationError(f"Could not generate vendor worklists from {input_path.name}: {exc}") from exc

    return GeneratedWorklist(
        input_path=input_path,
        output_directory=output_directory,
        ms_path=ms_path,
        lc_path=lc_path,
        filenames=tuple(str(value) for value in filenames),
        condition_names=tuple(str(value) for value in condition_names),
        replicate_numbers=tuple(int(value) for value in replicate_numbers),
    )
