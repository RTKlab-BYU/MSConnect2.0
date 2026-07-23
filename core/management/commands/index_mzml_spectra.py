import base64
import json
import math
import struct
import zlib
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import (
    DerivativeStatus,
    RawFile,
    RawFileDerivative,
    RawFileDerivativeType,
)


class Command(BaseCommand):
    help = "Create bounded spectrum-index JSON derivatives for imported mzML raw files."

    def add_arguments(self, parser):
        parser.add_argument("--raw-file-id", type=int, action="append", dest="raw_file_ids")
        parser.add_argument("--project", type=int)
        parser.add_argument("--all-mzml", action="store_true")
        parser.add_argument("--max-spectra", type=int, default=2500)
        parser.add_argument("--max-peaks", type=int, default=300)

    def handle(self, *args, **options):
        queryset = RawFile.objects.select_related("run", "run__sample", "run__sample__experiment__project")
        if options["raw_file_ids"]:
            queryset = queryset.filter(id__in=options["raw_file_ids"])
        elif options["project"]:
            queryset = queryset.filter(run__sample__experiment__project_id=options["project"])
        elif not options["all_mzml"]:
            raise CommandError("Provide --raw-file-id, --project, or --all-mzml.")

        queryset = queryset.filter(filename__iendswith=".mzml").order_by("id")
        count = 0
        for raw_file in queryset:
            mzml_path = Path(raw_file.storage_path)
            if not mzml_path.exists():
                self.stderr.write(self.style.WARNING(f"missing {raw_file.id}: {mzml_path}"))
                continue
            payload = _index_mzml(mzml_path, max_spectra=options["max_spectra"], max_peaks=options["max_peaks"])
            output_dir = Path(settings.RESULTS_ROOT) / "spectrum-indexes" / str(raw_file.id)
            output_dir.mkdir(parents=True, exist_ok=True)
            index_path = output_dir / f"{mzml_path.stem}.spectrum-index.json"
            index_path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")

            RawFileDerivative.objects.update_or_create(
                raw_file=raw_file,
                derivative_type=RawFileDerivativeType.MZML,
                path=str(mzml_path.resolve()),
                defaults={
                    "status": DerivativeStatus.READY,
                    "format": "mzML",
                    "size_bytes": mzml_path.stat().st_size,
                    "metadata": {"source": "raw_file_storage"},
                },
            )
            RawFileDerivative.objects.update_or_create(
                raw_file=raw_file,
                derivative_type=RawFileDerivativeType.SPECTRUM_INDEX,
                path=str(index_path.resolve()),
                defaults={
                    "status": DerivativeStatus.READY,
                    "format": "json",
                    "size_bytes": index_path.stat().st_size,
                    "metadata": payload.get("metadata", {}),
                },
            )
            count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"indexed {raw_file.filename}: {payload['metadata']['total_spectra']} spectra "
                    f"({payload['metadata']['ms1_spectra']} MS1, {payload['metadata']['ms2_spectra']} MS2)"
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Indexed {count} mzML raw files."))


def _index_mzml(path: Path, *, max_spectra: int, max_peaks: int) -> dict:
    spectra = []
    tic = []
    bpc = []
    total_spectra = 0
    ms1_spectra = 0
    ms2_spectra = 0

    for _event, spectrum in ElementTree.iterparse(path, events=("end",)):
        if _local_name(spectrum.tag) != "spectrum":
            continue
        total_spectra += 1
        summary = _spectrum_summary(spectrum, max_peaks=max_peaks)
        ms_level = summary.get("ms_level")
        if ms_level == 1:
            ms1_spectra += 1
        elif ms_level == 2:
            ms2_spectra += 1

        rt = summary.get("retention_time_seconds")
        if rt is not None:
            if summary.get("tic") is not None:
                tic.append([rt, summary["tic"]])
            if summary.get("base_peak_intensity") is not None:
                bpc.append([rt, summary["base_peak_intensity"]])

        if len(spectra) < max_spectra:
            spectra.append(summary)
        spectrum.clear()

    return {
        "metadata": {
            "source_file": str(path),
            "total_spectra": total_spectra,
            "stored_spectra": len(spectra),
            "ms1_spectra": ms1_spectra,
            "ms2_spectra": ms2_spectra,
            "max_peaks_per_spectrum": max_peaks,
            "indexer": "index_mzml_spectra",
        },
        "spectra": spectra,
        "chromatograms": {"tic": tic, "bpc": bpc},
    }


