import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Experiment,
    ExperimentStatus,
    Facility,
    Lab,
    PeptideQuant,
    PipelineEvent,
    PipelineEventType,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    ProjectStatus,
    ProteinQuant,
    RawFile,
    RawFileStatus,
    Run,
    Sample,
    University,
)
from core.services.lifecycle import recompute_experiment_and_project_status


class LifecycleStatusTests(TestCase):
    def test_recompute_marks_complete_and_records_events(self):
        user = get_user_model().objects.create_user(username="pi", password="pw")
        university = University.objects.create(name="Lifecycle University")
        facility = Facility.objects.create(university=university, name="Lifecycle Facility", slug="lifecycle")
        lab = Lab.objects.create(facility=facility, name="Lifecycle Lab", slug="lifecycle-lab", pi=user)
        project = Project.objects.create(lab=lab, code="LC-1", title="Lifecycle Project", pi=user)
        experiment = Experiment.objects.create(project=project, name="Discovery DIA")
        sample = Sample.objects.create(experiment=experiment, name="Sample 1")
        run = Run.objects.create(sample=sample, run_name="Run 1")
        raw_file = RawFile.objects.create(
            run=run,
            source_path="/tmp/sample.raw",
            storage_path="/tmp/storage/sample.raw",
            filename="sample.raw",
            checksum_sha256="a" * 64,
            size_bytes=128,
            imported_at=timezone.now(),
            status=RawFileStatus.PROCESSED,
        )
        pipeline = ProcessingPipeline.objects.create(name="DIA-NN", version="2.0")
        job = ProcessingJob.objects.create(
            run=run,
            raw_file=raw_file,
            pipeline=pipeline,
            status=ProcessingStatus.COMPLETE,
            finished_at=timezone.now(),
        )
        ProcessingJobArtifact.objects.create(job=job, artifact_type="log", path="/tmp/result.log", format="log")

        recompute_experiment_and_project_status(experiment)

        project.refresh_from_db()
        experiment.refresh_from_db()

        self.assertEqual(experiment.status, ExperimentStatus.COMPLETE)
        self.assertEqual(project.status, ProjectStatus.COMPLETE)
        self.assertIsNotNone(experiment.completed_at)
        self.assertIsNotNone(project.completed_at)
        self.assertEqual(
            PipelineEvent.objects.filter(event_type__in=[PipelineEventType.EXPERIMENT_COMPLETED, PipelineEventType.PROJECT_COMPLETED]).count(),
            2,
        )

    def test_import_legacy_sdms_export_rehydrates_raw_and_processed_records(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            storage_root = root / "storage"
            source_raw = root / "legacy" / "sample.raw"
            source_raw.parent.mkdir(parents=True)
            source_raw.write_bytes(b"legacy-raw-bytes")
            legacy_log = root / "legacy" / "process.log"
            legacy_log.write_text("processed", encoding="utf-8")

            user = get_user_model().objects.create_user(username="pi", password="pw")
            university = University.objects.create(name="Legacy University")
            facility = Facility.objects.create(university=university, name="Legacy Facility", slug="legacy-facility")
            lab = Lab.objects.create(facility=facility, name="Legacy Lab", slug="legacy-lab", pi=user)

            export = {
                "project": {
                    "code": "LEGACY-01",
                    "title": "Legacy Project",
                    "pi_username": "pi",
                },
                "experiments": [
                    {
                        "name": "Legacy Experiment",
                        "samples": [
                            {
                                "name": "Sample 1",
                            }
                        ],
                        "runs": [
                            {
                                "sample_name": "Sample 1",
                                "run_name": "Run 1",
                                "expected_filename": "sample.raw",
                                "file_role": "sample",
                            }
                        ],
                        "raw_files": [
                            {
                                "run_name": "Run 1",
                                "source_path": str(source_raw),
                                "filename": "sample.raw",
                                "status": "processed",
                                "file_role": "sample",
                            }
                        ],
                        "processing_jobs": [
                            {
                                "run_name": "Run 1",
                                "pipeline_name": "DIA-NN",
                                "pipeline_version": "2.0",
                                "status": "complete",
                                "log_path": str(legacy_log),
                                "artifacts": [
                                    {
                                        "artifact_type": "log",
                                        "path": str(legacy_log),
                                        "format": "log",
                                    }
                                ],
                                "protein_quants": [
                                    {
                                        "accession": "P12345",
                                        "value": 12.5,
                                    }
                                ],
                                "peptide_quants": [
                                    {
                                        "sequence": "PEPTIDE",
                                        "value": 4.2,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
            export_path = root / "legacy-export.json"
            export_path.write_text(json.dumps(export), encoding="utf-8")

            with override_settings(RAW_FILE_STORAGE_ROOT=str(storage_root)):
                call_command("import_legacy_sdms_export", input=str(export_path), lab_id=lab.id, copy_files=True)

            project = Project.objects.get(code="LEGACY-01")
            experiment = project.experiments.get(name="Legacy Experiment")
            run = Run.objects.get(run_name="Run 1")
            raw_file = RawFile.objects.get(run=run)
            job = ProcessingJob.objects.get(run=run)

            self.assertEqual(project.status, ProjectStatus.COMPLETE)
            self.assertEqual(experiment.status, ExperimentStatus.COMPLETE)
            self.assertEqual(raw_file.status, RawFileStatus.PROCESSED)
            self.assertEqual(job.status, ProcessingStatus.COMPLETE)
            self.assertTrue(Path(raw_file.storage_path).exists())
            self.assertEqual(ProcessingJobArtifact.objects.filter(job=job).count(), 1)
            self.assertEqual(ProteinQuant.objects.filter(job=job).count(), 1)
            self.assertEqual(PeptideQuant.objects.filter(job=job).count(), 1)
            self.assertTrue(
                PipelineEvent.objects.filter(event_type=PipelineEventType.MIGRATION_IMPORTED, project=project).exists()
            )
