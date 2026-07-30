import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import ProcessingJob, ProcessingStatus


class Command(BaseCommand):
    help = "Delete temporary processor workspace directories for completed jobs when safe."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--older-than-hours", type=float, default=0.0)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        results_root = Path(settings.RESULTS_ROOT).resolve()
        jobs_root = results_root / "jobs"
        removed = 0
        candidates = ProcessingJob.objects.filter(status=ProcessingStatus.COMPLETE).order_by("id")
        for job in candidates[: max(1, int(options["limit"]))]:
            workspace = jobs_root / str(job.id) / "workspace"
            staged = jobs_root / str(job.id) / "staged"
            for path in (workspace, staged):
                if not path.exists():
                    continue
                if not path.resolve().is_relative_to(results_root):
                    continue
                if options["dry_run"]:
                    self.stdout.write(f"would remove {path}")
                else:
                    shutil.rmtree(path)
                    self.stdout.write(f"removed {path}")
                removed += 1
        self.stdout.write(self.style.SUCCESS(f"processor workspace cleanup candidates={removed}"))
