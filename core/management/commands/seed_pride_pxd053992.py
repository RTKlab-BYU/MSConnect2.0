import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    AcquisitionWorklist,
    Experiment,
    Facility,
    Lab,
    LabMembership,
    ProcessingJob,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    Run,
    RunFileRole,
    RunStatus,
    Sample,
    University,
    UserProfile,
    UserRole,
    WorklistEntry,
    WorklistStatus,
)
from ingest.services import import_raw_path


class Command(BaseCommand):
    help = "Seed and optionally import the public PRIDE PXD053992 DIA-NN mzML smoke project."

    def add_arguments(self, parser):
        parser.add_argument("--incoming-dir", default="/data/incoming/pride-pxd053992")
        parser.add_argument("--project-code", default="PRIDE-PXD053992")
        parser.add_argument("--import-now", action="store_true")
        parser.add_argument("--limit", type=int, default=2)

    def handle(self, *args, **options):
        incoming_dir = Path(options["incoming_dir"])
        if not incoming_dir.exists():
            raise CommandError(f"Incoming directory does not exist: {incoming_dir}")

        mzml_files = sorted(incoming_dir.glob("KK2748-*.mzML"))[: options["limit"]]
        if not mzml_files:
            raise CommandError(f"No KK2748 mzML files found in {incoming_dir}")

        required = ["KK2748.pg_matrix.tsv", "KK2748.pr_matrix.tsv", "KK2748.stats.tsv"]
        missing = [filename for filename in required if not (incoming_dir / filename).exists()]
        if missing:
            raise CommandError(f"Missing required matrix/stat files: {', '.join(missing)}")

        with transaction.atomic():
            project, pipeline, runs = self._seed_records(
                project_code=options["project_code"],
                incoming_dir=incoming_dir,
                mzml_files=mzml_files,
            )

        imported = []
        if options["import_now"]:
            for run, mzml_path in runs:
                result = import_raw_path(
                    mzml_path,
                    storage_root=Path(settings.RAW_FILE_STORAGE_ROOT),
                    run=run,
                    match_run_by_name=False,
                )
                raw_file = result.raw_file
                if raw_file and raw_file.run_id is None:
                    raw_file.run = run
                    raw_file.match_confidence = 1.0
                    raw_file.save(update_fields=["run", "match_confidence", "updated_at"])
                if raw_file:
                    ProcessingJob.objects.get_or_create(
                        run=run,
                        raw_file=raw_file,
                        pipeline=pipeline,
                        defaults={
                            "status": ProcessingStatus.QUEUED,
                            "metadata": {
                                "queued_by": "seed_pride_pxd053992",
                                "source": "PXD053992 DIA-NN public smoke",
                            },
                        },
                    )
                    imported.append(raw_file.filename)

        self.stdout.write(self.style.SUCCESS(f"Seeded {project.code} with {len(runs)} runs."))
        if imported:
            self.stdout.write(self.style.SUCCESS(f"Imported and queued {len(imported)} raw files: {', '.join(imported)}"))

    def _seed_records(self, *, project_code: str, incoming_dir: Path, mzml_files: list[Path]):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="msconnect",
            defaults={"email": "msconnect@example.test", "is_staff": True, "is_superuser": True},
        )
        UserProfile.objects.update_or_create(user=user, defaults={"global_role": UserRole.ADMIN})

        university, _ = University.objects.get_or_create(
            name="Public PRIDE Archive",
            defaults={"abbreviation": "PRIDE", "website": "https://www.ebi.ac.uk/pride/"},
        )
        facility, _ = Facility.objects.get_or_create(
            university=university,
            slug="public-data",
            defaults={"name": "Public proteomics datasets"},
        )
        lab, _ = Lab.objects.get_or_create(
            facility=facility,
            slug="pxd053992",
            defaults={"name": "PXD053992 DIA-NN smoke lab", "pi": user},
        )
        LabMembership.objects.update_or_create(user=user, lab=lab, defaults={"role": UserRole.ADMIN, "active": True})

        project, _ = Project.objects.update_or_create(
            lab=lab,
            code=project_code,
            defaults={
                "title": "PXD053992 public DIA-NN matrix and mzML smoke test",
                "pi": user,
                "description": (
                    "Public PRIDE dataset PXD053992 seeded to exercise mzML ingestion, per-run DIA-NN matrix "
                    "import, protein/peptide counts, MS1/MS2 stats, artifact retention, and spectra indexing."
                ),
            },
        )
        experiment, _ = Experiment.objects.update_or_create(
            project=project,
            name="PXD053992 public DIA-NN smoke",
            defaults={
                "created_by": user,
                "metadata": {
                    "source": "PXD053992",
                    "source_url": "https://ftp.pride.ebi.ac.uk/pride/data/archive/2026/06/PXD053992/",
                    "downloaded_files": [path.name for path in mzml_files],
                },
            },
        )
        pipeline = self._pipeline(incoming_dir)
        worklist, _ = AcquisitionWorklist.objects.update_or_create(
            experiment=experiment,
            name="Downloaded mzML smoke worklist",
            defaults={
                "status": WorklistStatus.READY,
                "generated_by": user,
                "metadata": {
                    "processing_pipeline_id": pipeline.id,
                    "source": "PXD053992",
                },
            },
        )

        runs = []
        for position, mzml_path in enumerate(mzml_files, start=1):
            condition = "control" if "ctrl" in mzml_path.stem.lower() else "sample"
            sample, _ = Sample.objects.update_or_create(
                experiment=experiment,
                name=mzml_path.stem,
                defaults={
                    "external_id": f"{project.code}-{position:03d}",
                    "species": "Homo sapiens",
                    "matrix": "public PRIDE mzML",
                    "digestion_protocol": "trypsin",
                    "submitted_by": user,
                    "metadata": {"condition": condition, "source_filename": mzml_path.name},
                },
            )
            run, _ = Run.objects.update_or_create(
                sample=sample,
                run_name=mzml_path.stem,
                defaults={
                    "status": RunStatus.PLANNED,
                    "file_role": RunFileRole.SAMPLE,
                    "expected_filename": mzml_path.name,
                    "worklist_position": position,
                    "metadata": {"expected_filename": mzml_path.name, "source": "PXD053992"},
                },
            )
            WorklistEntry.objects.update_or_create(
                worklist=worklist,
                position=position,
                defaults={
                    "run": run,
                    "file_role": RunFileRole.SAMPLE,
                    "expected_filename": mzml_path.name,
                    "metadata": {"source": "PXD053992", "sample_name": sample.name},
                },
            )
            runs.append((run, mzml_path))
        return project, pipeline, runs

    def _pipeline(self, incoming_dir: Path) -> ProcessingPipeline:
        parameters = {
            "command": [
                sys.executable,
                "manage.py",
                "write_pride_diann_job_results",
                "{job_id}",
                "{results_dir}",
                "--pg-matrix",
                str(incoming_dir / "KK2748.pg_matrix.tsv"),
                "--pr-matrix",
                str(incoming_dir / "KK2748.pr_matrix.tsv"),
                "--stats",
                str(incoming_dir / "KK2748.stats.tsv"),
                "--max-proteins",
                "750",
                "--max-peptides",
                "1500",
            ],
            "working_dir": str(settings.BASE_DIR),
            "result_files": {
                "protein_table": "proteins.csv",
                "peptide_table": "peptides.csv",
                "stats_json": "stats.json",
                "delimiter": ",",
            },
            "artifact_files": [
                {"artifact_type": "diann_report", "path": "stats.json", "format": "json"},
            ],
        }
        pipeline, _ = ProcessingPipeline.objects.update_or_create(
            name="PRIDE PXD053992 DIA-NN matrix import",
            version="public-smoke",
            defaults={
                "container_image": settings.MSCONNECT_IMAGE,
                "parameters": parameters,
            },
        )
        return pipeline
