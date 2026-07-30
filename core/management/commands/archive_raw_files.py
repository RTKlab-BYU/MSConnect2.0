import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    RawFile,
    RawFileArchive,
    RawFileArchiveCopy,
    RawFileArchiveCopyStatus,
    RawFileArchiveStatus,
    RawFileStatus,
)
from core.storage_ops import (
    choose_storage_root,
    configured_roots,
    copy_and_verify,
    safe_archive_name,
    sha256_file,
    zip_raw_path,
)


class Command(BaseCommand):
    help = "Create verified zip archives and backup copies for imported raw files."

    def add_arguments(self, parser):
        parser.add_argument("--raw-file-id", type=int)
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=300)
        parser.add_argument("--include-unmatched", action="store_true", default=True)
        parser.add_argument("--no-include-unmatched", action="store_false", dest="include_unmatched")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        archive_roots = configured_roots(settings.MSCONNECT_ARCHIVE_ROOTS)
        backup_roots = configured_roots(settings.MSCONNECT_BACKUP_ROOTS)
        if not archive_roots:
            raise CommandError("MSCONNECT_ARCHIVE_ROOTS must contain at least one archive root.")

        while True:
            count = self._run_once(
                archive_roots=archive_roots,
                backup_roots=backup_roots,
                raw_file_id=options["raw_file_id"],
                limit=max(1, int(options["limit"])),
                include_unmatched=options["include_unmatched"],
                force=options["force"],
            )
            self.stdout.write(self.style.SUCCESS(f"archived raw files={count}"))
            if not options["loop"]:
                break
            time.sleep(max(5, int(options["interval"])))

    def _run_once(
        self,
        *,
        archive_roots,
        backup_roots,
        raw_file_id,
        limit,
        include_unmatched,
        force,
    ):
        queryset = RawFile.objects.filter(status__in=[RawFileStatus.IMPORTED, RawFileStatus.PROCESSED]).order_by("id")
        if raw_file_id:
            queryset = queryset.filter(id=raw_file_id)
        if not include_unmatched:
            queryset = queryset.filter(run__isnull=False)

        archived_count = 0
        for raw_file in queryset[:limit]:
            if not force and self._has_required_verified_copies(raw_file=raw_file, backup_roots=backup_roots):
                continue
            self._archive_one(raw_file=raw_file, archive_roots=archive_roots, backup_roots=backup_roots, force=force)
            archived_count += 1
        return archived_count

    def _archive_one(self, *, raw_file, archive_roots, backup_roots, force):
        source_path = Path(raw_file.storage_path).resolve()
        if not source_path.exists():
            raise CommandError(f"Raw file storage path does not exist: {source_path}")

        estimated_bytes = max(raw_file.size_bytes, source_path.stat().st_size if source_path.is_file() else raw_file.size_bytes)
        archive_root = choose_storage_root(
            archive_roots,
            required_bytes=estimated_bytes,
            block_percent=settings.MSCONNECT_STORAGE_BLOCK_PERCENT,
        )
        archive_name = safe_archive_name(raw_file.filename, raw_file.checksum_sha256)
        archive_path = archive_root / "raw-archives" / raw_file.checksum_sha256[:2] / archive_name

        with transaction.atomic():
            archive, _created = RawFileArchive.objects.update_or_create(
                raw_file=raw_file,
                archive_path=str(archive_path),
                defaults={
                    "status": RawFileArchiveStatus.ARCHIVING,
                    "original_storage_path": raw_file.storage_path,
                    "compression": "zip",
                    "error_message": "",
                    "metadata": {"archive_root": str(archive_root), "source_size_bytes": raw_file.size_bytes},
                },
            )

        try:
            if force or not archive_path.exists():
                zip_raw_path(source_path, archive_path)
            checksum, size_bytes = sha256_file(archive_path)
            archive.status = RawFileArchiveStatus.VERIFIED
            archive.size_bytes = size_bytes
            archive.checksum_sha256 = checksum
            archive.archived_at = timezone.now()
            archive.error_message = ""
            archive.save(
                update_fields=[
                    "status",
                    "size_bytes",
                    "checksum_sha256",
                    "archived_at",
                    "error_message",
                    "updated_at",
                ]
            )
            self._record_copy(
                archive=archive,
                copy_role="archive",
                root=archive_root,
                path=archive_path,
                checksum=checksum,
                size_bytes=size_bytes,
            )
            for backup_root in backup_roots:
                backup_path = backup_root / "raw-archive-backups" / raw_file.checksum_sha256[:2] / archive_name
                if force or not backup_path.exists():
                    copy_and_verify(archive_path, backup_path, checksum)
                backup_checksum, backup_size = sha256_file(backup_path)
                if backup_checksum != checksum:
                    raise RuntimeError(f"Backup checksum mismatch: {backup_path}")
                self._record_copy(
                    archive=archive,
                    copy_role="backup",
                    root=backup_root,
                    path=backup_path,
                    checksum=backup_checksum,
                    size_bytes=backup_size,
                )
        except Exception as exc:
            archive.status = RawFileArchiveStatus.FAILED
            archive.error_message = str(exc)
            archive.save(update_fields=["status", "error_message", "updated_at"])
            raise

    def _record_copy(self, *, archive, copy_role, root, path, checksum, size_bytes):
        RawFileArchiveCopy.objects.update_or_create(
            archive=archive,
            path=str(Path(path).resolve()),
            defaults={
                "copy_role": copy_role,
                "storage_root": str(Path(root).resolve()),
                "status": RawFileArchiveCopyStatus.VERIFIED,
                "size_bytes": size_bytes,
                "checksum_sha256": checksum,
                "verified_at": timezone.now(),
                "error_message": "",
            },
        )

    def _has_required_verified_copies(self, *, raw_file, backup_roots):
        archive = (
            raw_file.archives.filter(status=RawFileArchiveStatus.VERIFIED)
            .prefetch_related("copies")
            .order_by("-archived_at")
            .first()
        )
        if not archive:
            return False
        archive_copies = archive.copies.filter(copy_role="archive", status=RawFileArchiveCopyStatus.VERIFIED).count()
        backup_copies = archive.copies.filter(copy_role="backup", status=RawFileArchiveCopyStatus.VERIFIED).count()
        return archive_copies >= 1 and backup_copies >= len(backup_roots)
