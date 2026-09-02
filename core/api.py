import hashlib
import json
import math
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path, PurePath
from statistics import mean, median, pstdev

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, pagination, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.processing.diann import (
    build_diann_command_options,
    normalize_diann_settings,
    site_performance_tags,
)
from core.processing.registry import resolve_pipeline_parameters, validate_diann_pipeline_settings
from core.services.batch_rerun import rerun_latest_diann_batch
from core.services.lifecycle import (
    recompute_experiment_and_project_status,
    record_pipeline_event,
    record_processing_completion,
    record_raw_file_import,
    record_result_files_uploaded,
)
from core.services.notifications import send_notification
from core.services.processing_routing import should_queue_spectra_conversion_for_raw_file
from ingest.result_import import ResultTableImportError, import_result_tables
from ingest.services import build_storage_path, find_run_for_path, parse_filename_metadata, record_ingestion_failure
from msconnect.health import _database_check, _path_check

from .agent_auth import AgentTokenAuthentication
from .models import (
    AcquisitionWorklist,
    AnalysisPreset,
    DeploymentRelease,
    DeploymentSetting,
    DerivativeStatus,
    DirectUploadSession,
    DirectUploadStatus,
    Experiment,
    Facility,
    FileMatchException,
    Instrument,
    InstrumentConfiguration,
    IntakeRecordStatus,
    IntakeRequestStatus,
    Lab,
    LabMembership,
    MatchExceptionStatus,
    Peptide,
    PeptideIdentification,
    PeptideQuant,
    PipelineEvent,
    PipelineEventType,
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
    QcProgram,
    RawFile,
    RawFileArchive,
    RawFileArchiveCopy,
    RawFileDerivative,
    RawFileDerivativeType,
    RawFileStatus,
    Run,
    RunFileRole,
    RunStatus,
    Sample,
    SampleManifest,
    SampleManifestRow,
    University,
    UserProfile,
    UserRole,
    WorklistEntry,
    WorklistStatus,
)
from .permissions import AgentRolePermission, RoleScopedWritePermission, active_lab_ids, is_admin, user_role

User = get_user_model()


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


class AnalysisPresetSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = AnalysisPreset


class SampleManifestRowSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = SampleManifestRow


class SampleManifestSerializer(BaseSerializer):
    analysis_preset_name = serializers.CharField(source="analysis_preset.name", read_only=True)
    row_count = serializers.IntegerField(source="rows.count", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = SampleManifest


class FileMatchExceptionSerializer(BaseSerializer):
    filename = serializers.CharField(source="raw_file.filename", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True)
    resolved_run_name = serializers.CharField(source="resolved_run.run_name", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = FileMatchException


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
    processing_preset = serializers.CharField(max_length=128, default="DIA-NN speclib build")
    fasta_upload_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    speclib_upload_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    diann_version = serializers.CharField(max_length=128, default="2.0")
    diann_settings = serializers.JSONField(required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        sample_rows = _normalize_sample_rows(attrs.get("sample_rows") or [])
        diann_settings = normalize_diann_settings(_ensure_dict(attrs.get("diann_settings"), field_name="diann_settings"))
        diann_errors = validate_diann_pipeline_settings(diann_settings, allow_performance_tags=is_admin(user))
        if diann_errors:
            raise ValidationError({"diann_settings": diann_errors})
        if sample_rows:
            attrs["sample_rows"] = sample_rows
            attrs["sample_count"] = len(sample_rows)
            condition_counts = _condition_counts(sample_rows)
            attrs["healthy_count"] = condition_counts.get("healthy", 0)
            attrs["diseased_count"] = condition_counts.get("diseased", 0)
            attrs["organisms"] = _normalize_organisms(attrs.get("organisms"))
            attrs["diann_settings"] = diann_settings
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
        attrs["diann_settings"] = diann_settings
        return attrs


class ProjectQuickStartSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=80, required=False, allow_blank=True)
    lab = serializers.PrimaryKeyRelatedField(queryset=Lab.objects.all(), required=False)


class WorklistImportRowSerializer(serializers.Serializer):
    position = serializers.IntegerField(min_value=1)
    run_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    sample_name = serializers.CharField(max_length=255)
    expected_filename = serializers.CharField(max_length=255)
    file_role = serializers.CharField(max_length=32, default=RunFileRole.SAMPLE)
    qc_program = serializers.CharField(max_length=32, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=RunStatus.choices, required=False)
    well = serializers.CharField(max_length=32, required=False, allow_blank=True)
    plate = serializers.CharField(max_length=128, required=False, allow_blank=True)
    condition = serializers.CharField(max_length=128, required=False, allow_blank=True)
    hye_pair_label = serializers.CharField(max_length=64, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.DictField(required=False)


class WorklistImportSerializer(serializers.Serializer):
    worklist_name = serializers.CharField(max_length=255, default="Imported LC-MS worklist")
    experiment_name = serializers.CharField(max_length=255, default="Default experiment")
    diann_version = serializers.CharField(max_length=128, default="2.0")
    rows = WorklistImportRowSerializer(many=True)

    def validate_rows(self, rows):
        positions = [row["position"] for row in rows]
        if len(positions) != len(set(positions)):
            raise ValidationError("Worklist positions must be unique.")
        filenames = [row["expected_filename"] for row in rows]
        if len(filenames) != len(set(filenames)):
            raise ValidationError("Expected filenames must be unique within the worklist.")
        for row in rows:
            row["file_role"] = _normalize_run_file_role(row.get("file_role"))
            row["qc_program"] = _normalize_qc_program(row.get("qc_program"), row["file_role"])
        return rows


class QueueRunsSerializer(serializers.Serializer):
    run_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class ProjectIntakeQueueSerializer(BaseSerializer):
    lab_name = serializers.CharField(source="lab.name", read_only=True)
    submitted_by_username = serializers.CharField(source="submitted_by.username", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True)
    institution_name = serializers.CharField(read_only=True)
    contact_name = serializers.CharField(read_only=True)
    contact_email = serializers.CharField(read_only=True)
    invoice_email = serializers.CharField(read_only=True)
    organism = serializers.CharField(read_only=True)
    matrix = serializers.CharField(read_only=True)
    plate_format = serializers.CharField(read_only=True)

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
            "institution_name",
            "contact_name",
            "contact_email",
            "invoice_email",
            "organism",
            "matrix",
            "plate_format",
            "updated_at",
            "reviewed_by",
            "reviewed_by_username",
            "promoted_project",
        )


class ProjectIntakeRequestSerializer(BaseSerializer):
    metadata = serializers.JSONField(required=False)

    class Meta(BaseSerializer.Meta):
        model = ProjectIntakeRequest
        read_only_fields = ("submitted_by", "reviewed_by", "reviewed_at", "promoted_project")
        fields = "__all__"

    def validate_metadata(self, value):
        return validate_intake_metadata(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        lab = attrs.get("lab")
        fallback_email = getattr(user, "email", "") or f"{getattr(user, 'username', 'msconnect')}@localhost"
        institution_name = attrs.get("institution_name") or getattr(getattr(lab, "facility", None), "name", "")
        contact_name = (
            attrs.get("contact_name")
            or getattr(user, "get_full_name", lambda: "")()
            or getattr(user, "username", "")
        )
        contact_email = attrs.get("contact_email") or fallback_email
        invoice_email = attrs.get("invoice_email") or fallback_email
        organism = attrs.get("organism") or "unspecified"
        matrix = attrs.get("matrix") or "unspecified"
        plate_format = attrs.get("plate_format") or "96"
        sample_count = attrs.get("sample_count_estimate")
        if sample_count in (None, ""):
            sample_count = 1
        try:
            sample_count = int(sample_count)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"sample_count_estimate": "sample_count_estimate must be an integer."}) from exc
        if sample_count <= 0:
            raise ValidationError({"sample_count_estimate": "sample_count_estimate must be greater than zero."})

        metadata_defaults = {
            "schema_version": INTAKE_METADATA_SCHEMA_VERSION,
            "institution": {
                "name": institution_name,
            },
            "contact": {
                "name": contact_name,
                "email": contact_email,
            },
            "sample_planning": {
                "organism": organism,
                "matrix": matrix,
                "sample_count": sample_count,
                "plate_format": plate_format,
            },
            "shipping": {
                "expectations": attrs.get("shipping_notes") or "",
            },
            "billing": {
                "invoice_email": invoice_email,
                "po_reference": "",
                "billing_address": {},
            },
            "hazards": {
                "handling_notes": attrs.get("hazards_notes") or "",
            },
            "notes": attrs.get("objective") or "",
        }
        attrs["sample_count_estimate"] = sample_count
        metadata = validate_intake_metadata(_merge_metadata(metadata_defaults, attrs.get("metadata") or {}))
        attrs["metadata"] = metadata
        attrs["institution_name"] = metadata["institution"]["name"]
        attrs["contact_name"] = metadata["contact"]["name"]
        attrs["contact_email"] = metadata["contact"]["email"]
        attrs["invoice_email"] = metadata["billing"]["invoice_email"]
        attrs["organism"] = metadata["sample_planning"]["organism"]
        attrs["matrix"] = metadata["sample_planning"]["matrix"]
        attrs["plate_format"] = metadata["sample_planning"]["plate_format"]
        attrs["sample_count_estimate"] = metadata["sample_planning"]["sample_count"]
        attrs["shipping_notes"] = metadata["shipping"].get("expectations", "")
        attrs["hazards_notes"] = metadata["hazards"].get("handling_notes", "")
        return attrs


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


class RawFileArchiveSerializer(BaseSerializer):
    raw_file_filename = serializers.CharField(source="raw_file.filename", read_only=True)
    project_id = serializers.IntegerField(source="raw_file.run.sample.experiment.project_id", read_only=True)
    project_code = serializers.CharField(source="raw_file.run.sample.experiment.project.code", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = RawFileArchive
        fields = "__all__"


class RawFileArchiveCopySerializer(BaseSerializer):
    raw_file_filename = serializers.CharField(source="archive.raw_file.filename", read_only=True)
    archive_status = serializers.CharField(source="archive.status", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = RawFileArchiveCopy
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
        urls = []
        for index in range(obj.chunk_count):
            part_number = index + 1
            start = index * obj.chunk_size_bytes
            end = min(start + obj.chunk_size_bytes, obj.size_bytes)
            urls.append(
                {
                    "part_number": part_number,
                    "start": start,
                    "end": end,
                    "method": "PUT",
                    "url": f"/api/direct-uploads/{obj.id}/chunks/{part_number}/",
                    "headers": {"Content-Type": obj.content_type or "application/octet-stream"},
                }
            )
        return urls


def _direct_upload_root() -> Path:
    return Path(settings.DIRECT_UPLOAD_STAGING_ROOT).resolve()


def _direct_upload_session_root(session: DirectUploadSession) -> Path:
    return _direct_upload_root() / str(session.upload_id)


def _direct_upload_delivery_root(session: DirectUploadSession) -> Path:
    delivery_mode = str((session.metadata or {}).get("delivery_mode") or "direct").strip().lower()
    if delivery_mode == "watcher":
        return Path(settings.INCOMING_RAW_ROOT).resolve()
    return Path(settings.RAW_FILE_STORAGE_ROOT).resolve()


def _direct_upload_chunk_path(session: DirectUploadSession, part_number: int) -> Path:
    return _direct_upload_session_root(session) / "chunks" / f"{part_number:05d}.part"


def _direct_upload_cleanup(session: DirectUploadSession) -> None:
    shutil.rmtree(_direct_upload_session_root(session), ignore_errors=True)


class AcquisitionWorklistSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = AcquisitionWorklist


class WorklistEntrySerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = WorklistEntry


class ProcessingPipelineSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProcessingPipeline


class DeploymentReleaseSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = DeploymentRelease


class PipelineEventSerializer(BaseSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    experiment_name = serializers.CharField(source="experiment.name", read_only=True)
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta(BaseSerializer.Meta):
        model = PipelineEvent
        fields = "__all__"


class DeploymentSettingsSerializer(serializers.ModelSerializer):
    metadata = serializers.JSONField(required=False)
    prtc_skyline_pipeline_name = serializers.SerializerMethodField()
    prtc_skyline_pipeline_version = serializers.SerializerMethodField()
    targeted_skyline_pipeline_name = serializers.SerializerMethodField()
    targeted_skyline_pipeline_version = serializers.SerializerMethodField()

    class Meta:
        model = DeploymentSetting
        fields = (
            "scope",
            "prtc_skyline_pipeline",
            "prtc_skyline_pipeline_name",
            "prtc_skyline_pipeline_version",
            "targeted_skyline_pipeline",
            "targeted_skyline_pipeline_name",
            "targeted_skyline_pipeline_version",
            "metadata",
            "updated_at",
        )
        read_only_fields = (
            "scope",
            "prtc_skyline_pipeline_name",
            "prtc_skyline_pipeline_version",
            "targeted_skyline_pipeline_name",
            "targeted_skyline_pipeline_version",
            "updated_at",
        )

    def get_prtc_skyline_pipeline_name(self, obj):
        pipeline = obj.prtc_skyline_pipeline
        return pipeline.name if pipeline else ""

    def get_prtc_skyline_pipeline_version(self, obj):
        pipeline = obj.prtc_skyline_pipeline
        return pipeline.version if pipeline else ""

    def get_targeted_skyline_pipeline_name(self, obj):
        pipeline = obj.targeted_skyline_pipeline
        return pipeline.name if pipeline else ""

    def get_targeted_skyline_pipeline_version(self, obj):
        pipeline = obj.targeted_skyline_pipeline
        return pipeline.version if pipeline else ""


class ProcessingNodeSerializer(BaseSerializer):
    ip_address = serializers.SerializerMethodField()
    health = serializers.SerializerMethodField()
    active_control = serializers.SerializerMethodField()
    seconds_since_heartbeat = serializers.SerializerMethodField()

    class Meta(BaseSerializer.Meta):
        model = ProcessingNode

    def get_ip_address(self, obj):
        return (obj.metadata or {}).get("ip_address") or (obj.metadata or {}).get("remote_addr") or ""

    def get_health(self, obj):
        if obj.status == ProcessingNodeStatus.ERROR:
            return "red"
        if not obj.last_heartbeat_at:
            return "red"
        age = (timezone.now() - obj.last_heartbeat_at).total_seconds()
        if age > 180:
            return "red"
        if age > 75:
            return "yellow"
        return "green"

    def get_active_control(self, obj):
        return (obj.metadata or {}).get("control") or {}

    def get_seconds_since_heartbeat(self, obj):
        if not obj.last_heartbeat_at:
            return None
        return int((timezone.now() - obj.last_heartbeat_at).total_seconds())


class ProcessingJobSerializer(BaseSerializer):
    node_name = serializers.CharField(source="node.name", read_only=True)
    project_id = serializers.IntegerField(source="run.sample.experiment.project_id", read_only=True)
    project_code = serializers.CharField(source="run.sample.experiment.project.code", read_only=True)
    run_name = serializers.CharField(source="run.run_name", read_only=True)
    raw_file_filename = serializers.CharField(source="raw_file.filename", read_only=True)
    pipeline_name = serializers.CharField(source="pipeline.name", read_only=True)
    pipeline_version = serializers.CharField(source="pipeline.version", read_only=True)
    required_engine = serializers.SerializerMethodField()
    required_engine_version = serializers.SerializerMethodField()

    class Meta(BaseSerializer.Meta):
        model = ProcessingJob
        fields = "__all__"

    def get_required_engine(self, obj):
        return _required_engine_for_job(obj)

    def get_required_engine_version(self, obj):
        return _required_engine_version_for_job(obj)


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
    runs = serializers.ListField(child=serializers.DictField(), allow_empty=True, required=False)
    machine_summaries = serializers.ListField(child=serializers.DictField(), allow_empty=True, required=False)
    machine_series = serializers.ListField(child=serializers.DictField(), allow_empty=True, required=False)


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


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _filename_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return token.upper() or "MSCONNECT"


def _ensure_dict(value, *, field_name: str) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError({field_name: "Expected an object."})
    return value


INTAKE_METADATA_SCHEMA_VERSION = "2026-08-03"


def validate_intake_metadata(value: dict | None) -> dict:
    metadata = _ensure_dict(value, field_name="metadata")
    required_sections = {
        "institution": {"name"},
        "contact": {"name", "email"},
        "sample_planning": {"organism", "matrix", "sample_count", "plate_format"},
        "billing": {"invoice_email"},
    }
    normalized = {
        "schema_version": str(metadata.get("schema_version") or INTAKE_METADATA_SCHEMA_VERSION),
        "institution": _ensure_dict(metadata.get("institution"), field_name="metadata.institution"),
        "contact": _ensure_dict(metadata.get("contact"), field_name="metadata.contact"),
        "sample_planning": _ensure_dict(metadata.get("sample_planning"), field_name="metadata.sample_planning"),
        "shipping": _ensure_dict(metadata.get("shipping"), field_name="metadata.shipping"),
        "billing": _ensure_dict(metadata.get("billing"), field_name="metadata.billing"),
        "hazards": _ensure_dict(metadata.get("hazards"), field_name="metadata.hazards"),
        "notes": str(metadata.get("notes") or "").strip(),
    }
    missing_messages = []
    for section_name, fields in required_sections.items():
        section = normalized[section_name]
        for field_name in fields:
            if not str(section.get(field_name) or "").strip():
                missing_messages.append(f"metadata.{section_name}.{field_name} is required.")
    if missing_messages:
        raise ValidationError({"metadata": missing_messages})

    sample_planning = normalized["sample_planning"]
    try:
        sample_planning["sample_count"] = int(sample_planning.get("sample_count") or 0)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"metadata": "metadata.sample_planning.sample_count must be an integer."}) from exc
    if sample_planning["sample_count"] <= 0:
        raise ValidationError({"metadata": "metadata.sample_planning.sample_count must be greater than zero."})

    sample_planning["plate_format"] = str(sample_planning.get("plate_format") or "").strip()
    if sample_planning["plate_format"] not in {"96", "384"}:
        raise ValidationError({"metadata": "metadata.sample_planning.plate_format must be 96 or 384."})

    normalized["institution"]["name"] = str(normalized["institution"].get("name") or "").strip()
    normalized["contact"]["name"] = str(normalized["contact"].get("name") or "").strip()
    normalized["contact"]["email"] = str(normalized["contact"].get("email") or "").strip().lower()
    normalized["contact"]["email"] = _validate_email(
        normalized["contact"]["email"],
        field_name="metadata.contact.email",
    )
    normalized["shipping"]["expectations"] = str(normalized["shipping"].get("expectations") or "").strip()
    normalized["billing"]["invoice_email"] = str(normalized["billing"].get("invoice_email") or "").strip().lower()
    normalized["billing"]["invoice_email"] = _validate_email(
        normalized["billing"]["invoice_email"], field_name="metadata.billing.invoice_email"
    )
    normalized["billing"]["po_reference"] = str(normalized["billing"].get("po_reference") or "").strip()
    normalized["billing"]["billing_address"] = _ensure_dict(
        normalized["billing"].get("billing_address"),
        field_name="metadata.billing.billing_address",
    )
    normalized["hazards"]["handling_notes"] = str(normalized["hazards"].get("handling_notes") or "").strip()
    return normalized


def _validate_email(value: str, *, field_name: str) -> str:
    try:
        validate_email(value)
    except DjangoValidationError as exc:
        raise ValidationError({field_name: f"{field_name} must be a valid email address."}) from exc
    return value


def _merge_metadata(defaults: dict, overrides: dict) -> dict:
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_metadata(merged[key], value)
        else:
            merged[key] = value
    return merged


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=12, write_only=True)
    lab_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    institution_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    membership_role = serializers.ChoiceField(
        choices=((UserRole.COLLABORATOR, "Collaborator"), (UserRole.PI, "PI")),
        required=False,
    )


class CurrentUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.CharField()
    is_superuser = serializers.BooleanField()
    global_role = serializers.CharField()
    email_verified_at = serializers.DateTimeField(allow_null=True, required=False)
    labs = serializers.ListField(child=serializers.DictField())
    active_lab_ids = serializers.ListField(child=serializers.IntegerField())


def _normalize_qc_program(value: str | None, file_role: str = "") -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"none", "na", "n/a"}:
        normalized = ""
    if file_role == RunFileRole.HYE:
        return QcProgram.HYE
    if file_role == RunFileRole.PRTC:
        return QcProgram.PRTC
    if normalized in {choice for choice, _label in QcProgram.choices}:
        return normalized
    return QcProgram.NONE


