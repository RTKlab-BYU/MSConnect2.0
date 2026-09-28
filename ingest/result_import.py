import csv
from pathlib import Path, PureWindowsPath

from django.db import transaction

from core.models import (
    Peptide,
    PeptideIdentification,
    PeptideQuant,
    ProcessingJob,
    Protein,
    ProteinIdentification,
    ProteinQuant,
)


class ResultTableImportError(Exception):
    pass


def import_diann_report(*, job: ProcessingJob, report_path: Path) -> dict:
    """Import one DIA-NN parquet report while preserving FDR provenance.

    DIA-NN reports contain both run-level and experiment/global q-values. The
    run values are used for this job's immediate result status; global values
    remain attached to each identification for later experiment-level matrix
    filtering and are never silently substituted for the run-level value.
    """
    report_path = Path(report_path)
    if not report_path.exists():
        raise ResultTableImportError(f"DIA-NN report file not found: {report_path}")
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise ResultTableImportError("DIA-NN parquet import requires the pyarrow package.") from exc

    parquet_file = parquet.ParquetFile(report_path)
    available = set(parquet_file.schema_arrow.names)
    columns = [
        name
        for name in (
            "File.Name",
            "Protein.Group",
            "PG.MaxLFQ",
            "PG.Quantity",
            "PG.Q.Value",
            "Global.PG.Q.Value",
            "Stripped.Sequence",
            "Modified.Sequence",
            "Precursor.Id",
            "Precursor.Quantity",
            "Q.Value",
            "Global.Q.Value",
            "RT",
            "Precursor.Charge",
            "Precursor.Mz",
        )
        if name in available
    ]
    if not columns:
        raise ResultTableImportError(f"DIA-NN report has no recognized identification columns: {report_path}")

    summary = {
        "diann_report_rows": 0,
        "protein_quant_rows": 0,
        "protein_ident_rows": 0,
        "peptide_quant_rows": 0,
        "peptide_ident_rows": 0,
        "q_value_levels": {"protein_group": "PG.Q.Value", "precursor": "Q.Value"},
        "q_value_context": "run",
    }
    seen_proteins = set()
    raw_stem = _sample_key(getattr(job.raw_file, "filename", ""))

    with transaction.atomic():
        for batch in parquet_file.iter_batches(columns=columns, batch_size=10_000):
            for row in batch.to_pylist():
                if not _diann_row_matches_raw(row, raw_stem):
                    continue
                summary["diann_report_rows"] += 1
                protein_group = str(row.get("Protein.Group") or "").split(";")[0].strip()
                protein_value = _first_float(row, "PG.MaxLFQ", "PG.Quantity")
                protein_q = _first_float(row, "PG.Q.Value")
                global_protein_q = _first_float(row, "Global.PG.Q.Value")
                if protein_group and protein_value is not None and protein_group not in seen_proteins:
                    seen_proteins.add(protein_group)
                    protein, _ = Protein.objects.get_or_create(accession=protein_group[:128], organism="")
                    ProteinQuant.objects.update_or_create(
                        job=job,
                        protein=protein,
                        label="abundance",
                        defaults={"value": protein_value, "unit": "area", "metadata": {"source_file": report_path.name}},
                    )
                    summary["protein_quant_rows"] += 1
                if protein_group and protein_q is not None:
                    protein, _ = Protein.objects.get_or_create(accession=protein_group[:128], organism="")
                    ProteinIdentification.objects.update_or_create(
                        job=job,
                        protein=protein,
                        defaults={
                            "q_value": protein_q,
                            "q_value_level": "protein_group",
                            "q_value_context": "run",
                            "metadata": {
                                "source_file": report_path.name,
                                "global_pg_q_value": global_protein_q,
                                "global_q_value_context": "experiment",
                            },
                        },
                    )
                    summary["protein_ident_rows"] += 1

                sequence = str(row.get("Stripped.Sequence") or "").strip()
                peptide_value = _first_float(row, "Precursor.Quantity")
                peptide_q = _first_float(row, "Q.Value")
                global_peptide_q = _first_float(row, "Global.Q.Value")
                if sequence and peptide_value is not None:
                    peptide, _ = Peptide.objects.get_or_create(
                        sequence=sequence[:1024],
                        modified_sequence=str(row.get("Modified.Sequence") or sequence)[:2048],
                        charge=_first_int(row, "Precursor.Charge"),
                    )
                    PeptideQuant.objects.update_or_create(
                        job=job,
                        peptide=peptide,
                        label="abundance",
                        defaults={"value": peptide_value, "unit": "area", "metadata": {"source_file": report_path.name}},
                    )
                    summary["peptide_quant_rows"] += 1
                if sequence and peptide_q is not None:
                    peptide, _ = Peptide.objects.get_or_create(
                        sequence=sequence[:1024],
                        modified_sequence=str(row.get("Modified.Sequence") or sequence)[:2048],
                        charge=_first_int(row, "Precursor.Charge"),
                    )
                    PeptideIdentification.objects.update_or_create(
                        job=job,
                        peptide=peptide,
                        defaults={
                            "q_value": peptide_q,
                            "q_value_level": "precursor",
                            "q_value_context": "run",
                            "retention_time_seconds": _first_float(row, "RT"),
                            "mz": _first_float(row, "Precursor.Mz"),
                            "metadata": {
                                "source_file": report_path.name,
                                "precursor_id": row.get("Precursor.Id"),
                                "global_q_value": global_peptide_q,
                                "global_q_value_context": "experiment",
                            },
                        },
                    )
                    summary["peptide_ident_rows"] += 1
    return summary


