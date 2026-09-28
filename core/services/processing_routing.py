from core.models import DerivativeStatus, ProcessingJob, RawFile, RawFileDerivativeType


def should_queue_spectra_conversion_for_raw_file(raw_file: RawFile, *, processing_job: ProcessingJob | None = None) -> bool:
    raw_path = str(getattr(raw_file, "storage_path", "") or "").strip()
    if not raw_path:
        return False
    # Bruker timsTOF acquisitions are directory bundles and DIA-NN consumes
    # them directly.  ProteoWizard conversion is currently the Thermo RAW
    # handoff only; sending a .d bundle through msconvert creates a misleading
    # queued conversion job and can block the real analysis indefinitely.
    if raw_path.lower().endswith((".mzml", ".mzmlb", ".d")):
        return False
    if processing_job:
        required_engine = _required_engine_for_job(processing_job)
        if required_engine and required_engine != "processor":
            return False
    return not raw_file.derivatives.filter(
        derivative_type__in=(RawFileDerivativeType.MZML, RawFileDerivativeType.MZMLB),
        status=DerivativeStatus.READY,
    ).exists()


def is_spectra_conversion_job(job: ProcessingJob) -> bool:
    """Return whether *job* produces an intermediate mzML/mzMLb derivative."""
    metadata = getattr(job, "metadata", None) or {}
    if str(metadata.get("purpose") or "").strip().lower() == "spectra_conversion":
        return True
    return _required_engine_for_job(job) in {"msconvert", "pwiz"}


def job_dependencies_satisfied(job: ProcessingJob) -> bool:
    """Require a converted derivative before a non-conversion job can run."""
    if is_spectra_conversion_job(job):
        return True
    raw_file = getattr(job, "raw_file", None)
    if not raw_file:
        return False
    raw_path = str(getattr(raw_file, "storage_path", "") or "").lower()
    if raw_path.endswith((".mzml", ".mzmlb", ".d")):
        return True
    if raw_file.derivatives.filter(
        derivative_type__in=(RawFileDerivativeType.MZML, RawFileDerivativeType.MZMLB),
        status=DerivativeStatus.READY,
    ).exists():
        return True

    # Existing manually-created jobs may intentionally run DIA-NN directly
    # from vendor RAW.  Only enforce the dependency when this raw file has an
    # explicit conversion job queued by the watcher/rerun path.
    return not any(
        is_spectra_conversion_job(candidate)
        for candidate in raw_file.processing_jobs.all()
        if candidate.pk != job.pk
    )


def _required_engine_for_job(job: ProcessingJob) -> str:
    metadata = getattr(job, "metadata", None) or {}
    value = metadata.get("required_engine") or metadata.get("engine")
    if value:
        return str(value).strip().lower()
    pipeline = getattr(job, "pipeline", None)
    parameters = getattr(pipeline, "parameters", None) or {}
    return str(parameters.get("required_engine") or parameters.get("adapter") or "").strip().lower()
