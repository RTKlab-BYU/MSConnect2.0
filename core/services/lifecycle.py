from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.models import (
    AcquisitionWorklist,
    Experiment,
    ExperimentStatus,
    PipelineEvent,
    PipelineEventType,
    ProcessingStatus,
    Project,
    ProjectStatus,
    RawFileStatus,
    Run,
    WorklistEntry,
    WorklistStatus,
)
from core.services.processing_routing import is_spectra_conversion_job


def record_pipeline_event(
    *,
    event_type: str,
    project: Project | None = None,
    experiment: Experiment | None = None,
    run=None,
    raw_file=None,
    job=None,
    actor=None,
    from_status: str = "",
    to_status: str = "",
    message: str = "",
    payload: dict | None = None,
) -> PipelineEvent:
    return PipelineEvent.objects.create(
        project=project,
        experiment=experiment,
        run=run,
        raw_file=raw_file,
        job=job,
        event_type=event_type,
        from_status=str(from_status or ""),
        to_status=str(to_status or ""),
        actor=actor,
        message=message,
        payload=payload or {},
    )


def record_raw_file_import(raw_file, *, actor=None, message: str = "", payload: dict | None = None) -> PipelineEvent:
    run = getattr(raw_file, "run", None)
    experiment = getattr(getattr(run, "sample", None), "experiment", None)
    project = getattr(experiment, "project", None)
    return record_pipeline_event(
        event_type=PipelineEventType.RAW_FILE_IMPORTED,
        project=project,
        experiment=experiment,
        run=run,
        raw_file=raw_file,
        actor=actor,
        from_status=RawFileStatus.DISCOVERED,
        to_status=raw_file.status,
        message=message,
        payload=payload,
    )


def record_processing_completion(job, *, actor=None, message: str = "", payload: dict | None = None) -> PipelineEvent:
    run = job.run
    experiment = run.sample.experiment
    project = experiment.project
    return record_pipeline_event(
        event_type=PipelineEventType.PROCESSING_COMPLETED,
        project=project,
        experiment=experiment,
        run=run,
        raw_file=job.raw_file,
        job=job,
        actor=actor,
        from_status=ProcessingStatus.RUNNING,
        to_status=ProcessingStatus.COMPLETE,
        message=message,
        payload=payload,
    )


def record_result_files_uploaded(job, *, actor=None, payload: dict | None = None) -> PipelineEvent:
    run = job.run
    experiment = run.sample.experiment
    project = experiment.project
    return record_pipeline_event(
        event_type=PipelineEventType.RESULT_FILES_UPLOADED,
        project=project,
        experiment=experiment,
        run=run,
        raw_file=job.raw_file,
        job=job,
        actor=actor,
        to_status=ProcessingStatus.COMPLETE,
        payload=payload,
    )


def recompute_experiment_and_project_status(experiment: Experiment, *, actor=None, payload: dict | None = None) -> dict:
    with transaction.atomic():
        experiment = Experiment.objects.select_for_update().select_related("project").get(pk=experiment.pk)
        project = Project.objects.select_for_update().select_related("lab").get(pk=experiment.project_id)

        experiment_complete = _experiment_is_complete(experiment)
        project_complete = _project_is_complete(project)

        updates = {"experiment": None, "project": None}

        if experiment.status in {ExperimentStatus.ACTIVE, ExperimentStatus.COMPLETE}:
            desired_experiment_status = ExperimentStatus.COMPLETE if experiment_complete else ExperimentStatus.ACTIVE
            if experiment.status != desired_experiment_status:
                previous_status = experiment.status
                experiment.status = desired_experiment_status
                experiment.completed_at = timezone.now() if desired_experiment_status == ExperimentStatus.COMPLETE else None
                experiment.save(update_fields=["status", "completed_at", "updated_at"])
                updates["experiment"] = {
                    "from": previous_status,
                    "to": desired_experiment_status,
                }
                if desired_experiment_status == ExperimentStatus.COMPLETE:
                    record_pipeline_event(
                        event_type=PipelineEventType.EXPERIMENT_COMPLETED,
                        project=project,
                        experiment=experiment,
                        actor=actor,
                        from_status=previous_status,
                        to_status=desired_experiment_status,
                        message="Experiment completion criteria satisfied.",
                        payload=payload or {},
                    )

        if project.status in {ProjectStatus.ACTIVE, ProjectStatus.COMPLETE}:
            desired_project_status = ProjectStatus.COMPLETE if project_complete else ProjectStatus.ACTIVE
            if project.status != desired_project_status:
                previous_status = project.status
                project.status = desired_project_status
                project.completed_at = timezone.now() if desired_project_status == ProjectStatus.COMPLETE else None
                project.save(update_fields=["status", "completed_at", "updated_at"])
                updates["project"] = {
                    "from": previous_status,
                    "to": desired_project_status,
                }
                if desired_project_status == ProjectStatus.COMPLETE:
                    record_pipeline_event(
                        event_type=PipelineEventType.PROJECT_COMPLETED,
                        project=project,
                        experiment=experiment,
                        actor=actor,
                        from_status=previous_status,
                        to_status=desired_project_status,
                        message="Project completion criteria satisfied.",
                        payload=payload or {},
                    )

        return updates


def update_worklist_status_for_run(run: Run) -> None:
    """Advance acquisition status without conflating it with analysis status."""
    worklist = (
        AcquisitionWorklist.objects.filter(entries__run=run)
        .distinct()
        .first()
    )
    if not worklist or worklist.status not in {WorklistStatus.READY, WorklistStatus.ACQUIRING}:
        return

    if worklist.status == WorklistStatus.READY:
        worklist.status = WorklistStatus.ACQUIRING

    entries = list(worklist.entries.filter(is_active=True).select_related("run"))
    if entries and all(entry.run.raw_files.exists() for entry in entries):
        worklist.status = WorklistStatus.COMPLETE
    worklist.save(update_fields=["status", "updated_at"])


def _experiment_is_complete(experiment: Experiment) -> bool:
    active_entries = WorklistEntry.objects.filter(worklist__experiment=experiment, is_active=True)
    runs_query = (
        Run.objects.filter(worklist_entry__in=active_entries)
        if active_entries.exists()
        else Run.objects.filter(sample__experiment=experiment, worklist_entry__isnull=True)
    )
    runs = list(runs_query.select_related("sample", "sample__experiment").prefetch_related("raw_files", "processing_jobs"))
    if not runs:
        return False

    for run in runs:
        latest_raw_file = run.raw_files.order_by("-imported_at", "-created_at", "filename").first()
        analysis_jobs = [job for job in run.processing_jobs.all() if not is_spectra_conversion_job(job)]
        latest_job = sorted(analysis_jobs, key=lambda job: (job.created_at, job.id), reverse=True)[0] if analysis_jobs else None
        if not latest_raw_file or latest_raw_file.status != RawFileStatus.PROCESSED:
            return False
        if not latest_job or latest_job.status != ProcessingStatus.COMPLETE:
            return False

    return True


def _project_is_complete(project: Project) -> bool:
    experiments = list(Experiment.objects.filter(project=project))
    if not experiments:
        return False
    return all(_experiment_is_complete(experiment) for experiment in experiments)
