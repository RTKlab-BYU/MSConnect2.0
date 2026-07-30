import csv
import json
from pathlib import Path


class PostprocessError(Exception):
    pass


def run_postprocess(*, name: str, parameters: dict, results_dir: Path) -> dict:
    normalized = str(name or "").strip().lower().replace("-", "_")
    if not normalized:
        return {}
    if normalized == "skyline_prtc":
        return skyline_prtc_postprocess(parameters=parameters, results_dir=results_dir)
    raise PostprocessError(f"Unknown processor postprocess step: {name}")


def skyline_prtc_postprocess(*, parameters: dict, results_dir: Path) -> dict:
    results_dir = Path(results_dir)
    result_files = parameters.get("result_files") or {}
    report_path = _safe_results_path(results_dir, parameters.get("report") or "skyline-prtc-report.csv")
    peptide_path = _safe_results_path(results_dir, result_files.get("peptide_table") or "skyline-prtc-peptides.csv")
    stats_path = _safe_results_path(results_dir, result_files.get("stats_json") or "skyline-prtc-stats.json")
    settings = parameters.get("prtc") or {}
    column_map = {str(k).strip().lower(): str(v).strip() for k, v in (parameters.get("column_map") or {}).items()}
    expected = _expected_peptides(parameters)
    if not expected:
        raise PostprocessError("skyline_prtc postprocess requires expected_peptides.")

    rows = list(_iter_rows(report_path))
    measurements = _measurements(rows, column_map=column_map)
    selected = _select_expected_measurements(expected=expected, measurements=measurements)
    peptide_path.parent.mkdir(parents=True, exist_ok=True)
    _write_peptide_table(peptide_path, selected)

    stats = _stats_payload(
        expected=expected,
        selected=selected,
        report_path=report_path,
        peptide_path=peptide_path,
        thresholds={
            "default_rt_tolerance_seconds": _floatish(settings.get("rt_tolerance_seconds"), default=60.0),
            "default_min_area": _floatish(settings.get("min_area"), default=0.0),
        },
    )
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "skyline_prtc": {
            "peptide_table": str(peptide_path),
            "stats_json": str(stats_path),
            "status": stats["status"],
            "detected_peptide_count": stats["detected_peptide_count"],
            "expected_peptide_count": stats["expected_peptide_count"],
        }
    }


def _safe_results_path(results_dir: Path, value) -> Path:
    candidate = Path(str(value or ""))
    if not candidate.is_absolute():
        candidate = results_dir / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(results_dir.resolve()):
        raise PostprocessError("Postprocess paths must stay under the job results directory.")
    return candidate


def _expected_peptides(parameters: dict) -> list[dict]:
    values = parameters.get("expected_peptides") or (parameters.get("prtc") or {}).get("expected_peptides") or []
    expected = []
    for index, item in enumerate(values, start=1):
        if isinstance(item, str):
            entry = {"sequence": item, "label": item}
        elif isinstance(item, dict):
            entry = dict(item)
            entry.setdefault("sequence", entry.get("peptide") or entry.get("modified_sequence") or "")
            entry.setdefault("label", entry.get("sequence") or f"PRTC{index:02d}")
        else:
            raise PostprocessError("expected_peptides entries must be strings or objects.")
        sequence = str(entry.get("sequence") or "").strip()
        if not sequence:
            raise PostprocessError("expected_peptides entries require a sequence.")
        entry["sequence"] = sequence
        entry["modified_sequence"] = str(entry.get("modified_sequence") or "").strip()
        if entry.get("charge") not in (None, ""):
            try:
                entry["charge"] = int(entry["charge"])
            except (TypeError, ValueError) as exc:
                raise PostprocessError(f"Invalid charge for expected peptide {sequence}.") from exc
        else:
            entry["charge"] = None
        entry["expected_rt_seconds"] = _floatish(entry.get("expected_rt_seconds") or entry.get("expected_rt"))
        entry["rt_tolerance_seconds"] = _floatish(entry.get("rt_tolerance_seconds") or entry.get("rt_tolerance"))
        entry["min_area"] = _floatish(entry.get("min_area"))
        expected.append(entry)
    return expected


def _iter_rows(report_path: Path):
    if not report_path.exists():
        raise PostprocessError(f"Skyline report does not exist: {report_path}")
    delimiter = "\t" if report_path.suffix.lower() == ".tsv" else ","
    with report_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise PostprocessError(f"Skyline report has no header: {report_path}")
        for row in reader:
            normalized = {_normalize_header(k): (v or "").strip() for k, v in row.items()}
            if any(normalized.values()):
                yield normalized


def _measurements(rows: list[dict], *, column_map: dict[str, str]) -> list[dict]:
    measurements = []
    for row in rows:
        sequence = _value(row, column_map, "sequence", "peptide", "peptidesequence", "peptidemodifiedsequence")
        modified = _value(row, column_map, "modified_sequence", "modifiedpeptide", "peptidemodifiedsequence") or ""
        if not sequence and modified:
            sequence = modified
        if not sequence:
            continue
        area = _floatish(
            _value(row, column_map, "area", "totalarea", "peakarea", "precursorarea", "transitionarea"),
            default=0.0,
        )
        measurements.append(
            {
                "sequence": sequence,
                "modified_sequence": modified,
                "charge": _intish(_value(row, column_map, "charge", "precursorcharge", "peptidecharge")),
                "area": area,
                "retention_time_seconds": _floatish(
                    _value(row, column_map, "retention_time_seconds", "rt", "retentiontime", "bestretentiontime")
                ),
                "mz": _floatish(_value(row, column_map, "mz", "precursormz", "productmz")),
                "score": _floatish(_value(row, column_map, "score", "dotp", "librarydotproduct", "isotopedotp")),
                "mass_error_ppm": _floatish(_value(row, column_map, "mass_error_ppm", "masserrorppm")),
            }
        )
    return measurements


