from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.worklist_generation import WorklistGenerationError, generate_vendor_worklists


class Command(BaseCommand):
    help = "Generate MS and LC vendor CSVs from an upstream Worklist Generator workbook."

    def add_arguments(self, parser):
        parser.add_argument("workbook", type=Path)
        parser.add_argument("output_directory", type=Path)

    def handle(self, *args, **options):
        try:
            result = generate_vendor_worklists(options["workbook"], options["output_directory"])
        except WorklistGenerationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Generated MS worklist: {result.ms_path}"))
        self.stdout.write(self.style.SUCCESS(f"Generated LC worklist: {result.lc_path}"))
        self.stdout.write(f"Generated runs: {len(result.filenames)}")
