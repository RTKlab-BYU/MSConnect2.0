from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import (
    AcquisitionWorklist,
    ProcessingJob,
    ProcessingPipeline,
    ProcessingStatus,
    RawFile,
)
from core.services.processing_routing import should_queue_spectra_conversion_for_raw_file


def rerun_latest_diann_batch(*, project_code: str | None = None, worklist_id: int | None = None) -> dict:
    worklist = _resolve_worklist(worklist_id=worklist_id, project_code=project_code)
    if not worklist:
        raise ValueError("No acquisition worklist was found to rerun.")

    diann_pipeline_id = (worklist.metadata or {}).get("processing_pipeline_id")
    if not diann_pipeline_id:
        raise ValueError(f"Worklist {worklist.id} does not define processing_pipeline_id metadata.")
    try:
        diann_pipeline = ProcessingPipeline.objects.get(pk=int(diann_pipeline_id))
    except (TypeError, ValueError, ProcessingPipeline.DoesNotExist) as exc:
        raise ValueError(f"Invalid DIA-NN pipeline id on worklist {worklist.id}: {diann_pipeline_id}") from exc

    converted = 0
    rerun = 0
    skipped = 0
    with transaction.atomic():
        for entry in worklist.entries.select_related("run").prefetch_related("run__raw_files", "run__processing_jobs"):
            raw_file = entry.run.raw_files.order_by("-imported_at", "filename").first()
            if not raw_file:
                skipped += 1
                continue

            job = (
                ProcessingJob.objects.select_for_update()
                .filter(run=entry.run, raw_file=raw_file, pipeline=diann_pipeline)
                .order_by("-created_at")
                .first()
            )
            if job and job.status not in {ProcessingStatus.FAILED, ProcessingStatus.RETRYING}:
                skipped += 1
                continue

            if should_queue_spectra_conversion_for_raw_file(raw_file, processing_job=job):
                conversion_pipeline = _msconvert_pipeline()
                conversion_job = _queue_or_reset_conversion_job(raw_file, conversion_pipeline)
                if conversion_job:
                    converted += 1

            job = _queue_or_reset_diann_job(entry.run, raw_file, diann_pipeline, existing_job=job)
            rerun += 1 if job else 0

    return {
        "worklist_id": worklist.id,
        "project_id": worklist.experiment.project_id,
        "pipeline_id": diann_pipeline.id,
        "converted": converted,
        "rerun": rerun,
        "skipped": skipped,
    }


def _resolve_worklist(*, worklist_id: int | None, project_code: str | None):
    queryset = AcquisitionWorklist.objects.select_related("experiment__project").order_by("-updated_at", "-id")
    if worklist_id:
        return queryset.filter(pk=worklist_id).first()
    if project_code:
        return queryset.filter(experiment__project__code=project_code).first()
    return queryset.first()


def _msconvert_pipeline() -> ProcessingPipeline:
    pipeline, _created = ProcessingPipeline.objects.update_or_create(
        name="ProteoWizard msconvert",
        version=settings.MSCONNECT_PWIZ_VERSION,
        defaults={
            "container_image": "proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses:site-managed",
            "parameters": {
                "adapter": "msconvert",
                "executable": settings.MSCONNECT_MSCONVERT_EXECUTABLE,
                "output_format": settings.MSCONNECT_MSCONVERT_OUTPUT_FORMAT,
                "filters": ["peakPicking true 1-"],
            },
        },
    )
    return pipeline


def _queue_or_reset_conversion_job(raw_file: RawFile, pipeline: ProcessingPipeline):
    defaults = {
        "status": ProcessingStatus.QUEUED,
        "metadata": {
            "queued_by": "rerun_latest_diann_batch",
            "purpose": "spectra_conversion",
            "backfill": True,
        },
    }
    job, created = ProcessingJob.objects.get_or_create(
        run_id=raw_file.run_id,
        raw_file=raw_file,
        pipeline=pipeline,
        defaults=defaults,
    )
    if created:
        return job
    if job.status in {ProcessingStatus.FAILED, ProcessingStatus.RETRYING, ProcessingStatus.COMPLETE}:
        job.status = ProcessingStatus.QUEUED
        job.node = None
        job.started_at = None
        job.finished_at = None
        job.error_message = ""
        job.log_path = ""
        job.stats = {}
        job.metadata = {
            **(job.metadata or {}),
            "queued_by": "rerun_latest_diann_batch",
            "purpose": "spectra_conversion",
            "backfill": True,
            "requeued_at": timezone.now().isoformat(),
        }
        job.save(
            update_fields=[
                "status",
                "node",
                "started_at",
                "finished_at",
                "error_message",
                "log_path",
                "stats",
                "metadata",
                "updated_at",
            ]
        )
    return job


def _queue_or_reset_diann_job(
    run,
    raw_file: RawFile,
    pipeline: ProcessingPipeline,
    *,
    existing_job: ProcessingJob | None = None,
):
    defaults = {
        "status": ProcessingStatus.QUEUED,
        "metadata": {
            "queued_by": "rerun_latest_diann_batch",
            "purpose": "diann_rerun",
            "backfill": True,
        },
    }
    job = existing_job
    created = False
    if not job:
        job, created = ProcessingJob.objects.get_or_create(
            run=run,
            raw_file=raw_file,
            pipeline=pipeline,
            defaults=defaults,
        )
    if created:
        return job
    job.status = ProcessingStatus.QUEUED
    job.node = None
    job.started_at = None
    job.finished_at = None
    job.error_message = ""
    job.log_path = ""
    job.stats = {}
    job.metadata = {
        **(job.metadata or {}),
        "queued_by": "rerun_latest_diann_batch",
        "purpose": "diann_rerun",
        "backfill": True,
        "requeued_at": timezone.now().isoformat(),
    }
    job.save(
        update_fields=[
            "status",
            "node",
            "started_at",
            "finished_at",
            "error_message",
            "log_path",
            "stats",
            "metadata",
            "updated_at",
        ]
    )
    return job