def _normalize_run_file_role(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "trueblank": RunFileRole.TRUE_BLANK,
        "true_blank": RunFileRole.TRUE_BLANK,
        "hye_qc": RunFileRole.HYE,
        "prtc_qc": RunFileRole.PRTC,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {choice for choice, _label in RunFileRole.choices}:
        return normalized
    return RunFileRole.SAMPLE


REFERENCE_PRESETS = {
    "human": {
        "label": "Human",
        "fasta_path": "/data/shared/reference/human.fasta",
        "speclib_path": "/data/shared/reference/human.speclib",
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

DIANN_PRESET_SPECLIB_BUILD = "DIA-NN speclib build"
DIANN_PRESET_SPECLIB_REUSE = "DIA-NN speclib reuse"
DIANN_PRESET_SMOKE = "DIA-NN smoke test"
DIANN_PRESET_LEGACY_ALIASES = {
    "Standard DIA-NN plasma": DIANN_PRESET_SPECLIB_BUILD,
    "High confidence IDs": DIANN_PRESET_SPECLIB_BUILD,
    "Fast smoke test": DIANN_PRESET_SMOKE,
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


def _diann_settings_for_preset(preset: str) -> dict:
    normalized = _normalize_diann_preset_name(preset).lower()
    if normalized == DIANN_PRESET_SMOKE.lower():
        return {
            "report": "diann-first-pass.parquet",
            "q_value": 0.01,
            "matrices": False,
            "individual_reports": False,
            "individual_mass_acc": False,
            "individual_windows": False,
            "generate_speclib": False,
            "fasta_search": False,
            "out_library": "",
        }
    if normalized == DIANN_PRESET_SPECLIB_REUSE.lower():
        return {
            "report": "diann-report.parquet",
            "q_value": 0.005,
            "matrices": True,
            "individual_reports": True,
            "individual_mass_acc": True,
            "individual_windows": True,
            "generate_speclib": False,
            "fasta_search": False,
            "out_library": "",
        }
    return {
        "report": "diann-first-pass.parquet",
        "q_value": 0.005,
        "matrices": True,
        "individual_reports": True,
        "individual_mass_acc": True,
        "individual_windows": True,
        "generate_speclib": True,
        "fasta_search": True,
        "out_library": "diann-first-pass.speclib",
    }


def _normalize_diann_preset_name(preset: str) -> str:
    canonical = str(preset or "").strip()
    return DIANN_PRESET_LEGACY_ALIASES.get(canonical, canonical) or DIANN_PRESET_SPECLIB_BUILD


def _diann_speclib_mode(preset: str) -> str:
    canonical = _normalize_diann_preset_name(preset)
    if canonical == DIANN_PRESET_SPECLIB_REUSE:
        return "reuse"
    if canonical == DIANN_PRESET_SMOKE:
        return "smoke"
    return "build"


def _diann_command_options(settings: dict) -> list[str]:
    return build_diann_command_options(settings)


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


def _float_stat(stats: dict, *keys: str) -> float | None:
    for key in keys:
        value = stats.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


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


def _queue_spectra_conversion_job_for_raw_file(
    raw_file: RawFile,
    *,
    processing_job: ProcessingJob | None = None,
) -> ProcessingJob | None:
    if not should_queue_spectra_conversion_for_raw_file(raw_file, processing_job=processing_job):
        return None
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
    processable_roles = {
        RunFileRole.SAMPLE,
        RunFileRole.QC,
        RunFileRole.HYE,
        RunFileRole.PRTC,
        RunFileRole.LIBRARY,
    }
    if raw_file.file_role not in processable_roles:
        return None

    prtc_pipeline = _prtc_skyline_pipeline_for_raw_file(raw_file)
    if prtc_pipeline:
        job, _created = ProcessingJob.objects.get_or_create(
            run_id=raw_file.run_id,
            raw_file=raw_file,
            pipeline=prtc_pipeline,
            defaults={
                "status": ProcessingStatus.QUEUED,
                "metadata": {
                    "queued_by": "watcher_agent",
                    "routing": "prtc_skyline",
                    "required_engine": _required_engine_for_pipeline(prtc_pipeline),
                },
            },
        )
        return job

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

    diann_validation_errors = []
    if _required_engine_for_pipeline(pipeline) in {"diann", "dia-nn"}:
        diann_validation_errors = validate_diann_pipeline_settings(pipeline.parameters or {}, allow_performance_tags=True)
    if diann_validation_errors:
        job, _created = ProcessingJob.objects.get_or_create(
            run_id=raw_file.run_id,
            raw_file=raw_file,
            pipeline=pipeline,
            defaults={
                "status": ProcessingStatus.FAILED,
                "error_message": "DIANN pipeline settings validation failed.",
                "metadata": {
                    "queued_by": "watcher_agent",
                    "worklist_entry_id": entry.id,
                    "worklist_position": entry.position,
                    "required_engine": _required_engine_for_pipeline(pipeline),
                    "validation_errors": diann_validation_errors,
                },
            },
        )
        if not _created:
            job.status = ProcessingStatus.FAILED
            job.error_message = "DIANN pipeline settings validation failed."
            job.metadata = {
                **(job.metadata or {}),
                "queued_by": "watcher_agent",
                "worklist_entry_id": entry.id,
                "worklist_position": entry.position,
                "required_engine": _required_engine_for_pipeline(pipeline),
                "validation_errors": diann_validation_errors,
            }
            job.save(update_fields=["status", "error_message", "metadata", "updated_at"])
        return job

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
                "required_engine": _required_engine_for_pipeline(pipeline),
            },
        },
    )
    return job


def _resolve_run_for_expected_filename(*, project_id: int, filename: str) -> Run | None:
    if not filename:
        return None
    candidates = (
        Run.objects.filter(sample__experiment__project_id=project_id, expected_filename__iexact=filename)
        .select_related("sample", "sample__experiment", "sample__experiment__project")
        .order_by("id")
    )
    run = candidates.first()
    if run:
        return run
    return (
        Run.objects.filter(sample__experiment__project_id=project_id, run_name__iexact=PurePath(filename).stem)
        .select_related("sample", "sample__experiment", "sample__experiment__project")
        .order_by("id")
        .first()
    )


def _resolve_experiment_for_project(*, project_id: int, experiment_id: int | None):
    if not experiment_id:
        return None
    return Experiment.objects.filter(project_id=project_id, pk=experiment_id).select_related("project").first()


def _machine_identity_for_run(run: Run | None) -> dict[str, str]:
    if not run:
        return {"machine_key": "unassigned", "machine_label": "Unassigned machine"}

    configuration = getattr(run, "configuration", None)
    if configuration:
        lc_name = getattr(configuration.lc_instrument, "nickname", "") if configuration.lc_instrument_id else ""
        ms_name = getattr(configuration.ms_instrument, "nickname", "") if configuration.ms_instrument_id else ""
        label = configuration.name
        if ms_name and label not in ms_name:
            label = f"{label} · {ms_name}"
        elif lc_name and label not in lc_name:
            label = f"{label} · {lc_name}"
        key = f"configuration:{configuration.id}"
        return {"machine_key": key, "machine_label": label}

    metadata = run.metadata or {}
    label = str(metadata.get("machine_name") or metadata.get("instrument_name") or "Unassigned machine").strip()
    key = str(
        metadata.get("machine_key")
        or metadata.get("instrument_key")
        or metadata.get("machine_name")
        or metadata.get("instrument_name")
        or "unassigned"
    ).strip().lower().replace(" ", "_")
    return {"machine_key": key or "unassigned", "machine_label": label or "Unassigned machine"}


def _hye_pair_score(organism_rows: list[dict]) -> tuple[float | None, float | None]:
    errors = [row["relative_error"] for row in organism_rows if row.get("relative_error") is not None]
    if not errors:
        return None, None
    score = round(mean(errors), 4)
    worst = round(max(errors), 4)
    return score, worst


def _hye_health(score: float | None, pair_complete: bool, trend_deviation: float | None = None) -> tuple[float | None, str]:
    if score is None:
        return None, "incomplete"
    ratio_component = max(0.0, 100.0 * (1.0 - min(score, 1.0)))
    completeness_component = 100.0 if pair_complete else 0.0
    trend_component = max(0.0, 100.0 * (1.0 - min(trend_deviation or 0.0, 1.0)))
    health = round((ratio_component * 0.50) + (completeness_component * 0.25) + (trend_component * 0.25), 1)
    status = "pass" if health >= 85 else "warning" if health >= 70 else "failed"
    return health, status


def _prtc_skyline_pipeline_for_raw_file(raw_file: RawFile) -> ProcessingPipeline | None:
    qc_program = getattr(raw_file.run, "qc_program", "") if raw_file.run_id else ""
    if raw_file.file_role != RunFileRole.PRTC and qc_program != QcProgram.PRTC:
        return None
    deployment_setting = _deployment_setting()
    pipeline = deployment_setting.prtc_skyline_pipeline if deployment_setting else None
    if pipeline:
        return pipeline
    pipeline_id = str(getattr(settings, "MSCONNECT_PRTC_SKYLINE_PIPELINE_ID", "") or "").strip()
    if not pipeline_id:
        return None
    try:
        return ProcessingPipeline.objects.get(pk=int(pipeline_id))
    except (TypeError, ValueError, ProcessingPipeline.DoesNotExist):
        return None


def _diann_pipeline_for_run(run: Run | None) -> ProcessingPipeline | None:
    if not run:
        return None
    entry = getattr(run, "worklist_entry", None)
    if not entry:
        return None
    pipeline_id = str((entry.worklist.metadata or {}).get("processing_pipeline_id") or "").strip()
    if not pipeline_id:
        return None
    try:
        return ProcessingPipeline.objects.get(pk=int(pipeline_id))
    except (TypeError, ValueError, ProcessingPipeline.DoesNotExist):
        return None


def _validate_diann_pipeline_for_run(run: Run | None) -> list[str]:
    pipeline = _diann_pipeline_for_run(run)
    if not pipeline:
        return []
    return validate_diann_pipeline_settings(pipeline.parameters or {}, allow_performance_tags=True)


def _deployment_setting() -> DeploymentSetting:
    deployment_setting, _created = DeploymentSetting.objects.select_related(
        "prtc_skyline_pipeline",
        "targeted_skyline_pipeline",
    ).get_or_create(
        scope="site"
    )
    return deployment_setting


def _record_file_match_exception(raw_file: RawFile, *, reason: str, project=None, experiment=None, metadata=None):
    exception, created = FileMatchException.objects.get_or_create(
        raw_file=raw_file,
        defaults={
            "project": project,
            "experiment": experiment,
            "reason": reason,
            "candidate_metadata": metadata or {},
        },
    )
    if not created:
        exception.reason = reason
        exception.candidate_metadata = metadata or exception.candidate_metadata
        exception.save(update_fields=["reason", "candidate_metadata", "updated_at"])
    record_pipeline_event(
        event_type=PipelineEventType.MATCH_EXCEPTION_CREATED,
        project=project,
        experiment=experiment,
        raw_file=raw_file,
        message=reason,
        payload={"exception_id": exception.id, **(metadata or {})},
    )
    return exception


def _required_engine_for_pipeline(pipeline: ProcessingPipeline | None) -> str:
    if not pipeline:
        return ""
    parameters = pipeline.parameters or {}
    value = parameters.get("required_engine")
    if value:
        return _normalize_engine(value)
    adapter = parameters.get("adapter")
    if adapter:
        return _normalize_engine(adapter)
    return ""


def _required_engine_for_job(job: ProcessingJob) -> str:
    metadata = job.metadata or {}
    value = metadata.get("required_engine") or metadata.get("engine")
    if value:
        return _normalize_engine(value)
    return _required_engine_for_pipeline(getattr(job, "pipeline", None))


def _required_engine_version_for_pipeline(pipeline: ProcessingPipeline | None) -> str:
    if not pipeline:
        return ""
    parameters = pipeline.parameters or {}
    return str(parameters.get("required_engine_version") or parameters.get("engine_version") or "").strip()


def _required_engine_version_for_job(job: ProcessingJob) -> str:
    metadata = job.metadata or {}
    value = metadata.get("required_engine_version") or metadata.get("engine_version")
    if value:
        return str(value).strip()
    return _required_engine_version_for_pipeline(getattr(job, "pipeline", None))


def _normalize_engine(value) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _engine_aliases(engine: str) -> set[str]:
    normalized = _normalize_engine(engine)
    aliases = {normalized}
    if normalized in {"processor", "generic", "command-runner"}:
        aliases.update({"", "processor", "generic", "command-runner"})
    if normalized in {"diann", "dia-nn", "dia_nn"}:
        aliases.update({"diann", "dia-nn"})
    if normalized in {"msconvert", "pwiz", "proteowizard"}:
        aliases.update({"msconvert", "pwiz", "proteowizard"})
    if normalized in {"pd", "proteome-discoverer", "proteomediscoverer"}:
        aliases.update({"pd", "proteome-discoverer", "proteomediscoverer"})
    if normalized in {"spectronaut", "spectronaut-cli"}:
        aliases.update({"spectronaut", "spectronaut-cli"})
    return aliases


def _node_can_run_job(node: ProcessingNode, job: ProcessingJob) -> bool:
    required_engine = _required_engine_for_job(job)
    if not required_engine:
        return True
    if required_engine not in _engine_aliases(node.node_type):
        return False
    if required_engine in {"diann", "dia-nn"} and not _diann_input_ready(job):
        return False
    required_version = _required_engine_version_for_job(job)
    if not required_version:
        return True
    return required_version == _node_engine_version(node)


def _diann_input_ready(job: ProcessingJob) -> bool:
    raw_file = getattr(job, "raw_file", None)
    if not raw_file:
        return False
    raw_path = str(getattr(raw_file, "storage_path", "") or "").strip()
    return bool(raw_path)


def _node_engine_version(node: ProcessingNode) -> str:
    node_settings = node.settings or {}
    node_metadata = node.metadata or {}
    return str(
        node_settings.get("processor_engine_version")
        or node_settings.get("engine_version")
        or node_metadata.get("processor_engine_version")
        or node_metadata.get("engine_version")
        or ""
    ).strip()


def _build_processing_job_agent_payload(job: ProcessingJob) -> dict:
    experiment = job.run.sample.experiment
    worklist_entry = getattr(job.run, "worklist_entry", None)
    derivatives = [
        {
            "id": derivative.id,
            "derivative_type": derivative.derivative_type,
            "status": derivative.status,
            "path": derivative.path,
            "format": derivative.format,
        }
        for derivative in job.raw_file.derivatives.order_by("derivative_type", "-updated_at")
    ]
    return {
        "id": job.id,
        "status": job.status,
        "lease_token": job.lease_token,
        "lease_expires_at": job.lease_expires_at,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "created_at": job.created_at,
        "metadata": {
            **(job.metadata or {}),
            "required_engine": _required_engine_for_job(job),
            "required_engine_version": _required_engine_version_for_job(job),
        },
        "run": {
            "id": job.run_id,
            "name": job.run.run_name,
            "project_id": job.run.sample.experiment.project_id,
            "project_code": job.run.sample.experiment.project.code,
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "experiment_metadata": experiment.metadata,
            "worklist_id": worklist_entry.worklist_id if worklist_entry else None,
            "worklist_metadata": worklist_entry.worklist.metadata if worklist_entry else {},
        },
        "raw_file": {
            "id": job.raw_file_id,
            "filename": job.raw_file.filename,
            "storage_path": job.raw_file.storage_path,
            "checksum_sha256": job.raw_file.checksum_sha256,
            "size_bytes": job.raw_file.size_bytes,
            "derivatives": derivatives,
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

        agent_role = getattr(request.user, "agent_role", "")
        node_type = (request.data.get("node_type") or agent_role).strip()
        if agent_role == "processor":
            if not re.fullmatch(r"[A-Za-z0-9_. -]{1,64}", node_type):
                raise ValidationError({"node_type": "Processor node_type must be a short engine identifier."})
        elif node_type != agent_role:
            raise ValidationError({"node_type": "node_type must match the authenticated agent role."})

        status_value = (request.data.get("status") or ProcessingNodeStatus.IDLE).strip()
        valid_statuses = {value for value, _label in ProcessingNodeStatus.choices}
        if status_value not in valid_statuses:
            raise ValidationError({"status": "Invalid processing node status."})

        existing = ProcessingNode.objects.filter(name=name).first()
        incoming_metadata = _ensure_dict(request.data.get("metadata"), field_name="metadata")
        previous_control = ((existing.metadata or {}).get("control") if existing else None) or {}
        acknowledged_control_id = incoming_metadata.get("ack_control_id")
        if previous_control and acknowledged_control_id == previous_control.get("id"):
            previous_control = {
                **previous_control,
                "acknowledged_at": timezone.now().isoformat(),
                "status": "acknowledged",
            }
        remote_addr = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        metadata = {
            **incoming_metadata,
            "remote_addr": remote_addr,
            "ip_address": incoming_metadata.get("ip_address") or remote_addr,
        }
        if previous_control:
            metadata["control"] = previous_control

        node, _created = ProcessingNode.objects.update_or_create(
            name=name,
            defaults={
                "node_type": node_type,
                "status": status_value,
                "container_image": (request.data.get("container_image") or settings.MSCONNECT_IMAGE).strip(),
                "endpoint_url": (request.data.get("endpoint_url") or "").strip(),
                "last_heartbeat_at": timezone.now(),
                "settings": _ensure_dict(request.data.get("settings"), field_name="settings"),
                "metadata": metadata,
            },
        )
        reported_release = (request.data.get("release_version") or incoming_metadata.get("release_version") or "").strip()
        desired = node.desired_release
        node.reported_release = reported_release
        if desired and reported_release == desired.version:
            node.release_status, node.release_error = "current", ""
        elif desired and reported_release:
            node.release_status = "outdated"
        elif not desired:
            node.release_status = "unmanaged"
        node.save(update_fields=["reported_release", "release_status", "release_error", "updated_at"])
        payload = ProcessingNodeSerializer(node).data
        payload["desired_release"] = (
            {"id": desired.id, "version": desired.version, "channel": desired.channel, "image": desired.image}
            if desired else None
        )
        return Response(payload, status=status.HTTP_200_OK)


class AgentPingView(AgentApiView):
    agent_roles = ("watcher", "processor")

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "agent_role": getattr(request.user, "agent_role", ""),
                "token_label": getattr(request.user, "token_label", ""),
                "server_time": timezone.now().isoformat(),
            },
            status=status.HTTP_200_OK,
        )


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
            record_raw_file_import(
                raw_file,
                message="Raw file accepted from watcher upload.",
                payload={
                    "source_path": source_path,
                    "storage_path": str(storage_candidate),
                    "checksum_sha256": checksum,
                    "size_bytes": size_bytes,
                    "match_run_by_name": _boolish(request.data.get("match_run_by_name")),
                },
            )
            if run:
                processing_job = _queue_processing_job_for_raw_file(raw_file)
                _queue_spectra_conversion_job_for_raw_file(raw_file, processing_job=processing_job)
            else:
                _record_file_match_exception(
                    raw_file,
                    reason="Raw file was stored but could not be matched to a planned run.",
                    metadata=metadata,
                )
                processing_job = None
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
        self._reclaim_expired_jobs()

        for candidate_status in (ProcessingStatus.QUEUED, ProcessingStatus.RETRYING):
            candidate_ids = list(
                ProcessingJob.objects.filter(status=candidate_status)
                .order_by("created_at", "id")
                .values_list("id", flat=True)[:200]
            )
            for candidate_id in candidate_ids:
                with transaction.atomic():
                    job = (
                        ProcessingJob.objects.select_related(
                            "pipeline",
                        )
                        .filter(id=candidate_id, status=candidate_status)
                        .first()
                    )
                    if not job or not _node_can_run_job(node, job):
                        continue
                    updated = ProcessingJob.objects.filter(id=candidate_id, status=candidate_status).update(
                        status=ProcessingStatus.ASSIGNED,
                        node_id=node.id,
                        lease_token=uuid.uuid4().hex,
                        lease_expires_at=timezone.now() + timedelta(seconds=settings.MSCONNECT_PROCESSING_LEASE_SECONDS),
                        attempt_count=F("attempt_count") + 1,
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

    def _reclaim_expired_jobs(self):
        cutoff = timezone.now() - timedelta(seconds=settings.MSCONNECT_PROCESSING_RECOVERY_GRACE_SECONDS)
        expired = ProcessingJob.objects.filter(
            status__in=(ProcessingStatus.ASSIGNED, ProcessingStatus.RUNNING),
            lease_expires_at__lt=cutoff,
        )
        for job in expired.only("id", "node_id", "attempt_count", "max_attempts"):
            next_status = ProcessingStatus.RETRYING if job.attempt_count < job.max_attempts else ProcessingStatus.FAILED
            ProcessingJob.objects.filter(pk=job.pk).update(
                status=next_status,
                node=None,
                lease_token="",
                lease_expires_at=None,
                finished_at=timezone.now() if next_status == ProcessingStatus.FAILED else None,
                error_message="Lease expired while the processor was unavailable.",
                updated_at=timezone.now(),
            )
            if job.node_id:
                ProcessingNode.objects.filter(pk=job.node_id).update(
                    status=ProcessingNodeStatus.OFFLINE,
                    updated_at=timezone.now(),
                )

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
        job.lease_expires_at = timezone.now() + timedelta(seconds=settings.MSCONNECT_PROCESSING_LEASE_SECONDS)
        job.save(update_fields=["status", "started_at", "finished_at", "error_message", "lease_expires_at", "updated_at"])

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
        lease_token = str(request.data.get("lease_token") or "").strip()
        if job.lease_token and lease_token != job.lease_token:
            raise PermissionDenied("This processing lease is not valid for the provided job.")
        if job.lease_token and job.lease_expires_at and job.lease_expires_at < timezone.now():
            raise ValidationError({"lease_token": "This processing lease has expired."})
        return job.node


class ProcessingJobRenewView(ProcessingJobStartView):
    def post(self, request, pk):
        job = self._get_job(pk)
        node = self._resolve_assigned_node(request, job)
        if job.status not in {ProcessingStatus.ASSIGNED, ProcessingStatus.RUNNING}:
            raise ValidationError({"status": "Only assigned or running jobs can renew a lease."})
        job.lease_expires_at = timezone.now() + timedelta(seconds=settings.MSCONNECT_PROCESSING_LEASE_SECONDS)
        job.save(update_fields=["lease_expires_at", "updated_at"])
        node.last_heartbeat_at = timezone.now()
        node.save(update_fields=["last_heartbeat_at", "updated_at"])
        return Response(ProcessingJobSerializer(job).data, status=status.HTTP_200_OK)


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
            generated_speclibs = [
                artifact
                for artifact in artifact_records
                if (artifact.metadata or {}).get("role") == "diann_speclib"
            ]
            if generated_speclibs:
                preferred_path = generated_speclibs[0].path
                experiment = job.run.sample.experiment
                experiment_metadata = dict(experiment.metadata or {})
                diann_metadata = dict(experiment_metadata.get("diann") or {})
                diann_metadata.setdefault("generated_speclib_paths", [])
                if preferred_path not in diann_metadata["generated_speclib_paths"]:
                    diann_metadata["generated_speclib_paths"].append(preferred_path)
                diann_metadata["last_generated_speclib_path"] = preferred_path
                diann_metadata.setdefault("preferred_speclib_path", preferred_path)
                experiment_metadata["diann"] = diann_metadata
                experiment.metadata = experiment_metadata
                experiment.save(update_fields=["metadata", "updated_at"])

        if result_summary or protein_table or peptide_table:
            record_pipeline_event(
                event_type="results_parsed",
                project=job.run.sample.experiment.project,
                experiment=job.run.sample.experiment,
                run=job.run,
                raw_file=job.raw_file,
                job=job,
                to_status=ProcessingStatus.COMPLETE,
                message="Result tables were parsed into protein and peptide records.",
                payload={
                    "result_summary": result_summary or {},
                    "protein_table_path": str(protein_table) if protein_table else "",
                    "peptide_table_path": str(peptide_table) if peptide_table else "",
                },
            )
            record_result_files_uploaded(
                job,
                payload={
                    "protein_table_path": str(protein_table) if protein_table else "",
                    "peptide_table_path": str(peptide_table) if peptide_table else "",
                    "delimiter": delimiter or "",
                    "result_summary": result_summary or {},
                },
            )

        job.status = ProcessingStatus.COMPLETE
        job.finished_at = timezone.now()
        job.log_path = str(log_path) if log_path else job.log_path
        job.error_message = ""
        job.lease_token = ""
        job.lease_expires_at = None
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
                "lease_token",
                "lease_expires_at",
                "updated_at",
            ]
        )

        job.raw_file.status = RawFileStatus.PROCESSED
        job.raw_file.save(update_fields=["status", "updated_at"])
        job.run.status = "processed"
        job.run.save(update_fields=["status", "updated_at"])

        record_processing_completion(
            job,
            payload={
                "stats": stats_payload,
                "result_summary": result_summary or {},
                "artifacts": len(artifact_records),
            },
        )
        recompute_experiment_and_project_status(
            job.run.sample.experiment,
            payload={
                "job_id": job.id,
                "raw_file_id": job.raw_file_id,
                "pipeline_id": job.pipeline_id,
            },
        )

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
        stats_payload = _ensure_dict(request.data.get("stats"), field_name="stats")
        job.status = ProcessingStatus.FAILED
        job.finished_at = timezone.now()
        job.lease_token = ""
        job.lease_expires_at = None
        job.error_message = error_message
        if stats_payload:
            job.stats = {**(job.stats or {}), **stats_payload}
        if log_path:
            job.log_path = str(log_path)
        job.save(update_fields=["status", "finished_at", "error_message", "log_path", "stats", "lease_token", "lease_expires_at", "updated_at"])

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


