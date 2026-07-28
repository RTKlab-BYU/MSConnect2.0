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
    ProcessingStatus,
    Project,
    Protein,
    ProteinQuant,
    RawFile,
    RawFileStatus,
    RunStatus,
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
