from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import (
    AnalysisBatch,
    AnalysisBatchStatus,
    AnalysisExecutor,
    Experiment,
    ProcessingJob,
    ProcessingPipeline,
    ProcessingStatus,
    DerivativeStatus,
    RawFileDerivativeType,
    RawFile,
    RawFileStatus,
    Run,
    RunFileRole,
)
from core.services.lifecycle import recompute_experiment_and_project_status


def queue_project_analysis_batches(*, project, user, experiment=None, pipeline_id=None, executor="slurm"):
    if executor not in AnalysisExecutor.values:
        raise ValueError("executor must be 'local' or 'slurm'.")
    experiments = [experiment] if experiment else list(project.experiments.order_by("id"))
    if not experiments:
        raise ValueError("The project has no experiments to reanalyze.")

    batches = []
    with transaction.atomic():
        for item in experiments:
            pipeline, source_parameters = _resolve_pipeline(item, pipeline_id)
            parameters, reference_snapshot = _snapshot_parameters(item, pipeline, source_parameters=source_parameters)
            inputs = _sample_inputs(item)
            batch = AnalysisBatch.objects.create(
                project=project,
                experiment=item,
                pipeline=pipeline,
                created_by=user,
                executor=executor,
                status=AnalysisBatchStatus.QUEUED,
                parameters_snapshot=parameters,
                reference_snapshot=reference_snapshot,
                raw_file_ids=[raw.id for _run, raw in inputs],
                metadata={"source_pipeline_id": pipeline.id, "sample_run_count": len(inputs)},
            )
            sample_jobs = []
            for run, raw_file in inputs:
                conversion_job = _ensure_thermo_conversion_job(raw_file)
                job_metadata = _job_metadata(batch, parameters, job_kind="sample")
                if conversion_job:
                    job_metadata["depends_on_job_ids"] = [conversion_job.id]
                sample_jobs.append(
                    ProcessingJob.objects.create(
                        run=run,
                        raw_file=raw_file,
                        pipeline=pipeline,
                        analysis_batch=batch,
                        status=ProcessingStatus.QUEUED,
                        metadata=job_metadata,
                    )
                )

            first_run, first_raw = inputs[0]
            rollup_parameters = copy.deepcopy(parameters)
            rollup_parameters["input_files"] = [_diann_input_path(raw) for _run, raw in inputs]
            rollup_tags = copy.deepcopy(rollup_parameters.get("tags") or {})
            rollup_experimental = dict(rollup_tags.get("experimental") or {})
            rollup_experimental.update({"individual_reports": True, "matrices": True})
            rollup_tags["experimental"] = rollup_experimental
            rollup_parameters["tags"] = rollup_tags
            rollup_metadata = _job_metadata(batch, parameters, job_kind="experiment_rollup")
            rollup_metadata.update(
                {
                    "input_files": list(rollup_parameters["input_files"]),
                    "depends_on_job_ids": [job.id for job in sample_jobs],
                    "input_run_ids": [run.id for run, _raw in inputs],
                }
            )
            rollup_job = ProcessingJob.objects.create(
                run=first_run,
                raw_file=first_raw,
                pipeline=pipeline,
                analysis_batch=batch,
                status=ProcessingStatus.QUEUED,
                metadata=rollup_metadata,
            )
            batch.metadata = {
                **(batch.metadata or {}),
                "sample_job_ids": [job.id for job in sample_jobs],
                "rollup_job_id": rollup_job.id,
                "rollup_parameters": rollup_parameters,
            }
            batch.save(update_fields=["metadata", "updated_at"])
            recompute_experiment_and_project_status(
                item,
                actor=user,
                payload={"analysis_batch_id": batch.id, "executor": executor},
            )
            batches.append(batch)
    return batches


def _resolve_pipeline(experiment: Experiment, pipeline_id: int | None) -> tuple[ProcessingPipeline, dict]:
    worklists = list(experiment.worklists.order_by("-updated_at", "-id"))
    assigned_pipeline_ids = {
        int(candidate_id)
        for worklist in worklists
        if (candidate_id := (worklist.metadata or {}).get("processing_pipeline_id"))
        and str(candidate_id).isdigit()
    }
    if pipeline_id:
        if pipeline_id not in assigned_pipeline_ids:
            raise ValueError("The selected pipeline is not assigned to a worklist in this experiment.")
        pipeline = ProcessingPipeline.objects.filter(pk=pipeline_id).first()
    else:
        pipeline = None
        for worklist in experiment.worklists.order_by("-updated_at", "-id"):
            candidate_id = (worklist.metadata or {}).get("processing_pipeline_id")
            if candidate_id:
                pipeline = ProcessingPipeline.objects.filter(pk=candidate_id).first()
                if pipeline:
                    break
    if not pipeline:
        raise ValueError(f"Experiment {experiment.name!r} has no valid DIA-NN processing pipeline.")
    parameters = pipeline.parameters or {}
    if str(parameters.get("adapter") or parameters.get("required_engine") or "").lower() not in {"diann", "dia-nn"}:
        raise ValueError(f"Pipeline {pipeline.name!r} is not a DIA-NN pipeline.")
    source_parameters = next(
        (
            worklist.metadata.get("processing_plan")
            for worklist in worklists
            if str((worklist.metadata or {}).get("processing_pipeline_id") or "") == str(pipeline.id)
            and isinstance((worklist.metadata or {}).get("processing_plan"), dict)
        ),
        parameters,
    )
    return pipeline, source_parameters


