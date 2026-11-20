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
    DerivativeStatus,
    Experiment,
    ProcessingJob,
    ProcessingPipeline,
    ProcessingStatus,
    RawFile,
    RawFileDerivativeType,
    RawFileStatus,
    Run,
    RunFileRole,
)
from core.processing.diann import build_diann_command_options, normalize_diann_settings
from core.processing.registry import validate_diann_pipeline_settings
from core.services.lifecycle import recompute_experiment_and_project_status
from core.services.organism_references import normalize_organisms, organism_selection, resolve_project_fasta


def queue_project_analysis_batches(
    *, project, user, experiment=None, pipeline_id=None, executor="local", organisms=None, diann_settings=None,
    speclib_mode="reuse", speclib_path="",
):
    if executor not in AnalysisExecutor.values:
        raise ValueError("executor must be 'local' or 'slurm'.")
    experiments = [experiment] if experiment else list(project.experiments.order_by("id"))
    if not experiments:
        raise ValueError("The project has no experiments to reanalyze.")

    planned = []
    for item in experiments:
        pipeline, source_parameters = _resolve_pipeline(item, pipeline_id)
        parameters, reference_snapshot = _snapshot_parameters(
            item,
            pipeline,
            user=user,
            source_parameters=source_parameters,
            organisms_override=organisms,
            settings_override=diann_settings,
            speclib_mode=speclib_mode,
            speclib_path=speclib_path,
        )
        inputs = _sample_inputs(item)
        planned.append((item, pipeline, parameters, reference_snapshot, inputs))

    batches = []
    with transaction.atomic():
        for item, pipeline, parameters, reference_snapshot, inputs in planned:
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
            rollup_experimental.update({"individual_reports": False, "matrices": True})
            rollup_tags["experimental"] = rollup_experimental
            rollup_parameters["tags"] = rollup_tags
            rollup_settings = copy.deepcopy(rollup_parameters.get("settings") or {})
            rollup_settings_tags = dict(rollup_settings.get("tags") or {})
            rollup_settings_tags["experimental"] = dict(rollup_experimental)
            rollup_settings["tags"] = rollup_settings_tags
            rollup_parameters["settings"] = rollup_settings
            rollup_parameters["options"] = build_diann_command_options(rollup_settings)
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
            _configure_batch_speclib(
                sample_jobs=sample_jobs,
                rollup_job=rollup_job,
                parameters=parameters,
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
    user,
    source_parameters: dict | None = None,
    organisms_override=None,
    settings_override: dict | None = None,
    speclib_mode="reuse",
    speclib_path="",
) -> tuple[dict, dict]:
    parameters = copy.deepcopy(source_parameters or pipeline.parameters or {})
    experiment_diann = (experiment.metadata or {}).get("diann") or {}
    project_diann = (experiment.project.metadata or {}).get("diann") or {}
    base_references = parameters.get("reference_assets") or {}
    metadata_organisms = organism_selection(
        experiment_diann, experiment.metadata or {}, project_diann, experiment.project.metadata or {}
    )
    organisms = normalize_organisms(
        organisms_override
        or metadata_organisms
        or base_references.get("organisms")
        or parameters.get("organisms")
        or ["human", "yeast", "ecoli"]
    )

    current = normalize_diann_settings(parameters.get("settings") or parameters)
    if settings_override:
        proposed = normalize_diann_settings(settings_override)
        experimental = {
            **(current.get("tags", {}).get("experimental") or {}),
            **(proposed.get("tags", {}).get("experimental") or {}),
        }
        performance = dict(current.get("tags", {}).get("performance") or {})
        merged = {
            **{key: value for key, value in current.items() if key != "tags"},
            **{key: value for key, value in proposed.items() if key != "tags"},
            "tags": {"experimental": experimental, "performance": performance},
        }
        errors = validate_diann_pipeline_settings(merged, allow_performance_tags=False)
        if errors:
            raise ValueError("Invalid DIA-NN settings: " + "; ".join(errors))
        current = normalize_diann_settings(merged)

    parameters["organisms"] = organisms
    parameters["execution_mode"] = "nextflow"
    parameters.setdefault("nextflow_workflow", "/opt/msconnect/nextflow/diann/main.nf")
    parameters.setdefault("nextflow_config", "/opt/msconnect/nextflow/diann/nextflow.config")
    parameters.setdefault("nextflow_version_catalog", "/opt/msconnect/nextflow/diann/versions.json")
    parameters.setdefault("nextflow_profile", "local")
    parameters.setdefault("cli_script", "/opt/msconnect/diann_search.py")
    parameters["diann_version"] = str(parameters.get("diann_version") or pipeline.version or "2.7.0")
    parameters["required_engine_version"] = parameters["diann_version"]

    tags = current.get("tags") or {}
    experimental = dict(tags.get("experimental") or {})
    performance = dict(tags.get("performance") or {})
    reference_organisms = normalize_organisms(base_references.get("organisms") or parameters.get("organisms") or organisms)
    organism_changed = reference_organisms != organisms
    explicit_fasta = str(experimental.get("fasta") or parameters.get("fasta") or parameters.get("fasta_path") or "").strip()
    explicit_library = str(experimental.get("library") or parameters.get("library") or "").strip()
    preferred_organisms = experiment_diann.get("preferred_speclib_organisms") or project_diann.get("preferred_speclib_organisms") or []
    preferred_library = ""
    if preferred_organisms and normalize_organisms(preferred_organisms) == organisms and not organism_changed:
        preferred_library = str(
            experiment_diann.get("preferred_speclib_path") or project_diann.get("preferred_speclib_path") or ""
        ).strip()
    preferred_library = explicit_library or preferred_library
    if speclib_mode == "custom":
        preferred_library = str(speclib_path or "").strip()
    elif speclib_mode == "rebuild":
        preferred_library = ""

    reference_snapshot = {"organisms": organisms, "diann_version": parameters["diann_version"]}
    if preferred_library:
        path = Path(preferred_library).resolve()
        if not path.is_file():
            raise ValueError(f"The selected spectral library is missing: {path}")
        reference_snapshot["spectral_library"] = {
            "path": str(path), "filename": path.name, "size_bytes": path.stat().st_size, "checksum_sha256": _sha256(path)
        }
        parameters.update({"library": str(path), "fasta": "", "library_source": "project_reference", "generate_speclib": False, "fasta_search": False})
    else:
        fasta_asset = None
        if explicit_fasta and Path(explicit_fasta).is_file() and not organism_changed:
            fasta_path = str(Path(explicit_fasta).resolve())
        else:
            fasta_asset = resolve_project_fasta(organisms=organisms, project=experiment.project, experiment=experiment, user=user)
            fasta_path = fasta_asset.storage_path
        path = Path(fasta_path).resolve()
        if not path.is_file():
            raise ValueError(f"The selected FASTA is missing: {path}")
        reference_snapshot["fasta"] = {
            "path": str(path), "filename": path.name, "size_bytes": path.stat().st_size, "checksum_sha256": _sha256(path)
        }
        if fasta_asset:
            reference_snapshot["fasta_asset_id"] = fasta_asset.id
        parameters.update({"fasta": str(path), "fasta_path": str(path), "library": "", "library_source": "", "generate_speclib": True, "fasta_search": True})

    effective_settings = {
        **{key: value for key, value in current.items() if key != "tags"},
        "fasta": parameters.get("fasta", ""),
        "library": parameters.get("library", ""),
        "tags": {"experimental": experimental, "performance": performance},
    }
    parameters["settings"] = effective_settings
    parameters["tags"] = effective_settings["tags"]
    parameters["options"] = build_diann_command_options(effective_settings)
    parameters["reference_assets"] = {
        **base_references,
        "organisms": organisms,
        "fasta_path": parameters.get("fasta", ""),
        "speclib_asset": reference_snapshot.get("spectral_library", {}),
    }
    parameters["speclib_policy"] = {
        **(parameters.get("speclib_policy") or {}),
        "scope": "project",
        "build_runs": 1,
        "reuse_after_build": True,
    }
    parameters["settings_snapshot_at"] = timezone.now().isoformat()
    parameters["analysis_organisms"] = organisms
    parameters["analysis_settings_override"] = copy.deepcopy(settings_override or {})
    parameters["speclib_mode"] = speclib_mode
    parameters["reference_snapshot"] = reference_snapshot
    return parameters, reference_snapshot


def _configure_batch_speclib(*, sample_jobs, rollup_job, parameters):
    if not sample_jobs:
        return
    existing_library = str(parameters.get("library") or "").strip()
    builder = None if existing_library else sample_jobs[0]
    library_path = existing_library or str(
        Path(settings.RESULTS_ROOT) / "jobs" / str(sample_jobs[0].id) / "search-library.predicted.speclib"
    )
    for job in sample_jobs:
        metadata = dict(job.metadata or {})
        if builder and job.pk == builder.pk:
            metadata["diann_library_builder"] = True
        else:
            metadata["diann_library_path"] = library_path
            if builder:
                metadata["depends_on_job_ids"] = list(
                    dict.fromkeys([*(metadata.get("depends_on_job_ids") or []), builder.pk])
                )
        job.metadata = metadata
        job.save(update_fields=["metadata", "updated_at"])
    rollup_metadata = dict(rollup_job.metadata or {})
    if library_path:
        rollup_metadata["diann_library_path"] = library_path
    rollup_job.metadata = rollup_metadata
    rollup_job.save(update_fields=["metadata", "updated_at"])


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
