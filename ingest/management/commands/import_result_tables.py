from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import ProcessingJob
from ingest.result_import import ResultTableImportError, import_result_tables


class Command(BaseCommand):
    help = "Import peptide/protein quantification and identification result tables for a processing job."

    def add_arguments(self, parser):
        parser.add_argument("--job-id", type=int, required=True, help="ProcessingJob ID to attach imported results.")
        parser.add_argument("--protein-table", type=str, default=None, help="Path to protein results CSV/TSV.")
        parser.add_argument("--peptide-table", type=str, default=None, help="Path to peptide results CSV/TSV.")
        parser.add_argument(
            "--delimiter",
            type=str,
            default=None,
            help="Optional delimiter override, defaults to comma for .csv and tab for .tsv.",
        )

    def handle(self, *args, **options):
        job = self._get_job(options["job_id"])
        protein_table = Path(options["protein_table"]) if options["protein_table"] else None
        peptide_table = Path(options["peptide_table"]) if options["peptide_table"] else None
        delimiter = options["delimiter"]

        try:
            summary = import_result_tables(
                job=job,
                protein_table=protein_table,
                peptide_table=peptide_table,
                delimiter=delimiter,
            )
        except ResultTableImportError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "imported "
                f"protein_quants={summary['protein_quant_rows']} "
                f"protein_identifications={summary['protein_ident_rows']} "
                f"peptide_quants={summary['peptide_quant_rows']} "
                f"peptide_identifications={summary['peptide_ident_rows']}"
            )
        )

    def _get_job(self, job_id):
        try:
            return ProcessingJob.objects.get(pk=job_id)
        except ProcessingJob.DoesNotExist as exc:
            raise CommandError(f"ProcessingJob does not exist: {job_id}") from exc