def _sample_inputs(experiment: Experiment) -> list[tuple[Run, RawFile]]:
    runs = list(
        Run.objects.filter(sample__experiment=experiment, file_role=RunFileRole.SAMPLE)
        .select_related("sample")
        .order_by("worklist_position", "id")
    )
    inputs = []
    missing = []
    for run in runs:
        raw = (
            RawFile.objects.filter(run=run, file_role=RunFileRole.SAMPLE, status__in=(RawFileStatus.IMPORTED, RawFileStatus.PROCESSED))
            .order_by("-imported_at", "-id")
            .first()
        )
        if raw:
            inputs.append((run, raw))
        else:
            missing.append(run.run_name)
    if missing:
        raise ValueError("Cannot reanalyze until every sample run has an imported raw file: " + ", ".join(missing))
    if not inputs:
        raise ValueError(f"Experiment {experiment.name!r} has no sample-role raw files to reanalyze.")
    return inputs


def _snapshot_parameters(
    experiment: Experiment,
    pipeline: ProcessingPipeline,
    *,
    source_parameters: dict | None = None,
) -> tuple[dict, dict]:
    parameters = copy.deepcopy(source_parameters or pipeline.parameters or {})
    experiment_diann = (experiment.metadata or {}).get("diann") or {}
    project_diann = (experiment.project.metadata or {}).get("diann") or {}
    preferred_library = str(
        experiment_diann.get("preferred_speclib_path")
        or project_diann.get("preferred_speclib_path")
        or ((parameters.get("reference_assets") or {}).get("speclib_asset") or {}).get("path")
        or parameters.get("library")
        or ""
    ).strip()
    fasta_path = str(parameters.get("fasta") or parameters.get("fasta_path") or "").strip()
    if not fasta_path:
        fasta_path = str((parameters.get("reference_assets") or {}).get("fasta_path") or "").strip()
    if preferred_library:
        parameters.update(
            {
                "library": preferred_library,
                "library_source": "analysis_batch_reference",
                "generate_speclib": False,
                "fasta_search": False,
            }
        )
        tags = copy.deepcopy(parameters.get("tags") or {})
        experimental = dict(tags.get("experimental") or {})
        experimental.update({"library": preferred_library, "generate_speclib": False, "fasta_search": False})
        tags["experimental"] = experimental
        parameters["tags"] = tags
        if not bool(parameters.get("fasta_search")) and not bool(parameters.get("generate_speclib")):
            fasta_path = ""
    elif not bool(parameters.get("generate_speclib")) and not (fasta_path and bool(parameters.get("fasta_search"))):
        raise ValueError(
            f"Experiment {experiment.name!r} has no reusable spectral library. Upload one or complete a library-build analysis first."
        )

    reference_snapshot = {}
    for label, path_value in (("fasta", fasta_path), ("spectral_library", preferred_library)):
        if not path_value:
            continue
        path = Path(path_value).resolve()
        if not path.is_file():
            raise ValueError(f"The configured {label.replace('_', ' ')} reference is missing: {path}")
        reference_snapshot[label] = {
            "path": str(path),
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "checksum_sha256": _sha256(path),
        }
    parameters["reference_snapshot"] = reference_snapshot
    parameters["settings_snapshot_at"] = timezone.now().isoformat()
    return parameters, reference_snapshot


def _diann_input_path(raw_file: RawFile) -> str:
    derivative = (
        raw_file.derivatives.filter(
            derivative_type__in=(RawFileDerivativeType.MZML, RawFileDerivativeType.MZMLB),
            status=DerivativeStatus.READY,
        )
        .order_by("-updated_at", "-id")
        .first()
    )
    return derivative.path if derivative else raw_file.storage_path


def _ensure_thermo_conversion_job(raw_file: RawFile) -> ProcessingJob | None:
    if not str(raw_file.storage_path or "").lower().endswith(".raw"):
        return None
    if raw_file.derivatives.filter(
        derivative_type__in=(RawFileDerivativeType.MZML, RawFileDerivativeType.MZMLB),
        status=DerivativeStatus.READY,
    ).exists():
        return None
    if not settings.MSCONNECT_AUTO_QUEUE_SPECTRA_CONVERSION:
        raise ValueError(
            f"Thermo RAW file {raw_file.filename!r} needs an mzML conversion before Linux DIA-NN can process it."
        )
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
    job, _created = ProcessingJob.objects.get_or_create(
        run_id=raw_file.run_id,
        raw_file=raw_file,
        pipeline=pipeline,
        defaults={
            "status": ProcessingStatus.QUEUED,
            "metadata": {"queued_by": "analysis_batch", "purpose": "spectra_conversion"},
        },
    )
    if job.status == ProcessingStatus.FAILED:
        job.status = ProcessingStatus.QUEUED
        job.node = None
        job.attempt_count = 0
        job.finished_at = None
        job.error_message = ""
        job.lease_token = ""
        job.lease_expires_at = None
        job.save(
            update_fields=[
                "status", "node", "attempt_count", "finished_at", "error_message", "lease_token", "lease_expires_at", "updated_at"
            ]
        )
    return job


def _job_metadata(batch: AnalysisBatch, parameters: dict, *, job_kind: str) -> dict:
    return {
        "queued_by": "analysis_batch",
        "analysis_batch_id": batch.id,
        "job_kind": job_kind,
        "execution_backend": batch.executor,
        "required_engine": "diann",
        "required_engine_version": str(parameters.get("required_engine_version") or ""),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
