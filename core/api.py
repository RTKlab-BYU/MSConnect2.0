import json
import math
import re
import sys
import uuid
from pathlib import Path, PurePath
from statistics import median
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.signing import TimestampSigner
from django.db import transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, pagination, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ingest.result_import import ResultTableImportError, import_result_tables
from ingest.services import find_run_for_path, parse_filename_metadata, record_ingestion_failure

from .agent_auth import AgentTokenAuthentication
from .models import (
    AcquisitionWorklist,
    DerivativeStatus,
    DirectUploadSession,
    DirectUploadStatus,
    Experiment,
    Facility,
    Instrument,
    InstrumentConfiguration,
    IntakeRequestStatus,
    Lab,
    LabMembership,
    Peptide,
    PeptideIdentification,
    PeptideQuant,
    ProcessingArtifactType,
    ProcessingJob,
    ProcessingJobArtifact,
    ProcessingNode,
    ProcessingNodeStatus,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    ProjectIntakeRequest,
    Protein,
    ProteinIdentification,
    ProteinQuant,
    RawFile,
    RawFileDerivative,
    RawFileDerivativeType,
    RawFileStatus,
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
from .permissions import AgentRolePermission, RoleScopedWritePermission, active_lab_ids, is_admin, user_role


class OptionalPageNumberPagination(pagination.PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 500

    def paginate_queryset(self, queryset, request, view=None):
        if "page" not in request.query_params and self.page_size_query_param not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


class BaseSerializer(serializers.ModelSerializer):
    class Meta:
        fields = "__all__"


class UniversitySerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = University


class FacilitySerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Facility


class LabSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Lab


class UserProfileSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = UserProfile


class LabMembershipSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = LabMembership


class InstrumentSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Instrument


class InstrumentConfigurationSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = InstrumentConfiguration


class ProjectSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Project


class ProjectPreAcquisitionSetupSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=80)
    lab = serializers.PrimaryKeyRelatedField(queryset=Lab.objects.all(), required=False)
    sample_count = serializers.IntegerField(min_value=1, max_value=500, default=12)
    healthy_count = serializers.IntegerField(min_value=0, required=False)
    diseased_count = serializers.IntegerField(min_value=0, required=False)
    sample_rows = serializers.ListField(child=serializers.DictField(), required=False)
    plate_type = serializers.ChoiceField(choices=("96", "384"), default="96")
    hye_interval = serializers.IntegerField(min_value=0, max_value=100, default=10)
    experiment_name = serializers.CharField(max_length=255, default="Discovery DIA")
    worklist_name = serializers.CharField(max_length=255, default="Plate 1 DIA acquisition order")
    instrument_configuration = serializers.PrimaryKeyRelatedField(
        queryset=InstrumentConfiguration.objects.all(),
        required=False,
        allow_null=True,
    )
    fasta_path = serializers.CharField(max_length=1024, allow_blank=True, required=False)
    speclib_path = serializers.CharField(max_length=1024, allow_blank=True, required=False)
    organisms = serializers.ListField(child=serializers.CharField(max_length=128), required=False)
    processing_preset = serializers.CharField(max_length=128, default="Standard DIA-NN plasma")
    fasta_upload_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    speclib_upload_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    diann_version = serializers.CharField(max_length=128, default="1.9")
    diann_settings = serializers.JSONField(required=False)

    def validate(self, attrs):
        sample_rows = _normalize_sample_rows(attrs.get("sample_rows") or [])
        if sample_rows:
            attrs["sample_rows"] = sample_rows
            attrs["sample_count"] = len(sample_rows)
            condition_counts = _condition_counts(sample_rows)
            attrs["healthy_count"] = condition_counts.get("healthy", 0)
            attrs["diseased_count"] = condition_counts.get("diseased", 0)
            attrs["organisms"] = _normalize_organisms(attrs.get("organisms"))
            attrs["diann_settings"] = _ensure_dict(attrs.get("diann_settings"), field_name="diann_settings")
            return attrs

        sample_count = attrs.get("sample_count") or 0
        healthy_count = attrs.get("healthy_count")
        diseased_count = attrs.get("diseased_count")
        if healthy_count is None and diseased_count is None:
            healthy_count = sample_count // 2
            diseased_count = sample_count - healthy_count
        elif healthy_count is None:
            healthy_count = sample_count - diseased_count
        elif diseased_count is None:
            diseased_count = sample_count - healthy_count

        if healthy_count < 0 or diseased_count < 0 or healthy_count + diseased_count != sample_count:
            raise ValidationError({"sample_count": "healthy_count + diseased_count must equal sample_count."})

        attrs["healthy_count"] = healthy_count
        attrs["diseased_count"] = diseased_count
        attrs["sample_rows"] = []
        attrs["organisms"] = _normalize_organisms(attrs.get("organisms"))
        attrs["diann_settings"] = _ensure_dict(attrs.get("diann_settings"), field_name="diann_settings")
        return attrs


class ProjectIntakeQueueSerializer(BaseSerializer):
    lab_name = serializers.CharField(source="lab.name", read_only=True)
    submitted_by_username = serializers.CharField(source="submitted_by.username", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = ProjectIntakeRequest
        fields = (
            "id",
            "requested_title",
            "requested_code",
            "status",
            "lab",
            "lab_name",
            "submitted_by",
            "submitted_by_username",
            "updated_at",
            "reviewed_by",
            "reviewed_by_username",
            "promoted_project",
        )


class ProjectIntakeRequestSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProjectIntakeRequest
        read_only_fields = ("submitted_by", "reviewed_by", "reviewed_at", "promoted_project")


class ExperimentSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Experiment


class SampleSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Sample


class RunSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Run


class RawFileSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = RawFile


class RawFileDerivativeSerializer(BaseSerializer):
    raw_file_filename = serializers.CharField(source="raw_file.filename", read_only=True)
    project_id = serializers.IntegerField(source="raw_file.run.sample.experiment.project_id", read_only=True)
    project_code = serializers.CharField(source="raw_file.run.sample.experiment.project.code", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = RawFileDerivative
        fields = "__all__"


class DirectUploadSessionSerializer(BaseSerializer):
    upload_urls = serializers.SerializerMethodField()

    class Meta(BaseSerializer.Meta):
        model = DirectUploadSession
        fields = "__all__"
        read_only_fields = (
            "upload_id",
            "storage_key",
            "chunk_count",
            "status",
            "checksum_sha256",
            "completed_raw_file",
        )

    def get_upload_urls(self, obj):
        signer = TimestampSigner(salt="direct-upload")
        base_url = settings.OBJECT_STORAGE_UPLOAD_BASE_URL.rstrip("/")
        urls = []
        for index in range(obj.chunk_count):
            part_number = index + 1
            start = index * obj.chunk_size_bytes
            end = min(start + obj.chunk_size_bytes, obj.size_bytes)
            signature = signer.sign(f"{obj.upload_id}:{part_number}:{obj.storage_key}")
            query = urlencode(
                {
                    "upload_id": obj.upload_id,
                    "part_number": part_number,
                    "expires_in": settings.OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS,
                    "signature": signature,
                }
            )
            urls.append(
                {
                    "part_number": part_number,
                    "start": start,
                    "end": end,
                    "method": "PUT",
                    "url": f"{base_url}/{quote(obj.storage_key)}?{query}",
                    "headers": {"Content-Type": obj.content_type or "application/octet-stream"},
                }
            )
        return urls


class AcquisitionWorklistSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = AcquisitionWorklist


class WorklistEntrySerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = WorklistEntry


class ProcessingPipelineSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProcessingPipeline


class ProcessingNodeSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProcessingNode


class ProcessingJobSerializer(BaseSerializer):
    node_name = serializers.CharField(source="node.name", read_only=True)
    project_id = serializers.IntegerField(source="run.sample.experiment.project_id", read_only=True)
    project_code = serializers.CharField(source="run.sample.experiment.project.code", read_only=True)
    run_name = serializers.CharField(source="run.run_name", read_only=True)
    raw_file_filename = serializers.CharField(source="raw_file.filename", read_only=True)
    pipeline_name = serializers.CharField(source="pipeline.name", read_only=True)
    pipeline_version = serializers.CharField(source="pipeline.version", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = ProcessingJob
        fields = "__all__"


class ProcessingJobArtifactSerializer(BaseSerializer):
    job_status = serializers.CharField(source="job.status", read_only=True)
    raw_file_filename = serializers.CharField(source="job.raw_file.filename", read_only=True)
    run_name = serializers.CharField(source="job.run.run_name", read_only=True)
    project_id = serializers.IntegerField(source="job.run.sample.experiment.project_id", read_only=True)
    project_code = serializers.CharField(source="job.run.sample.experiment.project.code", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = ProcessingJobArtifact
        fields = "__all__"


class QcOverviewSerializer(serializers.Serializer):
    program = serializers.CharField()
    configured = serializers.BooleanField()
    qc_injection_count = serializers.IntegerField()
    complete_pair_count = serializers.IntegerField()
    out_of_spec_pair_count = serializers.IntegerField()
    missing_raw_file_count = serializers.IntegerField()
    latest_completed_at = serializers.DateTimeField(allow_null=True)
    pair_status_counts = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    empty_message = serializers.CharField(allow_blank=True)


class QcDetailsSerializer(serializers.Serializer):
    program = serializers.CharField()
    configured = serializers.BooleanField()
    thresholds = serializers.DictField()
    empty_message = serializers.CharField(allow_blank=True)
    pairs = serializers.ListField(child=serializers.DictField(), allow_empty=True)


class ProteinSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Protein


class PeptideSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = Peptide


class ProteinIdentificationSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProteinIdentification


class PeptideIdentificationSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = PeptideIdentification


class ProteinQuantSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProteinQuant


class PeptideQuantSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = PeptideQuant


def _boolish(value) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _filename_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return token.upper() or "MSCONNECT"


def _ensure_dict(value, *, field_name: str) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError({field_name: "Expected an object."})
    return value


REFERENCE_PRESETS = {
    "human": {
        "label": "Human",
        "fasta_path": "/data/reference/managed/2026Q3/human.fasta",
        "speclib_path": "/data/reference/managed/2026Q3/human.speclib",
    },
    "yeast": {
        "label": "Yeast",
        "fasta_path": "/data/reference/managed/2026Q3/yeast.fasta",
        "speclib_path": "/data/reference/managed/2026Q3/yeast.speclib",
    },
    "ecoli": {
        "label": "E. coli",
        "fasta_path": "/data/reference/managed/2026Q3/ecoli.fasta",
        "speclib_path": "/data/reference/managed/2026Q3/ecoli.speclib",
    },
}


def _normalize_organisms(value) -> list[str]:
    organisms = value or ["human", "yeast", "ecoli"]
    normalized = []
    for organism in organisms:
        token = str(organism).strip().lower().replace(" ", "_")
        if token in {"e_coli", "escherichia_coli"}:
            token = "ecoli"
        if token and token not in normalized:
            normalized.append(token)
    invalid = [organism for organism in normalized if organism not in REFERENCE_PRESETS]
    if invalid:
        raise ValidationError({"organisms": f"Unsupported organism preset(s): {', '.join(invalid)}."})
    return normalized or ["human"]


def _resolve_reference_assets(data: dict) -> dict:
    organisms = _normalize_organisms(data.get("organisms"))
    preset_version = "2026Q3"
    fasta_upload = (data.get("fasta_upload_name") or "").strip()
    speclib_upload = (data.get("speclib_upload_name") or "").strip()

    fasta_path = data.get("fasta_path", "")
    speclib_path = data.get("speclib_path", "")
    if not fasta_path:
        fasta_path = (
            f"/data/reference/uploads/{_filename_token(fasta_upload)}.fasta"
            if fasta_upload
            else f"/data/reference/managed/{preset_version}/{'_'.join(organisms)}.fasta"
        )
    if not speclib_path:
        speclib_path = (
            f"/data/reference/uploads/{_filename_token(speclib_upload)}.speclib"
            if speclib_upload
            else f"/data/reference/managed/{preset_version}/{'_'.join(organisms)}.speclib"
        )

    return {
        "organisms": organisms,
        "preset_version": preset_version,
        "refresh_policy": "quarterly",
        "fasta_path": fasta_path,
        "speclib_path": speclib_path,
        "uploads": {
            "fasta": fasta_upload,
            "speclib": speclib_upload,
        },
        "components": [REFERENCE_PRESETS[organism] for organism in organisms],
    }


def _normalize_sample_rows(rows: list[dict]) -> list[dict]:
    normalized_rows = []
    for index, row in enumerate(rows, start=1):
        lowered = {str(key).strip().lower(): value for key, value in row.items()}
        sample_id = (
            lowered.get("sample_id")
            or lowered.get("sample id")
            or lowered.get("sample")
            or lowered.get("id")
            or lowered.get("name")
        )
        condition = lowered.get("condition") or lowered.get("group") or lowered.get("status") or "sample"
        if not sample_id:
            raise ValidationError({"sample_rows": f"Row {index} is missing sample_id."})

        canonical = {
            "sample_id": str(sample_id).strip(),
            "condition": str(condition).strip().lower() or "sample",
            "well": str(lowered.get("well") or "").strip().upper(),
            "plate_id": str(lowered.get("plate") or lowered.get("plate_id") or "Plate 1").strip(),
            "metadata": {str(key): value for key, value in row.items()},
        }
        if not canonical["sample_id"]:
            raise ValidationError({"sample_rows": f"Row {index} has an empty sample_id."})
        normalized_rows.append(canonical)
    return normalized_rows


def _condition_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        condition = row["condition"]
        counts[condition] = counts.get(condition, 0) + 1
    return counts


def _well_for_position(position: int, plate_type: str) -> str:
    rows = "ABCDEFGHIJKLMNOP" if plate_type == "384" else "ABCDEFGH"
    columns = 24 if plate_type == "384" else 12
    zero_based = position - 1
    return f"{rows[(zero_based // columns) % len(rows)]}{(zero_based % columns) + 1:02d}"


def _well_coordinates(well: str) -> dict:
    match = re.fullmatch(r"([A-Z]+)(\d+)", well.strip().upper())
    if not match:
        return {"well": well, "row": "", "column": None}
    return {"well": well, "row": match.group(1), "column": int(match.group(2))}


def _resolve_results_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    results_root = Path(settings.RESULTS_ROOT).resolve()
    candidate = Path(path_value).resolve()
    if not candidate.is_relative_to(results_root):
        raise ValidationError({"path": "Artifact path must remain under RESULTS_ROOT."})
    if not candidate.exists():
        raise ValidationError({"path": f"Artifact path does not exist: {candidate}"})
    if not candidate.is_file():
        raise ValidationError({"path": f"Artifact path must point to a file: {candidate}"})
    return candidate


def _managed_storage_roots() -> tuple[Path, ...]:
    return (
        Path(settings.RESULTS_ROOT).resolve(),
        Path(settings.RAW_FILE_STORAGE_ROOT).resolve(),
        Path(settings.MEDIA_ROOT).resolve(),
    )


def _resolve_managed_read_path(path_value: str) -> Path:
    candidate = Path(path_value).resolve()
    if not any(candidate.is_relative_to(root) for root in _managed_storage_roots()):
        raise ValidationError({"path": "Derivative path must remain under managed MSConnect storage."})
    if not candidate.exists():
        raise ValidationError({"path": f"Derivative path does not exist: {candidate}"})
    if not candidate.is_file():
        raise ValidationError({"path": f"Derivative path must point to a file: {candidate}"})
    return candidate


def _load_spectrum_index(raw_file: RawFile) -> tuple[RawFileDerivative | None, dict]:
    derivative = (
        raw_file.derivatives.filter(
            derivative_type__in=(RawFileDerivativeType.SPECTRUM_INDEX, RawFileDerivativeType.PREVIEW_JSON),
            status="ready",
        )
        .order_by("derivative_type", "-updated_at")
        .first()
    )
    if not derivative:
        return None, {"spectra": [], "chromatograms": {"tic": [], "bpc": []}, "metadata": {}}

    index_path = _resolve_managed_read_path(derivative.path)
    try:
        with index_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValidationError({"spectrum_index": f"Invalid spectrum index JSON: {exc}"}) from exc
    if not isinstance(payload, dict):
        raise ValidationError({"spectrum_index": "Spectrum index must be a JSON object."})
    payload.setdefault("spectra", [])
    payload.setdefault("chromatograms", {"tic": [], "bpc": []})
    payload.setdefault("metadata", {})
    return derivative, payload


def _spectrum_index_counts(index_payload: dict) -> dict[str, int]:
    spectra = index_payload.get("spectra") or []
    if not isinstance(spectra, list):
        spectra = []
    metadata = index_payload.get("metadata") or {}
    return {
        "indexed_spectra_count": _numeric_stat(metadata, "total_spectra", "indexed_spectra_count") or len(spectra),
        "indexed_ms1_spectra_count": _numeric_stat(metadata, "ms1_spectra", "indexed_ms1_spectra_count")
        or sum(1 for item in spectra if item.get("ms_level") == 1),
        "indexed_ms2_spectra_count": _numeric_stat(metadata, "ms2_spectra", "indexed_ms2_spectra_count")
        or sum(1 for item in spectra if item.get("ms_level") == 2),
    }


def _safe_spectrum_counts_for_raw_files(raw_files) -> dict[str, int]:
    totals = {
        "indexed_spectra_count": 0,
        "indexed_ms1_spectra_count": 0,
        "indexed_ms2_spectra_count": 0,
    }
    for raw_file in raw_files:
        try:
            _derivative, index_payload = _load_spectrum_index(raw_file)
        except ValidationError:
            continue
        counts = _spectrum_index_counts(index_payload)
        for key, value in counts.items():
            totals[key] += value
    return totals


def _numeric_stat(stats: dict, *keys: str) -> int:
    for key in keys:
        value = stats.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _aggregate_job_stats(jobs) -> dict[str, int]:
    totals = {
        "reported_protein_count": 0,
        "reported_peptide_count": 0,
        "reported_precursor_count": 0,
        "ms1_feature_count": 0,
        "ms2_spectra_count": 0,
    }
    for job in jobs:
        stats = job.stats or {}
        totals["reported_protein_count"] += _numeric_stat(stats, "protein_groups", "protein_count")
        totals["reported_peptide_count"] += _numeric_stat(stats, "peptides", "peptide_count")
        totals["reported_precursor_count"] += _numeric_stat(stats, "precursors", "precursor_count")
        totals["ms1_feature_count"] += _numeric_stat(stats, "ms1_features", "ms1_feature_count")
        totals["ms2_spectra_count"] += _numeric_stat(stats, "ms2_spectra", "ms2_spectra_count")
    return totals


def _spectrum_summary(item: dict) -> dict:
    return {
        "id": str(item.get("id") or item.get("scan_number") or item.get("index") or ""),
        "index": item.get("index"),
        "scan_number": item.get("scan_number"),
        "ms_level": item.get("ms_level"),
        "retention_time_seconds": item.get("retention_time_seconds"),
        "base_peak_mz": item.get("base_peak_mz"),
        "base_peak_intensity": item.get("base_peak_intensity"),
        "tic": item.get("tic"),
        "precursor_mz": item.get("precursor_mz"),
    }


def _find_spectrum(index_payload: dict, spectrum_id: str) -> dict | None:
    for item in index_payload.get("spectra", []):
        if str(item.get("id")) == spectrum_id:
            return item
        if str(item.get("scan_number")) == spectrum_id:
            return item
        if str(item.get("index")) == spectrum_id:
            return item
    return None


def _record_job_derivatives(job: ProcessingJob, derivatives_payload) -> list[RawFileDerivative]:
    if not derivatives_payload:
        return []
    if not isinstance(derivatives_payload, list):
        raise ValidationError({"derivatives": "derivatives must be a list."})

    valid_types = {value for value, _label in RawFileDerivativeType.choices}
    valid_statuses = {value for value, _label in DerivativeStatus.choices}
    records = []
    for index, item in enumerate(derivatives_payload, start=1):
        if not isinstance(item, dict):
            raise ValidationError({"derivatives": f"Derivative {index} must be an object."})
        derivative_type = str(item.get("derivative_type") or item.get("type") or "").strip()
        if derivative_type not in valid_types:
            raise ValidationError({"derivatives": f"Derivative {index} has an invalid type."})
        path = str(item.get("path") or "").strip()
        if not path:
            raise ValidationError({"derivatives": f"Derivative {index} is missing path."})
        managed_path = _resolve_managed_read_path(path)
        size_bytes = item.get("size_bytes")
        if size_bytes in ("", None):
            size_bytes = managed_path.stat().st_size

        derivative_status = str(item.get("status") or DerivativeStatus.READY)
        if derivative_status not in valid_statuses:
            raise ValidationError({"derivatives": f"Derivative {index} has an invalid status."})

        record, _created = RawFileDerivative.objects.update_or_create(
            raw_file=job.raw_file,
            derivative_type=derivative_type,
            path=str(managed_path),
            defaults={
                "status": derivative_status,
                "format": str(item.get("format") or derivative_type),
                "size_bytes": size_bytes,
                "checksum_sha256": str(item.get("checksum_sha256") or ""),
                "created_by_job": job,
                "error_message": str(item.get("error_message") or ""),
                "metadata": _ensure_dict(item.get("metadata"), field_name="derivative.metadata"),
            },
        )
        records.append(record)
    return records


def _record_job_artifacts(job: ProcessingJob, artifacts_payload) -> list[ProcessingJobArtifact]:
    if not artifacts_payload:
        return []
    if not isinstance(artifacts_payload, list):
        raise ValidationError({"artifacts": "artifacts must be a list."})

    valid_types = {value for value, _label in ProcessingArtifactType.choices}
    records = []
    for index, item in enumerate(artifacts_payload, start=1):
        if not isinstance(item, dict):
            raise ValidationError({"artifacts": f"Artifact {index} must be an object."})
        artifact_type = str(item.get("artifact_type") or item.get("type") or "").strip() or ProcessingArtifactType.OTHER
        if artifact_type not in valid_types:
            raise ValidationError({"artifacts": f"Artifact {index} has an invalid type."})
        path = str(item.get("path") or "").strip()
        if not path:
            raise ValidationError({"artifacts": f"Artifact {index} is missing path."})
        managed_path = _resolve_managed_read_path(path)
        size_bytes = item.get("size_bytes")
        if size_bytes in ("", None):
            size_bytes = managed_path.stat().st_size

        record, _created = ProcessingJobArtifact.objects.update_or_create(
            job=job,
            artifact_type=artifact_type,
            path=str(managed_path),
            defaults={
                "format": str(item.get("format") or managed_path.suffix.lstrip(".") or artifact_type),
                "size_bytes": size_bytes,
                "checksum_sha256": str(item.get("checksum_sha256") or ""),
                "retained": not _boolish(item.get("discarded")),
                "metadata": _ensure_dict(item.get("metadata"), field_name="artifact.metadata"),
            },
        )
        records.append(record)
    return records


def _auto_artifact_payloads(
    *,
    protein_table: Path | None,
    peptide_table: Path | None,
    log_path: Path | None,
) -> list[dict]:
    payloads = []
    if protein_table:
        payloads.append(
            {
                "artifact_type": ProcessingArtifactType.PROTEIN_TABLE,
                "path": str(protein_table),
                "format": "table",
            }
        )
    if peptide_table:
        payloads.append(
            {
                "artifact_type": ProcessingArtifactType.PEPTIDE_TABLE,
                "path": str(peptide_table),
                "format": "table",
            }
        )
    if log_path:
        payloads.append({"artifact_type": ProcessingArtifactType.LOG, "path": str(log_path), "format": "log"})
    return payloads


def _queue_spectra_conversion_job_for_raw_file(raw_file: RawFile) -> ProcessingJob | None:
    if not settings.MSCONNECT_AUTO_QUEUE_SPECTRA_CONVERSION or not raw_file.run_id:
        return None

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
            "metadata": {
                "queued_by": "watcher_agent",
                "purpose": "spectra_conversion",
            },
        },
    )
    return job


def _queue_processing_job_for_raw_file(raw_file: RawFile) -> ProcessingJob | None:
    if not raw_file.run_id:
        return None

    Run.objects.filter(pk=raw_file.run_id).update(status=RunStatus.IMPORTED, updated_at=timezone.now())
    if raw_file.file_role not in {RunFileRole.SAMPLE, RunFileRole.QC, RunFileRole.LIBRARY}:
        return None

    entry = (
        WorklistEntry.objects.select_related("worklist")
        .filter(run_id=raw_file.run_id)
        .order_by("id")
        .first()
    )
    if not entry:
        return None

    pipeline_id = (entry.worklist.metadata or {}).get("processing_pipeline_id")
    if not pipeline_id:
        return None
    try:
        pipeline = ProcessingPipeline.objects.get(pk=pipeline_id)
    except ProcessingPipeline.DoesNotExist:
        return None

    job, _created = ProcessingJob.objects.get_or_create(
        run_id=raw_file.run_id,
        raw_file=raw_file,
        pipeline=pipeline,
        defaults={
            "status": ProcessingStatus.QUEUED,
            "metadata": {
                "queued_by": "watcher_agent",
                "worklist_entry_id": entry.id,
                "worklist_position": entry.position,
            },
        },
    )
    return job


def _build_processing_job_agent_payload(job: ProcessingJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "metadata": job.metadata,
        "run": {
            "id": job.run_id,
            "name": job.run.run_name,
            "project_id": job.run.sample.experiment.project_id,
            "project_code": job.run.sample.experiment.project.code,
        },
        "raw_file": {
            "id": job.raw_file_id,
            "filename": job.raw_file.filename,
            "storage_path": job.raw_file.storage_path,
            "checksum_sha256": job.raw_file.checksum_sha256,
            "size_bytes": job.raw_file.size_bytes,
        },
        "pipeline": {
            "id": job.pipeline_id,
            "name": job.pipeline.name,
            "version": job.pipeline.version,
            "container_image": job.pipeline.container_image,
            "parameters": job.pipeline.parameters,
        },
        "node": {
            "id": job.node_id,
            "name": job.node.name if job.node_id else None,
        },
    }


class AgentApiView(APIView):
    authentication_classes = (AgentTokenAuthentication,)
    permission_classes = (AgentRolePermission,)
    agent_roles = ()


class AgentHeartbeatView(AgentApiView):
    agent_roles = ("watcher", "processor")

    def post(self, request):
        name = (request.data.get("name") or settings.MSCONNECT_AGENT_NAME or "").strip()
        if not name:
            raise ValidationError({"name": "Agent name is required."})

        node_type = (request.data.get("node_type") or getattr(request.user, "agent_role", "")).strip()
        if node_type != getattr(request.user, "agent_role", ""):
            raise ValidationError({"node_type": "node_type must match the authenticated agent role."})

        status_value = (request.data.get("status") or ProcessingNodeStatus.IDLE).strip()
        valid_statuses = {value for value, _label in ProcessingNodeStatus.choices}
        if status_value not in valid_statuses:
            raise ValidationError({"status": "Invalid processing node status."})

        node, _created = ProcessingNode.objects.update_or_create(
            name=name,
            defaults={
                "node_type": node_type,
                "status": status_value,
                "container_image": (request.data.get("container_image") or settings.MSCONNECT_IMAGE).strip(),
                "endpoint_url": (request.data.get("endpoint_url") or "").strip(),
                "last_heartbeat_at": timezone.now(),
                "settings": _ensure_dict(request.data.get("settings"), field_name="settings"),
                "metadata": _ensure_dict(request.data.get("metadata"), field_name="metadata"),
            },
        )
        return Response(ProcessingNodeSerializer(node).data, status=status.HTTP_200_OK)


class AgentRawFileImportView(AgentApiView):
    agent_roles = ("watcher",)

    def post(self, request):
        filename = PurePath(str(request.data.get("filename") or "")).name
        if not filename:
            raise ValidationError({"filename": "Filename is required."})

        source_path = str(request.data.get("source_path") or "").strip()
        storage_path = str(request.data.get("storage_path") or "").strip()
        checksum = str(request.data.get("checksum_sha256") or "").strip()
        if len(checksum) != 64:
            raise ValidationError({"checksum_sha256": "A 64-character SHA-256 checksum is required."})
        if not source_path:
            raise ValidationError({"source_path": "Source path is required."})
        if not storage_path:
            raise ValidationError({"storage_path": "Storage path is required."})

        try:
            size_bytes = int(request.data.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"size_bytes": "A positive size_bytes value is required."}) from exc
        if size_bytes <= 0:
            raise ValidationError({"size_bytes": "A positive size_bytes value is required."})

        storage_candidate = Path(storage_path).resolve()
        storage_root = Path(settings.RAW_FILE_STORAGE_ROOT).resolve()
        if not storage_candidate.is_relative_to(storage_root):
            raise ValidationError({"storage_path": "Storage path must remain under RAW_FILE_STORAGE_ROOT."})
        if not storage_candidate.exists():
            raise ValidationError({"storage_path": f"Storage path does not exist: {storage_candidate}"})

        file_role = request.data.get("file_role") or RunFileRole.SAMPLE
        if file_role not in {value for value, _label in RunFileRole.choices}:
            raise ValidationError({"file_role": "Invalid file role."})

        existing = RawFile.objects.filter(checksum_sha256=checksum).first()
        if existing:
            return Response(
                {"created": False, "raw_file": RawFileSerializer(existing).data},
                status=status.HTTP_200_OK,
            )

        run = None
        run_id = request.data.get("run_id") or request.data.get("run")
        if run_id:
            try:
                run = Run.objects.get(pk=run_id)
            except Run.DoesNotExist as exc:
                raise ValidationError({"run_id": "Run does not exist."}) from exc
        elif _boolish(request.data.get("match_run_by_name")):
            run = find_run_for_path(Path(filename))
        if run:
            file_role = run.file_role

        metadata = _ensure_dict(request.data.get("metadata"), field_name="metadata")
        metadata.setdefault("importer", "watcher_agent")
        metadata.setdefault("filename_metadata", parse_filename_metadata(Path(filename)))

        with transaction.atomic():
            raw_file = RawFile.objects.create(
                run=run,
                source_path=source_path,
                storage_path=str(storage_candidate),
                filename=filename,
                checksum_sha256=checksum,
                size_bytes=size_bytes,
                imported_at=timezone.now(),
                status=RawFileStatus.IMPORTED,
                file_role=file_role,
                match_confidence=1.0 if run else 0.0,
                metadata=metadata,
            )
            _queue_spectra_conversion_job_for_raw_file(raw_file)
            processing_job = _queue_processing_job_for_raw_file(raw_file)
        return Response(
            {
                "created": True,
                "raw_file": RawFileSerializer(raw_file).data,
                "processing_job": ProcessingJobSerializer(processing_job).data if processing_job else None,
            },
            status=status.HTTP_201_CREATED,
        )


class AgentIngestionFailureView(AgentApiView):
    agent_roles = ("watcher",)

    def post(self, request):
        source_path = str(request.data.get("source_path") or "").strip()
        failure_reason = str(request.data.get("failure_reason") or "").strip()
        if not source_path:
            raise ValidationError({"source_path": "Source path is required."})
        if not failure_reason:
            raise ValidationError({"failure_reason": "failure_reason is required."})

        failure = record_ingestion_failure(
            Path(source_path),
            failure_reason,
            metadata=_ensure_dict(request.data.get("metadata"), field_name="metadata"),
        )
        return Response(
            {
                "id": failure.id,
                "filename": failure.filename,
                "source_path": failure.source_path,
                "seen_count": failure.seen_count,
                "failure_reason": failure.failure_reason,
            },
            status=status.HTTP_200_OK,
        )


class ProcessingJobClaimView(AgentApiView):
    agent_roles = ("processor",)

    def post(self, request):
        node = self._resolve_node(request)

        for candidate_status in (ProcessingStatus.QUEUED, ProcessingStatus.RETRYING):
            candidate_ids = list(
                ProcessingJob.objects.filter(status=candidate_status)
                .order_by("created_at", "id")
                .values_list("id", flat=True)[:20]
            )
            for candidate_id in candidate_ids:
                with transaction.atomic():
                    updated = ProcessingJob.objects.filter(id=candidate_id, status=candidate_status).update(
                        status=ProcessingStatus.ASSIGNED,
                        node_id=node.id,
                        started_at=None,
                        error_message="",
                        finished_at=None,
                    )
                    if not updated:
                        continue
                    job = (
                        ProcessingJob.objects.select_related(
                            "run",
                            "run__sample",
                            "run__sample__experiment",
                            "run__sample__experiment__project",
                            "pipeline",
                            "raw_file",
                            "node",
                        )
                        .get(pk=candidate_id)
                    )
                    node.status = ProcessingNodeStatus.BUSY
                    node.last_heartbeat_at = timezone.now()
                    node.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
                    return Response(_build_processing_job_agent_payload(job), status=status.HTTP_200_OK)

        node.status = ProcessingNodeStatus.IDLE
        node.last_heartbeat_at = timezone.now()
        node.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _resolve_node(self, request):
        node_name = str(request.data.get("node_name") or settings.MSCONNECT_AGENT_NAME or "").strip()
        if not node_name:
            raise ValidationError({"node_name": "node_name is required."})

        node, _created = ProcessingNode.objects.get_or_create(
            name=node_name,
            defaults={
                "node_type": "processor",
                "status": ProcessingNodeStatus.IDLE,
                "container_image": settings.MSCONNECT_IMAGE,
                "last_heartbeat_at": timezone.now(),
            },
        )
        if node.node_type != "processor":
            raise ValidationError({"node_name": "node_name belongs to a non-processor node."})
        return node


class ProcessingJobStartView(AgentApiView):
    agent_roles = ("processor",)

    def post(self, request, pk):
        job = self._get_job(pk)
        node = self._resolve_assigned_node(request, job)
        if job.status != ProcessingStatus.ASSIGNED:
            raise ValidationError({"status": "Only assigned jobs can be started."})

        job.status = ProcessingStatus.RUNNING
        job.started_at = timezone.now()
        job.finished_at = None
        job.error_message = ""
        job.save(update_fields=["status", "started_at", "finished_at", "error_message", "updated_at"])

        node.status = ProcessingNodeStatus.BUSY
        node.last_heartbeat_at = timezone.now()
        node.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
        return Response(ProcessingJobSerializer(job).data, status=status.HTTP_200_OK)

    def _get_job(self, pk):
        return get_object_or_404(ProcessingJob.objects.select_related("node"), pk=pk)

    def _resolve_assigned_node(self, request, job):
        node_name = str(request.data.get("node_name") or settings.MSCONNECT_AGENT_NAME or "").strip()
        if not node_name:
            raise ValidationError({"node_name": "node_name is required."})
        if not job.node_id or job.node.name != node_name:
            raise PermissionDenied("This job is not assigned to the provided processor node.")
        return job.node


class ProcessingJobCompleteView(ProcessingJobStartView):
    def post(self, request, pk):
        job = (
            get_object_or_404(
                ProcessingJob.objects.select_related("node", "run", "raw_file", "pipeline"),
                pk=pk,
            )
        )
        node = self._resolve_assigned_node(request, job)
        if job.status not in {ProcessingStatus.ASSIGNED, ProcessingStatus.RUNNING}:
            raise ValidationError({"status": "Only assigned or running jobs can be completed."})

        protein_table = _resolve_results_path(request.data.get("protein_table_path"))
        peptide_table = _resolve_results_path(request.data.get("peptide_table_path"))
        log_path = _resolve_results_path(request.data.get("log_path"))
        delimiter = request.data.get("delimiter") or None

        result_summary = None
        if protein_table or peptide_table:
            try:
                result_summary = import_result_tables(
                    job=job,
                    protein_table=protein_table,
                    peptide_table=peptide_table,
                    delimiter=delimiter,
                )
            except ResultTableImportError as exc:
                raise ValidationError({"result_files": str(exc)}) from exc

        metadata = dict(job.metadata or {})
        if result_summary:
            metadata["result_import"] = result_summary
        if protein_table or peptide_table:
            metadata["result_files"] = {
                "protein_table_path": str(protein_table) if protein_table else "",
                "peptide_table_path": str(peptide_table) if peptide_table else "",
                "delimiter": delimiter or "",
            }
        stats_payload = _ensure_dict(request.data.get("stats"), field_name="stats")
        stats_payload = {**(job.stats or {}), **stats_payload}
        if result_summary:
            stats_payload.setdefault("protein_quant_count", result_summary.get("protein_quant_rows", 0))
            stats_payload.setdefault("protein_identification_count", result_summary.get("protein_ident_rows", 0))
            stats_payload.setdefault("peptide_quant_count", result_summary.get("peptide_quant_rows", 0))
            stats_payload.setdefault("peptide_identification_count", result_summary.get("peptide_ident_rows", 0))

        derivative_records = _record_job_derivatives(job, request.data.get("derivatives"))
        if derivative_records:
            metadata["derivatives"] = [
                {
                    "id": derivative.id,
                    "derivative_type": derivative.derivative_type,
                    "path": derivative.path,
                    "status": derivative.status,
                }
                for derivative in derivative_records
            ]
            for derivative in derivative_records:
                if derivative.derivative_type not in {
                    RawFileDerivativeType.SPECTRUM_INDEX,
                    RawFileDerivativeType.PREVIEW_JSON,
                }:
                    continue
                try:
                    with _resolve_managed_read_path(derivative.path).open("r", encoding="utf-8") as handle:
                        index_payload = json.load(handle)
                except (json.JSONDecodeError, OSError, ValidationError):
                    continue
                for key, value in _spectrum_index_counts(index_payload).items():
                    stats_payload.setdefault(key, value)

        explicit_artifacts = request.data.get("artifacts") or []
        artifact_records = _record_job_artifacts(
            job,
            _auto_artifact_payloads(protein_table=protein_table, peptide_table=peptide_table, log_path=log_path)
            + explicit_artifacts,
        )
        if artifact_records:
            metadata["artifacts"] = [
                {
                    "id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "path": artifact.path,
                    "retained": artifact.retained,
                }
                for artifact in artifact_records
            ]

        job.status = ProcessingStatus.COMPLETE
        job.finished_at = timezone.now()
        job.log_path = str(log_path) if log_path else job.log_path
        job.error_message = ""
        job.stats = stats_payload
        job.metadata = metadata
        job.save(
            update_fields=[
                "status",
                "finished_at",
                "log_path",
                "error_message",
                "stats",
                "metadata",
                "updated_at",
            ]
        )

        job.raw_file.status = RawFileStatus.PROCESSED
        job.raw_file.save(update_fields=["status", "updated_at"])
        job.run.status = "processed"
        job.run.save(update_fields=["status", "updated_at"])

        node.status = ProcessingNodeStatus.IDLE
        node.last_heartbeat_at = timezone.now()
        node.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
        return Response(ProcessingJobSerializer(job).data, status=status.HTTP_200_OK)


class ProcessingJobFailView(ProcessingJobStartView):
    def post(self, request, pk):
        job = get_object_or_404(ProcessingJob.objects.select_related("node"), pk=pk)
        node = self._resolve_assigned_node(request, job)
        if job.status not in {ProcessingStatus.ASSIGNED, ProcessingStatus.RUNNING, ProcessingStatus.RETRYING}:
            raise ValidationError({"status": "Only active processor jobs can be failed."})

        error_message = str(request.data.get("error_message") or "").strip()
        if not error_message:
            raise ValidationError({"error_message": "error_message is required."})

        log_path = _resolve_results_path(request.data.get("log_path"))
        job.status = ProcessingStatus.FAILED
        job.finished_at = timezone.now()
        job.error_message = error_message
        if log_path:
            job.log_path = str(log_path)
        job.save(update_fields=["status", "finished_at", "error_message", "log_path", "updated_at"])

        node.status = (
            ProcessingNodeStatus.ERROR if _boolish(request.data.get("node_error")) else ProcessingNodeStatus.IDLE
        )
        node.last_heartbeat_at = timezone.now()
        node.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
        return Response(ProcessingJobSerializer(job).data, status=status.HTTP_200_OK)


class AuthenticatedModelViewSet(viewsets.ModelViewSet):
    permission_classes = (RoleScopedWritePermission,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    pagination_class = OptionalPageNumberPagination
    search_fields = ()
    ordering_fields = ("id", "created_at", "updated_at")
    ordering = ("id",)
    scope_lab_lookup = None
    write_scope_lab_path = None
    write_scope_facility_path = None
    write_requires_admin = False

    def get_queryset(self):
        base_queryset = super().get_queryset()
        user = self.request.user

        if is_admin(user):
            return base_queryset

        if self.scope_lab_lookup is None:
            return base_queryset

        lab_ids = active_lab_ids(user)
        if not lab_ids:
            return base_queryset.none()

        return base_queryset.filter(**{f"{self.scope_lab_lookup}__in": lab_ids}).distinct()

    def perform_create(self, serializer):
        self._enforce_write_scope(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._enforce_write_scope(serializer)
        serializer.save()

    def _enforce_write_scope(self, serializer):
        user = self.request.user
        if is_admin(user):
            return

        lab_ids = set(active_lab_ids(user))
        if not lab_ids:
            raise PermissionDenied("You are not a member of any active lab.")

        if self.write_scope_lab_path:
            target_lab_id = self._resolve_scope_pk(serializer, self.write_scope_lab_path)
            if target_lab_id is None or target_lab_id not in lab_ids:
                raise PermissionDenied("This write targets a lab outside your membership scope.")

        if self.write_scope_facility_path:
            target_facility_id = self._resolve_scope_pk(serializer, self.write_scope_facility_path)
            if target_facility_id is None:
                raise PermissionDenied("Could not resolve target facility for this write.")
            has_facility_access = Lab.objects.filter(
                id__in=lab_ids,
                facility_id=target_facility_id,
                active=True,
            ).exists()
            if not has_facility_access:
                raise PermissionDenied("This write targets a facility outside your membership scope.")

    def _resolve_scope_pk(self, serializer, field_path):
        parts = field_path.split(".")
        current_obj = serializer.instance
        current_data = serializer.validated_data

        value = None
        for part in parts:
            if isinstance(current_data, dict) and part in current_data:
                value = current_data[part]
            elif current_obj is not None:
                value = getattr(current_obj, part, None)
            else:
                value = None

            if value is None:
                return None

            current_obj = value if hasattr(value, "__dict__") else None
            current_data = value if isinstance(value, dict) else None

        if hasattr(value, "pk"):
            return value.pk
        if isinstance(value, int):
            return value
        return None


class QcApiMixin:
    qc_programs = {"hye", "prtc"}
    hye_ideal = {
        "Homo sapiens": {"a": 0.65, "b": 0.65},
        "Saccharomyces cerevisiae": {"a": 0.30, "b": 0.15},
        "Escherichia coli": {"a": 0.05, "b": 0.20},
    }
    pass_relative_error = 0.20
    warning_relative_error = 0.50

    def scoped_worklists(self):
        queryset = AcquisitionWorklist.objects.select_related("experiment", "experiment__project").prefetch_related(
            Prefetch(
                "entries",
                queryset=WorklistEntry.objects.select_related("run", "run__sample").order_by("position"),
            )
        )

        if not is_admin(self.request.user):
            lab_ids = active_lab_ids(self.request.user)
            if not lab_ids:
                return queryset.none()
            queryset = queryset.filter(experiment__project__lab_id__in=lab_ids)

        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(experiment__project_id=project_filter)

        worklist_filter = self.request.query_params.get("worklist")
        if worklist_filter:
            queryset = queryset.filter(id=worklist_filter)

        return queryset.order_by("experiment__project__code", "name")

    def requested_program(self):
        program = (self.request.query_params.get("program") or "hye").lower()
        if program not in self.qc_programs:
            raise ValidationError({"program": f"Unsupported QC program '{program}'."})
        return program

    def build_response(self):
        program = self.requested_program()
        if program == "prtc":
            return self.prtc_payload()
        return self.hye_payload()

    def prtc_payload(self):
        empty_message = (
            "PRTC spiked-in standards are scaffolded in the QC workspace "
            "but no tagged PRTC dataset is available yet."
        )
        return {
            "overview": {
                "program": "prtc",
                "configured": False,
                "qc_injection_count": 0,
                "complete_pair_count": 0,
                "out_of_spec_pair_count": 0,
                "missing_raw_file_count": 0,
                "latest_completed_at": None,
                "pair_status_counts": [],
                "empty_message": empty_message,
            },
            "details": {
                "program": "prtc",
                "configured": False,
                "thresholds": {
                    "pass_relative_error": self.pass_relative_error,
                    "warning_relative_error": self.warning_relative_error,
                },
                "empty_message": empty_message,
                "pairs": [],
            },
        }

    def hye_payload(self):
        worklists = list(self.scoped_worklists())
        qc_entries = []
        for worklist in worklists:
            for entry in worklist.entries.all():
                if entry.file_role == RunFileRole.QC:
                    qc_entries.append(entry)

        run_ids = [entry.run_id for entry in qc_entries]
        raw_files = RawFile.objects.filter(run_id__in=run_ids).select_related("run")
        raw_files_by_run = {}
        for raw_file in raw_files.order_by("run_id", "-imported_at", "filename"):
            raw_files_by_run.setdefault(raw_file.run_id, raw_file)

        complete_jobs_queryset = ProcessingJob.objects.filter(
            run_id__in=run_ids,
            status=ProcessingStatus.COMPLETE,
        ).select_related(
            "run",
            "raw_file",
            "pipeline",
            "run__sample",
            "run__sample__experiment",
            "run__sample__experiment__project",
        )
        complete_jobs = {job.run_id: job for job in complete_jobs_queryset}
        quant_job_ids = [job.id for job in complete_jobs.values()]
        quants = ProteinQuant.objects.filter(job_id__in=quant_job_ids).select_related("protein")
        quant_map = {}
        for quant in quants:
            organisms = quant_map.setdefault(quant.job_id, {})
            accessions = organisms.setdefault(quant.protein.organism, {})
            accessions[quant.protein.accession] = quant.value

        pairs = []
        status_counts = {}
        complete_pair_count = 0
        out_of_spec_pair_count = 0

        for worklist in worklists:
            labels = []
            seen_labels = set()
            for entry in worklist.entries.all():
                if (
                    entry.file_role == RunFileRole.QC
                    and entry.hye_pair_label
                    and entry.hye_pair_label not in seen_labels
                ):
                    labels.append(entry.hye_pair_label)
                    seen_labels.add(entry.hye_pair_label)

            entries_by_label = {}
            for entry in worklist.entries.all():
                if entry.file_role != RunFileRole.QC or not entry.hye_pair_label:
                    continue
                label_entries = entries_by_label.setdefault(entry.hye_pair_label, {})
                label_entries[entry.run.sample.name] = entry

            for label in labels:
                pair_entries = entries_by_label.get(label, {})
                a_entry = pair_entries.get("HYE-A")
                b_entry = pair_entries.get("HYE-B")
                a_job = complete_jobs.get(a_entry.run_id) if a_entry else None
                b_job = complete_jobs.get(b_entry.run_id) if b_entry else None
                completed_at = max(
                    [dt for dt in [getattr(a_job, "finished_at", None), getattr(b_job, "finished_at", None)] if dt],
                    default=None,
                )

                organism_rows = []
                pair_state = "pass"
                pair_complete = bool(a_job and b_job)
                shared_total_n = 0

                for organism, target in self.hye_ideal.items():
                    a_values = quant_map.get(getattr(a_job, "id", None), {}).get(organism, {})
                    b_values = quant_map.get(getattr(b_job, "id", None), {}).get(organism, {})
                    shared_accessions = sorted(set(a_values).intersection(b_values))
                    a_log2 = [
                        math.log2(a_values[accession]) for accession in shared_accessions if a_values[accession] > 0
                    ]
                    b_log2 = [
                        math.log2(b_values[accession]) for accession in shared_accessions if b_values[accession] > 0
                    ]
                    median_a = round(median(a_log2), 2) if a_log2 else None
                    median_b = round(median(b_log2), 2) if b_log2 else None
                    observed_ratio = (
                        round(2 ** (median_b - median_a), 2)
                        if median_a is not None and median_b is not None
                        else None
                    )
                    ideal_ratio = round(target["b"] / target["a"], 2)
                    deviation = (
                        round(abs(observed_ratio - ideal_ratio) / ideal_ratio, 2)
                        if observed_ratio is not None and ideal_ratio
                        else None
                    )
                    row_status = "incomplete"
                    if deviation is not None:
                        if deviation <= self.pass_relative_error:
                            row_status = "pass"
                        elif deviation <= self.warning_relative_error:
                            row_status = "warning"
                        else:
                            row_status = "failed"
                    elif pair_complete:
                        row_status = "warning"

                    if row_status == "failed":
                        pair_state = "failed"
                    elif row_status in {"warning", "incomplete"} and pair_state != "failed":
                        pair_state = "warning"
                    if observed_ratio is None:
                        pair_complete = False

                    shared_n = len(shared_accessions)
                    shared_total_n += shared_n
                    organism_rows.append(
                        {
                            "organism": organism,
                            "shared_n": shared_n,
                            "median_log2_a": median_a,
                            "median_log2_b": median_b,
                            "observed_ratio": observed_ratio,
                            "ideal_a": target["a"],
                            "ideal_b": target["b"],
                            "ideal_ratio": ideal_ratio,
                            "relative_error": deviation,
                            "status": row_status,
                        }
                    )

                if pair_complete:
                    complete_pair_count += 1
                if pair_state != "pass":
                    out_of_spec_pair_count += 1
                status_counts[pair_state] = status_counts.get(pair_state, 0) + 1

                project = worklist.experiment.project
                a_raw_file = raw_files_by_run.get(a_entry.run_id) if a_entry else None
                b_raw_file = raw_files_by_run.get(b_entry.run_id) if b_entry else None
                pairs.append(
                    {
                        "project_id": project.id,
                        "project_code": project.code,
                        "worklist_id": worklist.id,
                        "worklist_name": worklist.name,
                        "pair_label": label,
                        "status": pair_state,
                        "shared_total_n": shared_total_n,
                        "completed_at": completed_at,
                        "a_run_id": a_entry.run_id if a_entry else None,
                        "b_run_id": b_entry.run_id if b_entry else None,
                        "a_run_name": a_entry.run.run_name if a_entry else "",
                        "b_run_name": b_entry.run.run_name if b_entry else "",
                        "a_filename": a_job.raw_file.filename if a_job else (a_raw_file.filename if a_raw_file else ""),
                        "b_filename": b_job.raw_file.filename if b_job else (b_raw_file.filename if b_raw_file else ""),
                        "organisms": organism_rows,
                    }
                )

        latest_completed_at = max((pair["completed_at"] for pair in pairs if pair["completed_at"]), default=None)
        missing_raw_file_count = sum(1 for entry in qc_entries if entry.run_id not in raw_files_by_run)

        pairs.sort(key=lambda pair: (pair["project_code"], pair["worklist_name"], pair["pair_label"]))
        return {
            "overview": {
                "program": "hye",
                "configured": True,
                "qc_injection_count": len(qc_entries),
                "complete_pair_count": complete_pair_count,
                "out_of_spec_pair_count": out_of_spec_pair_count,
                "missing_raw_file_count": missing_raw_file_count,
                "latest_completed_at": latest_completed_at,
                "pair_status_counts": [
                    {"status": status, "count": count} for status, count in sorted(status_counts.items())
                ],
                "empty_message": "" if pairs else "Seed or acquire HYE A/B QC runs inside a project worklist.",
            },
            "details": {
                "program": "hye",
                "configured": True,
                "thresholds": {
                    "pass_relative_error": self.pass_relative_error,
                    "warning_relative_error": self.warning_relative_error,
                },
                "empty_message": "" if pairs else "Seed or acquire HYE A/B QC runs inside a project worklist.",
                "pairs": pairs,
            },
        }


class QcOverviewView(QcApiMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        serializer = QcOverviewSerializer(data=self.build_response()["overview"])
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class QcDetailsView(QcApiMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        serializer = QcDetailsSerializer(data=self.build_response()["details"])
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class UniversityViewSet(AuthenticatedModelViewSet):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    scope_lab_lookup = "facilities__labs__id"
    search_fields = ("name", "abbreviation", "website")
    ordering_fields = ("name", "abbreviation", "created_at", "updated_at")


class FacilityViewSet(AuthenticatedModelViewSet):
    queryset = Facility.objects.select_related("university")
    serializer_class = FacilitySerializer
    scope_lab_lookup = "labs__id"
    search_fields = ("name", "slug", "contact_email", "university__name")
    ordering_fields = ("name", "slug", "created_at", "updated_at")


class LabViewSet(AuthenticatedModelViewSet):
    queryset = Lab.objects.select_related("facility", "pi")
    serializer_class = LabSerializer
    scope_lab_lookup = "id"
    write_scope_facility_path = "facility"
    search_fields = ("name", "slug", "billing_code", "facility__name", "pi__username")
    ordering_fields = ("name", "slug", "created_at", "updated_at")


class UserProfileViewSet(AuthenticatedModelViewSet):
    queryset = UserProfile.objects.select_related("user")
    serializer_class = UserProfileSerializer
    write_requires_admin = True

    def get_queryset(self):
        base_queryset = super().get_queryset()
        if is_admin(self.request.user):
            return base_queryset
        return base_queryset.filter(user=self.request.user)


class LabMembershipViewSet(AuthenticatedModelViewSet):
    queryset = LabMembership.objects.select_related("user", "lab")
    serializer_class = LabMembershipSerializer
    scope_lab_lookup = "lab_id"
    write_scope_lab_path = "lab"


class InstrumentViewSet(AuthenticatedModelViewSet):
    queryset = Instrument.objects.select_related("facility")
    serializer_class = InstrumentSerializer
    scope_lab_lookup = "facility__labs__id"
    write_scope_facility_path = "facility"
    search_fields = ("nickname", "manufacturer", "model", "serial_number", "facility__name")
    ordering_fields = ("nickname", "instrument_type", "manufacturer", "model", "created_at", "updated_at")


class InstrumentConfigurationViewSet(AuthenticatedModelViewSet):
    queryset = InstrumentConfiguration.objects.select_related("facility", "lc_instrument", "ms_instrument")
    serializer_class = InstrumentConfigurationSerializer
    scope_lab_lookup = "facility__labs__id"
    write_scope_facility_path = "facility"
    search_fields = ("name", "method_name", "column_description", "ion_source", "facility__name")
    ordering_fields = ("name", "method_name", "created_at", "updated_at")


class ProjectViewSet(AuthenticatedModelViewSet):
    queryset = Project.objects.select_related("lab", "pi")
    serializer_class = ProjectSerializer
    scope_lab_lookup = "lab_id"
    write_scope_lab_path = "lab"
    search_fields = ("code", "title", "description", "lab__name", "pi__username")
    ordering_fields = ("code", "title", "status", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        lab_filter = self.request.query_params.get("lab")
        if lab_filter:
            queryset = queryset.filter(lab_id=lab_filter)
        return queryset

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        project = self.get_object()
        experiments = Experiment.objects.filter(project=project)
        samples = Sample.objects.filter(experiment__project=project)
        runs = Run.objects.filter(sample__experiment__project=project)
        raw_files = RawFile.objects.filter(run__sample__experiment__project=project).prefetch_related("derivatives")
        jobs = ProcessingJob.objects.filter(run__sample__experiment__project=project)
        worklists = AcquisitionWorklist.objects.filter(experiment__project=project)
        raw_file_count = raw_files.count()
        jobs_for_stats = list(jobs)
        raw_files_for_stats = list(raw_files)
        job_stats = _aggregate_job_stats(jobs_for_stats)
        spectrum_counts = _safe_spectrum_counts_for_raw_files(raw_files_for_stats)

        expected_raw_file_count = WorklistEntry.objects.filter(worklist__experiment__project=project).count()

        return Response(
            {
                "project_id": project.id,
                "project_code": project.code,
                "experiment_count": experiments.count(),
                "sample_count": samples.count(),
                "run_count": runs.count(),
                "acquisition_worklist_count": worklists.count(),
                "raw_file_count": raw_file_count,
                "processing_job_count": jobs.count(),
                "missing_raw_file_count": max(expected_raw_file_count - raw_file_count, 0),
                "protein_quant_count": ProteinQuant.objects.filter(job__in=jobs_for_stats).count(),
                "protein_identification_count": ProteinIdentification.objects.filter(job__in=jobs_for_stats).count(),
                "peptide_quant_count": PeptideQuant.objects.filter(job__in=jobs_for_stats).count(),
                "peptide_identification_count": PeptideIdentification.objects.filter(job__in=jobs_for_stats).count(),
                "artifact_count": ProcessingJobArtifact.objects.filter(job__in=jobs_for_stats).count(),
                "derivative_count": RawFileDerivative.objects.filter(raw_file__in=raw_files_for_stats).count(),
                **job_stats,
                **spectrum_counts,
                "raw_files_by_status": list(raw_files.values("status").annotate(count=Count("id")).order_by("status")),
                "raw_files_by_role": list(
                    raw_files.values("file_role").annotate(count=Count("id")).order_by("file_role")
                ),
                "jobs_by_status": list(jobs.values("status").annotate(count=Count("id")).order_by("status")),
                "worklists_by_status": list(worklists.values("status").annotate(count=Count("id")).order_by("status")),
            }
        )

    @action(detail=False, methods=["post"], url_path="pre-acquisition-setup")
    def pre_acquisition_setup(self, request):
        serializer = ProjectPreAcquisitionSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lab = data.get("lab") or self._default_lab_for_user(request.user)
        if lab is None:
            raise ValidationError({"lab": "No lab was provided and no active lab membership was found."})
        if not is_admin(request.user) and lab.id not in set(active_lab_ids(request.user)):
            raise PermissionDenied("This project targets a lab outside your membership scope.")

        configuration = data.get("instrument_configuration")
        if configuration and configuration.facility_id != lab.facility_id:
            raise ValidationError(
                {"instrument_configuration": "Configuration must belong to the selected lab facility."}
            )

        with transaction.atomic():
            project = Project.objects.create(
                lab=lab,
                title=data["title"],
                code=data["code"],
                pi=getattr(lab, "pi", None) or request.user,
                description=(
                    "Pre-acquisition project generated from MSConnect setup. "
                    "Expected filenames are available before LC-MS acquisition."
                ),
            )
            experiment = Experiment.objects.create(
                project=project,
                name=data["experiment_name"],
                created_by=request.user,
                metadata={
                    "setup_source": "pre_acquisition_setup",
                    "healthy_count": data["healthy_count"],
                    "diseased_count": data["diseased_count"],
                    "sample_metadata_mode": "sample_rows" if data["sample_rows"] else "counts",
                    "plate_type": data["plate_type"],
                },
            )
            pipeline = self._create_or_update_diann_pipeline(data)
            worklist = AcquisitionWorklist.objects.create(
                experiment=experiment,
                name=data["worklist_name"],
                configuration=configuration,
                status=WorklistStatus.READY,
                generated_by=request.user,
                notes="Generated before acquisition so watcher agents can match expected raw filenames.",
                metadata={
                    "setup_source": "pre_acquisition_setup",
                    "processing_pipeline_id": pipeline.id,
                    "processing_plan": pipeline.parameters,
                    "hye_interval": data["hye_interval"],
                    "plate_type": data["plate_type"],
                    "watcher_matching": "expected_filename",
                    "export_targets": ["thermo_ms_sequence", "lc_injection_sequence"],
                    "reference_assets": pipeline.parameters.get("reference_assets", {}),
                },
            )
            samples, runs, entries = self._build_pre_acquisition_entries(
                request=request,
                project=project,
                experiment=experiment,
                worklist=worklist,
                configuration=configuration,
                data=data,
            )

        return Response(
            {
                "project": ProjectSerializer(project).data,
                "experiment": ExperimentSerializer(experiment).data,
                "worklist": AcquisitionWorklistSerializer(worklist).data,
                "pipeline": ProcessingPipelineSerializer(pipeline).data,
                "samples_created": len(samples),
                "runs_created": len(runs),
                "worklist_entries_created": len(entries),
                "expected_filenames": [entry.expected_filename for entry in entries],
            },
            status=status.HTTP_201_CREATED,
        )

    def _default_lab_for_user(self, user):
        membership = LabMembership.objects.select_related("lab").filter(user=user, active=True).order_by("id").first()
        if membership:
            return membership.lab
        if is_admin(user):
            return Lab.objects.order_by("id").first()
        return None

    def _create_or_update_diann_pipeline(self, data):
        reference_assets = _resolve_reference_assets(data)
        parameters = {
            "engine": "diann",
            "command": [
                sys.executable,
                "manage.py",
                "seed_demo_showcase",
                "--write-job-results",
                "{job_id}",
                "{results_dir}",
            ],
            "working_dir": str(settings.BASE_DIR),
            "result_files": {
                "protein_table": "proteins.csv",
                "peptide_table": "peptides.csv",
                "delimiter": ",",
            },
            "fasta_path": reference_assets["fasta_path"],
            "speclib_path": reference_assets["speclib_path"],
            "reference_assets": reference_assets,
            "processing_preset": data.get("processing_preset", "Standard DIA-NN plasma"),
            "settings": data.get("diann_settings") or {},
            "project_level_rollup": {
                "enabled": True,
                "mode": "combine_runs_after_run_level_processing",
                "future_executor": "supercomputer",
            },
        }
        pipeline, _created = ProcessingPipeline.objects.update_or_create(
            name="DIA-NN",
            version=data["diann_version"],
            defaults={
                "container_image": "ghcr.io/rtklab-byu/msconnect-diann:latest",
                "parameters": parameters,
            },
        )
        return pipeline

    def _build_pre_acquisition_entries(self, *, request, project, experiment, worklist, configuration, data):
        if data["sample_rows"]:
            sample_defs = data["sample_rows"]
        else:
            sample_defs = [
                {
                    "sample_id": f"{condition.upper()}-{index:03d}",
                    "condition": condition,
                    "well": "",
                    "plate_id": "Plate 1",
                    "metadata": {"condition": condition},
                }
                for condition, count in (("healthy", data["healthy_count"]), ("diseased", data["diseased_count"]))
                for index in range(1, count + 1)
            ]
            sample_defs.sort(key=lambda item: (item["sample_id"].split("-")[-1], item["condition"]))

        sample_lookup = {}
        for index, sample_def in enumerate(sample_defs, start=1):
            condition = sample_def["condition"]
            sample_name = sample_def["sample_id"]
            well = sample_def["well"] or _well_for_position(index, data["plate_type"])
            well_metadata = _well_coordinates(well)
            sample_lookup[sample_name] = Sample.objects.create(
                experiment=experiment,
                name=sample_name,
                external_id=f"{project.code}-{sample_name}",
                species="Homo sapiens",
                matrix="plasma",
                digestion_protocol="trypsin",
                enrichment_protocol="none",
                submitted_by=request.user,
                metadata={
                    **sample_def["metadata"],
                    "condition": condition,
                    "setup_source": "pre_acquisition_setup",
                    "plate_type": data["plate_type"],
                    "plate_id": sample_def["plate_id"] or "Plate 1",
                    **well_metadata,
                },
            )

        hye_samples = {
            "HYE-A": Sample.objects.create(
                experiment=experiment,
                name="HYE-A",
                external_id=f"{project.code}-HYE-A",
                species="Homo sapiens / S. cerevisiae / E. coli",
                matrix="qc mixture",
                submitted_by=request.user,
                metadata={"qc_material": "hye", "pseudo_project_key": "hye", "mix": "A"},
            ),
            "HYE-B": Sample.objects.create(
                experiment=experiment,
                name="HYE-B",
                external_id=f"{project.code}-HYE-B",
                species="Homo sapiens / S. cerevisiae / E. coli",
                matrix="qc mixture",
                submitted_by=request.user,
                metadata={"qc_material": "hye", "pseudo_project_key": "hye", "mix": "B"},
            ),
        }

        ordered_names = list(sample_lookup)
        runs = []
        entries = []
        position = 0
        pair_index = 0

        def add_entry(sample, role=RunFileRole.SAMPLE, hye_pair_label=""):
            nonlocal position
            position += 1
            sample_well = sample.metadata.get("well") or _well_for_position(position, data["plate_type"])
            well_metadata = _well_coordinates(str(sample_well))
            expected_filename = f"{_filename_token(project.code)}_{position:03d}_{_filename_token(sample.name)}.raw"
            run = Run.objects.create(
                sample=sample,
                configuration=configuration,
                run_name=f"{project.code}-{position:03d}-{sample.name}",
                status=RunStatus.PLANNED,
                file_role=role,
                expected_filename=expected_filename,
                worklist_position=position,
                hye_pair_label=hye_pair_label,
                metadata={
                    "setup_source": "pre_acquisition_setup",
                    "expected_filename": expected_filename,
                    "plate_type": data["plate_type"],
                    **well_metadata,
                },
            )
            entry = WorklistEntry.objects.create(
                worklist=worklist,
                run=run,
                position=position,
                file_role=role,
                expected_filename=expected_filename,
                hye_pair_label=hye_pair_label,
                block_label=f"Block {math.ceil(position / 24)}",
                metadata={
                    "setup_source": "pre_acquisition_setup",
                    "sample_name": sample.name,
                    "sample_external_id": sample.external_id,
                    "condition": sample.metadata.get("condition", ""),
                    "qc_material": sample.metadata.get("qc_material", ""),
                    "watcher_match_key": expected_filename,
                    "plate_type": data["plate_type"],
                    "plate_id": sample.metadata.get("plate_id", "Plate 1"),
                    **well_metadata,
                },
            )
            runs.append(run)
            entries.append(entry)

        for index, sample_name in enumerate(ordered_names, start=1):
            add_entry(sample_lookup[sample_name])
            if data["hye_interval"] and index % data["hye_interval"] == 0:
                pair_index += 1
                label = f"HYE-{pair_index:02d}"
                add_entry(hye_samples["HYE-A"], role=RunFileRole.QC, hye_pair_label=label)
                add_entry(hye_samples["HYE-B"], role=RunFileRole.QC, hye_pair_label=label)

        return list(sample_lookup.values()) + list(hye_samples.values()), runs, entries


class ProjectIntakeRequestViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectIntakeRequestSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    pagination_class = OptionalPageNumberPagination
    search_fields = ("requested_title", "requested_code", "objective", "lab__name", "submitted_by__username")

    def get_queryset(self):
        base_queryset = ProjectIntakeRequest.objects.select_related(
            "lab",
            "submitted_by",
            "reviewed_by",
            "promoted_project",
        )

        user = self.request.user
        if is_admin(user):
            queryset = base_queryset
        else:
            lab_ids = active_lab_ids(user)
            if not lab_ids:
                return base_queryset.none()
            queryset = base_queryset.filter(lab_id__in=lab_ids)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        lab_filter = self.request.query_params.get("lab")
        if lab_filter:
            queryset = queryset.filter(lab_id=lab_filter)

        submitter_filter = self.request.query_params.get("submitter")
        if submitter_filter:
            queryset = queryset.filter(submitted_by_id=submitter_filter)

        start_date = self.request.query_params.get("start_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)

        end_date = self.request.query_params.get("end_date")
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        ordering = self.request.query_params.get("ordering", "-updated_at")
        allowed_ordering = {
            "updated_at",
            "-updated_at",
            "created_at",
            "-created_at",
            "requested_title",
            "-requested_title",
        }
        if ordering not in allowed_ordering:
            ordering = "-updated_at"

        return queryset.order_by(ordering, "-id")

    def get_serializer_class(self):
        if self.action == "list":
            return ProjectIntakeQueueSerializer
        return ProjectIntakeRequestSerializer

    def perform_create(self, serializer):
        user = self.request.user
        lab = serializer.validated_data["lab"]
        self._enforce_lab_scope(user=user, lab_id=lab.id)
        serializer.save(submitted_by=user)

    def perform_update(self, serializer):
        user = self.request.user
        intake = self.get_object()
        target_lab = serializer.validated_data.get("lab", intake.lab)
        self._enforce_lab_scope(user=user, lab_id=target_lab.id)

        if is_admin(user):
            serializer.save()
            return

        if intake.submitted_by_id != user.id:
            raise PermissionDenied("Only the submitter or an admin can edit this intake request.")
        if intake.status != IntakeRequestStatus.SUBMITTED:
            raise PermissionDenied("Submitted requests can only be edited while in submitted state.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if is_admin(user) or (instance.submitted_by_id == user.id and instance.status == IntakeRequestStatus.SUBMITTED):
            instance.delete()
            return
        raise PermissionDenied("Only the submitter can delete submitted requests.")

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        intake = self.get_object()
        self._enforce_review_permission(user=request.user, lab_id=intake.lab_id)

        new_status = request.data.get("status")
        note = request.data.get("review_note", "")
        if new_status not in (
            IntakeRequestStatus.IN_REVIEW,
            IntakeRequestStatus.APPROVED,
            IntakeRequestStatus.REJECTED,
        ):
            raise ValidationError({"status": "Status must be one of in_review, approved, rejected."})

        intake.transition_to(new_status=new_status, reviewer=request.user, note=note)
        serializer = self.get_serializer(intake)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def promote(self, request, pk=None):
        intake = self.get_object()
        self._enforce_review_permission(user=request.user, lab_id=intake.lab_id)
        project = intake.promote_to_project()
        intake.refresh_from_db()
        return Response(
            {
                "intake_request": self.get_serializer(intake).data,
                "project_id": project.id,
                "project_code": project.code,
            },
            status=status.HTTP_200_OK,
        )

    def _enforce_lab_scope(self, *, user, lab_id: int):
        if is_admin(user):
            return
        if lab_id not in set(active_lab_ids(user)):
            raise PermissionDenied("This action targets a lab outside your membership scope.")

    def _enforce_review_permission(self, *, user, lab_id: int):
        if is_admin(user):
            return
        if lab_id not in set(active_lab_ids(user)):
            raise PermissionDenied("You do not have access to this intake request's lab.")
        is_lab_pi = LabMembership.objects.filter(
            user=user,
            lab_id=lab_id,
            active=True,
            role=UserRole.PI,
        ).exists() or Lab.objects.filter(id=lab_id, pi=user).exists()
        if not is_lab_pi and user_role(user) != UserRole.PI:
            raise PermissionDenied("Only PI or admin users can review intake requests.")


class ExperimentViewSet(AuthenticatedModelViewSet):
    queryset = Experiment.objects.select_related("project", "created_by")
    serializer_class = ExperimentSerializer
    scope_lab_lookup = "project__lab_id"
    write_scope_lab_path = "project.lab"
    search_fields = ("name", "hypothesis", "project__code", "project__title")
    ordering_fields = ("name", "started_on", "ended_on", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(project_id=project_filter)
        return queryset


class SampleViewSet(AuthenticatedModelViewSet):
    queryset = Sample.objects.select_related("experiment", "submitted_by")
    serializer_class = SampleSerializer
    scope_lab_lookup = "experiment__project__lab_id"
    write_scope_lab_path = "experiment.project.lab"
    search_fields = ("name", "external_id", "species", "matrix", "digestion_protocol", "experiment__name")
    ordering_fields = ("name", "external_id", "species", "matrix", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(experiment__project_id=project_filter)
        experiment_filter = self.request.query_params.get("experiment")
        if experiment_filter:
            queryset = queryset.filter(experiment_id=experiment_filter)
        return queryset


class RunViewSet(AuthenticatedModelViewSet):
    queryset = Run.objects.select_related("sample", "configuration", "acquired_by")
    serializer_class = RunSerializer
    scope_lab_lookup = "sample__experiment__project__lab_id"
    write_scope_lab_path = "sample.experiment.project.lab"
    search_fields = ("run_name", "expected_filename", "hye_pair_label", "sample__name", "sample__external_id")
    ordering_fields = (
        "run_name",
        "status",
        "file_role",
        "worklist_position",
        "acquisition_started_at",
        "acquisition_ended_at",
        "created_at",
        "updated_at",
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(sample__experiment__project_id=project_filter)
        sample_filter = self.request.query_params.get("sample")
        if sample_filter:
            queryset = queryset.filter(sample_id=sample_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        file_role_filter = self.request.query_params.get("file_role")
        if file_role_filter:
            queryset = queryset.filter(file_role=file_role_filter)
        return queryset

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        run = self.get_object()
        raw_files = list(run.raw_files.prefetch_related("derivatives").order_by("-imported_at", "filename"))
        jobs = list(
            run.processing_jobs.select_related("pipeline", "raw_file", "node").prefetch_related("artifacts").order_by(
                "-created_at"
            )
        )
        job_ids = [job.id for job in jobs]
        job_stats = _aggregate_job_stats(jobs)
        spectrum_counts = _safe_spectrum_counts_for_raw_files(raw_files)
        artifacts = ProcessingJobArtifact.objects.filter(job_id__in=job_ids).select_related(
            "job",
            "job__run",
            "job__raw_file",
            "job__run__sample",
            "job__run__sample__experiment",
            "job__run__sample__experiment__project",
        )
        derivatives = RawFileDerivative.objects.filter(raw_file__in=raw_files).select_related(
            "raw_file",
            "raw_file__run",
            "raw_file__run__sample",
            "raw_file__run__sample__experiment",
            "raw_file__run__sample__experiment__project",
            "created_by_job",
        )

        return Response(
            {
                "run": RunSerializer(run).data,
                "sample": SampleSerializer(run.sample).data,
                "raw_files": RawFileSerializer(raw_files, many=True).data,
                "processing_jobs": ProcessingJobSerializer(jobs, many=True).data,
                "derivatives": RawFileDerivativeSerializer(derivatives, many=True).data,
                "artifacts": ProcessingJobArtifactSerializer(artifacts, many=True).data,
                "stats": {
                    "raw_file_count": len(raw_files),
                    "processing_job_count": len(jobs),
                    "protein_quant_count": ProteinQuant.objects.filter(job_id__in=job_ids).count(),
                    "protein_identification_count": ProteinIdentification.objects.filter(job_id__in=job_ids).count(),
                    "peptide_quant_count": PeptideQuant.objects.filter(job_id__in=job_ids).count(),
                    "peptide_identification_count": PeptideIdentification.objects.filter(job_id__in=job_ids).count(),
                    "artifact_count": artifacts.count(),
                    "derivative_count": derivatives.count(),
                    **job_stats,
                    **spectrum_counts,
                },
            }
        )


class RawFileViewSet(AuthenticatedModelViewSet):
    queryset = RawFile.objects.select_related("run")
    serializer_class = RawFileSerializer
    scope_lab_lookup = "run__sample__experiment__project__lab_id"
    write_scope_lab_path = "run.sample.experiment.project.lab"
    search_fields = ("filename", "source_path", "storage_path", "checksum_sha256", "failure_reason", "run__run_name")
    ordering_fields = (
        "filename",
        "status",
        "file_role",
        "size_bytes",
        "acquired_at",
        "imported_at",
        "created_at",
        "updated_at",
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(run__sample__experiment__project_id=project_filter)
        run_filter = self.request.query_params.get("run")
        if run_filter:
            queryset = queryset.filter(run_id=run_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        file_role_filter = self.request.query_params.get("file_role")
        if file_role_filter:
            queryset = queryset.filter(file_role=file_role_filter)
        unmatched = self.request.query_params.get("unmatched")
        if unmatched in {"1", "true", "True"}:
            queryset = queryset.filter(run__isnull=True)
        return queryset

    @action(detail=False, methods=["get"])
    def overview(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            {
                "total": queryset.count(),
                "by_status": list(queryset.values("status").annotate(count=Count("id")).order_by("status")),
                "by_role": list(queryset.values("file_role").annotate(count=Count("id")).order_by("file_role")),
                "unmatched": queryset.filter(run__isnull=True).count(),
            }
        )

    @action(detail=True, methods=["get"])
    def derivatives(self, request, pk=None):
        raw_file = self.get_object()
        queryset = raw_file.derivatives.order_by("derivative_type", "-updated_at")
        return Response(RawFileDerivativeSerializer(queryset, many=True).data)

    @action(detail=True, methods=["get"])
    def spectra(self, request, pk=None):
        raw_file = self.get_object()
        derivative, index_payload = _load_spectrum_index(raw_file)
        spectra = index_payload.get("spectra", [])
        ms_level = request.query_params.get("ms_level")
        if ms_level:
            try:
                ms_level_value = int(ms_level)
            except ValueError as exc:
                raise ValidationError({"ms_level": "ms_level must be an integer."}) from exc
            spectra = [item for item in spectra if item.get("ms_level") == ms_level_value]
        limit = min(int(request.query_params.get("limit") or 200), 1000)
        return Response(
            {
                "raw_file": RawFileSerializer(raw_file).data,
                "index_derivative": RawFileDerivativeSerializer(derivative).data if derivative else None,
                "count": len(spectra),
                "spectra": [_spectrum_summary(item) for item in spectra[:limit]],
            }
        )

    @action(detail=True, methods=["get"], url_path=r"spectra/(?P<spectrum_id>[^/.]+)")
    def spectrum(self, request, pk=None, spectrum_id=None):
        raw_file = self.get_object()
        derivative, index_payload = _load_spectrum_index(raw_file)
        item = _find_spectrum(index_payload, str(spectrum_id or ""))
        if not item:
            raise ValidationError({"spectrum_id": "Spectrum was not found in the available index."})
        return Response(
            {
                "raw_file": RawFileSerializer(raw_file).data,
                "index_derivative": RawFileDerivativeSerializer(derivative).data if derivative else None,
                "spectrum": item,
            }
        )

    @action(detail=True, methods=["get"])
    def chromatograms(self, request, pk=None):
        raw_file = self.get_object()
        derivative, index_payload = _load_spectrum_index(raw_file)
        return Response(
            {
                "raw_file": RawFileSerializer(raw_file).data,
                "index_derivative": RawFileDerivativeSerializer(derivative).data if derivative else None,
                "chromatograms": index_payload.get("chromatograms", {"tic": [], "bpc": []}),
            }
        )


class DirectUploadSessionViewSet(AuthenticatedModelViewSet):
    queryset = DirectUploadSession.objects.select_related("project", "run", "completed_raw_file")
    serializer_class = DirectUploadSessionSerializer
    scope_lab_lookup = "project__lab_id"
    write_scope_lab_path = "project.lab"
    search_fields = ("filename", "storage_key", "checksum_sha256", "project__code", "run__run_name")
    ordering_fields = ("filename", "status", "size_bytes", "created_at", "updated_at")

    def create(self, request, *args, **kwargs):
        project_id = request.data.get("project")
        if not project_id:
            raise ValidationError({"project": "Project is required for a direct upload session."})

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist as exc:
            raise ValidationError({"project": "Project does not exist."}) from exc

        if not is_admin(request.user) and project.lab_id not in set(active_lab_ids(request.user)):
            raise PermissionDenied("This upload targets a project outside your lab scope.")

        filename = PurePath(str(request.data.get("filename", ""))).name
        if not filename:
            raise ValidationError({"filename": "Filename is required."})

        try:
            size_bytes = int(request.data.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"size_bytes": "A positive size_bytes value is required."}) from exc
        if size_bytes <= 0:
            raise ValidationError({"size_bytes": "A positive size_bytes value is required."})

        run_id = request.data.get("run") or None
        if run_id and not Run.objects.filter(pk=run_id, sample__experiment__project=project).exists():
            raise ValidationError({"run": "Run must belong to the selected project."})

        file_role = request.data.get("file_role") or RunFileRole.SAMPLE
        if file_role not in {value for value, _label in RunFileRole.choices}:
            raise ValidationError({"file_role": "Invalid file role."})

        chunk_size_bytes = int(request.data.get("chunk_size_bytes") or 8 * 1024 * 1024)
        chunk_count = max(1, math.ceil(size_bytes / chunk_size_bytes))
        upload_id = uuid.uuid4()
        session = DirectUploadSession.objects.create(
            project=project,
            run_id=run_id,
            upload_id=upload_id,
            filename=filename,
            storage_key=f"projects/{project.code}/uploads/{timezone.now():%Y%m%d}/{upload_id}/{filename}",
            content_type=request.data.get("content_type", ""),
            size_bytes=size_bytes,
            chunk_size_bytes=chunk_size_bytes,
            chunk_count=chunk_count,
            file_role=file_role,
            status=DirectUploadStatus.CREATED,
            metadata=request.data.get("metadata") or {},
        )
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        session = self.get_object()
        checksum = request.data.get("checksum_sha256", "")
        if len(checksum) != 64:
            raise ValidationError({"checksum_sha256": "A 64-character SHA-256 checksum is required."})

        if session.completed_raw_file_id:
            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_200_OK)

        raw_file = RawFile.objects.create(
            run=session.run,
            source_path=f"direct-upload:{session.upload_id}",
            storage_path=session.storage_key,
            filename=session.filename,
            checksum_sha256=checksum,
            size_bytes=session.size_bytes,
            imported_at=timezone.now(),
            status=RawFileStatus.IMPORTED,
            file_role=session.file_role,
            match_confidence=1.0 if session.run_id else 0.0,
            metadata={
                "direct_upload_session": session.id,
                "object_storage_key": session.storage_key,
                **session.metadata,
            },
        )
        with transaction.atomic():
            _queue_spectra_conversion_job_for_raw_file(raw_file)
            _queue_processing_job_for_raw_file(raw_file)
        session.checksum_sha256 = checksum
        session.completed_raw_file = raw_file
        session.status = DirectUploadStatus.COMPLETE
        session.save(update_fields=["checksum_sha256", "completed_raw_file", "status", "updated_at"])
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RawFileDerivativeViewSet(AuthenticatedModelViewSet):
    queryset = RawFileDerivative.objects.select_related(
        "raw_file",
        "raw_file__run",
        "raw_file__run__sample",
        "raw_file__run__sample__experiment",
        "raw_file__run__sample__experiment__project",
        "created_by_job",
    )
    serializer_class = RawFileDerivativeSerializer
    scope_lab_lookup = "raw_file__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "raw_file.run.sample.experiment.project.lab"
    search_fields = ("raw_file__filename", "path", "checksum_sha256", "format")
    ordering_fields = ("derivative_type", "status", "format", "size_bytes", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        raw_file_filter = self.request.query_params.get("raw_file")
        if raw_file_filter:
            queryset = queryset.filter(raw_file_id=raw_file_filter)
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(raw_file__run__sample__experiment__project_id=project_filter)
        derivative_type_filter = self.request.query_params.get("derivative_type")
        if derivative_type_filter:
            queryset = queryset.filter(derivative_type=derivative_type_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class ProcessingJobArtifactViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingJobArtifact.objects.select_related(
        "job",
        "job__run",
        "job__raw_file",
        "job__run__sample",
        "job__run__sample__experiment",
        "job__run__sample__experiment__project",
    )
    serializer_class = ProcessingJobArtifactSerializer
    scope_lab_lookup = "job__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "job.run.sample.experiment.project.lab"
    search_fields = ("job__run__run_name", "job__raw_file__filename", "path", "checksum_sha256", "format")
    ordering_fields = ("artifact_type", "format", "size_bytes", "retained", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        job_filter = self.request.query_params.get("job")
        if job_filter:
            queryset = queryset.filter(job_id=job_filter)
        raw_file_filter = self.request.query_params.get("raw_file")
        if raw_file_filter:
            queryset = queryset.filter(job__raw_file_id=raw_file_filter)
        run_filter = self.request.query_params.get("run")
        if run_filter:
            queryset = queryset.filter(job__run_id=run_filter)
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(job__run__sample__experiment__project_id=project_filter)
        artifact_type_filter = self.request.query_params.get("artifact_type")
        if artifact_type_filter:
            queryset = queryset.filter(artifact_type=artifact_type_filter)
        retained_filter = self.request.query_params.get("retained")
        if retained_filter in {"1", "true", "True"}:
            queryset = queryset.filter(retained=True)
        elif retained_filter in {"0", "false", "False"}:
            queryset = queryset.filter(retained=False)
        return queryset


class AcquisitionWorklistViewSet(AuthenticatedModelViewSet):
    queryset = AcquisitionWorklist.objects.select_related("experiment", "configuration", "generated_by")
    serializer_class = AcquisitionWorklistSerializer
    scope_lab_lookup = "experiment__project__lab_id"
    write_scope_lab_path = "experiment.project.lab"
    search_fields = ("name", "notes", "experiment__name", "experiment__project__code")
    ordering_fields = ("name", "status", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(experiment__project_id=project_filter)
        experiment_filter = self.request.query_params.get("experiment")
        if experiment_filter:
            queryset = queryset.filter(experiment_id=experiment_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class WorklistEntryViewSet(AuthenticatedModelViewSet):
    queryset = WorklistEntry.objects.select_related("worklist", "run", "run__sample")
    serializer_class = WorklistEntrySerializer
    scope_lab_lookup = "worklist__experiment__project__lab_id"
    write_scope_lab_path = "worklist.experiment.project.lab"
    search_fields = (
        "expected_filename",
        "hye_pair_label",
        "block_label",
        "notes",
        "run__run_name",
        "run__sample__name",
    )
    ordering_fields = ("position", "file_role", "expected_filename", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(worklist__experiment__project_id=project_filter)
        worklist_filter = self.request.query_params.get("worklist")
        if worklist_filter:
            queryset = queryset.filter(worklist_id=worklist_filter)
        file_role_filter = self.request.query_params.get("file_role")
        if file_role_filter:
            queryset = queryset.filter(file_role=file_role_filter)
        return queryset


class ProcessingPipelineViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingPipeline.objects.all()
    serializer_class = ProcessingPipelineSerializer
    write_requires_admin = True
    search_fields = ("name", "version", "container_image")
    ordering_fields = ("name", "version", "created_at", "updated_at")


class ProcessingNodeViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingNode.objects.all()
    serializer_class = ProcessingNodeSerializer
    write_requires_admin = True
    search_fields = ("name", "node_type", "container_image", "endpoint_url")
    ordering_fields = ("name", "node_type", "status", "last_heartbeat_at", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        node_type_filter = self.request.query_params.get("node_type")
        if node_type_filter:
            queryset = queryset.filter(node_type=node_type_filter)
        return queryset

    @action(detail=False, methods=["get"])
    def overview(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            {
                "total": queryset.count(),
                "by_status": list(queryset.values("status").annotate(count=Count("id")).order_by("status")),
                "by_type": list(queryset.values("node_type").annotate(count=Count("id")).order_by("node_type")),
            }
        )


class ProcessingJobViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingJob.objects.select_related(
        "run",
        "run__sample",
        "run__sample__experiment",
        "run__sample__experiment__project",
        "pipeline",
        "raw_file",
        "node",
    )
    serializer_class = ProcessingJobSerializer
    scope_lab_lookup = "run__sample__experiment__project__lab_id"
    write_scope_lab_path = "run.sample.experiment.project.lab"
    search_fields = (
        "run__run_name",
        "raw_file__filename",
        "pipeline__name",
        "pipeline__version",
        "log_path",
        "error_message",
        "node__name",
    )
    ordering_fields = ("status", "started_at", "finished_at", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        project_filter = self.request.query_params.get("project")
        if project_filter:
            queryset = queryset.filter(run__sample__experiment__project_id=project_filter)
        run_filter = self.request.query_params.get("run")
        if run_filter:
            queryset = queryset.filter(run_id=run_filter)
        raw_file_filter = self.request.query_params.get("raw_file")
        if raw_file_filter:
            queryset = queryset.filter(raw_file_id=raw_file_filter)
        pipeline_filter = self.request.query_params.get("pipeline")
        if pipeline_filter:
            queryset = queryset.filter(pipeline_id=pipeline_filter)
        node_filter = self.request.query_params.get("node")
        if node_filter:
            queryset = queryset.filter(node_id=node_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        active = self.request.query_params.get("active")
        if active in {"1", "true", "True"}:
            queryset = queryset.filter(
                status__in=(
                    ProcessingStatus.QUEUED,
                    ProcessingStatus.ASSIGNED,
                    ProcessingStatus.RUNNING,
                    ProcessingStatus.RETRYING,
                )
            )
        return queryset

    @action(detail=False, methods=["get"])
    def overview(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        active_statuses = (
            ProcessingStatus.QUEUED,
            ProcessingStatus.ASSIGNED,
            ProcessingStatus.RUNNING,
            ProcessingStatus.RETRYING,
        )
        return Response(
            {
                "total": queryset.count(),
                "active": queryset.filter(status__in=active_statuses).count(),
                "failed": queryset.filter(status=ProcessingStatus.FAILED).count(),
                "by_status": list(queryset.values("status").annotate(count=Count("id")).order_by("status")),
                "by_pipeline": list(
                    queryset.values("pipeline_id", "pipeline__name", "pipeline__version")
                    .annotate(count=Count("id"))
                    .order_by("pipeline__name", "pipeline__version")
                ),
                "by_node": list(
                    queryset.values("node_id", "node__name")
                    .annotate(count=Count("id"))
                    .order_by("node__name", "node_id")
                ),
            }
        )


class ProteinViewSet(AuthenticatedModelViewSet):
    queryset = Protein.objects.all()
    serializer_class = ProteinSerializer


class PeptideViewSet(AuthenticatedModelViewSet):
    queryset = Peptide.objects.all()
    serializer_class = PeptideSerializer


class ProteinIdentificationViewSet(AuthenticatedModelViewSet):
    queryset = ProteinIdentification.objects.select_related("job", "protein")
    serializer_class = ProteinIdentificationSerializer
    scope_lab_lookup = "job__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "job.run.sample.experiment.project.lab"


class PeptideIdentificationViewSet(AuthenticatedModelViewSet):
    queryset = PeptideIdentification.objects.select_related("job", "peptide")
    serializer_class = PeptideIdentificationSerializer
    scope_lab_lookup = "job__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "job.run.sample.experiment.project.lab"


class ProteinQuantViewSet(AuthenticatedModelViewSet):
    queryset = ProteinQuant.objects.select_related("job", "protein")
    serializer_class = ProteinQuantSerializer
    scope_lab_lookup = "job__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "job.run.sample.experiment.project.lab"


class PeptideQuantViewSet(AuthenticatedModelViewSet):
    queryset = PeptideQuant.objects.select_related("job", "peptide")
    serializer_class = PeptideQuantSerializer
    scope_lab_lookup = "job__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "job.run.sample.experiment.project.lab"
