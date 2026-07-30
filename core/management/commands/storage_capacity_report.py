from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from core.models import RawFile, RawFileArchiveCopy, RawFileArchiveCopyStatus
from core.storage_ops import capacity_report, configured_roots


class Command(BaseCommand):
    help = "Report lab-drive storage capacity and archive redundancy coverage."

    def add_arguments(self, parser):
        parser.add_argument("--projected-files", type=int, default=0)
        parser.add_argument("--average-raw-gb", type=float, default=0.0)

    def handle(self, *args, **options):
        roots = [
            ("incoming", Path(settings.INCOMING_RAW_ROOT)),
            ("raw", Path(settings.RAW_FILE_STORAGE_ROOT)),
            ("results", Path(settings.RESULTS_ROOT)),
            *[(f"archive:{index}", root) for index, root in enumerate(configured_roots(settings.MSCONNECT_ARCHIVE_ROOTS), 1)],
            *[(f"backup:{index}", root) for index, root in enumerate(configured_roots(settings.MSCONNECT_BACKUP_ROOTS), 1)],
        ]
        self.stdout.write("Storage roots")
        for label, root in roots:
            report = capacity_report(root)
            status = self._status(report.used_percent, report.exists)
            self.stdout.write(
                f"{label:12} {status:8} used={self._fmt(report.used_bytes)} "
                f"free={self._fmt(report.free_bytes)} total={self._fmt(report.total_bytes)} "
                f"used_percent={report.used_percent:.2f}% path={report.root}"
            )

        raw_summary = RawFile.objects.aggregate(count=Count("id"), size=Sum("size_bytes"))
        verified_copy_count = RawFileArchiveCopy.objects.filter(status=RawFileArchiveCopyStatus.VERIFIED).count()
        raw_with_archive = (
            RawFile.objects.filter(archives__copies__status=RawFileArchiveCopyStatus.VERIFIED)
            .distinct()
            .count()
        )
        self.stdout.write("")
        self.stdout.write(
            f"Raw files: count={raw_summary['count'] or 0} size={self._fmt(raw_summary['size'] or 0)} "
            f"with_verified_archive_or_backup={raw_with_archive} verified_copies={verified_copy_count}"
        )

        projected_bytes = int(options["projected_files"] * options["average_raw_gb"] * 1024**3)
        if projected_bytes:
            self.stdout.write(
                f"Projected new raw footprint: files={options['projected_files']} "
                f"average={options['average_raw_gb']}GB total={self._fmt(projected_bytes)}"
            )

    def _status(self, used_percent, exists):
        if not exists:
            return "missing"
        if used_percent >= settings.MSCONNECT_STORAGE_BLOCK_PERCENT:
            return "block"
        if used_percent >= settings.MSCONNECT_STORAGE_WARN_PERCENT:
            return "warn"
        return "ok"

    def _fmt(self, value):
        value = float(value or 0)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if value < 1024 or unit == "PB":
                return f"{value:.1f}{unit}"
            value /= 1024
        return f"{value:.1f}PB"