class AnalysisPresetViewSet(AuthenticatedModelViewSet):
    queryset = AnalysisPreset.objects.all()
    serializer_class = AnalysisPresetSerializer
    write_requires_admin = True
    search_fields = ("code", "name", "analysis_type", "description")
    ordering_fields = ("name", "code", "analysis_type", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        active = self.request.query_params.get("active")
        if active in {"1", "true", "True"}:
            queryset = queryset.filter(active=True)
        return queryset


class SampleManifestViewSet(AuthenticatedModelViewSet):
    queryset = SampleManifest.objects.select_related("experiment", "experiment__project", "analysis_preset", "uploaded_by")
    serializer_class = SampleManifestSerializer
    scope_lab_lookup = "experiment__project__lab_id"
    write_scope_lab_path = "experiment.project.lab"
    search_fields = ("name", "source_filename", "experiment__name", "experiment__project__code")
    ordering_fields = ("name", "status", "created_at", "updated_at")

    def create(self, request, *args, **kwargs):
        experiment_id = request.data.get("experiment")
        rows = request.data.get("rows") or []
        if not experiment_id:
            raise ValidationError({"experiment": "Experiment is required."})
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"rows": "At least one manifest row is required."})
        experiment = get_object_or_404(Experiment.objects.select_related("project__lab"), pk=experiment_id)
        if not is_admin(request.user) and experiment.project.lab_id not in set(active_lab_ids(request.user)):
            raise PermissionDenied("This manifest targets a project outside your lab scope.")
        preset = None
        preset_id = request.data.get("analysis_preset")
        if preset_id:
            preset = get_object_or_404(AnalysisPreset, pk=preset_id, active=True)
        seen_filenames = set()
        with transaction.atomic():
            manifest = SampleManifest.objects.create(
                experiment=experiment,
                analysis_preset=preset,
                uploaded_by=request.user,
                name=str(request.data.get("name") or "Sample manifest"),
                source_filename=str(request.data.get("source_filename") or ""),
                status=IntakeRecordStatus.READY,
                metadata=_ensure_dict(request.data.get("metadata"), field_name="metadata"),
            )
            worklist = AcquisitionWorklist.objects.create(
                experiment=experiment,
                name=f"Manifest: {manifest.name}",
                status=WorklistStatus.READY,
                generated_by=request.user,
                metadata={"manifest_id": manifest.id, "analysis_preset": preset.code if preset else ""},
            )
            for row_number, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    raise ValidationError({"rows": f"Row {row_number} must be an object."})
                sample_name = str(row.get("sample_name") or row.get("sample") or "").strip()
                expected_filename = PurePath(str(row.get("expected_filename") or row.get("filename") or "")).name
                if not sample_name or not expected_filename:
                    raise ValidationError({"rows": f"Row {row_number} requires sample_name and expected_filename."})
                if expected_filename.lower() in seen_filenames:
                    raise ValidationError({"rows": f"Duplicate expected_filename at row {row_number}."})
                seen_filenames.add(expected_filename.lower())
                sample, _created = Sample.objects.get_or_create(
                    experiment=experiment,
                    name=sample_name,
                    defaults={
                        "external_id": str(row.get("external_id") or ""),
                        "submitted_by": request.user,
                        "metadata": {"condition": str(row.get("condition") or ""), "batch": str(row.get("batch") or "")},
                    },
                )
                run_name = str(row.get("run_name") or PurePath(expected_filename).stem)
                run, _created = Run.objects.get_or_create(
                    sample=sample,
                    run_name=run_name,
                    defaults={"expected_filename": expected_filename, "file_role": RunFileRole.SAMPLE},
                )
                run.expected_filename = expected_filename
                run.metadata = {**(run.metadata or {}), "manifest_id": manifest.id, "condition": str(row.get("condition") or ""), "batch": str(row.get("batch") or "")}
                run.save(update_fields=["expected_filename", "metadata", "updated_at"])
                WorklistEntry.objects.create(
                    worklist=worklist,
                    run=run,
                    position=row_number,
                    expected_filename=expected_filename,
                    metadata={"manifest_id": manifest.id, "external_id": str(row.get("external_id") or "")},
                )
                SampleManifestRow.objects.create(
                    manifest=manifest,
                    row_number=row_number,
                    sample_name=sample_name,
                    external_id=str(row.get("external_id") or ""),
                    expected_filename=expected_filename,
                    condition=str(row.get("condition") or ""),
                    replicate=str(row.get("replicate") or ""),
                    batch=str(row.get("batch") or ""),
                    method_version=str(row.get("method_version") or ""),
                    metadata=_ensure_dict(row.get("metadata"), field_name=f"rows[{row_number}].metadata"),
                    matched_run=run,
                )
            manifest.metadata = {**(manifest.metadata or {}), "worklist_id": worklist.id, "row_count": len(rows)}
            manifest.save(update_fields=["metadata", "updated_at"])
            record_pipeline_event(
                event_type=PipelineEventType.SETTINGS_UPDATED,
                project=experiment.project,
                experiment=experiment,
                actor=request.user,
                message="Sample manifest created and runs planned.",
                payload={"manifest_id": manifest.id, "worklist_id": worklist.id, "row_count": len(rows)},
            )
        return Response(self.get_serializer(manifest).data, status=status.HTTP_201_CREATED)


class FileMatchExceptionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (permissions.IsAuthenticated,)
    queryset = FileMatchException.objects.select_related(
        "raw_file", "project", "experiment", "resolved_run", "resolved_by"
    )
    serializer_class = FileMatchExceptionSerializer
    pagination_class = OptionalPageNumberPagination
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("raw_file__filename", "raw_file__source_path", "reason", "project__code")
    ordering_fields = ("status", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        if not is_admin(self.request.user):
            lab_ids = active_lab_ids(self.request.user)
            queryset = queryset.filter(
                Q(project__lab_id__in=lab_ids)
                | Q(raw_file__run__sample__experiment__project__lab_id__in=lab_ids)
            ).distinct()
        project = self.request.query_params.get("project")
        status_filter = self.request.query_params.get("status")
        if project:
            queryset = queryset.filter(project_id=project)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        exception = self.get_object()
        run = get_object_or_404(Run.objects.select_related("sample__experiment__project"), pk=request.data.get("run"))
        if not is_admin(request.user) and run.sample.experiment.project.lab_id not in set(active_lab_ids(request.user)):
            raise PermissionDenied("This run is outside your lab scope.")
        diann_validation_errors = _validate_diann_pipeline_for_run(run)
        if diann_validation_errors:
            raise ValidationError({"diann_settings": diann_validation_errors})
        raw_file = exception.raw_file
        raw_file.run = run
        raw_file.match_confidence = 1.0
        raw_file.metadata = {**(raw_file.metadata or {}), "matched_run_id": run.id, "match_source": "exception_resolution"}
        raw_file.save(update_fields=["run", "match_confidence", "metadata", "updated_at"])
        exception.project = run.sample.experiment.project
        exception.experiment = run.sample.experiment
        exception.resolved_run = run
        exception.resolved_by = request.user
        exception.resolution_note = str(request.data.get("resolution_note") or "")
        exception.status = MatchExceptionStatus.RESOLVED
        exception.save(update_fields=["project", "experiment", "resolved_run", "resolved_by", "resolution_note", "status", "updated_at"])
        record_pipeline_event(
            event_type=PipelineEventType.FILE_MATCHED,
            project=run.sample.experiment.project,
            experiment=run.sample.experiment,
            run=run,
            raw_file=raw_file,
            actor=request.user,
            message="Raw file matched from the exception queue.",
            payload={"exception_id": exception.id},
        )
        processing_job = _queue_processing_job_for_raw_file(raw_file)
        _queue_spectra_conversion_job_for_raw_file(raw_file, processing_job=processing_job)
        return Response(self.get_serializer(exception).data)


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

    def qc_date_bounds(self):
        start = self.request.query_params.get("start") or self.request.query_params.get("date_from")
        end = self.request.query_params.get("end") or self.request.query_params.get("date_to")

        def parse(value, end_of_day=False):
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = timezone.make_aware(parsed)
                return parsed
            except ValueError:
                raise ValidationError({"date": "Use ISO-8601 dates or datetimes for start and end."}) from None

        start_value = parse(start)
        end_value = parse(end, end_of_day=True)
        if end_value and len(str(end)) == 10:
            end_value = end_value.replace(hour=23, minute=59, second=59, microsecond=999999)
        if start_value and end_value and start_value > end_value:
            raise ValidationError({"date": "The start date must be before the end date."})
        return start_value, end_value

    def qc_matches_filters(self, *, machine_key=None, project_id=None, run_ids=(), completed_at=None):
        machine_filter = self.request.query_params.get("machine") or self.request.query_params.get("instrument")
        project_filter = self.request.query_params.get("project")
        run_filter = self.request.query_params.get("run")
        start, end = self.qc_date_bounds()
        if machine_filter and machine_key != machine_filter:
            return False
        if project_filter and str(project_id) != str(project_filter):
            return False
        if run_filter and str(run_filter) not in {str(value) for value in run_ids}:
            return False
        if start and (not completed_at or completed_at < start):
            return False
        if end and (not completed_at or completed_at > end):
            return False
        return True

    def build_response(self):
        program = self.requested_program()
        if program == "prtc":
            return self.prtc_payload()
        return self.hye_payload()

    def prtc_payload(self):
        entries = []
        for worklist in self.scoped_worklists():
            entries.extend(
                entry
                for entry in worklist.entries.all()
                if entry.file_role == RunFileRole.PRTC or entry.qc_program == QcProgram.PRTC
            )
        run_ids = [entry.run_id for entry in entries if entry.run_id]
        jobs = list(
            ProcessingJob.objects.filter(
                run_id__in=run_ids,
                status=ProcessingStatus.COMPLETE,
            )
            .select_related("run", "raw_file", "pipeline")
            .order_by("-finished_at", "-id")
        )
        configured = bool(entries)
        empty_message = "" if configured else (
            "PRTC spiked-in standards are scaffolded in the QC workspace "
            "but no tagged PRTC dataset is available yet."
        )
        runs = []
        status_counts = {}
        for job in jobs:
            machine = _machine_identity_for_run(job.run)
            if not self.qc_matches_filters(
                machine_key=machine["machine_key"],
                project_id=job.run.sample.experiment.project_id,
                run_ids=(job.run_id,),
                completed_at=job.finished_at,
            ):
                continue
            stats = job.stats or {}
            status_value = str(stats.get("status") or stats.get("skyline_prtc", {}).get("status") or "unknown")
            status_counts[status_value] = status_counts.get(status_value, 0) + 1
            runs.append(
                {
                    "job_id": job.id,
                    "run_id": job.run_id,
                    "run_name": job.run.run_name,
                    "filename": job.raw_file.filename,
                    "status": status_value,
                    "expected_peptide_count": _numeric_stat(stats, "expected_peptide_count"),
                    "detected_peptide_count": _numeric_stat(stats, "detected_peptide_count"),
                    "missing_peptide_count": _numeric_stat(stats, "missing_peptide_count"),
                    "out_of_tolerance_peptide_count": _numeric_stat(stats, "out_of_tolerance_peptide_count"),
                    "total_area": _float_stat(stats, "total_area"),
                    "mean_rt_shift_seconds": _float_stat(stats, "mean_rt_shift_seconds"),
                    "max_abs_rt_shift_seconds": _float_stat(stats, "max_abs_rt_shift_seconds"),
                    "missing_peptides": stats.get("missing_peptides") or [],
                    "out_of_tolerance_peptides": stats.get("out_of_tolerance_peptides") or [],
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "machine_key": machine["machine_key"],
                    "machine_label": machine["machine_label"],
                    "project_id": job.run.sample.experiment.project_id,
                    "project_code": job.run.sample.experiment.project.code,
                }
            )
        missing_raw_count = max(0, len(entries) - len({job.run_id for job in jobs}))
        return {
            "overview": {
                "program": "prtc",
                "configured": configured,
                "qc_injection_count": len(entries),
                "complete_pair_count": len(jobs),
                "out_of_spec_pair_count": sum(count for key, count in status_counts.items() if key not in {"pass"}),
                "missing_raw_file_count": missing_raw_count,
                "latest_completed_at": jobs[0].finished_at.isoformat() if jobs and jobs[0].finished_at else None,
                "pair_status_counts": [
                    {"status": key, "count": count} for key, count in sorted(status_counts.items())
                ],
                "empty_message": empty_message,
            },
            "details": {
                "program": "prtc",
                "configured": configured,
                "thresholds": {
                    "pass_relative_error": self.pass_relative_error,
                    "warning_relative_error": self.warning_relative_error,
                },
                "empty_message": empty_message,
                "pairs": [],
                "runs": runs,
            },
        }

    def hye_payload(self):
        worklists = list(self.scoped_worklists())
        qc_entries = []
        for worklist in worklists:
            for entry in worklist.entries.all():
                if entry.file_role in {RunFileRole.QC, RunFileRole.HYE} or entry.qc_program == QcProgram.HYE:
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
            "run__configuration",
            "run__configuration__lc_instrument",
            "run__configuration__ms_instrument",
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
        machine_map: dict[str, dict] = {}

        for worklist in worklists:
            labels = []
            seen_labels = set()
            for entry in worklist.entries.all():
                if (
                    (entry.file_role in {RunFileRole.QC, RunFileRole.HYE} or entry.qc_program == QcProgram.HYE)
                    and entry.hye_pair_label
                    and entry.hye_pair_label not in seen_labels
                ):
                    labels.append(entry.hye_pair_label)
                    seen_labels.add(entry.hye_pair_label)

            entries_by_label = {}
            for entry in worklist.entries.all():
                if not entry.hye_pair_label:
                    continue
                if entry.file_role not in {RunFileRole.QC, RunFileRole.HYE} and entry.qc_program != QcProgram.HYE:
                    continue
                label_entries = entries_by_label.setdefault(entry.hye_pair_label, {})
                label_entries[entry.run.sample.name] = entry

            for label in labels:
                pair_entries = entries_by_label.get(label, {})
                a_entry = pair_entries.get("HYE-A")
                b_entry = pair_entries.get("HYE-B")
                a_job = complete_jobs.get(a_entry.run_id) if a_entry else None
                b_job = complete_jobs.get(b_entry.run_id) if b_entry else None
                a_machine = _machine_identity_for_run(a_entry.run if a_entry else None)
                b_machine = _machine_identity_for_run(b_entry.run if b_entry else None)
                if a_machine["machine_key"] == b_machine["machine_key"]:
                    machine_key = a_machine["machine_key"]
                    machine_label = a_machine["machine_label"]
                else:
                    machine_key = f"mixed:{a_machine['machine_key']}|{b_machine['machine_key']}"
                    machine_label = f"{a_machine['machine_label']} / {b_machine['machine_label']}"
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

                project = worklist.experiment.project
                score, worst_relative_error = _hye_pair_score(organism_rows)
                health_score, health_status = _hye_health(score, pair_complete)
                if not self.qc_matches_filters(
                    machine_key=machine_key,
                    project_id=project.id,
                    run_ids=(a_entry.run_id if a_entry else None, b_entry.run_id if b_entry else None),
                    completed_at=completed_at,
                ):
                    continue
                if pair_complete:
                    complete_pair_count += 1
                if pair_state != "pass":
                    out_of_spec_pair_count += 1
                status_counts[pair_state] = status_counts.get(pair_state, 0) + 1

                a_raw_file = raw_files_by_run.get(a_entry.run_id) if a_entry else None
                b_raw_file = raw_files_by_run.get(b_entry.run_id) if b_entry else None
                pairs.append(
                    {
                        "project_id": project.id,
                        "project_code": project.code,
                        "worklist_id": worklist.id,
                        "worklist_name": worklist.name,
                        "pair_label": label,
                        "machine_key": machine_key,
                        "machine_label": machine_label,
                        "a_machine_key": a_machine["machine_key"],
                        "a_machine_label": a_machine["machine_label"],
                        "b_machine_key": b_machine["machine_key"],
                        "b_machine_label": b_machine["machine_label"],
                        "status": pair_state,
                        "shared_total_n": shared_total_n,
                        "completed_at": completed_at,
                        "a_run_id": a_entry.run_id if a_entry else None,
                        "b_run_id": b_entry.run_id if b_entry else None,
                        "a_run_name": a_entry.run.run_name if a_entry else "",
                        "b_run_name": b_entry.run.run_name if b_entry else "",
                        "a_filename": a_job.raw_file.filename if a_job else (a_raw_file.filename if a_raw_file else ""),
                        "b_filename": b_job.raw_file.filename if b_job else (b_raw_file.filename if b_raw_file else ""),
                        "score": score,
                        "worst_relative_error": worst_relative_error,
                        "health_score": health_score,
                        "health_status": health_status,
                        "organisms": organism_rows,
                    }
                )

                machine_entry = machine_map.setdefault(
                    machine_key,
                    {
                        "machine_key": machine_key,
                        "machine_label": machine_label,
                        "pair_count": 0,
                        "complete_pair_count": 0,
                        "scores": [],
                        "latest_completed_at": None,
                        "series": [],
                    },
                )
                machine_entry["pair_count"] += 1
                if score is not None:
                    machine_entry["complete_pair_count"] += 1
                    machine_entry["scores"].append(score)
                if completed_at and (
                    not machine_entry["latest_completed_at"] or completed_at > machine_entry["latest_completed_at"]
                ):
                    machine_entry["latest_completed_at"] = completed_at
                machine_entry["series"].append(
                    {
                        "machine_key": machine_key,
                        "machine_label": machine_label,
                        "project_id": project.id,
                        "project_code": project.code,
                        "worklist_id": worklist.id,
                        "worklist_name": worklist.name,
                        "pair_label": label,
                        "completed_at": completed_at.isoformat() if completed_at else None,
                        "score": score,
                        "health_score": health_score,
                        "health_status": health_status,
                        "ratio_homo_sapiens": next((row["observed_ratio"] for row in organism_rows if row["organism"] == "Homo sapiens"), None),
                        "ratio_saccharomyces_cerevisiae": next((row["observed_ratio"] for row in organism_rows if row["organism"] == "Saccharomyces cerevisiae"), None),
                        "ratio_escherichia_coli": next((row["observed_ratio"] for row in organism_rows if row["organism"] == "Escherichia coli"), None),
                        "status": pair_state,
                        "pair_count": machine_entry["pair_count"],
                    }
                )

        latest_completed_at = max((pair["completed_at"] for pair in pairs if pair["completed_at"]), default=None)
        missing_raw_file_count = sum(1 for entry in qc_entries if entry.run_id not in raw_files_by_run)

        machine_summaries = []
        machine_series = []
        for machine in sorted(machine_map.values(), key=lambda item: item["machine_label"]):
            scores = machine["scores"]
            mean_score = round(mean(scores), 4) if scores else None
            stddev_score = round(pstdev(scores), 4) if len(scores) > 1 else 0.0 if scores else None
            lower_band = (
                round(mean_score - (2 * stddev_score), 4)
                if mean_score is not None and stddev_score is not None
                else None
            )
            upper_band = (
                round(mean_score + (2 * stddev_score), 4)
                if mean_score is not None and stddev_score is not None
                else None
            )
            machine_summaries.append(
                {
                    "machine_key": machine["machine_key"],
                    "machine_label": machine["machine_label"],
                    "pair_count": machine["pair_count"],
                    "complete_pair_count": machine["complete_pair_count"],
                    "mean_score": mean_score,
                    "stddev_score": stddev_score,
                    "lower_band": lower_band,
                    "upper_band": upper_band,
                    "latest_completed_at": (
                        machine["latest_completed_at"].isoformat() if machine["latest_completed_at"] else None
                    ),
                }
            )
            for point in machine["series"]:
                machine_series.append(
                    {
                        **point,
                        "mean_score": mean_score,
                        "lower_band": lower_band,
                        "upper_band": upper_band,
                        "pair_count": machine["pair_count"],
                    }
                )

        pairs.sort(key=lambda pair: (pair["project_code"], pair["worklist_name"], pair["pair_label"]))
        machine_series.sort(
            key=lambda point: (point["machine_label"], point["completed_at"] or "", point["pair_label"])
        )
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
                "machine_summaries": machine_summaries,
                "machine_series": machine_series,
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


class SystemHealthView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    stale_seconds = 180

    def get(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can view system health.")

        now = timezone.now()
        readiness_checks = {
            "healthz": {"ok": True, "status": "green", "label": "Django", "detail": "healthz is reachable"},
            "database": _database_check(),
            "incoming_raw_root": _path_check(settings.INCOMING_RAW_ROOT, require_read=True),
            "raw_file_storage_root": _path_check(settings.RAW_FILE_STORAGE_ROOT, require_read=True, require_write=True),
            "results_root": _path_check(settings.RESULTS_ROOT, require_read=True, require_write=True),
            "media_root": _path_check(settings.MEDIA_ROOT, require_read=True, require_write=True),
        }
        ready_ok = all(check["ok"] for key, check in readiness_checks.items() if key != "healthz")
        readiness_checks["readyz"] = {
            "ok": ready_ok,
            "status": "green" if ready_ok else "red",
            "label": "Readiness",
            "detail": "All storage and database checks passed" if ready_ok else "One or more readiness checks failed",
        }

        nodes = list(ProcessingNode.objects.all().order_by("node_type", "name"))
        jobs = ProcessingJob.objects.all()
        raw_files = RawFile.objects.all()
        node_groups = self._node_groups(nodes, now)
        watcher_group = self._aggregate_groups(node_groups, include_types={"watcher"})
        processor_group = self._aggregate_groups(node_groups, exclude_types={"watcher"})
        serialized_node_groups = [self._serialize_group(group) for group in node_groups]
        connected_total = sum(group["connected"] for group in node_groups)
        stale_total = sum(group["stale"] for group in node_groups)
        offline_total = sum(group["offline"] for group in node_groups)
        failed_jobs = jobs.filter(status=ProcessingStatus.FAILED).count()
        active_jobs = jobs.filter(
            status__in=(
                ProcessingStatus.QUEUED,
                ProcessingStatus.ASSIGNED,
                ProcessingStatus.RUNNING,
                ProcessingStatus.RETRYING,
            )
        ).count()
        unmatched_raw_files = raw_files.filter(run__isnull=True).count()
        alerts = []
        if not ready_ok:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "readiness",
                    "title": "Readiness check failed",
                    "detail": "One or more database or storage roots are not healthy.",
                    "route": "/admin/",
                }
            )
        if offline_total:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "offline-nodes",
                    "title": "Downed nodes detected",
                    "detail": f"{offline_total} node(s) are marked offline.",
                    "route": "/processing/admin",
                }
            )
        if stale_total:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "stale-nodes",
                    "title": "Stale node heartbeats",
                    "detail": f"{stale_total} node(s) have not checked in within {self.stale_seconds} seconds.",
                    "route": "/processing/admin",
                }
            )
        if watcher_group["total"] and watcher_group["connected"] == 0:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "watcher-disconnected",
                    "title": "Watcher disconnected",
                    "detail": "No watcher nodes are currently connected.",
                    "route": "/monitoring",
                }
            )
        if nodes and not watcher_group["total"]:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "watcher-missing",
                    "title": "No watcher nodes registered",
                    "detail": "No watcher containers or agents have reported yet.",
                    "route": "/monitoring",
                }
            )
        if processor_group["total"] and processor_group["connected"] == 0:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "processor-disconnected",
                    "title": "Processor disconnected",
                    "detail": "No processor nodes are currently connected.",
                    "route": "/processing/admin",
                }
            )
        if nodes and not processor_group["total"]:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "processor-missing",
                    "title": "No processor nodes registered",
                    "detail": "No processor containers or agents have reported yet.",
                    "route": "/processing/admin",
                }
            )
        if failed_jobs:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "failed-jobs",
                    "title": "Failed processing jobs",
                    "detail": f"{failed_jobs} job(s) need operator review.",
                    "route": "/monitoring",
                }
            )
        if unmatched_raw_files:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "unmatched-raw-files",
                    "title": "Unmatched raw files",
                    "detail": f"{unmatched_raw_files} raw file(s) have not been matched to a run.",
                    "route": "/monitoring",
                }
            )
        if not nodes:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "no-nodes",
                    "title": "No connected nodes",
                    "detail": "No watcher or processor nodes have reported yet.",
                    "route": "/processing/admin",
                }
            )

        overall_status = "green"
        if any(alert["severity"] == "critical" for alert in alerts):
            overall_status = "red"
        elif alerts:
            overall_status = "yellow"

        return Response(
            {
                "status": overall_status,
                "server_time": now.isoformat(),
                "readiness": readiness_checks,
                "nodes": {
                    "total": len(nodes),
                    "connected": connected_total,
                    "stale": stale_total,
                    "offline": offline_total,
                    "watcher": self._serialize_group(watcher_group),
                    "processor": self._serialize_group(processor_group),
                    "by_type": serialized_node_groups,
                },
                "jobs": {
                    "active": active_jobs,
                    "failed": failed_jobs,
                },
                "raw_files": {
                    "total": raw_files.count(),
                    "unmatched": unmatched_raw_files,
                },
                "alerts": alerts,
            }
        )

    def _node_groups(self, nodes: list[ProcessingNode], now):
        groups: dict[str, dict] = {}
        for node in nodes:
            group = groups.setdefault(
                node.node_type,
                {
                    "node_type": node.node_type,
                    "total": 0,
                    "connected": 0,
                    "stale": 0,
                    "offline": 0,
                    "latest_heartbeat_at": None,
                },
            )
            group["total"] += 1
            if node.status == ProcessingNodeStatus.OFFLINE:
                group["offline"] += 1
            elif node.last_heartbeat_at and (now - node.last_heartbeat_at).total_seconds() <= self.stale_seconds:
                group["connected"] += 1
            else:
                group["stale"] += 1
            if node.last_heartbeat_at and (
                not group["latest_heartbeat_at"] or node.last_heartbeat_at > group["latest_heartbeat_at"]
            ):
                group["latest_heartbeat_at"] = node.last_heartbeat_at
        return sorted(groups.values(), key=lambda item: item["node_type"])

    def _aggregate_groups(
        self,
        groups: list[dict],
        *,
        include_types: set[str] | None = None,
        exclude_types: set[str] | None = None,
    ):
        selected = []
        for group in groups:
            if include_types is not None and group["node_type"] not in include_types:
                continue
            if exclude_types is not None and group["node_type"] in exclude_types:
                continue
            selected.append(group)
        if not selected:
            return {
                "node_type": "processor" if exclude_types else "watcher",
                "total": 0,
                "connected": 0,
                "stale": 0,
                "offline": 0,
                "latest_heartbeat_at": None,
            }
        return {
            "node_type": "watcher" if include_types else "processor",
            "total": sum(group["total"] for group in selected),
            "connected": sum(group["connected"] for group in selected),
            "stale": sum(group["stale"] for group in selected),
            "offline": sum(group["offline"] for group in selected),
            "latest_heartbeat_at": max(
                (group["latest_heartbeat_at"] for group in selected if group["latest_heartbeat_at"]),
                default=None,
            ),
        }

    def _serialize_group(self, group: dict):
        return {
            **group,
            "latest_heartbeat_at": (
                group["latest_heartbeat_at"].isoformat() if group.get("latest_heartbeat_at") else None
            ),
        }


