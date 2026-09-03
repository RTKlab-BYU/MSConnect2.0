import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import (
    AcquisitionWorklist,
    Experiment,
    Facility,
    Lab,
    ProcessingPipeline,
    Project,
    Run,
    RunFileRole,
    Sample,
    University,
    UserProfile,
    UserRole,
    WorklistEntry,
    WorklistStatus,
)


class Command(BaseCommand):
    help = "Create a clean two-experiment lifecycle fixture with ten acquisitions per experiment."

    def add_arguments(self, parser):
        parser.add_argument("--code", default="LIFECYCLE-TEST")

    def handle(self, *args, **options):
        code = options["code"]
        user = self._user()
        lab = self._lab(user)
        project, _ = Project.objects.update_or_create(
            code=code, defaults={"lab": lab, "title": "Lifecycle validation project", "pi": user}
        )
        pipeline, _ = ProcessingPipeline.objects.update_or_create(
            name="Lifecycle Test Processor", version="1.0", defaults={
                "container_image": settings.MSCONNECT_IMAGE,
                "parameters": {
                    "command": [sys.executable, "manage.py", "seed_demo_showcase", "--write-job-results", "{job_id}", "{results_dir}"],
                    "working_dir": str(settings.BASE_DIR),
                    "result_files": {"protein_table": "proteins.csv", "peptide_table": "peptides.csv", "delimiter": ","},
                    "stats_json": "stats.json",
                },
            },
        )
        incoming = Path(settings.INCOMING_RAW_ROOT)
        incoming.mkdir(parents=True, exist_ok=True)
        for experiment_number in range(1, 3):
            experiment, _ = Experiment.objects.update_or_create(
                project=project, name=f"Experiment {experiment_number}", defaults={"created_by": user}
            )
            worklist, _ = AcquisitionWorklist.objects.update_or_create(
                experiment=experiment,
                name=f"Experiment {experiment_number} Worklist",
                defaults={"status": WorklistStatus.READY, "generated_by": user, "metadata": {"processing_pipeline_id": pipeline.id, "setup_source": "lifecycle_fixture"}},
            )
            for file_number in range(1, 11):
                filename = f"{code}_E{experiment_number:02d}_R{file_number:02d}.mzML"
                (incoming / filename).write_text(f"MSConnect lifecycle placeholder E{experiment_number} R{file_number}\n", encoding="utf-8")
                sample, _ = Sample.objects.update_or_create(experiment=experiment, name=f"Sample {file_number:02d}")
                run, _ = Run.objects.update_or_create(
                    sample=sample, run_name=f"{code} E{experiment_number} R{file_number:02d}",
                    defaults={"expected_filename": filename, "file_role": RunFileRole.SAMPLE, "metadata": {"watcher_match_key": filename}},
                )
                WorklistEntry.objects.update_or_create(
                    worklist=worklist, position=file_number,
                    defaults={"run": run, "expected_filename": filename, "file_role": RunFileRole.SAMPLE, "metadata": {"watcher_match_key": filename}},
                )
        self.stdout.write(self.style.SUCCESS(f"created lifecycle fixture project={code} experiments=2 files=20 incoming={incoming} pipeline={pipeline.id}"))

    def _user(self):
        user, _ = get_user_model().objects.get_or_create(username="lifecycle-admin", defaults={"is_staff": True})
        UserProfile.objects.get_or_create(user=user, defaults={"global_role": UserRole.ADMIN})
        return user

    def _lab(self, user):
        university, _ = University.objects.get_or_create(name="MSConnect Lifecycle University")
        facility, _ = Facility.objects.get_or_create(university=university, slug="lifecycle", defaults={"name": "Lifecycle Facility"})
        lab, _ = Lab.objects.get_or_create(facility=facility, slug="lifecycle", defaults={"name": "Lifecycle Lab", "pi": user})
        return lab
