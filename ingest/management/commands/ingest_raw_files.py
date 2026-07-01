import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Run
from ingest.services import DEFAULT_RAW_SUFFIXES, discover_raw_paths, import_raw_path, record_ingestion_failure


class Command(BaseCommand):
    help = "Import LC-MS raw files from the configured watched share."

    def add_arguments(self, parser):
        parser.add_argument("--source", default=settings.INCOMING_RAW_ROOT)
        parser.add_argument("--storage", default=settings.RAW_FILE_STORAGE_ROOT)
        parser.add_argument("--run-id", type=int, default=None)
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--match-run-by-name",
            action="store_true",
            help="When run-id is not provided, link files to a run by parsed filename run token.",
        )
        parser.add_argument(
            "--suffix",
            action="append",
            dest="suffixes",
            help="Raw file suffix to import. Can be provided multiple times.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        storage = Path(options["storage"])
        suffixes = tuple(options["suffixes"] or DEFAULT_RAW_SUFFIXES)
        run = self._get_run(options["run_id"])

        if not source.exists():
            raise CommandError(f"Source path does not exist: {source}")

        while True:
            self._import_once(
                source=source,
                storage=storage,
                run=run,
                recursive=options["recursive"],
                dry_run=options["dry_run"],
                match_run_by_name=options["match_run_by_name"],
                suffixes=suffixes,
            )

            if not options["watch"]:
                break

            time.sleep(options["interval"])

    def _get_run(self, run_id):
        if run_id is None:
            return None

        try:
            return Run.objects.get(pk=run_id)
        except Run.DoesNotExist as exc:
            raise CommandError(f"Run does not exist: {run_id}") from exc

    def _import_once(self, *, source, storage, run, recursive, dry_run, match_run_by_name, suffixes):
        candidates = list(discover_raw_paths(source, suffixes=suffixes, recursive=recursive))
        if not candidates:
            self.stdout.write("No raw files discovered.")
            return

        for path in candidates:
            try:
                result = import_raw_path(
                    path,
                    storage_root=storage,
                    run=run,
                    dry_run=dry_run,
                    match_run_by_name=match_run_by_name,
                )
            except Exception as exc:
                record_ingestion_failure(path, str(exc), metadata={"importer": "ingest_raw_files"})
                self.stderr.write(self.style.ERROR(f"failed {path}: {exc}"))
                continue

            if result.skipped:
                self.stdout.write(f"skipped {path} checksum={result.checksum_sha256}")
            elif dry_run:
                self.stdout.write(f"would import {path} checksum={result.checksum_sha256}")
            else:
                self.stdout.write(self.style.SUCCESS(f"imported {result.raw_file.filename}"))
