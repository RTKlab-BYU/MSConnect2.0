from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
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
            skyline_document.write_text("skyline", encoding="utf-8")
            with override_settings(INCOMING_RAW_ROOT=str(root / "incoming")):
                call_command(
                    "create_engine_operations_fixture",
                    code="OPS-ENGINE-UNIT",
                    diann_file=["DIA-NN-01.mzML"],
                    skyline_file=["Skyline-01.mzML"],
                    skyline_document=str(skyline_document),
                    create_placeholders=True,
                )

            project = Project.objects.get(code="OPS-ENGINE-UNIT")
            self.assertEqual(project.experiments.count(), 2)
            diann_pipeline = ProcessingPipeline.objects.get(name="Real DIA-NN")
            skyline_pipeline = ProcessingPipeline.objects.get(name="Real Skyline")
            self.assertEqual(diann_pipeline.parameters["required_engine"], "diann")
            self.assertEqual(skyline_pipeline.parameters["required_engine"], "skyline")
            self.assertEqual(
                WorklistEntry.objects.filter(worklist__metadata__required_engine="diann").get().expected_filename,
                "DIA-NN-01.mzML",
            )
            self.assertEqual(
                WorklistEntry.objects.filter(worklist__metadata__required_engine="skyline").get().expected_filename,
                "Skyline-01.mzML",
            )
