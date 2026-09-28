from __future__ import annotations

import csv
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
    with generated.ms_path.open(newline="", encoding="utf-8-sig") as handle:
        records = list(csv.reader(handle))
    for position, record in enumerate(records[2:], start=1):
        if len(record) < 6 or not record[1].strip():
            continue
        filename = record[1].strip()
        condition = generated.condition_names[position - 1] if position <= len(generated.condition_names) else ""
        replicate = generated.replicate_numbers[position - 1] if position <= len(generated.replicate_numbers) else position
        rows.append(
            {
                "position": position,
                "run_name": filename,
                "sample_name": filename,
                "expected_filename": filename,
                "file_role": "sample",
                "condition": condition,
                "metadata": {
                    "source": "worklist_generation",
                    "sample_type": record[0].strip(),
                    "ms_path": record[2].strip(),
                    "ms_method": record[3].strip(),
                    "instrument_position": record[4].strip(),
                    "replicate": replicate,
                },
            }
        )
    if not rows:
        raise WorklistGenerationError("The generated MS worklist did not contain any usable runs.")
    return rows


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