class DeploymentSettingsView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can view deployment settings.")
        return Response(DeploymentSettingsSerializer(_deployment_setting()).data)

    def patch(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can edit deployment settings.")
        deployment_setting = _deployment_setting()
        serializer = DeploymentSettingsSerializer(deployment_setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DeploymentReleaseAuditView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can view release audit history.")
        events = PipelineEvent.objects.filter(event_type=PipelineEventType.SETTINGS_UPDATED).order_by("-created_at", "-id")[:100]
        return Response(PipelineEventSerializer(events, many=True).data)


class CurrentUserView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        profile = getattr(user, "profile", None)
        memberships = (
            LabMembership.objects.filter(user=user, active=True)
            .select_related("lab", "lab__facility", "lab__facility__university")
            .order_by("lab__name")
        )
        payload = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_superuser": bool(user.is_superuser),
            "global_role": profile.global_role if profile else UserRole.RESEARCHER,
            "email_verified_at": getattr(profile, "email_verified_at", None),
            "labs": [
                {
                    "id": membership.lab_id,
                    "name": membership.lab.name,
                    "slug": membership.lab.slug,
                    "role": membership.role,
                    "facility_name": membership.lab.facility.name,
                    "university_name": membership.lab.facility.university.name,
                }
                for membership in memberships
            ],
            "active_lab_ids": [membership.lab_id for membership in memberships],
        }
        serializer = CurrentUserSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class SignupView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        email = data["email"].strip().lower()
        username = data["username"].strip()
        password = data["password"]
        lab_name = (data.get("lab_name") or "").strip()
        institution_name = (data.get("institution_name") or "").strip()
        membership_role = data.get("membership_role") or UserRole.COLLABORATOR

        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError({"username": "That username is already in use."})
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({"email": "That email address is already in use."})

        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            UserProfile.objects.create(user=user, global_role=UserRole.COLLABORATOR)

            lab = self._ensure_default_lab(
                institution_name=institution_name or lab_name or "Collaborator Intake",
                lab_name=lab_name or f"{username}-collaboration",
                owner=user,
            )
            LabMembership.objects.create(user=user, lab=lab, role=membership_role, active=True)
            user = self._activate_and_sign_in(request, user)

        verification_payload = self._verification_payload(user)
        try:
            send_mail(
                subject="Verify your MSConnect account",
                message=(
                    f"Verify your account by visiting: "
                    f"{request.build_absolute_uri(verification_payload['verify_url'])}\n\n"
                    f"Your temporary verification code: {verification_payload['token']}"
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "msconnect@localhost"),
                recipient_list=[email],
                fail_silently=settings.MSCONNECT_EMAIL_FAIL_SILENT,
            )
        except Exception:
            pass

        return Response(
            {
                "user": self._current_user_payload(user),
                "verification": verification_payload,
                "lab_id": lab.id,
                "lab_code": lab.slug,
            },
            status=status.HTTP_201_CREATED,
        )

    def _ensure_default_lab(self, *, institution_name: str, lab_name: str, owner):
        default_facility = self._default_facility()
        if default_facility is None:
            university, _created = University.objects.get_or_create(name=institution_name or "Collaborator Institute")
            facility, _created = Facility.objects.get_or_create(
                university=university,
                slug=_filename_token(institution_name or "collaborator-core").lower()[:80],
                defaults={"name": institution_name or "Collaborator Core"},
            )
        else:
            facility = default_facility

        lab_slug = _filename_token(lab_name).lower()[:80]
        lab, _created = Lab.objects.get_or_create(
            facility=facility,
            slug=lab_slug,
            defaults={
                "name": lab_name or "Collaborator Lab",
                "pi": owner,
                "billing_code": "",
            },
        )
        if not lab.pi_id:
            lab.pi = owner
            lab.save(update_fields=["pi", "updated_at"])
        return lab

    def _default_facility(self):
        slug = str(getattr(settings, "MSCONNECT_DEFAULT_FACILITY_SLUG", "") or "").strip()
        if not slug:
            return None
        return Facility.objects.select_related("university").filter(slug=slug, active=True).first()

    def _activate_and_sign_in(self, request, user):
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(request, user)
        return user

    def _verification_payload(self, user):
        signer = TimestampSigner(salt="signup-verification")
        token = signer.sign(f"{user.pk}:{user.email}")
        return {
            "token": token,
            "verify_url": f"/accounts/verify-email/{token}/",
        }

    def _current_user_payload(self, user):
        profile = getattr(user, "profile", None)
        memberships = LabMembership.objects.filter(user=user, active=True)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_superuser": bool(user.is_superuser),
            "global_role": profile.global_role if profile else UserRole.RESEARCHER,
            "email_verified_at": getattr(profile, "email_verified_at", None),
            "labs": [
                {
                    "id": membership.lab_id,
                    "name": membership.lab.name,
                    "slug": membership.lab.slug,
                    "role": membership.role,
                    "facility_name": membership.lab.facility.name,
                    "university_name": membership.lab.facility.university.name,
                }
                for membership in memberships.select_related("lab", "lab__facility", "lab__facility__university")
            ],
            "active_lab_ids": list(memberships.values_list("lab_id", flat=True)),
        }


class VerifySignupEmailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, token):
        signer = TimestampSigner(salt="signup-verification")
        try:
            raw = signer.unsign(token, max_age=60 * 60 * 24 * 7)
            user_id, email = raw.split(":", 1)
        except SignatureExpired as exc:
            raise ValidationError({"token": "Verification link expired."}) from exc
        except (BadSignature, ValueError) as exc:
            raise ValidationError({"token": "Verification token is invalid."}) from exc

        user = get_object_or_404(User, pk=user_id)
        if user.email.lower() != email.lower():
            raise ValidationError({"token": "Verification token does not match this account."})
        profile = getattr(user, "profile", None)
        if profile and not profile.email_verified_at:
            profile.email_verified_at = timezone.now()
            profile.save(update_fields=["email_verified_at", "updated_at"])

        login(request, user)
        return Response({"verified": True, "user_id": user.id})


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
    ordering = ("-updated_at",)

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        lab_filter = self.request.query_params.get("lab")
        if lab_filter:
            queryset = queryset.filter(lab_id=lab_filter)
        return queryset

    @action(detail=False, methods=["post"], url_path="quick-start")
    def quick_start(self, request):
        serializer = ProjectQuickStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lab = data.get("lab") or self._default_lab_for_user(request.user)
        if lab is None:
            raise ValidationError({"lab": "No lab was provided and no active lab membership was found."})
        if not is_admin(request.user) and lab.id not in set(active_lab_ids(request.user)):
            raise PermissionDenied("This project targets a lab outside your membership scope.")

        with transaction.atomic():
            code = data.get("code") or self._next_quick_start_code(data["title"])
            project = Project.objects.create(
                lab=lab,
                title=data["title"],
                code=code,
                pi=getattr(lab, "pi", None) or request.user,
                description="Quick-start project. Import or generate a worklist to establish run ground truth.",
            )
            experiment = Experiment.objects.create(
                project=project,
                name="Default experiment",
                created_by=request.user,
                metadata={"setup_source": "quick_start"},
            )

        return Response(
            {
                "project": ProjectSerializer(project).data,
                "experiment": ExperimentSerializer(experiment).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        project = self.get_object()
        experiment = _resolve_experiment_for_project(
            project_id=project.id,
            experiment_id=_int_or_none(request.query_params.get("experiment")),
        )
        if request.query_params.get("experiment") and experiment is None:
            raise ValidationError({"experiment": "Experiment does not belong to this project."})
        experiments = Experiment.objects.filter(project=project)
        samples = Sample.objects.filter(experiment__project=project)
        runs = Run.objects.filter(sample__experiment__project=project)
        raw_files = RawFile.objects.filter(run__sample__experiment__project=project).prefetch_related("derivatives")
        jobs = ProcessingJob.objects.filter(run__sample__experiment__project=project)
        worklists = AcquisitionWorklist.objects.filter(experiment__project=project)
        if experiment:
            samples = samples.filter(experiment=experiment)
            runs = runs.filter(sample__experiment=experiment)
            raw_files = raw_files.filter(run__sample__experiment=experiment)
            jobs = jobs.filter(run__sample__experiment=experiment)
            worklists = worklists.filter(experiment=experiment)
        raw_file_count = raw_files.count()
        jobs_for_stats = list(jobs)
        raw_files_for_stats = list(raw_files)
        job_stats = _aggregate_job_stats(jobs_for_stats)
        spectrum_counts = _safe_spectrum_counts_for_raw_files(raw_files_for_stats)

        expected_raw_file_count = WorklistEntry.objects.filter(worklist__experiment__project=project).count()
        if experiment:
            expected_raw_file_count = WorklistEntry.objects.filter(worklist__experiment=experiment).count()

        return Response(
            {
                "project_id": project.id,
                "project_code": project.code,
                "experiment_count": 1 if experiment else experiments.count(),
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
                **({"experiment_id": experiment.id, "experiment_name": experiment.name} if experiment else {}),
            }
        )

    @action(detail=True, methods=["get"], url_path="researcher-status")
    def researcher_status(self, request, pk=None):
        project = self.get_object()
        experiment = _resolve_experiment_for_project(
            project_id=project.id,
            experiment_id=_int_or_none(request.query_params.get("experiment")),
        )
        if request.query_params.get("experiment") and experiment is None:
            raise ValidationError({"experiment": "Experiment does not belong to this project."})
        summary_response = self.summary(request, pk=pk)
        summary = summary_response.data
        if experiment:
            summary = {**summary, "experiment_id": experiment.id, "experiment_name": experiment.name}
        runs = (
            Run.objects.filter(sample__experiment__project=project)
            .select_related("sample", "sample__experiment")
            .prefetch_related("raw_files", "processing_jobs", "processing_jobs__artifacts")
            .order_by("worklist_position", "run_name", "id")
        )
        if experiment:
            runs = runs.filter(sample__experiment=experiment)
        rows = []
        failed_count = 0
        active_count = 0
        for run in runs:
            raw_files = list(run.raw_files.order_by("-imported_at", "filename"))
            latest_raw = raw_files[0] if raw_files else None
            jobs = list(run.processing_jobs.order_by("-created_at"))
            latest_job = jobs[0] if jobs else None
            job_stats = _aggregate_job_stats(jobs)
            failed_count += 1 if latest_job and latest_job.status == ProcessingStatus.FAILED else 0
            active_count += 1 if latest_job and latest_job.status in {
                ProcessingStatus.QUEUED,
                ProcessingStatus.ASSIGNED,
                ProcessingStatus.RUNNING,
                ProcessingStatus.RETRYING,
            } else 0
            entry = getattr(run, "worklist_entry", None)
            rows.append(
                {
                    "run": RunSerializer(run).data,
                    "sample": SampleSerializer(run.sample).data,
                    "worklist_entry_id": entry.id if entry else None,
                    "worklist_name": entry.worklist.name if entry else "",
                    "raw_file": RawFileSerializer(latest_raw).data if latest_raw else None,
                    "raw_file_count": len(raw_files),
                    "processing_job": ProcessingJobSerializer(latest_job).data if latest_job else None,
                    "processing_job_count": len(jobs),
                    "stats": {
                        "protein_quant_count": ProteinQuant.objects.filter(job__in=jobs).count(),
                        "peptide_quant_count": PeptideQuant.objects.filter(job__in=jobs).count(),
                        **job_stats,
                        **_safe_spectrum_counts_for_raw_files(raw_files),
                    },
                }
            )

        health = "green"
        if failed_count:
            health = "red"
        elif summary["missing_raw_file_count"] or active_count:
            health = "yellow"

        return Response(
            {
                "project": ProjectSerializer(project).data,
                "summary": summary,
                **({"experiment": ExperimentSerializer(experiment).data} if experiment else {}),
                "system_health": {
                    "status": health,
                    "failed_jobs": failed_count,
                    "active_jobs": active_count,
                    "missing_raw_files": summary["missing_raw_file_count"],
                },
                "runs": rows,
            }
        )

    @action(detail=True, methods=["get"], url_path="diann-preflight")
    def diann_preflight(self, request, pk=None):
        project = self.get_object()
        experiment = _resolve_experiment_for_project(
            project_id=project.id,
            experiment_id=_int_or_none(request.query_params.get("experiment")),
        )
        if request.query_params.get("experiment") and experiment is None:
            raise ValidationError({"experiment": "Experiment does not belong to this project."})
        return Response(self._build_diann_preflight(project, experiment=experiment))

    @action(detail=True, methods=["patch"], url_path="diann-settings")
    def diann_settings(self, request, pk=None):
        project = self.get_object()
        experiment = _resolve_experiment_for_project(
            project_id=project.id,
            experiment_id=_int_or_none(request.query_params.get("experiment") or request.data.get("experiment")),
        )
        if experiment is None:
            raise ValidationError({"experiment": "An experiment with a processing worklist is required."})
        worklist = (
            AcquisitionWorklist.objects.filter(experiment=experiment)
            .order_by("-updated_at", "-created_at")
            .first()
        )
        pipeline_id = (worklist.metadata or {}).get("processing_pipeline_id") if worklist else None
        pipeline = ProcessingPipeline.objects.filter(pk=pipeline_id).first() if pipeline_id else None
        if not pipeline:
            raise ValidationError({"settings": "This experiment does not have a project processing pipeline yet."})

        incoming = request.data.get("settings", request.data.get("experimental_tags", {}))
        if not isinstance(incoming, dict):
            raise ValidationError({"settings": "Settings must be a JSON object."})
        current = normalize_diann_settings(pipeline.parameters or {})
        proposed = normalize_diann_settings(incoming)
        merged = {
            **{key: value for key, value in current.items() if key != "tags"},
            **{key: value for key, value in proposed.items() if key != "tags"},
            "tags": {
                "experimental": {
                    **(current.get("tags", {}).get("experimental") or {}),
                    **(proposed.get("tags", {}).get("experimental") or {}),
                },
                "performance": site_performance_tags(),
            },
        }
        merged["tags"]["performance"].setdefault("threads", 1)
        validation_errors = validate_diann_pipeline_settings(merged, allow_performance_tags=True)
        if validation_errors:
            raise ValidationError({"settings": validation_errors})
        pipeline.parameters = {
            **(pipeline.parameters or {}),
            **{key: value for key, value in merged.items() if key not in {"tags", "settings", "options"}},
            "settings": merged,
            "tags": merged["tags"],
            "options": _diann_command_options(merged),
        }
        pipeline.save(update_fields=["parameters", "updated_at"])
        record_pipeline_event(
            event_type=PipelineEventType.SETTINGS_UPDATED,
            project=project,
            experiment=experiment,
            actor=request.user,
            message="Project DIA-NN settings updated.",
            payload={"pipeline_id": pipeline.id, "experimental_tags": merged["tags"]["experimental"]},
        )
        return Response(self._build_diann_preflight(project, experiment=experiment))

    @action(detail=True, methods=["post"], url_path="import-worklist")
    def import_worklist(self, request, pk=None):
        project = self.get_object()
        serializer = WorklistImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            experiment, _created = Experiment.objects.get_or_create(
                project=project,
                name=data["experiment_name"],
                defaults={
                    "created_by": request.user,
                    "metadata": {"setup_source": "worklist_import"},
                },
            )
            pipeline = self._create_or_update_diann_pipeline(
                {
                    "organisms": ["human", "yeast", "ecoli"],
                    "diann_settings": {},
                    "diann_version": data["diann_version"],
                    "processing_preset": DIANN_PRESET_SPECLIB_BUILD,
                }
            )
            worklist, _created = AcquisitionWorklist.objects.get_or_create(
                experiment=experiment,
                name=data["worklist_name"],
                defaults={
                    "status": WorklistStatus.READY,
                    "generated_by": request.user,
                    "notes": "Imported from LC-MS worklist file.",
                    "metadata": {
                        "setup_source": "worklist_import",
                        "processing_pipeline_id": pipeline.id,
                        "processing_plan": pipeline.parameters,
                        "watcher_matching": "expected_filename",
                    },
                },
            )
            worklist.status = WorklistStatus.READY
            worklist.generated_by = worklist.generated_by or request.user
            worklist.metadata = {
                **(worklist.metadata or {}),
                "setup_source": "worklist_import",
                "processing_pipeline_id": pipeline.id,
                "processing_plan": pipeline.parameters,
                "watcher_matching": "expected_filename",
            }
            worklist.save(update_fields=["status", "generated_by", "metadata", "updated_at"])

            existing_by_position = {
                entry.position: entry for entry in worklist.entries.select_related("run", "run__sample")
            }
            samples = []
            runs = []
            entries = []
            for row in sorted(data["rows"], key=lambda item: item["position"]):
                metadata = {
                    **(row.get("metadata") or {}),
                    "setup_source": "worklist_import",
                    "condition": row.get("condition", ""),
                    "qc_program": row.get("qc_program", ""),
                    "synthetic_peptides_present": row.get("qc_program") == QcProgram.PRTC,
                    "plate_id": row.get("plate", ""),
                    **_well_coordinates(row.get("well", "")),
                }
                sample, _created = Sample.objects.get_or_create(
                    experiment=experiment,
                    name=row["sample_name"],
                    defaults={
                        "external_id": f"{project.code}-{row['sample_name']}",
                        "submitted_by": request.user,
                        "metadata": metadata,
                    },
                )
                sample.metadata = {**(sample.metadata or {}), **metadata}
                sample.save(update_fields=["metadata", "updated_at"])

                run_name = row.get("run_name") or f"{project.code}-{row['position']:03d}-{sample.name}"
                entry = existing_by_position.get(row["position"])
                if entry:
                    run = entry.run
                    run.sample = sample
                    run.run_name = run_name
                    run.status = row.get("status", run.status)
                    run.file_role = row["file_role"]
                    run.qc_program = row.get("qc_program", "")
                    run.metadata = {**(run.metadata or {}), **metadata, "expected_filename": row["expected_filename"]}
                    run.save(
                        update_fields=[
                            "sample",
                            "run_name",
                            "status",
                            "file_role",
                            "qc_program",
                            "metadata",
                            "updated_at",
                        ]
                    )
                    entry.file_role = row["file_role"]
                    entry.qc_program = row.get("qc_program", "")
                    entry.expected_filename = row["expected_filename"]
                    entry.hye_pair_label = row.get("hye_pair_label", "")
                    entry.notes = row.get("notes", "")
                    entry.metadata = {
                        **(entry.metadata or {}),
                        **metadata,
                        "sample_name": sample.name,
                        "sample_external_id": sample.external_id,
                        "watcher_match_key": row["expected_filename"],
                    }
                    entry.save()
                else:
                    run = Run.objects.create(
                        sample=sample,
                        run_name=run_name,
                        status=row.get("status", RunStatus.PLANNED),
                        file_role=row["file_role"],
                        qc_program=row.get("qc_program", ""),
                        expected_filename=row["expected_filename"],
                        worklist_position=row["position"],
                        hye_pair_label=row.get("hye_pair_label", ""),
                        metadata={**metadata, "expected_filename": row["expected_filename"]},
                    )
                    entry = WorklistEntry.objects.create(
                        worklist=worklist,
                        run=run,
                        position=row["position"],
                        file_role=row["file_role"],
                        qc_program=row.get("qc_program", ""),
                        expected_filename=row["expected_filename"],
                        hye_pair_label=row.get("hye_pair_label", ""),
                        block_label=f"Block {math.ceil(row['position'] / 24)}",
                        notes=row.get("notes", ""),
                        metadata={
                            **metadata,
                            "sample_name": sample.name,
                            "sample_external_id": sample.external_id,
                            "watcher_match_key": row["expected_filename"],
                        },
                    )
                samples.append(sample)
                runs.append(run)
                entries.append(entry)

        return Response(
            {
                "worklist": AcquisitionWorklistSerializer(worklist).data,
                "samples_imported": len({sample.id for sample in samples}),
                "runs_imported": len({run.id for run in runs}),
                "worklist_entries_imported": len({entry.id for entry in entries}),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="queue-ready-runs")
    def queue_ready_runs(self, request, pk=None):
        project = self.get_object()
        experiment = _resolve_experiment_for_project(
            project_id=project.id,
            experiment_id=_int_or_none(request.data.get("experiment") or request.query_params.get("experiment")),
        )
        if (request.data.get("experiment") or request.query_params.get("experiment")) and experiment is None:
            raise ValidationError({"experiment": "Experiment does not belong to this project."})
        raw_files = RawFile.objects.filter(
            run__sample__experiment__project=project,
            run__isnull=False,
            run__processing_jobs__isnull=True,
        ).select_related("run")
        if experiment:
            raw_files = raw_files.filter(run__sample__experiment=experiment)
        queued_jobs = []
        for raw_file in raw_files:
            job = _queue_processing_job_for_raw_file(raw_file)
            if job:
                queued_jobs.append(job)

        return Response(
            {
                "queued": len(queued_jobs),
                "jobs": ProcessingJobSerializer(queued_jobs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="queue-runs")
    def queue_runs(self, request, pk=None):
        project = self.get_object()
        serializer = QueueRunsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run_ids = serializer.validated_data["run_ids"]
        experiment = _resolve_experiment_for_project(
            project_id=project.id,
            experiment_id=_int_or_none(request.data.get("experiment") or request.query_params.get("experiment")),
        )
        if (request.data.get("experiment") or request.query_params.get("experiment")) and experiment is None:
            raise ValidationError({"experiment": "Experiment does not belong to this project."})
        raw_files = RawFile.objects.filter(
            run__sample__experiment__project=project,
            run_id__in=run_ids,
            run__isnull=False,
            run__processing_jobs__isnull=True,
        ).select_related("run")
        if experiment:
            raw_files = raw_files.filter(run__sample__experiment=experiment)
        queued_jobs = []
        for raw_file in raw_files:
            job = _queue_processing_job_for_raw_file(raw_file)
            if job:
                queued_jobs.append(job)

        return Response(
            {
                "requested": len(set(run_ids)),
                "queued": len(queued_jobs),
                "jobs": ProcessingJobSerializer(queued_jobs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="rerun-latest-diann-batch")
    def rerun_latest_diann_batch(self, request, pk=None):
        project = self.get_object()
        try:
            result = rerun_latest_diann_batch(project_code=project.code)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="pre-acquisition-setup")
    def pre_acquisition_setup(self, request):
        serializer = ProjectPreAcquisitionSetupSerializer(data=request.data, context={"request": request})
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

    @action(detail=False, methods=["post"], url_path="pre-acquisition-preflight")
    def pre_acquisition_preflight(self, request):
        serializer = ProjectPreAcquisitionSetupSerializer(data=request.data, context={"request": request})
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

        parameters = self._build_diann_pipeline_parameters(data)
        validation_errors = validate_diann_pipeline_settings(parameters, allow_performance_tags=True)
        normalized = normalize_diann_settings(parameters)
        tags = normalized.get("tags") or {}
        sample_count = int(data["sample_count"] or 0)
        planned_runs = sample_count + (sample_count // data["hye_interval"]) * 2 if data["hye_interval"] else sample_count
        source = "site_defaults"
        source_label = "Draft setup preview"
        source_detail = "This preview reflects the draft setup, including site-controlled performance tags, before project creation."

        return Response(
            {
                "title": data["title"],
                "code": data["code"],
                "source": source,
                "source_label": source_label,
                "source_detail": source_detail,
                "lab": LabSerializer(lab).data,
                "instrument_configuration": InstrumentConfigurationSerializer(configuration).data if configuration else None,
                "sample_count": sample_count,
                "healthy_count": data["healthy_count"],
                "diseased_count": data["diseased_count"],
                "hye_interval": data["hye_interval"],
                "planned_runs": planned_runs,
                "processing_preset": data["processing_preset"],
                "diann_version": data["diann_version"],
                "speclib_mode": _diann_speclib_mode(data["processing_preset"]),
                "reference_assets": parameters.get("reference_assets", {}),
                "settings": normalized,
                "performance_tags": tags.get("performance") or {},
                "experimental_tags": tags.get("experimental") or {},
                "options": _diann_command_options(parameters),
                "validation_errors": validation_errors,
                "is_valid": not validation_errors,
            },
            status=status.HTTP_200_OK,
        )

    def _default_lab_for_user(self, user):
        membership = LabMembership.objects.select_related("lab").filter(user=user, active=True).order_by("id").first()
        if membership:
            return membership.lab
        if is_admin(user):
            return Lab.objects.order_by("id").first()
        return None

    def _next_quick_start_code(self, title):
        prefix = _filename_token(title)[:12] or "PROJECT"
        today = timezone.now().strftime("%y%m%d")
        base = f"{prefix}-{today}"
        candidate = base
        index = 1
        while Project.objects.filter(code=candidate).exists():
            index += 1
            candidate = f"{base}-{index}"
        return candidate

    def _build_diann_pipeline_parameters(self, data):
        reference_assets = _resolve_reference_assets(data)
        preset_name = _normalize_diann_preset_name(data.get("processing_preset", ""))
        preset_settings = normalize_diann_settings(_diann_settings_for_preset(preset_name))
        user_settings = normalize_diann_settings(_ensure_dict(data.get("diann_settings"), field_name="diann_settings"))
        merged_settings = {
            **{key: value for key, value in preset_settings.items() if key != "tags"},
            **{key: value for key, value in user_settings.items() if key != "tags"},
        }
        performance_tags = {
            **(preset_settings.get("tags", {}).get("performance") or {}),
            **(user_settings.get("tags", {}).get("performance") or {}),
            **site_performance_tags(),
        }
        performance_tags.setdefault("threads", 1)
        experimental_tags = {
            **(preset_settings.get("tags", {}).get("experimental") or {}),
            **(user_settings.get("tags", {}).get("experimental") or {}),
        }
        effective_settings = {
            **merged_settings,
            **experimental_tags,
            **performance_tags,
            "tags": {
                "performance": performance_tags,
                "experimental": experimental_tags,
            },
        }
        speclib_mode = _diann_speclib_mode(preset_name)
        temp_value = str((effective_settings.get("tags", {}).get("performance") or {}).get("temp") or "").strip()
        fasta_path = str(effective_settings.get("fasta") or reference_assets["fasta_path"])
        library_path = str(effective_settings.get("library") or "")
        library_source = ""
        out_library = str(effective_settings.get("out_library") or "")
        generate_speclib = _boolish(effective_settings.get("generate_speclib"))
        fasta_search = _boolish(effective_settings.get("fasta_search"))
        if speclib_mode == "reuse":
            library_source = "preferred_speclib_path"
            fasta_path = ""
            library_path = ""
            out_library = ""
            generate_speclib = False
            fasta_search = False
        elif speclib_mode == "smoke":
            fasta_path = ""
            library_path = ""
            out_library = ""
            generate_speclib = False
            fasta_search = False
        effective_settings = {
            **effective_settings,
            "fasta": fasta_path,
            "library": library_path,
            "library_source": library_source,
            "out_library": out_library,
            "generate_speclib": generate_speclib,
            "fasta_search": fasta_search,
        }
        parameters = {
            "engine": "diann",
            "adapter": "diann",
            "required_engine": "diann",
            "required_engine_version": data.get("diann_version", ""),
            "executable": "diann",
            "version_command": ["diann"],
            "report": str(effective_settings.get("report") or "diann-first-pass.parquet"),
            "fasta": fasta_path,
            "library": library_path,
            "library_source": library_source,
            "out_library": out_library,
            "generate_speclib": generate_speclib,
            "fasta_search": fasta_search,
            "fasta_path": reference_assets["fasta_path"],
            "speclib_path": reference_assets["speclib_path"],
            "reference_assets": reference_assets,
            "processing_preset": preset_name,
            "settings": effective_settings,
            "tags": effective_settings["tags"],
            "options": _diann_command_options(effective_settings),
            "project_level_rollup": {
                "enabled": True,
                "mode": "combine_runs_after_run_level_processing",
                "future_executor": "supercomputer",
            },
        }
        if temp_value:
            parameters["temp"] = temp_value
        return resolve_pipeline_parameters(parameters, engine="diann")

    def _create_or_update_diann_pipeline(self, data):
        parameters = self._build_diann_pipeline_parameters(data)
        pipeline, _created = ProcessingPipeline.objects.update_or_create(
            name="DIA-NN",
            version=data["diann_version"],
            defaults={
                "container_image": "ghcr.io/rtklab-byu/msconnect-diann:latest",
                "parameters": parameters,
            },
        )
        return pipeline

    def _build_diann_preflight(self, project, experiment=None):
        worklist = (
            AcquisitionWorklist.objects.filter(experiment__project=project)
            .order_by("-updated_at", "-created_at")
            .first()
        )
        if experiment:
            worklist = (
                AcquisitionWorklist.objects.filter(experiment=experiment)
                .order_by("-updated_at", "-created_at")
                .first()
            )
        pipeline = None
        if worklist:
            pipeline_id = (worklist.metadata or {}).get("processing_pipeline_id")
            if pipeline_id:
                pipeline = ProcessingPipeline.objects.filter(pk=pipeline_id).first()

        if pipeline:
            parameters = pipeline.parameters or {}
            processing_preset = str(parameters.get("processing_preset") or "")
            diann_version = pipeline.version
            speclib_mode = _diann_speclib_mode(processing_preset)
            source = "project_pipeline"
            source_label = "Project pipeline"
            source_detail = f"Using processing pipeline {pipeline.name} {pipeline.version}."
        else:
            parameters = self._build_diann_pipeline_parameters(
                {
                    "organisms": ["human", "yeast", "ecoli"],
                    "diann_settings": {},
                    "diann_version": "preview",
                    "processing_preset": DIANN_PRESET_SPECLIB_BUILD,
                }
            )
            processing_preset = DIANN_PRESET_SPECLIB_BUILD
            diann_version = "preview"
            speclib_mode = _diann_speclib_mode(processing_preset)
            source = "site_defaults"
            source_label = "Site defaults"
            source_detail = "No project pipeline is configured yet, so this preview reflects the active site defaults."

        validation_errors = validate_diann_pipeline_settings(parameters, allow_performance_tags=True)
        normalized = normalize_diann_settings(parameters)
        tags = normalized.get("tags") or {}
        return {
            "project": ProjectSerializer(project).data,
            "source": source,
            "source_label": source_label,
            "source_detail": source_detail,
            "worklist": AcquisitionWorklistSerializer(worklist).data if worklist else None,
            "pipeline": ProcessingPipelineSerializer(pipeline).data if pipeline else None,
            "processing_preset": processing_preset,
            "diann_version": diann_version,
            "speclib_mode": speclib_mode,
            "reference_assets": parameters.get("reference_assets", {}),
            "settings": normalized,
            "performance_tags": tags.get("performance") or {},
            "experimental_tags": tags.get("experimental") or {},
            "options": _diann_command_options(parameters),
            "validation_errors": validation_errors,
            "is_valid": not validation_errors,
        }

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

        def add_entry(sample, role=RunFileRole.SAMPLE, hye_pair_label="", qc_program=""):
            nonlocal position
            position += 1
            sample_well = sample.metadata.get("well") or _well_for_position(position, data["plate_type"])
            well_metadata = _well_coordinates(str(sample_well))
            expected_filename = f"{_filename_token(project.code)}_{position:03d}_{_filename_token(sample.name)}.raw"
            normalized_qc_program = _normalize_qc_program(qc_program, role)
            run = Run.objects.create(
                sample=sample,
                configuration=configuration,
                run_name=f"{project.code}-{position:03d}-{sample.name}",
                status=RunStatus.PLANNED,
                file_role=role,
                qc_program=normalized_qc_program,
                expected_filename=expected_filename,
                worklist_position=position,
                hye_pair_label=hye_pair_label,
                metadata={
                    "setup_source": "pre_acquisition_setup",
                    "expected_filename": expected_filename,
                    "qc_program": normalized_qc_program,
                    "synthetic_peptides_present": normalized_qc_program == QcProgram.PRTC,
                    "plate_type": data["plate_type"],
                    **well_metadata,
                },
            )
            entry = WorklistEntry.objects.create(
                worklist=worklist,
                run=run,
                position=position,
                file_role=role,
                qc_program=normalized_qc_program,
                expected_filename=expected_filename,
                hye_pair_label=hye_pair_label,
                block_label=f"Block {math.ceil(position / 24)}",
                metadata={
                    "setup_source": "pre_acquisition_setup",
                    "qc_program": normalized_qc_program,
                    "synthetic_peptides_present": normalized_qc_program == QcProgram.PRTC,
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
                add_entry(hye_samples["HYE-A"], role=RunFileRole.HYE, hye_pair_label=label, qc_program=QcProgram.HYE)
                add_entry(hye_samples["HYE-B"], role=RunFileRole.HYE, hye_pair_label=label, qc_program=QcProgram.HYE)

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

        mine_filter = self.request.query_params.get("mine")
        if mine_filter and _boolish(mine_filter):
            queryset = queryset.filter(submitted_by_id=self.request.user.id)

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

    def create(self, request, *args, **kwargs):
        if not is_admin(request.user):
            lab_id = _int_or_none(request.data.get("lab"))
            if lab_id is not None:
                self._enforce_lab_scope(user=request.user, lab_id=lab_id)
        return super().create(request, *args, **kwargs)

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

    @action(detail=False, methods=["get"], url_path="metrics")
    def metrics(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can view intake reporting metrics.")

        queryset = self.filter_queryset(self.get_queryset())
        rows = list(
            queryset.values("institution_name", "status")
            .annotate(count=Count("id"), sample_volume=Sum("sample_count_estimate"))
            .order_by("institution_name", "status")
        )
        totals = {
            "requests": queryset.count(),
            "sample_count_estimate": sum(item.sample_count_estimate or 0 for item in queryset),
            "approved": queryset.filter(status=IntakeRequestStatus.APPROVED).count(),
            "rejected": queryset.filter(status=IntakeRequestStatus.REJECTED).count(),
            "in_review": queryset.filter(status=IntakeRequestStatus.IN_REVIEW).count(),
            "submitted": queryset.filter(status=IntakeRequestStatus.SUBMITTED).count(),
        }
        by_institution = {}
        for intake in queryset:
            key = intake.institution_name or intake.lab.name
            entry = by_institution.setdefault(
                key,
                {
                    "institution_name": key,
                    "count": 0,
                    "sample_count_estimate": 0,
                    "approved": 0,
                    "rejected": 0,
                    "in_review": 0,
                    "submitted": 0,
                },
            )
            entry["count"] += 1
            entry["sample_count_estimate"] += intake.sample_count_estimate or 0
            entry[intake.status] += 1

        return Response(
            {
                "totals": totals,
                "by_institution": sorted(by_institution.values(), key=lambda row: row["institution_name"]),
                "status_rows": rows,
            }
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


class RawFileArchiveViewSet(AuthenticatedModelViewSet):
    queryset = RawFileArchive.objects.select_related(
        "raw_file",
        "raw_file__run",
        "raw_file__run__sample",
        "raw_file__run__sample__experiment",
        "raw_file__run__sample__experiment__project",
    )
    serializer_class = RawFileArchiveSerializer
    scope_lab_lookup = "raw_file__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "raw_file.run.sample.experiment.project.lab"
    search_fields = ("raw_file__filename", "archive_path", "original_storage_path", "checksum_sha256")
    ordering_fields = ("status", "compression", "size_bytes", "archived_at", "restored_at", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        raw_file_filter = self.request.query_params.get("raw_file")
        if raw_file_filter:
            queryset = queryset.filter(raw_file_id=raw_file_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class RawFileArchiveCopyViewSet(AuthenticatedModelViewSet):
    queryset = RawFileArchiveCopy.objects.select_related(
        "archive",
        "archive__raw_file",
        "archive__raw_file__run",
        "archive__raw_file__run__sample",
        "archive__raw_file__run__sample__experiment",
        "archive__raw_file__run__sample__experiment__project",
    )
    serializer_class = RawFileArchiveCopySerializer
    scope_lab_lookup = "archive__raw_file__run__sample__experiment__project__lab_id"
    write_scope_lab_path = "archive.raw_file.run.sample.experiment.project.lab"
    search_fields = ("archive__raw_file__filename", "path", "storage_root", "checksum_sha256")
    ordering_fields = ("status", "copy_role", "size_bytes", "verified_at", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        archive_filter = self.request.query_params.get("archive")
        if archive_filter:
            queryset = queryset.filter(archive_id=archive_filter)
        raw_file_filter = self.request.query_params.get("raw_file")
        if raw_file_filter:
            queryset = queryset.filter(archive__raw_file_id=raw_file_filter)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


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
        intended_filename = PurePath(
            str(request.data.get("expected_filename") or request.data.get("intended_filename") or "")
        ).name

        try:
            size_bytes = int(request.data.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"size_bytes": "A positive size_bytes value is required."}) from exc
        if size_bytes <= 0:
            raise ValidationError({"size_bytes": "A positive size_bytes value is required."})

        delivery_mode = str(request.data.get("delivery_mode") or "direct").strip().lower()
        if delivery_mode not in {"direct", "watcher"}:
            raise ValidationError({"delivery_mode": "delivery_mode must be direct or watcher."})

        run_id = request.data.get("run") or None
        if run_id and not Run.objects.filter(pk=run_id, sample__experiment__project=project).exists():
            raise ValidationError({"run": "Run must belong to the selected project."})
        if not run_id and intended_filename:
            matched_run = _resolve_run_for_expected_filename(project_id=project.id, filename=intended_filename)
            if matched_run:
                run_id = matched_run.id
        matched_run = Run.objects.filter(pk=run_id, sample__experiment__project=project).select_related(
            "sample", "sample__experiment"
        ).first() if run_id else None

        if matched_run:
            diann_validation_errors = _validate_diann_pipeline_for_run(matched_run)
            if diann_validation_errors:
                raise ValidationError({"diann_settings": diann_validation_errors})

        file_role = request.data.get("file_role") or (matched_run.file_role if matched_run else RunFileRole.SAMPLE)
        if file_role not in {value for value, _label in RunFileRole.choices}:
            raise ValidationError({"file_role": "Invalid file role."})
        if matched_run:
            file_role = matched_run.file_role

        chunk_size_bytes = int(request.data.get("chunk_size_bytes") or 8 * 1024 * 1024)
        chunk_count = max(1, math.ceil(size_bytes / chunk_size_bytes))
        upload_id = uuid.uuid4()
        session = DirectUploadSession.objects.create(
            project=project,
            run_id=run_id,
            upload_id=upload_id,
            filename=filename,
            intended_filename=intended_filename,
            storage_key=f"projects/{project.code}/uploads/{timezone.now():%Y%m%d}/{upload_id}/{filename}",
            content_type=request.data.get("content_type", ""),
            size_bytes=size_bytes,
            chunk_size_bytes=chunk_size_bytes,
            chunk_count=chunk_count,
            file_role=file_role,
            status=DirectUploadStatus.CREATED,
            match_metadata={
                "intended_filename": intended_filename,
                "matched_run_id": matched_run.id if matched_run else None,
                "match_source": "expected_filename" if intended_filename else "run" if run_id else "project_only",
                "delivery_mode": delivery_mode,
            },
            metadata={**_ensure_dict(request.data.get("metadata"), field_name="metadata"), "delivery_mode": delivery_mode},
        )
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path=r"chunks/(?P<part_number>\d+)")
    def upload_chunk(self, request, pk=None, part_number=None):
        session = self.get_object()
        if session.status == DirectUploadStatus.COMPLETE:
            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_200_OK)

        try:
            part_number = int(part_number)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"part_number": "part_number must be a positive integer."}) from exc
        if part_number < 1 or part_number > session.chunk_count:
            raise ValidationError({"part_number": "part_number is out of range for this upload session."})

        payload = request.body or b""
        if not payload:
            raise ValidationError({"chunk": "Chunk payload is required."})

        expected_size = min(session.chunk_size_bytes, session.size_bytes - (part_number - 1) * session.chunk_size_bytes)
        if len(payload) != expected_size:
            raise ValidationError(
                {
                    "chunk": (
                        f"Chunk {part_number} must be {expected_size} bytes; received {len(payload)} bytes."
                    )
                }
            )

        chunk_path = _direct_upload_chunk_path(session, part_number)
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        if chunk_path.exists() and chunk_path.read_bytes() == payload:
            session.status = DirectUploadStatus.UPLOADING
            session.save(update_fields=["status", "updated_at"])
            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_200_OK)

        temp_path = chunk_path.with_suffix(".tmp")
        temp_path.write_bytes(payload)
        temp_path.replace(chunk_path)

        session.status = DirectUploadStatus.UPLOADING
        session.save(update_fields=["status", "updated_at"])
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        session = self.get_object()
        checksum = request.data.get("checksum_sha256", "")
        if len(checksum) != 64:
            raise ValidationError({"checksum_sha256": "A 64-character SHA-256 checksum is required."})

        if session.completed_raw_file_id:
            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_200_OK)

        run = session.run
        if not run and session.intended_filename:
            run = _resolve_run_for_expected_filename(project_id=session.project_id, filename=session.intended_filename)
        if not run:
            run = _resolve_run_for_expected_filename(project_id=session.project_id, filename=session.filename)
        file_role = run.file_role if run else session.file_role
        diann_validation_errors = _validate_diann_pipeline_for_run(run)
        if diann_validation_errors:
            raise ValidationError({"diann_settings": diann_validation_errors})

        chunk_paths = [_direct_upload_chunk_path(session, part_number) for part_number in range(1, session.chunk_count + 1)]
        missing_parts = [str(index + 1) for index, path in enumerate(chunk_paths) if not path.exists()]
        if missing_parts:
            raise ValidationError({"chunks": f"Missing uploaded chunks: {', '.join(missing_parts)}"})

        delivery_root = _direct_upload_delivery_root(session)
        destination = build_storage_path(delivery_root, Path(session.filename), checksum)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_destination = destination.parent / f".{destination.name}.{session.upload_id}.uploading"

        digest = hashlib.sha256()
        size_bytes = 0
        with temp_destination.open("wb") as output_file:
            for path in chunk_paths:
                data = path.read_bytes()
                digest.update(data)
                size_bytes += len(data)
                output_file.write(data)

        assembled_checksum = digest.hexdigest()
        if assembled_checksum != checksum:
            temp_destination.unlink(missing_ok=True)
            raise ValidationError({"checksum_sha256": "Uploaded chunks do not match the provided checksum."})
        if size_bytes != session.size_bytes:
            temp_destination.unlink(missing_ok=True)
            raise ValidationError({"size_bytes": "Uploaded chunks do not match the expected file size."})

        delivery_mode = str((session.metadata or {}).get("delivery_mode") or "direct").strip().lower()
        if delivery_mode == "watcher":
            if destination.exists():
                temp_destination.unlink(missing_ok=True)
                raise ValidationError({"storage_path": "A file already exists at the watcher inbox destination path."})
            shutil.copy2(temp_destination, destination)
            temp_destination.unlink(missing_ok=True)
            session.checksum_sha256 = checksum
            session.status = DirectUploadStatus.COMPLETE
            session.save(update_fields=["checksum_sha256", "status", "updated_at"])
            for path in chunk_paths:
                path.unlink(missing_ok=True)
            _direct_upload_cleanup(session)
            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_200_OK)

        raw_file = RawFile.objects.filter(checksum_sha256=checksum).first()
        if not raw_file:
            if destination.exists():
                temp_destination.unlink(missing_ok=True)
                raise ValidationError({"storage_path": "A file already exists at the destination path."})
            shutil.copy2(temp_destination, destination)
            temp_destination.unlink(missing_ok=True)
            raw_file = RawFile.objects.create(
                run=run,
                source_path=f"direct-upload:{session.upload_id}",
                storage_path=str(destination),
                filename=session.filename,
                checksum_sha256=checksum,
                size_bytes=session.size_bytes,
                imported_at=timezone.now(),
                status=RawFileStatus.IMPORTED,
                file_role=file_role,
                match_confidence=1.0 if run else 0.0,
                metadata={
                    "direct_upload_session": session.id,
                    "direct_upload_storage_key": session.storage_key,
                    "intended_filename": session.intended_filename,
                    "file_role": file_role,
                    "matched_run_id": run.id if run else None,
                    **session.metadata,
                },
            )
        else:
            temp_destination.unlink(missing_ok=True)

        record_raw_file_import(
            raw_file,
            message="Raw file completed through direct upload delivery.",
            payload={
                "direct_upload_session_id": session.id,
                "storage_path": str(destination),
                "checksum_sha256": checksum,
                "size_bytes": session.size_bytes,
                "delivery_mode": delivery_mode,
            },
        )
        with transaction.atomic():
            if run:
                processing_job = _queue_processing_job_for_raw_file(raw_file)
                _queue_spectra_conversion_job_for_raw_file(raw_file, processing_job=processing_job)
            else:
                _record_file_match_exception(
                    raw_file,
                    reason="Upload was stored but could not be matched to a planned run.",
                    project=session.project,
                    metadata=session.match_metadata,
                )
                processing_job = None
        session.checksum_sha256 = checksum
        session.completed_raw_file = raw_file
        session.status = DirectUploadStatus.COMPLETE
        session.save(update_fields=["checksum_sha256", "completed_raw_file", "status", "updated_at"])
        for path in chunk_paths:
            path.unlink(missing_ok=True)
        _direct_upload_cleanup(session)
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


class PipelineEventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (permissions.IsAuthenticated,)
    queryset = PipelineEvent.objects.select_related("project", "experiment", "actor")
    serializer_class = PipelineEventSerializer
    pagination_class = OptionalPageNumberPagination
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("created_at", "event_type")
    ordering = ("-created_at", "-id")

    def get_queryset(self):
        queryset = super().get_queryset()
        if not is_admin(self.request.user):
            queryset = queryset.filter(project__lab_id__in=active_lab_ids(self.request.user))
        project = self.request.query_params.get("project")
        experiment = self.request.query_params.get("experiment")
        event_type = self.request.query_params.get("event_type")
        if project:
            queryset = queryset.filter(project_id=project)
        if experiment:
            queryset = queryset.filter(experiment_id=experiment)
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        return queryset


class ProcessingPipelineViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingPipeline.objects.all()
    serializer_class = ProcessingPipelineSerializer
    write_requires_admin = True
    search_fields = ("name", "version", "container_image")
    ordering_fields = ("name", "version", "created_at", "updated_at")


class DeploymentReleaseViewSet(AuthenticatedModelViewSet):
    queryset = DeploymentRelease.objects.all()
    serializer_class = DeploymentReleaseSerializer
    write_requires_admin = True
    search_fields = ("version", "channel", "image", "digest", "release_notes")
    ordering_fields = ("version", "channel", "active", "created_at", "updated_at")

    @action(detail=True, methods=["post"])
    def promote(self, request, pk=None):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can promote deployment releases.")
        release = self.get_object()
        DeploymentRelease.objects.filter(channel=release.channel, active=True).exclude(pk=release.pk).update(active=False)
        release.active = True
        release.save(update_fields=["active", "updated_at"])
        record_pipeline_event(
            event_type=PipelineEventType.SETTINGS_UPDATED, actor=request.user,
            message=f"Promoted release {release.version}",
            payload={"release_id": release.id, "action": "promote", "channel": release.channel},
        )
        return Response(self.get_serializer(release).data)

    @action(detail=True, methods=["post"])
    def rollout(self, request, pk=None):
        """Set desired state and ask selected agents to perform an upgrade."""
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can roll out deployment releases.")
        release = self.get_object()
        node_ids = request.data.get("node_ids")
        if node_ids is not None and (not isinstance(node_ids, list) or not node_ids):
            raise ValidationError({"node_ids": "Provide a non-empty list of node IDs, or omit it for all nodes."})
        nodes = ProcessingNode.objects.all()
        if node_ids is not None:
            nodes = nodes.filter(id__in=node_ids)
            if nodes.count() != len(set(node_ids)):
                raise ValidationError({"node_ids": "One or more processing nodes do not exist."})
        control_parameters = {
            "profile": release.version,
            "release_version": release.version,
            "image": release.image,
            "digest": release.digest,
            "channel": release.channel,
        }
        requested_at = timezone.now().isoformat()
        for node in nodes:
            node.desired_release = release
            node.release_status = "pending"
            node.release_error = ""
            node.metadata = {
                **(node.metadata or {}),
                "control": {
                    "id": str(uuid.uuid4()),
                    "command": "upgrade",
                    "status": "requested",
                    "requested_by": request.user.username,
                    "requested_at": requested_at,
                    "reason": str(request.data.get("reason") or "").strip(),
                    "parameters": control_parameters,
                },
            }
            node.save(update_fields=["desired_release", "release_status", "release_error", "metadata", "updated_at"])
        record_pipeline_event(
            event_type=PipelineEventType.SETTINGS_UPDATED, actor=request.user,
            message=f"Rolled out release {release.version}",
            payload={"release_id": release.id, "action": "rollout", "node_ids": [node.id for node in nodes]},
        )
        return Response(
            {
                "release": self.get_serializer(release).data,
                "nodes": ProcessingNodeSerializer(nodes, many=True).data,
                "requested_at": requested_at,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Verify rollout health and optionally queue rollback for failed nodes."""
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can verify deployment releases.")
        release = self.get_object()
        node_ids = request.data.get("node_ids")
        nodes = ProcessingNode.objects.filter(desired_release=release)
        if node_ids is not None:
            if not isinstance(node_ids, list) or not node_ids:
                raise ValidationError({"node_ids": "Provide a non-empty list of node IDs."})
            nodes = nodes.filter(id__in=node_ids)
        stale_seconds = max(30, int(request.data.get("stale_seconds") or 180))
        rollback = request.data.get("rollback", True) is not False
        previous = (
            DeploymentRelease.objects.filter(channel=release.channel)
            .exclude(pk=release.pk)
            .order_by("-created_at")
            .first()
        )
        now = timezone.now()
        results = []
        for node in nodes:
            healthy = (
                node.reported_release == release.version
                and node.release_status == "current"
                and node.last_heartbeat_at
                and (now - node.last_heartbeat_at).total_seconds() <= stale_seconds
            )
            if healthy:
                results.append({"node_id": node.id, "status": "healthy", "release": release.version})
                continue
            if rollback and previous:
                node.desired_release = previous
                node.release_status = "rollback_pending"
                node.release_error = f"Release {release.version} failed verification."
                node.metadata = {
                    **(node.metadata or {}),
                    "control": {
                        "id": str(uuid.uuid4()),
                        "command": "upgrade",
                        "status": "requested",
                        "requested_by": request.user.username,
                        "requested_at": now.isoformat(),
                        "reason": "Automatic rollback after failed release verification.",
                        "parameters": {
                            "profile": previous.version,
                            "release_version": previous.version,
                            "image": previous.image,
                            "digest": previous.digest,
                            "channel": previous.channel,
                        },
                    },
                }
                node.save(update_fields=["desired_release", "release_status", "release_error", "metadata", "updated_at"])
                results.append({"node_id": node.id, "status": "rollback_pending", "release": previous.version})
            else:
                node.release_status = "failed"
                node.release_error = f"Release {release.version} failed verification."
                node.save(update_fields=["release_status", "release_error", "updated_at"])
                results.append({"node_id": node.id, "status": "failed", "release": release.version})
        record_pipeline_event(
            event_type=PipelineEventType.SETTINGS_UPDATED, actor=request.user,
            message=f"Verified release {release.version}",
            payload={"release_id": release.id, "action": "verify", "results": results},
        )
        if any(result["status"] in {"failed", "rollback_pending"} for result in results):
            send_notification(
                subject=f"MSConnect release verification: {release.version}",
                message=f"Release {release.version} verification produced failures. Results: {json.dumps(results)}",
            )
        return Response({"release": release.version, "results": results, "rollback_release": previous.version if previous else None})


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

    @action(detail=True, methods=["post"], url_path="control")
    def control(self, request, pk=None):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can control processing nodes.")
        node = self.get_object()
        command = str(request.data.get("command") or "").strip()
        valid_commands = {"start", "pause", "resume", "drain", "restart", "stop", "upgrade", "reconfigure"}
        if command not in valid_commands:
            raise ValidationError({"command": "Unsupported processing-node command."})
        parameters = request.data.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise ValidationError({"parameters": "Command parameters must be an object."})
        if command in {"upgrade", "reconfigure"} and not parameters.get("profile"):
            raise ValidationError({"parameters": "An approved profile is required for upgrade or reconfigure."})
        reason = str(request.data.get("reason") or "").strip()
        control = {
            "id": str(uuid.uuid4()),
            "command": command,
            "status": "requested",
            "requested_by": request.user.username,
            "requested_at": timezone.now().isoformat(),
            "reason": reason,
            "parameters": parameters,
        }
        node.metadata = {**(node.metadata or {}), "control": control}
        node.save(update_fields=["metadata", "updated_at"])
        return Response(ProcessingNodeSerializer(node).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="mark-offline")
    def mark_offline(self, request, pk=None):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can mark processing nodes offline.")
        node = self.get_object()
        node.status = ProcessingNodeStatus.OFFLINE
        node.metadata = {
            **(node.metadata or {}),
            "control": {
                "id": str(uuid.uuid4()),
                "command": "mark-offline",
                "status": "applied",
                "requested_by": request.user.username,
                "requested_at": timezone.now().isoformat(),
                "reason": str(request.data.get("reason") or "").strip(),
            },
        }
        node.save(update_fields=["status", "metadata", "updated_at"])
        return Response(ProcessingNodeSerializer(node).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def overview(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        now = timezone.now()
        stale_count = sum(
            1
            for node in queryset
            if not node.last_heartbeat_at or (now - node.last_heartbeat_at).total_seconds() > 180
        )
        return Response(
            {
                "total": queryset.count(),
                "by_status": list(queryset.values("status").annotate(count=Count("id")).order_by("status")),
                "by_type": list(queryset.values("node_type").annotate(count=Count("id")).order_by("node_type")),
                "stale": stale_count,
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
