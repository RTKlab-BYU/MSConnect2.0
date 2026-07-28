from django.core.management.base import BaseCommand, CommandError

from core.models import (
    PeptideQuant,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingNode,
    ProcessingStatus,
    Project,
    ProteinQuant,
    RawFile,
    RawFileStatus,
    RunStatus,
)


class Command(BaseCommand):
    help = "Verify that an end-to-end smoke fixture was ingested and processed."

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)

    def handle(self, *args, **options):
        project = Project.objects.filter(code=options["code"]).first()
        if not project:
            raise CommandError(f"Project does not exist: {options['code']}")

        raw_files = RawFile.objects.filter(run__sample__experiment__project=project)
        jobs = ProcessingJob.objects.filter(run__sample__experiment__project=project)
        completed_jobs = jobs.filter(status=ProcessingStatus.COMPLETE)
        failures = []
        if not raw_files.exists():
            failures.append("no raw files were imported by watcher")
        if raw_files.exclude(status__in=[RawFileStatus.IMPORTED, RawFileStatus.PROCESSED]).exists():
            failures.append("one or more raw files have an unexpected status")
        if not jobs.exists():
            failures.append("no processing job was queued")
        if not completed_jobs.exists():
            failures.append("no processing job completed")
        if jobs.filter(status=ProcessingStatus.FAILED).exists():
            failures.append("one or more processing jobs failed")
        if completed_jobs.filter(log_path="").exists():
            failures.append("completed job is missing a log path")
        if completed_jobs.filter(stats__runtime_manifest_path__isnull=True).exists():
            failures.append("completed job is missing runtime_manifest_path")
        if not ProcessingJobArtifact.objects.filter(job__in=completed_jobs).exists():
            failures.append("completed job has no recorded artifacts")
        if not ProteinQuant.objects.filter(job__in=completed_jobs).exists():
            failures.append("completed job has no imported protein quant rows")
        if not PeptideQuant.objects.filter(job__in=completed_jobs).exists():
            failures.append("completed job has no imported peptide quant rows")
        if project.experiments.filter(samples__runs__status=RunStatus.PROCESSED).count() == 0:
            failures.append("run status did not reach processed")
        if not ProcessingNode.objects.filter(last_heartbeat_at__isnull=False).exists():
            failures.append("no agent heartbeats were recorded")

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"- {failure}"))
            raise CommandError("End-to-end smoke verification failed.")

        message = (
            f"e2e smoke verified project={project.code} "
            f"raw_files={raw_files.count()} completed_jobs={completed_jobs.count()}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                message
            )
        )