def _select_expected_measurements(*, expected: list[dict], measurements: list[dict]) -> list[dict]:
    selected = []
    for entry in expected:
        candidates = [item for item in measurements if _matches_expected(entry, item)]
        measurement = max(candidates, key=lambda item: item["area"], default=None)
        selected.append({**entry, "measurement": measurement})
    return selected


def _matches_expected(expected: dict, measurement: dict) -> bool:
    expected_sequence = _plain_sequence(expected["sequence"])
    measured_sequence = _plain_sequence(measurement["sequence"])
    if expected_sequence != measured_sequence:
        return False
    if expected.get("charge") and measurement.get("charge") and expected["charge"] != measurement["charge"]:
        return False
    return True


def _write_peptide_table(path: Path, selected: list[dict]) -> None:
    fieldnames = [
        "sequence",
        "modified_sequence",
        "charge",
        "label",
        "value",
        "unit",
        "score",
        "retention_time_seconds",
        "mz",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in selected:
            measurement = entry.get("measurement")
            if not measurement:
                continue
            writer.writerow(
                {
                    "sequence": _plain_sequence(entry["sequence"]),
                    "modified_sequence": entry.get("modified_sequence") or measurement.get("modified_sequence") or "",
                    "charge": entry.get("charge") or measurement.get("charge") or "",
                    "label": "prtc_area",
                    "value": measurement.get("area") or 0,
                    "unit": "area",
                    "score": measurement.get("score") if measurement.get("score") is not None else "",
                    "retention_time_seconds": (
                        measurement.get("retention_time_seconds")
                        if measurement.get("retention_time_seconds") is not None
                        else ""
                    ),
                    "mz": measurement.get("mz") if measurement.get("mz") is not None else "",
                }
            )


def _stats_payload(
    *,
    expected: list[dict],
    selected: list[dict],
    report_path: Path,
    peptide_path: Path,
    thresholds: dict,
):
    detected = []
    missing = []
    out_of_tolerance = []
    total_area = 0.0
    rt_shifts = []
    for entry in selected:
        measurement = entry.get("measurement")
        if not measurement:
            missing.append(entry["sequence"])
            continue
        total_area += float(measurement.get("area") or 0.0)
        peptide_status = "pass"
        expected_rt = entry.get("expected_rt_seconds")
        measured_rt = measurement.get("retention_time_seconds")
        tolerance = entry.get("rt_tolerance_seconds") or thresholds["default_rt_tolerance_seconds"]
        rt_shift = None
        if expected_rt is not None and measured_rt is not None:
            rt_shift = measured_rt - expected_rt
            rt_shifts.append(rt_shift)
            if abs(rt_shift) > tolerance:
                peptide_status = "fail"
        min_area = entry.get("min_area")
        if min_area is None:
            min_area = thresholds["default_min_area"]
        if min_area and float(measurement.get("area") or 0.0) < min_area:
            peptide_status = "fail"
        if peptide_status != "pass":
            out_of_tolerance.append(entry["sequence"])
        detected.append(
            {
                "sequence": entry["sequence"],
                "status": peptide_status,
                "area": measurement.get("area") or 0,
                "retention_time_seconds": measured_rt,
                "rt_shift_seconds": rt_shift,
                "score": measurement.get("score"),
                "mass_error_ppm": measurement.get("mass_error_ppm"),
            }
        )
    status = "pass"
    if missing or out_of_tolerance:
        status = "fail"
    elif len(detected) < len(expected):
        status = "warn"
    return {
        "program": "prtc",
        "status": status,
        "expected_peptide_count": len(expected),
        "detected_peptide_count": len(detected),
        "missing_peptide_count": len(missing),
        "out_of_tolerance_peptide_count": len(out_of_tolerance),
        "missing_peptides": missing,
        "out_of_tolerance_peptides": out_of_tolerance,
        "total_area": total_area,
        "mean_rt_shift_seconds": _mean(rt_shifts),
        "max_abs_rt_shift_seconds": max((abs(value) for value in rt_shifts), default=None),
        "peptides": detected,
        "source_files": {
            "skyline_report": str(report_path),
            "peptide_table": str(peptide_path),
        },
    }


def _value(row: dict, column_map: dict[str, str], key: str, *aliases: str):
    mapped = column_map.get(key)
    candidates = [mapped] if mapped else []
    candidates.extend(aliases)
    candidates.append(key)
    for candidate in candidates:
        normalized = _normalize_header(candidate)
        value = row.get(normalized)
        if value not in (None, ""):
            return value
    return ""


def _normalize_header(value) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch == "_")


def _plain_sequence(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalpha())


def _floatish(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _intish(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]):
    if not values:
        return None
    return sum(values) / len(values)
