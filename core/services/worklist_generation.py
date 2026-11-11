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
    condition_types: tuple[str, ...] = ()


def generated_worklist_rows(generated: GeneratedWorklist) -> list[dict[str, object]]:
    """Translate the MS CSV into the application's run-ground-truth rows."""
    rows: list[dict[str, object]] = []
    condition_by_filename = dict(zip(generated.filenames, generated.condition_names, strict=False))
    type_by_filename = dict(zip(generated.filenames, generated.condition_types, strict=False))
    replicate_by_filename = dict(zip(generated.filenames, generated.replicate_numbers, strict=False))
    hye_pair_occurrences: dict[tuple[str, str], int] = {}
    with generated.ms_path.open(newline="", encoding="utf-8-sig") as handle:
        records = list(csv.reader(handle))
    lc_metadata_by_filename: dict[str, dict[str, str]] = {}
    if generated.lc_path.is_file():
        with generated.lc_path.open(newline="", encoding="utf-8-sig") as handle:
            for record in list(csv.reader(handle))[2:]:
                if len(record) >= 6 and record[1].strip():
                    lc_metadata_by_filename[record[1].strip()] = {
                        "lc_data_path": record[2].strip(),
                        "lc_method": record[3].strip(),
                        "lc_position": record[4].strip(),
                        "injection_volume": record[5].strip(),
                    }
    for position, record in enumerate(records[2:], start=1):
        if len(record) < 6 or not record[1].strip():
            continue
        filename = record[1].strip()
        condition = str(condition_by_filename.get(filename, ""))
        well_type = str(type_by_filename.get(filename, "")).strip()
        normalized_type = re.sub(r"[\s-]+", "_", well_type.lower())
        replicate = replicate_by_filename.get(filename, position)
        is_preblank = "_preblank" in filename.lower()
        hye_match = re.search(r"(?:^|[_\-\s])HYE[_\-\s]?([AB])(?:[_\-\s]|$)", filename, re.IGNORECASE)
        if hye_match or normalized_type == "hye":
            file_role = "hye"
        elif normalized_type in {"trueblank", "true_blank"}:
            file_role = "true_blank"
        elif normalized_type == "blank" or is_preblank:
            file_role = "blank"
        elif normalized_type in {
            "qc",
            "wetqc",
            "wet_qc",
            "prepqc",
            "prep_qc",
            "preparationqc",
            "preparation_qc",
            "processqc",
            "process_qc",
            "digestionqc",
            "digestion_qc",
            "systemvalidation",
            "system_validation",
        }:
            file_role = "qc"
        elif normalized_type in {"library", "lib"}:
            file_role = "library"
        else:
            file_role = "sample"
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
                "notes": "",
                "condition": condition,
                "metadata": {
                    "source": "worklist_generation",
                    "vendor_sample_type": record[0].strip(),
                    "generator_condition_type": well_type or ("instrument_preblank" if is_preblank else ""),
                    "sample_type": well_type or ("blank" if is_preblank else record[0].strip()),
                    "ms_path": record[2].strip(),
                    "ms_method": record[3].strip(),
                    "instrument_position": record[4].strip(),
                    **lc_metadata_by_filename.get(filename, {}),
                    "replicate": replicate,
                    "source_sample_name": filename,
                    "hye_mix": hye_match.group(1).upper() if hye_match else "",
                    **({"blank_type": "instrument_preblank" if is_preblank else "true_blank" if file_role == "true_blank" else "blank"} if file_role in {"blank", "true_blank"} else {}),
                    **({"qc_stage": normalized_type, "qc_material": condition} if file_role == "qc" else {}),
                    "role_tagging_required": file_role == "sample" and normalized_type not in {"sample", "experimental_sample", "specimen"},
                    "role_confirmed": file_role != "sample" or normalized_type in {"sample", "experimental_sample", "specimen"},
                },
            }
        )
    if not rows:
        raise WorklistGenerationError("The generated MS worklist did not contain any usable runs.")
    return rows


def namespace_generated_worklist(generated: GeneratedWorklist, rows: list[dict[str, object]], namespace: str) -> None:
    """Keep generated instrument filenames unique across project acquisitions."""
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", namespace).strip("_- ")
    if not suffix:
        raise WorklistGenerationError("A project and worklist name are required to make generated filenames unique.")

    def scoped_name(filename: str) -> str:
        stem, separator, extension = filename.rpartition(".")
        if not separator:
            stem, extension = filename, ""
        else:
            extension = f".{extension}"
        suffix_part = f"_{suffix}"
        stem = stem[: 255 - len(extension) - len(suffix_part)]
        return f"{stem}{suffix_part}{extension}"

    for row in rows:
        original_name = str(row["expected_filename"])
        instrument_filename = scoped_name(original_name)
        row["expected_filename"] = instrument_filename
        row["run_name"] = instrument_filename
        metadata = dict(row.get("metadata") or {})
        metadata["source_sample_name"] = metadata.get("source_sample_name") or original_name
        metadata["instrument_filename"] = instrument_filename
        metadata["filename_namespace"] = suffix
        row["metadata"] = metadata

    for path in (generated.ms_path, generated.lc_path):
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            records = list(csv.reader(handle))
        for record in records[2:]:
            if len(record) >= 2 and record[1].strip():
                record[1] = scoped_name(record[1].strip())
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            csv.writer(handle, lineterminator="\n").writerows(records)


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
        ms_frame, lc_frame, ms_name, lc_name, filenames, condition_names, condition_types, replicate_numbers = main(str(input_path))
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
        condition_types=tuple(str(value) for value in condition_types),
    )
