import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import ProcessingJob, ProcessingNode, ProcessingNodeStatus, ProcessingStatus


class Command(BaseCommand):
    help = "Remove transient processing jobs and reset visible node state before a fresh smoke pass."

    def add_arguments(self, parser):
        parser.add_argument(
            "--project-code",
            help="Optional project code to scope the job cleanup to one project.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        job_statuses = (
            ProcessingStatus.QUEUED,
            ProcessingStatus.ASSIGNED,
            ProcessingStatus.RUNNING,
            ProcessingStatus.RETRYING,
        )
        jobs = ProcessingJob.objects.filter(status__in=job_statuses).order_by("id")
        project_code = str(options.get("project_code") or "").strip()
        if project_code:
            jobs = jobs.filter(run__sample__experiment__project__code=project_code)

        job_ids = list(jobs.values_list("id", flat=True))
        node_ids = list(ProcessingNode.objects.values_list("id", flat=True))

        if options["dry_run"]:
            self.stdout.write(
                f"would remove transient jobs={len(job_ids)} nodes_reset={len(node_ids)}"
                + (f" project={project_code}" if project_code else "")
            )
            return

        results_root = Path(settings.RESULTS_ROOT).resolve()
        jobs_root = results_root / "jobs"
        removed_job_dirs = 0
        removed_jobs = 0
        reset_nodes = 0

        with transaction.atomic():
            for job in jobs.select_related("raw_file"):
                workspace = (jobs_root / str(job.id)).resolve()
                if workspace.exists() and workspace.is_relative_to(results_root):
                    shutil.rmtree(workspace)
                    removed_job_dirs += 1
                job.delete()
                removed_jobs += 1

            for node in ProcessingNode.objects.all():
                node.status = ProcessingNodeStatus.OFFLINE
                node.last_heartbeat_at = None
                metadata = dict(node.metadata or {})
                metadata.pop("control", None)
                metadata["cleanup"] = {
                    "performed_at": timezone.now().isoformat(),
                    "reason": "cleanup_processing_state",
                }
                node.metadata = metadata
                node.save(update_fields=["status", "last_heartbeat_at", "metadata", "updated_at"])
                reset_nodes += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"processing state cleaned jobs={removed_jobs} job_dirs={removed_job_dirs} nodes={reset_nodes}"
                + (f" project={project_code}" if project_code else "")
            )
        )
