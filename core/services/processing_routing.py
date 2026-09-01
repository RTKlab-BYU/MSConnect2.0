from core.models import DerivativeStatus, ProcessingJob, RawFile, RawFileDerivativeType


def should_queue_spectra_conversion_for_raw_file(raw_file: RawFile, *, processing_job: ProcessingJob | None = None) -> bool:
    raw_path = str(getattr(raw_file, "storage_path", "") or "").strip()
    if not raw_path:
        return False
    if raw_path.lower().endswith((".mzml", ".mzmlb")):
        return False
    if processing_job:
        required_engine = _required_engine_for_job(processing_job)
        if required_engine and required_engine != "processor":
            return False
    return not raw_file.derivatives.filter(
        derivative_type__in=(RawFileDerivativeType.MZML, RawFileDerivativeType.MZMLB),
        status=DerivativeStatus.READY,
    ).exists()


def _required_engine_for_job(job: ProcessingJob) -> str:
    metadata = getattr(job, "metadata", None) or {}
    value = metadata.get("required_engine") or metadata.get("engine")
    if value:
        return str(value).strip().lower()
    pipeline = getattr(job, "pipeline", None)
    parameters = getattr(pipeline, "parameters", None) or {}
    return str(parameters.get("required_engine") or parameters.get("adapter") or "").strip().lower()