def import_result_tables(
    *,
    job: ProcessingJob,
    protein_table: Path | None = None,
    peptide_table: Path | None = None,
    delimiter: str | None = None,
) -> dict:
    if not protein_table and not peptide_table:
        raise ResultTableImportError("At least one table path is required.")

    summary = {
        "protein_quant_rows": 0,
        "protein_ident_rows": 0,
        "peptide_quant_rows": 0,
        "peptide_ident_rows": 0,
    }

    with transaction.atomic():
        if protein_table:
            protein_counts = _import_protein_table(job=job, table_path=Path(protein_table), delimiter=delimiter)
            summary["protein_quant_rows"] = protein_counts["quant_rows"]
            summary["protein_ident_rows"] = protein_counts["ident_rows"]

        if peptide_table:
            peptide_counts = _import_peptide_table(job=job, table_path=Path(peptide_table), delimiter=delimiter)
            summary["peptide_quant_rows"] = peptide_counts["quant_rows"]
            summary["peptide_ident_rows"] = peptide_counts["ident_rows"]

    return summary


def _import_protein_table(*, job: ProcessingJob, table_path: Path, delimiter: str | None) -> dict:
    quant_rows = 0
    ident_rows = 0

    for row in _iter_rows(table_path, delimiter=delimiter):
        accession = _required_value(row, "accession", "protein_accession", "protein")
        organism = _optional_value(row, "organism") or ""
        protein, _ = Protein.objects.get_or_create(accession=accession, organism=organism)

        label = _optional_value(row, "label") or "abundance"
        value = _required_float(row, "value", "abundance", "intensity", "quantity")
        unit = _optional_value(row, "unit") or ""
        ProteinQuant.objects.update_or_create(
            job=job,
            protein=protein,
            label=label,
            defaults={
                "value": value,
                "unit": unit,
                "metadata": {"source_file": table_path.name},
            },
        )
        quant_rows += 1

        ident_defaults = {}
        score = _optional_float(row, "score")
        q_value = _optional_float(row, "q_value", "qvalue")
        coverage = _optional_float(row, "coverage_percent", "coverage")
        peptide_count = _optional_int(row, "peptide_count")
        if score is not None:
            ident_defaults["score"] = score
        if q_value is not None:
            ident_defaults["q_value"] = q_value
        if coverage is not None:
            ident_defaults["coverage_percent"] = coverage
        if peptide_count is not None:
            ident_defaults["peptide_count"] = peptide_count

        if ident_defaults:
            ident_defaults["metadata"] = {"source_file": table_path.name}
            ProteinIdentification.objects.update_or_create(
                job=job,
                protein=protein,
                defaults=ident_defaults,
            )
            ident_rows += 1

    return {"quant_rows": quant_rows, "ident_rows": ident_rows}


