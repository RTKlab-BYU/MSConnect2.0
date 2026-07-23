import csv
import json
from pathlib import Path, PureWindowsPath

from django.core.management.base import BaseCommand, CommandError

from core.models import ProcessingJob


class Command(BaseCommand):
    help = "Write per-job protein/peptide CSVs and stats JSON from downloaded PRIDE DIA-NN matrices."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("results_dir")
        parser.add_argument("--pg-matrix", required=True)
        parser.add_argument("--pr-matrix", required=True)
        parser.add_argument("--stats", required=True)
        parser.add_argument("--max-proteins", type=int, default=750)
        parser.add_argument("--max-peptides", type=int, default=1500)

    def handle(self, *args, **options):
        job = ProcessingJob.objects.select_related("raw_file").get(pk=options["job_id"])
        results_dir = Path(options["results_dir"])
        results_dir.mkdir(parents=True, exist_ok=True)

        sample_key = _sample_key(job.raw_file.filename)
        pg_matrix = Path(options["pg_matrix"])
        pr_matrix = Path(options["pr_matrix"])
        stats_path = Path(options["stats"])

        protein_column = _matching_quantity_column(pg_matrix, sample_key=sample_key)
        peptide_column = _matching_quantity_column(pr_matrix, sample_key=sample_key)
        stats_row = _matching_stats_row(stats_path, sample_key=sample_key)

        protein_count = _write_protein_csv(
            source=pg_matrix,
            quantity_column=protein_column,
            target=results_dir / "proteins.csv",
            limit=options["max_proteins"],
        )
        peptide_count = _write_peptide_csv(
            source=pr_matrix,
            quantity_column=peptide_column,
            target=results_dir / "peptides.csv",
            limit=options["max_peptides"],
        )
        stats = _stats_payload(stats_row, protein_count=protein_count, peptide_count=peptide_count)
        (results_dir / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {protein_count} proteins, {peptide_count} peptides, and stats for {job.raw_file.filename}"
            )
        )


def _sample_key(value: str) -> str:
    name = PureWindowsPath(value).name or Path(value).name
    for suffix in (".mzML", ".mzXML", ".raw", ".RAW"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.lower()


def _matching_quantity_column(path: Path, *, sample_key: str) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for fieldname in reader.fieldnames or []:
            if _sample_key(fieldname) == sample_key:
                return fieldname
    raise CommandError(f"No matrix quantity column matched sample {sample_key!r} in {path}")


def _matching_stats_row(path: Path, *, sample_key: str) -> dict:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            if _sample_key(row.get("File.Name", "")) == sample_key:
                return row
    raise CommandError(f"No stats row matched sample {sample_key!r} in {path}")


def _write_protein_csv(*, source: Path, quantity_column: str, target: Path, limit: int) -> int:
    count = 0
    with source.open("r", encoding="utf-8", newline="") as input_file, target.open(
        "w", encoding="utf-8", newline=""
    ) as output_file:
        reader = csv.DictReader(input_file, delimiter="\t")
        writer = csv.DictWriter(
            output_file,
            fieldnames=(
                "accession",
                "label",
                "value",
                "unit",
                "score",
                "q_value",
                "coverage_percent",
                "peptide_count",
                "organism",
            ),
        )
        writer.writeheader()
        for row in reader:
            value = _positive_float(row.get(quantity_column))
            if value is None:
                continue
            accession = (row.get("Protein.Group") or "").split(";")[0][:128]
            if not accession:
                continue
            writer.writerow(
                {
                    "accession": accession,
                    "label": "abundance",
                    "value": value,
                    "unit": "area",
                    "score": 95,
                    "q_value": 0.01,
                    "coverage_percent": "",
                    "peptide_count": "",
                    "organism": "Homo sapiens",
                }
            )
            count += 1
            if count >= limit:
                break
    return count


def _write_peptide_csv(*, source: Path, quantity_column: str, target: Path, limit: int) -> int:
    count = 0
    with source.open("r", encoding="utf-8", newline="") as input_file, target.open(
        "w", encoding="utf-8", newline=""
    ) as output_file:
        reader = csv.DictReader(input_file, delimiter="\t")
        writer = csv.DictWriter(
            output_file,
            fieldnames=(
                "sequence",
                "modified_sequence",
                "charge",
                "label",
                "value",
                "unit",
                "score",
                "q_value",
                "retention_time_seconds",
                "mz",
            ),
        )
        writer.writeheader()
        for row in reader:
            value = _positive_float(row.get(quantity_column))
            if value is None:
                continue
            sequence = row.get("Stripped.Sequence") or ""
            if not sequence:
                continue
            writer.writerow(
                {
                    "sequence": sequence[:1024],
                    "modified_sequence": (row.get("Modified.Sequence") or sequence)[:2048],
                    "charge": row.get("Precursor.Charge") or "",
                    "label": "abundance",
                    "value": value,
                    "unit": "area",
                    "score": 95,
                    "q_value": 0.01,
                    "retention_time_seconds": "",
                    "mz": "",
                }
            )
            count += 1
            if count >= limit:
                break
    return count


def _stats_payload(row: dict, *, protein_count: int, peptide_count: int) -> dict:
    precursors = _intish(row.get("Precursors.Identified"))
    proteins = _intish(row.get("Proteins.Identified"))
    return {
        "protein_groups": proteins,
        "protein_count": proteins,
        "peptides": peptide_count,
        "peptide_count": peptide_count,
        "precursors": precursors,
        "precursor_count": precursors,
        "ms1_features": precursors,
        "ms2_spectra": precursors,
        "ms1_signal": _floatish(row.get("MS1.Signal")),
        "ms2_signal": _floatish(row.get("MS2.Signal")),
        "total_quantity": _floatish(row.get("Total.Quantity")),
        "median_ms1_mass_error_ppm": _floatish(row.get("Median.Mass.Acc.MS1")),
        "median_ms2_mass_error_ppm": _floatish(row.get("Median.Mass.Acc.MS2")),
        "fwhm_scans": _floatish(row.get("FWHM.Scans")),
        "fwhm_rt": _floatish(row.get("FWHM.RT")),
        "average_peptide_length": _floatish(row.get("Average.Peptide.Length")),
        "average_peptide_charge": _floatish(row.get("Average.Peptide.Charge")),
        "imported_protein_rows": protein_count,
        "imported_peptide_rows": peptide_count,
        "source": "PXD053992 DIA-NN matrices",
    }


def _positive_float(value: str | None) -> float | None:
    parsed = _floatish(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _floatish(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _intish(value: str | None) -> int:
    parsed = _floatish(value)
    return int(parsed) if parsed is not None else 0
