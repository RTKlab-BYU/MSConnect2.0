import tempfile
import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import RawFileArchive, RawFileArchiveCopyStatus, RawFileArchiveStatus
from core.storage_ops import sha256_file
from ingest.services import hash_path


class Command(BaseCommand):
    help = "Verify archive and backup copy checksums, optionally testing restore fidelity."

    def add_arguments(self, parser):
        parser.add_argument("--archive-id", type=int)
        parser.add_argument("--raw-file-id", type=int)
        parser.add_argument("--restore-test", action="store_true")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        queryset = RawFileArchive.objects.select_related("raw_file").prefetch_related("copies").order_by("id")
        if options["archive_id"]:
            queryset = queryset.filter(id=options["archive_id"])
        if options["raw_file_id"]:
            queryset = queryset.filter(raw_file_id=options["raw_file_id"])

        checked = 0
        failures = []
        for archive in queryset[: max(1, int(options["limit"]))]:
            try:
                self._verify_one(archive=archive, restore_test=options["restore_test"])
                checked += 1
            except Exception as exc:
                failures.append(f"archive {archive.id} {archive.raw_file.filename}: {exc}")
                archive.status = RawFileArchiveStatus.FAILED
                archive.error_message = str(exc)
                archive.save(update_fields=["status", "error_message", "updated_at"])

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"- {failure}"))
            raise CommandError("Archive verification failed.")
        self.stdout.write(self.style.SUCCESS(f"verified archives={checked}"))

    def _verify_one(self, *, archive, restore_test):
        expected = archive.checksum_sha256
        if not expected:
            raise CommandError("archive is missing checksum")
        for copy in archive.copies.all():
            path = Path(copy.path)
            if not path.exists():
                raise CommandError(f"copy path does not exist: {path}")
            checksum, size_bytes = sha256_file(path)
            if checksum != expected:
                raise CommandError(f"copy checksum mismatch: {path}")
            copy.status = RawFileArchiveCopyStatus.VERIFIED
            copy.size_bytes = size_bytes
            copy.checksum_sha256 = checksum
            copy.verified_at = timezone.now()
            copy.error_message = ""
            copy.save(
                update_fields=[
                    "status",
                    "size_bytes",
                    "checksum_sha256",
                    "verified_at",
                    "error_message",
                    "updated_at",
                ]
            )
        if restore_test:
            self._restore_test(archive)
        archive.status = RawFileArchiveStatus.VERIFIED
        archive.error_message = ""
        archive.save(update_fields=["status", "error_message", "updated_at"])

    def _restore_test(self, archive):
        archive_path = Path(archive.archive_path)
        if not archive_path.exists():
            archive_copy = archive.copies.filter(copy_role="archive", status=RawFileArchiveCopyStatus.VERIFIED).first()
            archive_path = Path(archive_copy.path) if archive_copy else archive_path
        with tempfile.TemporaryDirectory() as temp_dir:
            restore_root = Path(temp_dir)
            with zipfile.ZipFile(archive_path) as zip_file:
                zip_file.extractall(restore_root)
            restored_items = list(restore_root.iterdir())
            if len(restored_items) != 1:
                raise CommandError("restore test expected exactly one top-level restored path")
            restored_checksum, restored_size = hash_path(restored_items[0])
            if restored_checksum != archive.raw_file.checksum_sha256:
                raise CommandError("restore test checksum does not match original raw checksum")
            if restored_size != archive.raw_file.size_bytes:
                raise CommandError("restore test size does not match original raw size")
        archive.restored_at = timezone.now()
        archive.save(update_fields=["restored_at", "updated_at"])