def _spectrum_summary(spectrum, *, max_peaks: int) -> dict:
    cv_params = _cv_params(spectrum)
    mz_array = None
    intensity_array = None
    for binary_array in spectrum.findall(".//{*}binaryDataArray"):
        array_params = _cv_params(binary_array)
        if "MS:1000514" in array_params:
            mz_array = _decode_binary_array(binary_array, array_params, kind="mz")
        elif "MS:1000515" in array_params:
            intensity_array = _decode_binary_array(binary_array, array_params, kind="intensity")

    peaks = []
    if mz_array and intensity_array:
        for mz, intensity in zip(mz_array, intensity_array, strict=False):
            if math.isfinite(mz) and math.isfinite(intensity) and intensity >= 0:
                peaks.append([round(mz, 6), round(float(intensity), 3)])
        if len(peaks) > max_peaks:
            peaks = sorted(peaks, key=lambda item: item[1], reverse=True)[:max_peaks]
            peaks.sort(key=lambda item: item[0])

    spectrum_id = spectrum.attrib.get("id", "")
    scan_number = _scan_number(spectrum_id)
    return {
        "id": spectrum_id or str(spectrum.attrib.get("index", "")),
        "index": _int_or_none(spectrum.attrib.get("index")),
        "scan_number": scan_number,
        "ms_level": _int_or_none(_cv_value(cv_params, "MS:1000511")),
        "retention_time_seconds": _retention_time_seconds(spectrum),
        "base_peak_mz": _float_or_none(_cv_value(cv_params, "MS:1000504")),
        "base_peak_intensity": _float_or_none(_cv_value(cv_params, "MS:1000505")),
        "tic": _float_or_none(_cv_value(cv_params, "MS:1000285")),
        "precursor_mz": _precursor_mz(spectrum),
        "peaks": peaks,
    }


def _decode_binary_array(binary_array, cv_params: dict, *, kind: str) -> list[float]:
    binary = binary_array.find("{*}binary")
    if binary is None or not binary.text:
        return []
    try:
        data = base64.b64decode(binary.text.strip())
        if "MS:1000574" in cv_params:
            data = zlib.decompress(data)
    except (ValueError, zlib.error):
        return []

    if "MS:1000521" in cv_params:
        byte_width = 4
        code = "f"
    else:
        byte_width = 8
        code = "d"
    if len(data) < byte_width:
        return []

    little = _unpack(data, byte_width=byte_width, code=code, endian="<")
    big = _unpack(data, byte_width=byte_width, code=code, endian=">")
    return little if _array_score(little, kind=kind) >= _array_score(big, kind=kind) else big


def _unpack(data: bytes, *, byte_width: int, code: str, endian: str) -> list[float]:
    count = len(data) // byte_width
    try:
        return list(struct.unpack(f"{endian}{count}{code}", data[: count * byte_width]))
    except struct.error:
        return []


def _array_score(values: list[float], *, kind: str) -> float:
    if not values:
        return -1
    sample = values[: min(len(values), 200)]
    finite = [value for value in sample if math.isfinite(value)]
    if not finite:
        return -1
    if kind == "mz":
        plausible = [value for value in finite if 0 < value < 100000]
        monotonic = sum(1 for left, right in zip(plausible, plausible[1:], strict=False) if right >= left)
        return len(plausible) + monotonic / max(len(plausible), 1)
    plausible = [value for value in finite if 0 <= value < 1e20]
    return len(plausible)


def _cv_params(element) -> dict:
    params = {}
    for cv_param in element.findall(".//{*}cvParam"):
        accession = cv_param.attrib.get("accession")
        if accession:
            params[accession] = cv_param.attrib
    return params


def _cv_value(params: dict, accession: str) -> str | None:
    item = params.get(accession)
    return item.get("value") if item else None


def _retention_time_seconds(spectrum) -> float | None:
    for cv_param in spectrum.findall(".//{*}scan/{*}cvParam"):
        if cv_param.attrib.get("accession") != "MS:1000016":
            continue
        value = _float_or_none(cv_param.attrib.get("value"))
        if value is None:
            return None
        unit = (cv_param.attrib.get("unitName") or "").lower()
        return value * 60 if "minute" in unit else value
    return None


def _precursor_mz(spectrum) -> float | None:
    for cv_param in spectrum.findall(".//{*}selectedIon/{*}cvParam"):
        if cv_param.attrib.get("accession") in {"MS:1000744", "MS:1000827"}:
            value = _float_or_none(cv_param.attrib.get("value"))
            if value is not None:
                return value
    return None


def _scan_number(spectrum_id: str) -> int | None:
    if "scan=" not in spectrum_id:
        return None
    return _int_or_none(spectrum_id.rsplit("scan=", 1)[-1].split()[0])


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
