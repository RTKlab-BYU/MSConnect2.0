import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Experiment,
    ExperimentStatus,
    Lab,
    Peptide,
    PeptideQuant,
    PipelineEventType,
    ProcessingArtifactType,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    ProjectStatus,
    Protein,
    ProteinQuant,
    RawFile,
    RawFileStatus,
    Run,
    RunFileRole,
    RunStatus,
    Sample,
    UserProfile,
    UserRole,
)
from core.services.lifecycle import (
    recompute_experiment_and_project_status,
    record_pipeline_event,
    record_processing_completion,
    record_raw_file_import,
    record_result_files_uploaded,
)
from ingest.services import build_storage_path


class Command(BaseCommand):
    help = "Import a legacy SDMS export into the current project/experiment/raw-file schema."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="Path to a JSON export file.")
        parser.add_argument("--lab-id", type=int, help="Target lab id for the imported project.")
        parser.add_argument("--lab-code", help="Target lab code for the imported project.")
        parser.add_argument("--storage-root", default=settings.RAW_FILE_STORAGE_ROOT)
        parser.add_argument("--copy-files", action="store_true", help="Copy legacy source files into storage.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        input_path = Path(options["input"]).expanduser()
        if not input_path.exists():
            raise CommandError(f"input file does not exist: {input_path}")

        payload = json.loads(input_path.read_text(encoding="utf-8"))
        lab = self._resolve_lab(options, payload)
        project_payload = payload.get("project") or {}
        experiments_payload = payload.get("experiments") or []
        if not experiments_payload:
            raise CommandError("input file must contain at least one experiment.")

        storage_root = Path(options["storage_root"]).expanduser()
        storage_root.mkdir(parents=True, exist_ok=True)
        dry_run = bool(options["dry_run"])

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"dry-run project={project_payload.get('code') or project_payload.get('title') or 'legacy-import'} "
                    f"experiments={len(experiments_payload)}"
                )
            )
            return

        with transaction.atomic():
            project = self._upsert_project(project_payload, lab)
            imported_experiments = []
            for experiment_payload in experiments_payload:
                experiment = self._import_experiment(
                    project=project,
                    experiment_payload=experiment_payload,
                    storage_root=storage_root,
                    copy_files=bool(options["copy_files"]),
                )
                imported_experiments.append(experiment)

            record_pipeline_event(
                event_type=PipelineEventType.MIGRATION_IMPORTED,
                project=project,
                message="Legacy SDMS export imported into the new schema.",
                payload={
                    "input_file": str(input_path),
                    "experiment_count": len(imported_experiments),
                    "copy_files": bool(options["copy_files"]),
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"imported project={project.code} experiments={len(imported_experiments)} storage_root={storage_root}"
            )
        )

    def _resolve_lab(self, options, payload):
        lab_id = options.get("lab_id")
        lab_code = str(options.get("lab_code") or "").strip()
        if lab_id:
            return Lab.objects.select_related("facility__university").get(pk=lab_id)
        if lab_code:
            lab = Lab.objects.select_related("facility__university").filter(slug=lab_code).first()
            if lab:
                return lab
        project_payload = payload.get("project") or {}
        if project_payload.get("lab_id"):
            return Lab.objects.select_related("facility__university").get(pk=project_payload["lab_id"])
        raise CommandError("Provide --lab-id, --lab-code, or project.lab_id in the input file.")

    def _upsert_project(self, project_payload, lab: Lab) -> Project:
        code = str(project_payload.get("code") or f"LEGACY-{timezone.now():%Y%m%d%H%M%S}")
        pi = self._resolve_user(project_payload.get("pi_username")) or lab.pi or self._default_user()
        project, _created = Project.objects.update_or_create(
            lab=lab,
            code=code,
            defaults={
                "title": str(project_payload.get("title") or code),
                "pi": pi,
                "description": str(project_payload.get("description") or "Imported from a legacy SDMS export."),
                "status": project_payload.get("status") or ProjectStatus.ACTIVE,
                "completed_at": self._parse_datetime(project_payload.get("completed_at")),
            },
        )
        return project

    def _import_experiment(self, *, project: Project, experiment_payload: dict, storage_root: Path, copy_files: bool):
        experiment_name = str(experiment_payload.get("name") or "Imported experiment")
        experiment, _created = Experiment.objects.update_or_create(
            project=project,
            name=experiment_name,
            defaults={
                "hypothesis": str(experiment_payload.get("hypothesis") or ""),
                "status": experiment_payload.get("status") or ExperimentStatus.ACTIVE,
                "completed_at": self._parse_datetime(experiment_payload.get("completed_at")),
                "started_on": experiment_payload.get("started_on") or None,
                "ended_on": experiment_payload.get("ended_on") or None,
                "metadata": {
                    **(experiment_payload.get("metadata") or {}),
                    "migration": {
                        "source": "legacy_sdms_export",
                        "sample_count": len(experiment_payload.get("samples") or []),
                        "run_count": len(experiment_payload.get("runs") or []),
                    },
                },
            },
        )

        samples_by_name = {}
        for sample_payload in experiment_payload.get("samples") or []:
            sample_name = str(sample_payload.get("name") or "").strip()
            if not sample_name:
                raise CommandError("Each sample requires a name.")
            sample, _created = Sample.objects.update_or_create(
                experiment=experiment,
                name=sample_name,
                defaults={
                    "external_id": str(sample_payload.get("external_id") or ""),
                    "species": str(sample_payload.get("species") or ""),
                    "matrix": str(sample_payload.get("matrix") or ""),
                    "digestion_protocol": str(sample_payload.get("digestion_protocol") or ""),
                    "enrichment_protocol": str(sample_payload.get("enrichment_protocol") or ""),
                    "metadata": sample_payload.get("metadata") or {},
                },
            )
            samples_by_name[sample.name] = sample

        runs_by_key = {}
        for run_payload in experiment_payload.get("runs") or []:
            run = self._import_run(experiment=experiment, run_payload=run_payload, samples_by_name=samples_by_name)
            runs_by_key[self._run_key(run_payload, run)] = run

        for raw_payload in experiment_payload.get("raw_files") or []:
            self._import_raw_file(
                experiment=experiment,
                raw_payload=raw_payload,
                runs_by_key=runs_by_key,
                storage_root=storage_root,
                copy_files=copy_files,
            )

        for job_payload in experiment_payload.get("processing_jobs") or []:
            self._import_processing_job(
                experiment=experiment,
                job_payload=job_payload,
                runs_by_key=runs_by_key,
            )

        recompute_experiment_and_project_status(
            experiment,
            payload={"importer": "legacy_sdms_export", "experiment": experiment.name},
        )
        return experiment

    def _import_run(self, *, experiment: Experiment, run_payload: dict, samples_by_name: dict[str, Sample]) -> Run:
        sample_name = str(run_payload.get("sample_name") or "").strip()
        if not sample_name:
            raise CommandError("Each run requires sample_name.")
        sample = samples_by_name.get(sample_name)
        if not sample:
            sample, _created = Sample.objects.update_or_create(
                experiment=experiment,
                name=sample_name,
                defaults={"metadata": {"migration": {"source": "legacy_sdms_export"}}},
            )
            samples_by_name[sample_name] = sample

        run_name = str(run_payload.get("run_name") or run_payload.get("expected_filename") or sample_name).strip()
        run, _created = Run.objects.update_or_create(
            sample=sample,
            run_name=run_name,
            defaults={
                "status": run_payload.get("status") or RunStatus.IMPORTED,
                "file_role": run_payload.get("file_role") or RunFileRole.SAMPLE,
                "expected_filename": str(run_payload.get("expected_filename") or ""),
                "metadata": run_payload.get("metadata") or {},
                "worklist_position": run_payload.get("worklist_position"),
                "hye_pair_label": str(run_payload.get("hye_pair_label") or ""),
            },
        )
        return run

    def _import_raw_file(
        self,
        *,
        experiment: Experiment,
        raw_payload: dict,
        runs_by_key: dict[str, Run],
        storage_root: Path,
        copy_files: bool,
    ) -> RawFile:
        run = self._resolve_run_for_payload(raw_payload, runs_by_key)
        source_path = Path(str(raw_payload.get("source_path") or raw_payload.get("legacy_path") or "")).expanduser()
        filename = str(raw_payload.get("filename") or source_path.name or raw_payload.get("expected_filename") or "")
        if not filename:
            raise CommandError("Each raw file requires a filename or source_path.")

        checksum = str(raw_payload.get("checksum_sha256") or "").strip()
        if not checksum and source_path.exists():
            from ingest.services import hash_path

            checksum, size_bytes = hash_path(source_path)
        else:
            size_bytes = int(raw_payload.get("size_bytes") or 0)
        if not checksum:
            checksum = f"legacy-{abs(hash((experiment.id, filename))) & ((1 << 256) - 1):064x}"[:64]
        if not size_bytes and source_path.exists():
            size_bytes = source_path.stat().st_size

        storage_path = raw_payload.get("storage_path")
        if copy_files and source_path.exists():
            destination = build_storage_path(storage_root, source_path, checksum)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source_path.is_file():
                destination.write_bytes(source_path.read_bytes())
            else:
                if destination.exists():
                    pass
                else:
                    import shutil

                    shutil.copytree(source_path, destination)
            storage_path = str(destination)
        elif not storage_path:
            storage_path = str(build_storage_path(storage_root, source_path if source_path.exists() else Path(filename), checksum))

        raw_file, _created = RawFile.objects.update_or_create(
            checksum_sha256=checksum,
            defaults={
                "run": run,
                "source_path": str(source_path) if source_path else f"legacy:{filename}",
                "storage_path": storage_path,
                "filename": filename,
                "size_bytes": int(size_bytes),
                "imported_at": self._parse_datetime(raw_payload.get("imported_at")) or timezone.now(),
                "acquired_at": self._parse_datetime(raw_payload.get("acquired_at")),
                "status": raw_payload.get("status") or RawFileStatus.IMPORTED,
                "file_role": raw_payload.get("file_role") or (run.file_role if run else RunFileRole.SAMPLE),
                "match_confidence": raw_payload.get("match_confidence"),
                "failure_reason": str(raw_payload.get("failure_reason") or ""),
                "metadata": {
                    **(raw_payload.get("metadata") or {}),
                    "migration": {"source": "legacy_sdms_export", "experiment": experiment.name},
                },
            },
        )
        record_raw_file_import(
            raw_file,
            message="Legacy raw file imported.",
            payload={"source": "legacy_sdms_export", "raw_payload": raw_payload},
        )
        return raw_file

    def _import_processing_job(self, *, experiment: Experiment, job_payload: dict, runs_by_key: dict[str, Run]):
        run = self._resolve_run_for_payload(job_payload, runs_by_key)
        if not run:
            raise CommandError("Each processing job requires a run reference.")
        raw_file = self._resolve_raw_file_for_run(run, job_payload)
        pipeline_name = str(job_payload.get("pipeline_name") or "Legacy pipeline").strip()
        pipeline_version = str(job_payload.get("pipeline_version") or "legacy").strip()
        pipeline, _created = ProcessingPipeline.objects.update_or_create(
            name=pipeline_name,
            version=pipeline_version,
            defaults={
                "container_image": str(job_payload.get("container_image") or ""),
                "parameters": job_payload.get("parameters") or {},
            },
        )
        job, _created = ProcessingJob.objects.update_or_create(
            run=run,
            raw_file=raw_file,
            pipeline=pipeline,
            defaults={
                "status": job_payload.get("status") or ProcessingStatus.COMPLETE,
                "started_at": self._parse_datetime(job_payload.get("started_at")),
                "finished_at": self._parse_datetime(job_payload.get("finished_at")) or timezone.now(),
                "log_path": str(job_payload.get("log_path") or ""),
                "error_message": str(job_payload.get("error_message") or ""),
                "stats": job_payload.get("stats") or {},
                "metadata": {
                    **(job_payload.get("metadata") or {}),
                    "migration": {"source": "legacy_sdms_export", "experiment": experiment.name},
                },
            },
        )
        for artifact_payload in job_payload.get("artifacts") or []:
            ProcessingJobArtifact.objects.update_or_create(
                job=job,
                artifact_type=artifact_payload.get("artifact_type") or ProcessingArtifactType.OTHER,
                path=str(artifact_payload.get("path") or ""),
                defaults={
                    "format": str(artifact_payload.get("format") or ""),
                    "size_bytes": artifact_payload.get("size_bytes"),
                    "checksum_sha256": str(artifact_payload.get("checksum_sha256") or ""),
                    "retained": bool(artifact_payload.get("retained", True)),
                    "metadata": artifact_payload.get("metadata") or {},
                },
            )
        for protein_payload in job_payload.get("protein_quants") or []:
            protein, _created = Protein.objects.get_or_create(
                accession=str(protein_payload.get("accession") or protein_payload.get("protein") or "LEGACY"),
                defaults={
                    "gene_symbol": str(protein_payload.get("gene_symbol") or ""),
                    "description": str(protein_payload.get("description") or ""),
                    "organism": str(protein_payload.get("organism") or ""),
                },
            )
            ProteinQuant.objects.update_or_create(
                job=job,
                protein=protein,
                label=str(protein_payload.get("label") or "abundance"),
                defaults={
                    "value": float(protein_payload.get("value") or 0.0),
                    "unit": str(protein_payload.get("unit") or ""),
                    "metadata": protein_payload.get("metadata") or {},
                },
            )
        for peptide_payload in job_payload.get("peptide_quants") or []:
            peptide, _created = Peptide.objects.get_or_create(
                sequence=str(peptide_payload.get("sequence") or peptide_payload.get("peptide") or "LEGACY"),
                defaults={
                    "modified_sequence": str(peptide_payload.get("modified_sequence") or ""),
                    "charge": peptide_payload.get("charge"),
                },
            )
            PeptideQuant.objects.update_or_create(
                job=job,
                peptide=peptide,
                label=str(peptide_payload.get("label") or "abundance"),
                defaults={
                    "value": float(peptide_payload.get("value") or 0.0),
                    "unit": str(peptide_payload.get("unit") or ""),
                    "metadata": peptide_payload.get("metadata") or {},
                },
            )
        if job.status == ProcessingStatus.COMPLETE:
            record_result_files_uploaded(
                job,
                payload={"source": "legacy_sdms_export", "artifacts": len(job_payload.get("artifacts") or [])},
            )
            record_processing_completion(
                job,
                payload={"source": "legacy_sdms_export", "pipeline": pipeline.name},
            )

    def _resolve_run_for_payload(self, payload: dict, runs_by_key: dict[str, Run]) -> Run | None:
        for key_name in ("run_name", "expected_filename", "sample_name"):
            key_value = str(payload.get(key_name) or "").strip()
            if key_value and key_value in runs_by_key:
                return runs_by_key[key_value]
        return None

    def _resolve_raw_file_for_run(self, run: Run, job_payload: dict) -> RawFile:
        raw_file = run.raw_files.order_by("-imported_at", "-created_at", "filename").first()
        if raw_file:
            return raw_file
        checksum = str(job_payload.get("raw_file_checksum") or f"legacy-{run.id:064x}")[:64]
        return RawFile.objects.create(
            run=run,
            source_path=f"legacy:{run.run_name}",
            storage_path=f"legacy:{run.run_name}:{checksum}",
            filename=run.expected_filename or f"{run.run_name}.raw",
            checksum_sha256=checksum,
            size_bytes=int(job_payload.get("raw_file_size_bytes") or 0),
            imported_at=timezone.now(),
            status=RawFileStatus.IMPORTED,
            file_role=run.file_role,
            metadata={"migration": {"source": "legacy_sdms_export"}},
        )

    def _run_key(self, run_payload: dict, run: Run) -> str:
        for key_name in ("run_name", "expected_filename", "sample_name"):
            key_value = str(run_payload.get(key_name) or "").strip()
            if key_value:
                return key_value
        return run.run_name

    def _resolve_user(self, username: str | None):
        if not username:
            return None
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user:
            return user
        return None

    def _default_user(self):
        User = get_user_model()
        user, _created = User.objects.get_or_create(username="legacy-import", defaults={"is_staff": True})
        UserProfile.objects.get_or_create(user=user, defaults={"global_role": UserRole.ADMIN})
        return user

    def _parse_datetime(self, value):
        if not value:
            return None
        if hasattr(value, "isoformat"):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
