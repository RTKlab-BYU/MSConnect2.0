from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.models import (
    PeptideQuant,
    ProcessingArtifactType,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingNode,
    ProcessingStatus,
    Project,
    ProteinQuant,
    QcProgram,
    RawFile,
    RawFileStatus,
    RunFileRole,
    RunStatus,
    WorklistEntry,
)


class Command(BaseCommand):
    help = "Verify the tagged operations fixture after watcher and processor agents run."

    processable_roles = {
        RunFileRole.SAMPLE,
        RunFileRole.QC,
        RunFileRole.HYE,
        RunFileRole.PRTC,
        RunFileRole.LIBRARY,
    }

    def add_arguments(self, parser):
        parser.add_argument("--code-prefix", default="OPS-TAGGED")
        parser.add_argument("--require-complete-processing", action="store_true", default=True)
        parser.add_argument("--no-require-complete-processing", action="store_false", dest="require_complete_processing")

    def handle(self, *args, **options):
        code_prefix = str(options["code_prefix"]).strip() or "OPS-TAGGED"
        failures = []
        failures.extend(self._migration_failures())

        projects = list(Project.objects.filter(code__startswith=f"{code_prefix}-").order_by("code"))
        if not projects:
            failures.append(f"no projects found with prefix {code_prefix}")

        for project in projects:
            failures.extend(
                self._project_failures(
                    project=project,
                    require_complete_processing=options["require_complete_processing"],
                )
            )

        if not ProcessingNode.objects.filter(last_heartbeat_at__isnull=False).exists():
            failures.append("no watcher or processor heartbeats were recorded")

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"- {failure}"))
            raise CommandError("Tagged operations verification failed.")

        raw_file_count = RawFile.objects.filter(run__sample__experiment__project__in=projects).count()
        job_count = ProcessingJob.objects.filter(run__sample__experiment__project__in=projects).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"tagged operations verified prefix={code_prefix} projects={len(projects)} "
                f"raw_files={raw_file_count} jobs={job_count}"
            )
        )

    def _project_failures(self, *, project, require_complete_processing):
        failures = []
        entries = list(
            WorklistEntry.objects.select_related("run", "run__sample", "worklist")
            .filter(worklist__experiment__project=project)
            .order_by("position")
        )
        if not entries:
            return [f"{project.code}: no worklist entries found"]

        hye_entries = [entry for entry in entries if entry.file_role == RunFileRole.HYE or entry.qc_program == QcProgram.HYE]
        prtc_entries = [
            entry for entry in entries if entry.file_role == RunFileRole.PRTC or entry.qc_program == QcProgram.PRTC
        ]
        if len(hye_entries) < 2:
            failures.append(f"{project.code}: fewer than two HYE entries found")
        if not prtc_entries:
            failures.append(f"{project.code}: no PRTC entries found")

        raw_files_by_run = {
            raw_file.run_id: raw_file
            for raw_file in RawFile.objects.filter(run__sample__experiment__project=project).select_related("run")
        }
        jobs_by_run = {
            job.run_id: job
            for job in ProcessingJob.objects.filter(run__sample__experiment__project=project).select_related(
                "pipeline",
                "raw_file",
            )
        }

        for entry in entries:
            failures.extend(self._entry_failures(entry=entry, raw_files_by_run=raw_files_by_run))
            if entry.file_role in self.processable_roles:
                failures.extend(
                    self._processing_failures(
                        entry=entry,
                        jobs_by_run=jobs_by_run,
                        require_complete_processing=require_complete_processing,
                    )
                )
            elif entry.run_id in jobs_by_run:
                failures.append(f"{project.code}: non-processable run queued unexpectedly: {entry.expected_filename}")

        return failures

    def _entry_failures(self, *, entry, raw_files_by_run):
        failures = []
        project_code = entry.worklist.experiment.project.code
        run = entry.run
        if run.file_role != entry.file_role:
            failures.append(f"{project_code}: run role mismatch for {entry.expected_filename}")
        if run.qc_program != entry.qc_program:
            failures.append(f"{project_code}: run QC program mismatch for {entry.expected_filename}")
        if run.expected_filename != entry.expected_filename:
            failures.append(f"{project_code}: expected filename mismatch for {entry.expected_filename}")
        if entry.file_role == RunFileRole.HYE and entry.qc_program != QcProgram.HYE:
            failures.append(f"{project_code}: HYE entry is missing qc_program=hye: {entry.expected_filename}")
        if entry.file_role == RunFileRole.PRTC and entry.qc_program != QcProgram.PRTC:
            failures.append(f"{project_code}: PRTC entry is missing qc_program=prtc: {entry.expected_filename}")

        raw_file = raw_files_by_run.get(run.id)
        if not raw_file:
            failures.append(f"{project_code}: watcher did not import {entry.expected_filename}")
            return failures
        if raw_file.filename != entry.expected_filename:
            failures.append(f"{project_code}: raw file attached to wrong filename for {entry.expected_filename}")
        if raw_file.file_role != entry.file_role:
            failures.append(f"{project_code}: raw file role mismatch for {entry.expected_filename}")
        if raw_file.status not in {RawFileStatus.IMPORTED, RawFileStatus.PROCESSED}:
            failures.append(f"{project_code}: raw file status unexpected for {entry.expected_filename}")
        return failures

    def _processing_failures(self, *, entry, jobs_by_run, require_complete_processing):
        failures = []
        project_code = entry.worklist.experiment.project.code
        job = jobs_by_run.get(entry.run_id)
        if not job:
            return [f"{project_code}: no processing job queued for {entry.expected_filename}"]
        if not job.metadata.get("worklist_entry_id"):
            failures.append(f"{project_code}: job missing worklist_entry_id metadata for {entry.expected_filename}")
        if not require_complete_processing:
            return failures

        if job.status != ProcessingStatus.COMPLETE:
            failures.append(f"{project_code}: job did not complete for {entry.expected_filename}")
            return failures
        if not job.log_path:
            failures.append(f"{project_code}: completed job missing log path for {entry.expected_filename}")
        if not job.stats.get("runtime_manifest_path"):
            failures.append(f"{project_code}: completed job missing runtime manifest for {entry.expected_filename}")
        if job.raw_file.status != RawFileStatus.PROCESSED:
            failures.append(f"{project_code}: raw file did not reach processed for {entry.expected_filename}")
        if job.run.status != RunStatus.PROCESSED:
            failures.append(f"{project_code}: run did not reach processed for {entry.expected_filename}")
        if not ProcessingJobArtifact.objects.filter(job=job, artifact_type=ProcessingArtifactType.LOG).exists():
            failures.append(f"{project_code}: completed job missing log artifact for {entry.expected_filename}")
        if not ProteinQuant.objects.filter(job=job).exists():
            failures.append(f"{project_code}: completed job missing protein quants for {entry.expected_filename}")
        if not PeptideQuant.objects.filter(job=job).exists():
            failures.append(f"{project_code}: completed job missing peptide quants for {entry.expected_filename}")
        return failures

    def _migration_failures(self):
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            return []
        return ["database has unapplied migrations; run manage.py migrate before verification"]
