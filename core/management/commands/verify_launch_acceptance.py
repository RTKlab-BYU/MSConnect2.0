import json
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import (
    Experiment,
    FileMatchException,
    MatchExceptionStatus,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingNode,
    ProcessingStatus,
    Project,
    QcProgram,
    RawFile,
    RawFileArchive,
    RawFileArchiveCopyStatus,
    RawFileArchiveStatus,
    RawFileDerivative,
    RawFileStatus,
    Run,
    RunStatus,
    WorklistEntry,
)


class Command(BaseCommand):
    help = "Verify the real-data acceptance gates for one MSConnect project experiment."

    def add_arguments(self, parser):
        parser.add_argument("--project-code", required=True)
        parser.add_argument("--experiment-id", type=int, required=True)
        parser.add_argument("--min-runs", type=int, default=20)
        parser.add_argument("--stale-seconds", type=int, default=300)
        parser.add_argument("--skip-archive", action="store_true")
        parser.add_argument("--skip-qc", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        project = Project.objects.filter(code=options["project_code"]).first()
        if not project:
            raise CommandError(f"Project does not exist: {options['project_code']}")
        experiment = Experiment.objects.filter(id=options["experiment_id"], project=project).first()
        if not experiment:
            raise CommandError(f"Experiment {options['experiment_id']} does not belong to project {project.code}")

        min_runs = max(1, int(options["min_runs"]))
        runs = list(Run.objects.filter(sample__experiment=experiment).order_by("worklist_position", "id"))
        run_ids = [run.id for run in runs]
        raw_files = list(RawFile.objects.filter(run_id__in=run_ids))
        jobs = list(ProcessingJob.objects.filter(run_id__in=run_ids).order_by("-created_at", "-id"))
        latest_jobs = {}
        for job in jobs:
            latest_jobs.setdefault(job.run_id, job)
        active_entries = WorklistEntry.objects.filter(worklist__experiment=experiment, is_active=True)
        frozen_entries = active_entries.filter(worklist__frozen_at__isnull=False).count()
        matched_run_ids = {raw_file.run_id for raw_file in raw_files if raw_file.run_id is not None}
        processed_run_ids = {run.id for run in runs if run.status == RunStatus.PROCESSED}
        invalid_raw_files = sum(1 for raw_file in raw_files if raw_file.status not in {RawFileStatus.IMPORTED, RawFileStatus.PROCESSED})
        unmatched_count = FileMatchException.objects.filter(
            project=project,
            status=MatchExceptionStatus.OPEN,
        ).count()
        completed_jobs = [job for job in latest_jobs.values() if job.status == ProcessingStatus.COMPLETE]
        failed_jobs = [job for job in latest_jobs.values() if job.status == ProcessingStatus.FAILED]
        active_jobs = [
            job
            for job in latest_jobs.values()
            if job.status in {
                ProcessingStatus.QUEUED,
                ProcessingStatus.ASSIGNED,
                ProcessingStatus.RUNNING,
                ProcessingStatus.RETRYING,
            }
        ]
        now = timezone.now()
        fresh_since = now - timedelta(seconds=max(1, int(options["stale_seconds"])))
        fresh_watchers = ProcessingNode.objects.filter(
            node_type="watcher",
            last_heartbeat_at__gte=fresh_since,
        ).count()
        fresh_processors = ProcessingNode.objects.filter(
            last_heartbeat_at__gte=fresh_since,
        ).exclude(node_type="watcher").count()
        expected_run_count = max(len(runs), active_entries.count())
        completed_job_ids = [job.id for job in completed_jobs]
        artifact_job_ids = set(
            ProcessingJobArtifact.objects.filter(job_id__in=completed_job_ids).values_list("job_id", flat=True)
        )
        missing_artifacts = len(set(completed_job_ids) - artifact_job_ids)
        missing_manifests = sum(1 for job in completed_jobs if not (job.stats or {}).get("runtime_manifest_path"))
        qc_runs = sum(1 for run in runs if run.qc_program in {QcProgram.HYE, QcProgram.PRTC})
        indexed_files = RawFileDerivative.objects.filter(
            raw_file_id__in=[raw_file.id for raw_file in raw_files],
            derivative_type__in=("spectrum_index", "preview_json"),
            status="ready",
        ).count()
        verified_archives = RawFileArchive.objects.filter(
            raw_file_id__in=[raw_file.id for raw_file in raw_files],
            status=RawFileArchiveStatus.VERIFIED,
            copies__status=RawFileArchiveCopyStatus.VERIFIED,
        ).distinct()
        restored_archives = verified_archives.filter(restored_at__isnull=False).count()

        checks = [
            self._check("minimum_runs", len(runs) >= min_runs, len(runs), f"at least {min_runs} planned runs"),
            self._check(
                "frozen_worklist",
                active_entries.count() >= min_runs and frozen_entries >= min_runs,
                {"active_entries": active_entries.count(), "frozen_entries": frozen_entries},
                "active worklist entries are frozen before acquisition",
            ),
            self._check(
                "raw_file_matching",
                len(matched_run_ids) >= expected_run_count and unmatched_count == 0 and invalid_raw_files == 0,
                {"matched_runs": len(matched_run_ids), "unmatched_exceptions": unmatched_count, "invalid_raw_files": invalid_raw_files},
                "every acceptance run has a matched raw file and no open match exception",
            ),
            self._check(
                "processing_complete",
                len(completed_jobs) >= expected_run_count
                and len(processed_run_ids) >= expected_run_count
                and not failed_jobs
                and not active_jobs
                and missing_artifacts == 0
                and missing_manifests == 0,
                {
                    "completed": len(completed_jobs),
                    "processed_runs": len(processed_run_ids),
                    "failed": len(failed_jobs),
                    "active": len(active_jobs),
                    "missing_artifacts": missing_artifacts,
                    "missing_runtime_manifests": missing_manifests,
                },
                "every acceptance run has a completed latest job, artifacts, and runtime manifest",
            ),
            self._check(
                "agent_heartbeats",
                fresh_watchers > 0 and fresh_processors > 0,
                {"watchers": fresh_watchers, "processors": fresh_processors, "stale_seconds": options["stale_seconds"]},
                "watcher and processor agents have fresh heartbeats",
            ),
        ]
        if not options["skip_qc"]:
            checks.extend(
                [
                    self._check("qc_runs", qc_runs > 0, qc_runs, "at least one HYE or PRTC run is present"),
                    self._check(
                        "indexed_visualization",
                        indexed_files > 0,
                        indexed_files,
                        "at least one ready spectrum/chromatogram index is available",
                    ),
                ]
            )
        if not options["skip_archive"]:
            checks.extend(
                [
                    self._check("verified_archive", verified_archives.exists(), verified_archives.count(), "at least one verified archive copy exists"),
                    self._check("restore_test", restored_archives > 0, restored_archives, "at least one verified archive has a recorded restore test"),
                ]
            )

        report = {
            "project": project.code,
            "project_id": project.id,
            "experiment": experiment.name,
            "experiment_id": experiment.id,
            "release_version": settings.MSCONNECT_RELEASE_VERSION,
            "checks": checks,
            "passed": all(check["passed"] for check in checks),
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str))
        else:
            self.stdout.write(f"Launch acceptance: {project.code} / {experiment.name}")
            for check in checks:
                style = self.style.SUCCESS if check["passed"] else self.style.ERROR
                state = "PASS" if check["passed"] else "FAIL"
                self.stdout.write(style(f"{state:4} {check['name']}: {check['detail']} (observed={check['observed']})"))

        if not report["passed"]:
            raise CommandError("Launch acceptance failed; resolve the failed checks before sign-off.")

    @staticmethod
    def _check(name, passed, observed, detail):
        return {"name": name, "passed": bool(passed), "observed": observed, "detail": detail}
