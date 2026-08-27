from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Facility,
    Lab,
    Peptide,
    PeptideQuant,
    ProcessingArtifactType,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingNode,
    ProcessingNodeStatus,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    Protein,
    ProteinQuant,
    QcProgram,
    RawFile,
    RawFileArchive,
    RawFileArchiveCopy,
    RawFileArchiveCopyStatus,
    RawFileArchiveStatus,
    RawFileStatus,
    RunFileRole,
    RunStatus,
    University,
    WorklistEntry,
)


class OperationalSmokeCommandTests(TestCase):
    def test_create_e2e_smoke_fixture_creates_project_and_incoming_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command("create_e2e_smoke_fixture", code="E2E-UNIT")

            project = Project.objects.get(code="E2E-UNIT")
            run = project.experiments.get().samples.get().runs.get()

            self.assertEqual(run.expected_filename, "E2E-UNIT_run01.mzML")
            self.assertTrue((root / "incoming" / "E2E-UNIT_run01.mzML").exists())

    def test_create_e2e_smoke_fixture_can_stage_real_source_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source" / "JM1025_DigestMix_other_RK9_rep5_ch1_DIA100win_dry_run77.raw"
            source.parent.mkdir(parents=True)
            source.write_text("real raw placeholder bytes", encoding="utf-8")

            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command(
                    "create_e2e_smoke_fixture",
                    code="E2E-REAL",
                    source_file=str(source),
                )

            project = Project.objects.get(code="E2E-REAL")
            run = project.experiments.get().samples.get().runs.get()
            staged = root / "incoming" / source.name

            self.assertEqual(run.expected_filename, source.name)
            self.assertTrue(staged.exists())
            self.assertEqual(staged.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))

    def test_verify_e2e_smoke_fixture_fails_before_processing(self):
        with TemporaryDirectory() as temp_dir:
            with override_settings(INCOMING_RAW_ROOT=str(Path(temp_dir) / "incoming")):
                call_command("create_e2e_smoke_fixture", code="E2E-INCOMPLETE")

            with self.assertRaises(CommandError):
                call_command("verify_e2e_smoke_fixture", code="E2E-INCOMPLETE")

    def test_verify_e2e_smoke_fixture_passes_after_completed_job(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command("create_e2e_smoke_fixture", code="E2E-COMPLETE")

            project = Project.objects.get(code="E2E-COMPLETE")
            run = project.experiments.get().samples.get().runs.get()
            pipeline = project.experiments.get().worklists.get().metadata["processing_pipeline_id"]
            raw_file = RawFile.objects.create(
                run=run,
                source_path=str(root / "incoming" / run.expected_filename),
                storage_path=str(root / "raw" / run.expected_filename),
                filename=run.expected_filename,
                checksum_sha256="e" * 64,
                size_bytes=100,
                imported_at=timezone.now(),
                status=RawFileStatus.PROCESSED,
            )
            job = ProcessingJob.objects.create(
                run=run,
                raw_file=raw_file,
                pipeline_id=pipeline,
                status=ProcessingStatus.COMPLETE,
                log_path=str(root / "results" / "process.log"),
                stats={"runtime_manifest_path": str(root / "results" / "runtime-manifest.json")},
            )
            run.status = RunStatus.PROCESSED
            run.save(update_fields=["status", "updated_at"])
            ProcessingJobArtifact.objects.create(
                job=job,
                artifact_type=ProcessingArtifactType.LOG,
                path=job.log_path,
                format="log",
            )
            protein = Protein.objects.create(accession="P12345")
            peptide = Peptide.objects.create(sequence="PEPTIDE")
            ProteinQuant.objects.create(job=job, protein=protein, value=10.0)
            PeptideQuant.objects.create(job=job, peptide=peptide, value=5.0)
            ProcessingNode.objects.create(
                name="processor-test",
                node_type="processor",
                status=ProcessingNodeStatus.IDLE,
                last_heartbeat_at=timezone.now(),
            )

            call_command("verify_e2e_smoke_fixture", code="E2E-COMPLETE")

    def test_create_tagged_operations_fixture_creates_hye_prtc_and_incoming_files(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command(
                    "create_tagged_operations_fixture",
                    code_prefix="OPS-UNIT",
                    project_count=2,
                    sample_count=1,
                )

            projects = Project.objects.filter(code__startswith="OPS-UNIT-").order_by("code")
            self.assertEqual(projects.count(), 2)
            for project in projects:
                entries = WorklistEntry.objects.filter(worklist__experiment__project=project)
                self.assertEqual(entries.filter(file_role=RunFileRole.HYE, qc_program=QcProgram.HYE).count(), 2)
                self.assertEqual(entries.filter(file_role=RunFileRole.PRTC, qc_program=QcProgram.PRTC).count(), 1)
                for entry in entries:
                    self.assertEqual(entry.run.file_role, entry.file_role)
                    self.assertEqual(entry.run.qc_program, entry.qc_program)
                    self.assertTrue((root / "incoming" / entry.expected_filename).exists())

    def test_verify_tagged_operations_fixture_passes_after_import_and_processing(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command(
                    "create_tagged_operations_fixture",
                    code_prefix="OPS-COMPLETE",
                    project_count=1,
                    sample_count=1,
                )

            project = Project.objects.get(code="OPS-COMPLETE-01")
            pipeline_id = project.experiments.get().worklists.get().metadata["processing_pipeline_id"]
            protein = Protein.objects.create(accession="P12345", organism="Homo sapiens")
            peptide = Peptide.objects.create(sequence="PEPTIDE")

            for index, entry in enumerate(
                WorklistEntry.objects.select_related("run").filter(worklist__experiment__project=project),
                start=1,
            ):
                is_processable = entry.file_role in {
                    RunFileRole.SAMPLE,
                    RunFileRole.QC,
                    RunFileRole.HYE,
                    RunFileRole.PRTC,
                    RunFileRole.LIBRARY,
                }
                raw_file = RawFile.objects.create(
                    run=entry.run,
                    source_path=str(root / "incoming" / entry.expected_filename),
                    storage_path=str(root / "raw" / entry.expected_filename),
                    filename=entry.expected_filename,
                    checksum_sha256=f"{index:064x}",
                    size_bytes=100 + index,
                    imported_at=timezone.now(),
                    status=RawFileStatus.PROCESSED if is_processable else RawFileStatus.IMPORTED,
                    file_role=entry.file_role,
                )
                if not is_processable:
                    continue
                job = ProcessingJob.objects.create(
                    run=entry.run,
                    raw_file=raw_file,
                    pipeline_id=pipeline_id,
                    status=ProcessingStatus.COMPLETE,
                    log_path=str(root / "results" / f"{index}" / "process.log"),
                    stats={"runtime_manifest_path": str(root / "results" / f"{index}" / "runtime-manifest.json")},
                    metadata={"worklist_entry_id": entry.id},
                )
                entry.run.status = RunStatus.PROCESSED
                entry.run.save(update_fields=["status", "updated_at"])
                ProcessingJobArtifact.objects.create(
                    job=job,
                    artifact_type=ProcessingArtifactType.LOG,
                    path=job.log_path,
                    format="log",
                )
                ProteinQuant.objects.create(job=job, protein=protein, value=10.0 + index)
                PeptideQuant.objects.create(job=job, peptide=peptide, value=5.0 + index)

            ProcessingNode.objects.create(
                name="tagged-watcher-test",
                node_type="watcher",
                status=ProcessingNodeStatus.IDLE,
                last_heartbeat_at=timezone.now(),
            )
            ProcessingNode.objects.create(
                name="tagged-processor-test",
                node_type="processor",
                status=ProcessingNodeStatus.IDLE,
                last_heartbeat_at=timezone.now(),
            )

            call_command("verify_tagged_operations_fixture", code_prefix="OPS-COMPLETE")

    def test_archive_raw_files_creates_verified_archive_and_backup_copy(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_root = root / "raw"
            archive_root = root / "archive"
            backup_root = root / "backup"
            raw_root.mkdir()
            source = raw_root / "Sample_A.raw"
            source.write_bytes(b"raw-data")

            raw_file = RawFile.objects.create(
                source_path=str(source),
                storage_path=str(source),
                filename="Sample_A.raw",
                checksum_sha256="d" * 64,
                size_bytes=len(b"raw-data"),
                imported_at=timezone.now(),
                status=RawFileStatus.IMPORTED,
            )
            from ingest.services import hash_path

            checksum, size_bytes = hash_path(source)
            raw_file.checksum_sha256 = checksum
            raw_file.size_bytes = size_bytes
            raw_file.save(update_fields=["checksum_sha256", "size_bytes", "updated_at"])

            with override_settings(
                MSCONNECT_ARCHIVE_ROOTS=[str(archive_root)],
                MSCONNECT_BACKUP_ROOTS=[str(backup_root)],
            ):
                call_command("archive_raw_files", raw_file_id=raw_file.id)
                call_command("verify_archives", raw_file_id=raw_file.id, restore_test=True)

            archive = RawFileArchive.objects.get(raw_file=raw_file)
            self.assertEqual(archive.status, RawFileArchiveStatus.VERIFIED)
            self.assertTrue(Path(archive.archive_path).exists())
            self.assertEqual(
                RawFileArchiveCopy.objects.filter(
                    archive=archive,
                    status=RawFileArchiveCopyStatus.VERIFIED,
                ).count(),
                2,
            )

    def test_cleanup_processing_state_removes_transient_jobs_and_resets_nodes(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results_root = root / "results"
            results_root.mkdir()
            jobs_root = results_root / "jobs"
            jobs_root.mkdir()

            user = get_user_model().objects.create(username="cleanup-user")
            university = University.objects.create(name="Cleanup University")
            facility = Facility.objects.create(university=university, name="Cleanup Facility", slug="cleanup-facility")
            lab = Lab.objects.create(facility=facility, name="Cleanup Lab", slug="cleanup-lab", pi=user)
            project = Project.objects.create(lab=lab, code="CLEANUP-UNIT", title="Cleanup Unit", pi=user)
            experiment = project.experiments.create(name="Cleanup Experiment")
            run = experiment.samples.create(name="Cleanup Sample").runs.create(run_name="cleanup-run")
            raw_file = RawFile.objects.create(
                run=run,
                source_path=str(root / "incoming" / "cleanup.raw"),
                storage_path=str(root / "raw" / "cleanup.raw"),
                filename="cleanup.raw",
                checksum_sha256="c" * 64,
                size_bytes=128,
                status=RawFileStatus.IMPORTED,
            )
            pipeline = ProcessingPipeline.objects.create(name="Cleanup Pipeline", version="1.0")
            complete_job = ProcessingJob.objects.create(
                run=run,
                raw_file=raw_file,
                pipeline=pipeline,
                status=ProcessingStatus.COMPLETE,
                log_path=str(jobs_root / "99" / "process.log"),
            )
            queued_job = ProcessingJob.objects.create(
                run=run,
                raw_file=raw_file,
                pipeline=pipeline,
                status=ProcessingStatus.QUEUED,
                log_path=str(jobs_root / "100" / "process.log"),
            )
            running_job = ProcessingJob.objects.create(
                run=run,
                raw_file=raw_file,
                pipeline=pipeline,
                status=ProcessingStatus.RUNNING,
                node=None,
                log_path=str(jobs_root / "101" / "process.log"),
            )
            for job in (queued_job, running_job):
                job_dir = jobs_root / str(job.id)
                job_dir.mkdir(parents=True)
                (job_dir / "process.log").write_text("job log", encoding="utf-8")

            node = ProcessingNode.objects.create(
                name="cleanup-node",
                node_type="diann",
                status=ProcessingNodeStatus.BUSY,
                last_heartbeat_at=timezone.now(),
                metadata={"control": {"id": "ctrl-1", "command": "pause"}},
            )

            with override_settings(RESULTS_ROOT=str(results_root)):
                call_command("cleanup_processing_state")

            self.assertTrue(ProcessingJob.objects.filter(pk=complete_job.pk).exists())
            self.assertFalse(ProcessingJob.objects.filter(pk=queued_job.pk).exists())
            self.assertFalse(ProcessingJob.objects.filter(pk=running_job.pk).exists())
            self.assertFalse((jobs_root / str(queued_job.id)).exists())
            self.assertFalse((jobs_root / str(running_job.id)).exists())
            node.refresh_from_db()
            self.assertEqual(node.status, ProcessingNodeStatus.OFFLINE)
            self.assertIsNone(node.last_heartbeat_at)
            self.assertNotIn("control", node.metadata)
            self.assertIn("cleanup", node.metadata)

    def test_storage_capacity_report_runs_with_configured_roots(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ["incoming", "raw", "results", "archive", "backup"]:
                (root / name).mkdir()
            with override_settings(
                INCOMING_RAW_ROOT=str(root / "incoming"),
                RAW_FILE_STORAGE_ROOT=str(root / "raw"),
                RESULTS_ROOT=str(root / "results"),
                MSCONNECT_ARCHIVE_ROOTS=[str(root / "archive")],
                MSCONNECT_BACKUP_ROOTS=[str(root / "backup")],
            ):
                call_command("storage_capacity_report", projected_files=10, average_raw_gb=2)

    def test_create_engine_operations_fixture_creates_engine_specific_worklists(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skyline_document = root / "project.sky"
            fragpipe_workflow = root / "fragpipe.workflow"
            skyline_document.write_text("skyline", encoding="utf-8")
            fragpipe_workflow.write_text("fragpipe", encoding="utf-8")
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command(
                    "create_engine_operations_fixture",
                    code="OPS-ENGINE-UNIT",
                    diann_file=["DIA-NN-01.mzML"],
                    fragpipe_file=["FragPipe-01.mzML"],
                    fragpipe_workflow=str(fragpipe_workflow),
                    skyline_file=["Skyline-01.mzML"],
                    skyline_document=str(skyline_document),
                    create_placeholders=True,
                )

            project = Project.objects.get(code="OPS-ENGINE-UNIT")
            self.assertEqual(project.experiments.count(), 3)
            diann_pipeline = ProcessingPipeline.objects.get(name="Real DIA-NN")
            fragpipe_pipeline = ProcessingPipeline.objects.get(name="Real FragPipe")
            skyline_pipeline = ProcessingPipeline.objects.get(name="Skyline Targeted")
            self.assertEqual(diann_pipeline.parameters["required_engine"], "diann")
            self.assertEqual(fragpipe_pipeline.parameters["required_engine"], "fragpipe")
            self.assertEqual(fragpipe_pipeline.parameters["workflow"], str(fragpipe_workflow))
            self.assertEqual(skyline_pipeline.parameters["required_engine"], "skyline")
            self.assertEqual(
                WorklistEntry.objects.filter(worklist__metadata__required_engine="diann").get().expected_filename,
                "DIA-NN-01.mzML",
            )
            self.assertEqual(
                WorklistEntry.objects.filter(worklist__metadata__required_engine="fragpipe").get().expected_filename,
                "FragPipe-01.mzML",
            )
            self.assertEqual(
                WorklistEntry.objects.filter(worklist__metadata__required_engine="skyline").get().expected_filename,
                "Skyline-01.mzML",
            )

    def test_create_filename_worklist_matches_expected_filenames(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            filenames = [
                "/Volumes/T7_Shield/tempDataMS/EN1033_FluidBlank_BufferA_rep1_ch1_GL17_DIA100win1uL_run3.raw",
                "/Volumes/T7_Shield/tempDataMS/EN1033_try2_TB500_UFBW_rep1_ch2_GD12_DIA100windry_run34.raw",
                "/Volumes/T7_Shield/tempDataMS/EN1033_TB500_BacStat_rep3_ch1_GB15_DIA100win2uL_run15.raw",
            ]
            filenames_file = root / "filenames.txt"
            filenames_file.write_text("\n".join(filenames) + "\n", encoding="utf-8")
            with override_settings(INCOMING_RAW_ROOT=str(incoming)):
                call_command(
                    "create_filename_worklist",
                    code="EN1033",
                    project_title="EN1033 filename matching smoke project",
                    worklist_name="EN1033 filename matching worklist",
                    filenames_file=str(filenames_file),
                    create_placeholders=True,
                )

            project = Project.objects.get(code="EN1033")
            worklist = project.experiments.get().worklists.get()
            entries = list(WorklistEntry.objects.filter(worklist=worklist).order_by("position"))

            self.assertEqual(worklist.metadata["watcher_matching"], "expected_filename")
            self.assertEqual(worklist.metadata["filename_count"], 3)
            self.assertEqual(entries[0].expected_filename, Path(filenames[0]).name)
            self.assertEqual(entries[1].expected_filename, Path(filenames[1]).name)
            self.assertEqual(entries[2].expected_filename, Path(filenames[2]).name)
            self.assertEqual(entries[0].file_role, RunFileRole.TRUE_BLANK)
            self.assertEqual(entries[1].file_role, RunFileRole.SAMPLE)
            self.assertEqual(entries[2].file_role, RunFileRole.SAMPLE)
            self.assertEqual(entries[0].qc_program, QcProgram.NONE)
            self.assertEqual(entries[1].qc_program, QcProgram.NONE)
            self.assertEqual(entries[2].qc_program, QcProgram.NONE)
            self.assertTrue((incoming / Path(filenames[0]).name).exists())
            self.assertTrue((incoming / Path(filenames[1]).name).exists())
            self.assertTrue((incoming / Path(filenames[2]).name).exists())
            self.assertEqual(
                entries[0].worklist.metadata["processing_pipeline_id"],
                ProcessingPipeline.objects.get(name="Filename matching DIA-NN", version="site-managed").id,
            )

    def test_rerun_latest_diann_batch_requeues_failed_jobs_and_backfills_conversion(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command(
                    "create_filename_worklist",
                    code="BATCH-UNIT",
                    project_title="Batch rerun smoke project",
                    worklist_name="Batch rerun worklist",
                    filename=["BATCH-01.raw"],
                )

            project = Project.objects.get(code="BATCH-UNIT")
            worklist = project.experiments.get().worklists.get()
            entry = worklist.entries.get(position=1)
            run = entry.run
            raw_file = RawFile.objects.create(
                run=run,
                source_path="/incoming/BATCH-01.raw",
                storage_path=str(root / "raw" / "aa" / "batch-01.raw"),
                filename="BATCH-01.raw",
                checksum_sha256="f" * 64,
                size_bytes=1024,
                imported_at=timezone.now(),
                status=RawFileStatus.IMPORTED,
            )
            failed_node = ProcessingNode.objects.create(
                name="diann-rerun-test",
                node_type="diann",
                status=ProcessingNodeStatus.IDLE,
                last_heartbeat_at=timezone.now(),
            )
            diann_pipeline = ProcessingPipeline.objects.get(name="Filename matching DIA-NN", version="site-managed")
            failed_job = ProcessingJob.objects.create(
                run=run,
                raw_file=raw_file,
                pipeline=diann_pipeline,
                node=failed_node,
                status=ProcessingStatus.FAILED,
                error_message="previous failure",
            )

            call_command("rerun_latest_diann_batch", project_code="BATCH-UNIT")

            failed_job.refresh_from_db()
            conversion_job = ProcessingJob.objects.get(
                run=run,
                raw_file=raw_file,
                pipeline__name="ProteoWizard msconvert",
            )

            self.assertEqual(failed_job.status, ProcessingStatus.QUEUED)
            self.assertIsNone(failed_job.node_id)
            self.assertEqual(failed_job.error_message, "")
            self.assertEqual(failed_job.started_at, None)
            self.assertEqual(failed_job.finished_at, None)
            self.assertEqual(conversion_job.status, ProcessingStatus.QUEUED)
            self.assertEqual(conversion_job.metadata["purpose"], "spectra_conversion")
            self.assertEqual(conversion_job.metadata["backfill"], True)

    def test_processor_registry_create_pipeline_pins_engine_profile(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_file = root / "diann-settings.json"
            settings_file.write_text('{"options": ["--threads", "8"]}', encoding="utf-8")
            with override_settings(PROCESSOR_SHARED_STORAGE_ROOT=str(root / "shared")):
                call_command("processor_registry", "init")
                call_command(
                    "processor_registry",
                    "add-settings",
                    "--engine",
                    "diann",
                    "--key",
                    "standard",
                    "--json-file",
                    str(settings_file),
                )
                call_command(
                    "processor_registry",
                    "add-engine",
                    "--engine",
                    "diann",
                    "--version",
                    "2.1.0",
                    "--image",
                    "registry.example.org/msconnect/processor-diann:2.1.0",
                    "--executable",
                    "diann",
                )
                call_command(
                    "processor_registry",
                    "create-pipeline",
                    "--engine",
                    "diann",
                    "--version",
                    "MSConnect DIA-NN 2.1.0",
                    "--engine-version",
                    "2.1.0",
                    "--settings-key",
                    "standard",
                )

            pipeline = ProcessingPipeline.objects.get(name="Real DIA-NN", version="MSConnect DIA-NN 2.1.0")
            self.assertEqual(pipeline.container_image, "registry.example.org/msconnect/processor-diann:2.1.0")
            self.assertEqual(pipeline.parameters["required_engine_version"], "2.1.0")
            self.assertEqual(pipeline.parameters["engine_profile"]["image"], pipeline.container_image)