def _import_peptide_table(*, job: ProcessingJob, table_path: Path, delimiter: str | None) -> dict:
    quant_rows = 0
    ident_rows = 0

    for row in _iter_rows(table_path, delimiter=delimiter):
        sequence = _required_value(row, "sequence", "peptide")
        modified_sequence = _optional_value(row, "modified_sequence", "modified_peptide") or ""
        charge = _optional_int(row, "charge")

        peptide, _ = Peptide.objects.get_or_create(
            sequence=sequence,
            modified_sequence=modified_sequence,
            charge=charge,
        )

        label = _optional_value(row, "label") or "abundance"
        value = _required_float(row, "value", "abundance", "intensity", "quantity")
        unit = _optional_value(row, "unit") or ""
        PeptideQuant.objects.update_or_create(
            job=job,
            peptide=peptide,
            label=label,
            defaults={
                "value": value,
                "unit": unit,
                "metadata": {"source_file": table_path.name},
            },
        )
        quant_rows += 1

        ident_defaults = {}
        score = _optional_float(row, "score")
        q_value = _optional_float(row, "q_value", "qvalue")
        rt = _optional_float(row, "retention_time_seconds", "rt_seconds", "rt")
        mz = _optional_float(row, "mz")

        if score is not None:
            ident_defaults["score"] = score
        if q_value is not None:
            ident_defaults["q_value"] = q_value
        if rt is not None:
            ident_defaults["retention_time_seconds"] = rt
        if mz is not None:
            ident_defaults["mz"] = mz

        if ident_defaults:
            ident_defaults["metadata"] = {"source_file": table_path.name}
            PeptideIdentification.objects.update_or_create(
                job=job,
                peptide=peptide,
                defaults=ident_defaults,
            )
            ident_rows += 1

    return {"quant_rows": quant_rows, "ident_rows": ident_rows}


def _iter_rows(table_path: Path, *, delimiter: str | None):
    if not table_path.exists():
        raise ResultTableImportError(f"Table file not found: {table_path}")

    dialect_delimiter = delimiter or ("\t" if table_path.suffix.lower() == ".tsv" else ",")
    with table_path.open("r", encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj, delimiter=dialect_delimiter)
        if not reader.fieldnames:
            raise ResultTableImportError(f"Missing header row in {table_path}")
        normalized_headers = {header.strip().lower() for header in reader.fieldnames if header}
        if not normalized_headers:
            raise ResultTableImportError(f"Empty header row in {table_path}")
        for row in reader:
            normalized_row = {(key or "").strip().lower(): (value or "").strip() for key, value in row.items()}
            if any(value for value in normalized_row.values()):
                yield normalized_row


def _sample_key(value: str) -> str:
    name = PureWindowsPath(str(value)).name or Path(str(value)).name
    lowered = name.lower()
    for suffix in (".mzml", ".mzxml", ".raw", ".wiff", ".d"):
        if lowered.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.lower()


def _diann_row_matches_raw(row: dict, raw_stem: str) -> bool:
    file_name = row.get("File.Name")
    return not file_name or _sample_key(str(file_name)) == raw_stem


def _first_float(row: dict, *aliases: str) -> float | None:
    for alias in aliases:
        value = row.get(alias)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_int(row: dict, *aliases: str) -> int | None:
    value = _first_float(row, *aliases)
    return int(value) if value is not None else None


def _required_value(row, *aliases):
    value = _optional_value(row, *aliases)
    if value is None:
        raise ResultTableImportError(f"Missing required column value for one of: {', '.join(aliases)}")
    return value


def _optional_value(row, *aliases):
    for alias in aliases:
        value = row.get(alias.lower())
        if value not in (None, ""):
            return value
    return None


def _required_float(row, *aliases):
    value = _required_value(row, *aliases)
    try:
        return float(value)
    except ValueError as exc:
        raise ResultTableImportError(f"Invalid float for {aliases[0]}: {value}") from exc


def _optional_float(row, *aliases):
    value = _optional_value(row, *aliases)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ResultTableImportError(f"Invalid float for {aliases[0]}: {value}") from exc


def _optional_int(row, *aliases):
    value = _optional_value(row, *aliases)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ResultTableImportError(f"Invalid integer for {aliases[0]}: {value}") from exc
