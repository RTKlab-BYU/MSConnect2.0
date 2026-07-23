import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    PI = "pi", "PI"
    RESEARCHER = "researcher", "Researcher"
    COLLABORATOR = "collaborator", "Collaborator"


class ProjectStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    COMPLETE = "complete", "Complete"
    ARCHIVED = "archived", "Archived"


class IntakeRequestStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    IN_REVIEW = "in_review", "In Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class InstrumentType(models.TextChoices):
    LC = "lc", "LC"
    MS = "ms", "MS"
    LCMS = "lcms", "LC-MS"
    OTHER = "other", "Other"


class RunStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACQUIRED = "acquired", "Acquired"
    IMPORTED = "imported", "Imported"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"


class RawFileStatus(models.TextChoices):
    DISCOVERED = "discovered", "Discovered"
    VALIDATED = "validated", "Validated"
    IMPORTED = "imported", "Imported"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"


class RawFileDerivativeType(models.TextChoices):
    MZML = "mzml", "mzML"
    MZMLB = "mzmlb", "mzMLb"
    MGF = "mgf", "MGF"
    SPECTRUM_INDEX = "spectrum_index", "Spectrum index"
    PREVIEW_JSON = "preview_json", "Preview JSON"
    VENDOR_METADATA = "vendor_metadata", "Vendor metadata"


class DerivativeStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class ProcessingArtifactType(models.TextChoices):
    LOG = "log", "Log"
    PROTEIN_TABLE = "protein_table", "Protein table"
    PEPTIDE_TABLE = "peptide_table", "Peptide table"
    DIANN_REPORT = "diann_report", "DIA-NN report"
    FRAGPIPE_OUTPUT = "fragpipe_output", "FragPipe output"
    ENTERPRISE_EXPORT = "enterprise_export", "Enterprise export"
    MATRIX = "matrix", "Matrix"
    RAW_OUTPUT = "raw_output", "Raw output"
    OTHER = "other", "Other"


class ProcessingStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    ASSIGNED = "assigned", "Assigned"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"
    RETRYING = "retrying", "Retrying"


class DirectUploadStatus(models.TextChoices):
    CREATED = "created", "Created"
    UPLOADING = "uploading", "Uploading"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"


class RunFileRole(models.TextChoices):
    SAMPLE = "sample", "Sample"
    QC = "qc", "QC"
    LIBRARY = "library", "Library"
    BLANK = "blank", "Blank"
    WASH = "wash", "Wash"
    CALIBRATION = "calibration", "Calibration"


class WorklistStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    READY = "ready", "Ready"
    ACQUIRING = "acquiring", "Acquiring"
    COMPLETE = "complete", "Complete"


class ProcessingNodeStatus(models.TextChoices):
    OFFLINE = "offline", "Offline"
    IDLE = "idle", "Idle"
    BUSY = "busy", "Busy"
    ERROR = "error", "Error"


class University(TimestampedModel):
    name = models.CharField(max_length=255, unique=True)
    abbreviation = models.CharField(max_length=64, blank=True)
    website = models.URLField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Facility(TimestampedModel):
    university = models.ForeignKey(University, on_delete=models.PROTECT, related_name="facilities")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80)
    contact_email = models.EmailField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("university__name", "name")
        constraints = (
            models.UniqueConstraint(fields=("university", "slug"), name="uniq_facility_slug_per_university"),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.university})"


class Lab(TimestampedModel):
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="labs")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80)
    pi = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pi_labs",
        blank=True,
        null=True,
    )
    billing_code = models.CharField(max_length=128, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("facility__name", "name")
        constraints = (
            models.UniqueConstraint(fields=("facility", "slug"), name="uniq_lab_slug_per_facility"),
        )

    def __str__(self) -> str:
        return self.name


class UserProfile(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    global_role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.RESEARCHER)
    phone = models.CharField(max_length=64, blank=True)

    def __str__(self) -> str:
        return f"{self.user} ({self.get_global_role_display()})"


class LabMembership(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lab_memberships")
    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.RESEARCHER)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("lab__name", "user__username")
        constraints = (
            models.UniqueConstraint(fields=("user", "lab"), name="uniq_user_lab_membership"),
        )

    def __str__(self) -> str:
        return f"{self.user} in {self.lab} as {self.get_role_display()}"


class Instrument(TimestampedModel):
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="instruments")
    nickname = models.CharField(max_length=128)
    instrument_type = models.CharField(max_length=20, choices=InstrumentType.choices)
    manufacturer = models.CharField(max_length=128, blank=True)
    model = models.CharField(max_length=128, blank=True)
    serial_number = models.CharField(max_length=128, blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("facility__name", "nickname")
        constraints = (
            models.UniqueConstraint(fields=("facility", "nickname"), name="uniq_instrument_nickname_per_facility"),
        )

    def __str__(self) -> str:
        return self.nickname


class InstrumentConfiguration(TimestampedModel):
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="instrument_configurations")
    name = models.CharField(max_length=255)
    lc_instrument = models.ForeignKey(
        Instrument,
        on_delete=models.PROTECT,
        related_name="lc_configurations",
        blank=True,
        null=True,
    )
    ms_instrument = models.ForeignKey(
        Instrument,
        on_delete=models.PROTECT,
        related_name="ms_configurations",
        blank=True,
        null=True,
    )
    method_name = models.CharField(max_length=255, blank=True)
    column_description = models.CharField(max_length=255, blank=True)
    gradient_description = models.TextField(blank=True)
    ion_source = models.CharField(max_length=128, blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("facility__name", "name")
        constraints = (
            models.UniqueConstraint(fields=("facility", "name"), name="uniq_configuration_name_per_facility"),
        )

    def clean(self) -> None:
        for field_name, expected_type in (("lc_instrument", InstrumentType.LC), ("ms_instrument", InstrumentType.MS)):
            instrument = getattr(self, field_name)
            if instrument and instrument.instrument_type not in (expected_type, InstrumentType.LCMS):
                raise ValidationError({field_name: f"Expected {expected_type.label} or LC-MS instrument."})

    def __str__(self) -> str:
        return self.name


class Project(TimestampedModel):
    lab = models.ForeignKey(Lab, on_delete=models.PROTECT, related_name="projects")
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=80)
    pi = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_projects")
    status = models.CharField(max_length=32, choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("lab__name", "code")
        constraints = (
            models.UniqueConstraint(fields=("lab", "code"), name="uniq_project_code_per_lab"),
        )

    def __str__(self) -> str:
        return f"{self.code}: {self.title}"


class ProjectIntakeRequest(TimestampedModel):
    lab = models.ForeignKey(Lab, on_delete=models.PROTECT, related_name="intake_requests")
    requested_title = models.CharField(max_length=255)
    requested_code = models.CharField(max_length=80, blank=True)
    requested_pi = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_intakes",
        blank=True,
        null=True,
    )
    objective = models.TextField(blank=True)
    sample_count_estimate = models.PositiveIntegerField(blank=True, null=True)
    acquisition_deadline = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=IntakeRequestStatus.choices, default=IntakeRequestStatus.SUBMITTED)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_intake_requests",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_intake_requests",
        blank=True,
        null=True,
    )
    review_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    promoted_project = models.OneToOneField(
        Project,
        on_delete=models.PROTECT,
        related_name="source_intake_request",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self) -> str:
        return f"Intake {self.id}: {self.requested_title}"

    @property
    def allowed_review_transitions(self):
        return {
            IntakeRequestStatus.SUBMITTED: {IntakeRequestStatus.IN_REVIEW, IntakeRequestStatus.REJECTED},
            IntakeRequestStatus.IN_REVIEW: {IntakeRequestStatus.APPROVED, IntakeRequestStatus.REJECTED},
            IntakeRequestStatus.APPROVED: set(),
            IntakeRequestStatus.REJECTED: set(),
        }

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.allowed_review_transitions.get(self.status, set())

    def transition_to(self, *, new_status: str, reviewer, note: str = "") -> None:
        if not self.can_transition_to(new_status):
            raise ValidationError(f"Invalid transition from {self.status} to {new_status}.")
        self.status = new_status
        self.reviewed_by = reviewer
        self.review_note = note
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "review_note", "reviewed_at", "updated_at"])

    def promote_to_project(self):
        if self.promoted_project_id:
            return self.promoted_project
        if self.status != IntakeRequestStatus.APPROVED:
            raise ValidationError("Only approved intake requests can be promoted to a project.")

        with transaction.atomic():
            intake = ProjectIntakeRequest.objects.select_for_update().select_related("lab").get(pk=self.pk)
            if intake.promoted_project_id:
                return intake.promoted_project

            preferred_pi = intake.requested_pi or intake.lab.pi or intake.reviewed_by or intake.submitted_by
            candidate_code = intake.requested_code or f"INTAKE-{intake.id}"
            unique_code = candidate_code
            suffix = 1
            while Project.objects.filter(lab_id=intake.lab_id, code=unique_code).exists():
                suffix += 1
                unique_code = f"{candidate_code}-{suffix}"

            project = Project.objects.create(
                lab=intake.lab,
                title=intake.requested_title,
                code=unique_code,
                pi=preferred_pi,
                status=ProjectStatus.ACTIVE,
                description=intake.objective,
            )
            intake.promoted_project = project
            intake.save(update_fields=["promoted_project", "updated_at"])
            self.promoted_project = project
            return project


class Experiment(TimestampedModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="experiments")
    name = models.CharField(max_length=255)
    hypothesis = models.TextField(blank=True)
    started_on = models.DateField(blank=True, null=True)
    ended_on = models.DateField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_experiments",
        blank=True,
        null=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("project__code", "name")
        constraints = (
            models.UniqueConstraint(fields=("project", "name"), name="uniq_experiment_name_per_project"),
        )

    def __str__(self) -> str:
        return self.name


class Sample(TimestampedModel):
    experiment = models.ForeignKey(Experiment, on_delete=models.PROTECT, related_name="samples")
    name = models.CharField(max_length=255)
    external_id = models.CharField(max_length=128, blank=True)
    species = models.CharField(max_length=128, blank=True)
    matrix = models.CharField(max_length=128, blank=True)
    digestion_protocol = models.CharField(max_length=255, blank=True)
    enrichment_protocol = models.CharField(max_length=255, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_samples",
        blank=True,
        null=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("experiment__name", "name")
        constraints = (
            models.UniqueConstraint(fields=("experiment", "name"), name="uniq_sample_name_per_experiment"),
        )

    def __str__(self) -> str:
        return self.name


class Run(TimestampedModel):
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="runs")
    configuration = models.ForeignKey(
        InstrumentConfiguration,
        on_delete=models.PROTECT,
        related_name="runs",
        blank=True,
        null=True,
    )
    run_name = models.CharField(max_length=255)
    acquired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acquired_runs",
        blank=True,
        null=True,
    )
    acquisition_started_at = models.DateTimeField(blank=True, null=True)
    acquisition_ended_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=RunStatus.choices, default=RunStatus.PLANNED)
    file_role = models.CharField(max_length=32, choices=RunFileRole.choices, default=RunFileRole.SAMPLE)
    expected_filename = models.CharField(max_length=255, blank=True)
    worklist_position = models.PositiveIntegerField(blank=True, null=True)
    hye_pair_label = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-acquisition_started_at", "run_name")
        constraints = (
            models.UniqueConstraint(fields=("sample", "run_name"), name="uniq_run_name_per_sample"),
        )

    def __str__(self) -> str:
        return self.run_name


class RawFile(TimestampedModel):
    run = models.ForeignKey(Run, on_delete=models.PROTECT, related_name="raw_files", blank=True, null=True)
    source_path = models.TextField(db_index=True)
    storage_path = models.TextField(unique=True)
    filename = models.CharField(max_length=255)
    checksum_sha256 = models.CharField(max_length=64, unique=True)
    size_bytes = models.PositiveBigIntegerField()
    acquired_at = models.DateTimeField(blank=True, null=True)
    imported_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=RawFileStatus.choices, default=RawFileStatus.DISCOVERED)
    file_role = models.CharField(max_length=32, choices=RunFileRole.choices, default=RunFileRole.SAMPLE)
    match_confidence = models.FloatField(blank=True, null=True)
    failure_reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-imported_at", "filename")

    def __str__(self) -> str:
        return self.filename


class RawFileDerivative(TimestampedModel):
    raw_file = models.ForeignKey(RawFile, on_delete=models.CASCADE, related_name="derivatives")
    derivative_type = models.CharField(max_length=32, choices=RawFileDerivativeType.choices)
    status = models.CharField(max_length=32, choices=DerivativeStatus.choices, default=DerivativeStatus.QUEUED)
    path = models.TextField()
    format = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(blank=True, null=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    created_by_job = models.ForeignKey(
        "ProcessingJob",
        on_delete=models.SET_NULL,
        related_name="raw_file_derivatives",
        blank=True,
        null=True,
    )
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("raw_file", "derivative_type", "-updated_at")
        constraints = (
            models.UniqueConstraint(
                fields=("raw_file", "derivative_type", "path"),
                name="uniq_raw_file_derivative_path",
            ),
        )

    def __str__(self) -> str:
        return f"{self.raw_file.filename} {self.derivative_type}"


class IngestionFailure(TimestampedModel):
    source_path = models.TextField(unique=True, db_index=True)
    filename = models.CharField(max_length=255)
    failure_reason = models.TextField()
    seen_count = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-last_seen_at",)

    def __str__(self) -> str:
        return f"{self.filename}: {self.failure_reason}"


class DirectUploadSession(TimestampedModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="direct_upload_sessions")
    run = models.ForeignKey(Run, on_delete=models.PROTECT, related_name="direct_upload_sessions", blank=True, null=True)
    upload_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    filename = models.CharField(max_length=255)
    storage_key = models.TextField(unique=True)
    content_type = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveBigIntegerField()
    chunk_size_bytes = models.PositiveIntegerField(default=8 * 1024 * 1024)
    chunk_count = models.PositiveIntegerField(default=1)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, choices=DirectUploadStatus.choices, default=DirectUploadStatus.CREATED)
    file_role = models.CharField(max_length=32, choices=RunFileRole.choices, default=RunFileRole.SAMPLE)
    completed_raw_file = models.OneToOneField(
        RawFile,
        on_delete=models.PROTECT,
        related_name="direct_upload_session",
        blank=True,
        null=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-updated_at", "filename")

    def __str__(self) -> str:
        return f"{self.filename} ({self.status})"


class AcquisitionWorklist(TimestampedModel):
    experiment = models.ForeignKey(Experiment, on_delete=models.PROTECT, related_name="worklists")
    name = models.CharField(max_length=255)
    configuration = models.ForeignKey(
        InstrumentConfiguration,
        on_delete=models.PROTECT,
        related_name="worklists",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=32, choices=WorklistStatus.choices, default=WorklistStatus.DRAFT)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_worklists",
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-updated_at", "name")
        constraints = (
            models.UniqueConstraint(fields=("experiment", "name"), name="uniq_worklist_name_per_experiment"),
        )

    def __str__(self) -> str:
        return self.name


class WorklistEntry(TimestampedModel):
    worklist = models.ForeignKey(AcquisitionWorklist, on_delete=models.CASCADE, related_name="entries")
    run = models.OneToOneField(Run, on_delete=models.PROTECT, related_name="worklist_entry")
    position = models.PositiveIntegerField()
    file_role = models.CharField(max_length=32, choices=RunFileRole.choices, default=RunFileRole.SAMPLE)
    expected_filename = models.CharField(max_length=255)
    injection_volume_ul = models.FloatField(blank=True, null=True)
    hye_pair_label = models.CharField(max_length=64, blank=True)
    block_label = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("worklist", "position")
        constraints = (
            models.UniqueConstraint(fields=("worklist", "position"), name="uniq_worklist_position"),
            models.UniqueConstraint(fields=("worklist", "expected_filename"), name="uniq_worklist_expected_filename"),
        )

    def save(self, *args, **kwargs):
        self.run.file_role = self.file_role
        self.run.expected_filename = self.expected_filename
        self.run.worklist_position = self.position
        self.run.hye_pair_label = self.hye_pair_label
        self.run.save(
            update_fields=["file_role", "expected_filename", "worklist_position", "hye_pair_label", "updated_at"]
        )
        super().save(*args, **kwargs)

    @property
    def matched_raw_file(self):
        return self.run.raw_files.order_by("-imported_at", "filename").first()

    def __str__(self) -> str:
        return f"{self.worklist} #{self.position}: {self.expected_filename}"


class ProcessingPipeline(TimestampedModel):
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=128)
    container_image = models.CharField(max_length=255, blank=True)
    parameters = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name", "version")
        constraints = (
            models.UniqueConstraint(fields=("name", "version"), name="uniq_pipeline_name_version"),
        )

    def __str__(self) -> str:
        return f"{self.name} {self.version}"


class ProcessingNode(TimestampedModel):
    name = models.CharField(max_length=128, unique=True)
    node_type = models.CharField(max_length=64, default="diann")
    status = models.CharField(max_length=32, choices=ProcessingNodeStatus.choices, default=ProcessingNodeStatus.OFFLINE)
    container_image = models.CharField(max_length=255, blank=True)
    endpoint_url = models.URLField(blank=True)
    last_heartbeat_at = models.DateTimeField(blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ProcessingJob(TimestampedModel):
    run = models.ForeignKey(Run, on_delete=models.PROTECT, related_name="processing_jobs")
    pipeline = models.ForeignKey(ProcessingPipeline, on_delete=models.PROTECT, related_name="jobs")
    raw_file = models.ForeignKey(RawFile, on_delete=models.PROTECT, related_name="processing_jobs")
    node = models.ForeignKey(
        ProcessingNode,
        on_delete=models.SET_NULL,
        related_name="processing_jobs",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=32, choices=ProcessingStatus.choices, default=ProcessingStatus.QUEUED)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    log_path = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    stats = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.pipeline} on {self.run}"


class ProcessingJobArtifact(TimestampedModel):
    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="artifacts")
    artifact_type = models.CharField(max_length=32, choices=ProcessingArtifactType.choices)
    path = models.TextField()
    format = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(blank=True, null=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    retained = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("job", "artifact_type", "-updated_at")
        constraints = (
            models.UniqueConstraint(fields=("job", "artifact_type", "path"), name="uniq_processing_artifact_path"),
        )

    def __str__(self) -> str:
        return f"{self.job_id} {self.artifact_type}"


class Protein(TimestampedModel):
    accession = models.CharField(max_length=128)
    gene_symbol = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    organism = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ("accession",)
        constraints = (
            models.UniqueConstraint(fields=("accession", "organism"), name="uniq_protein_accession_organism"),
        )

    def __str__(self) -> str:
        return self.accession


class Peptide(TimestampedModel):
    sequence = models.CharField(max_length=1024)
    modified_sequence = models.CharField(max_length=2048, blank=True)
    charge = models.PositiveSmallIntegerField(blank=True, null=True)

    class Meta:
        ordering = ("sequence", "modified_sequence", "charge")
        constraints = (
            models.UniqueConstraint(fields=("sequence", "modified_sequence", "charge"), name="uniq_peptide_variant"),
        )

    def __str__(self) -> str:
        return self.modified_sequence or self.sequence


class ProteinIdentification(TimestampedModel):
    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="protein_identifications")
    protein = models.ForeignKey(Protein, on_delete=models.PROTECT, related_name="identifications")
    score = models.FloatField(blank=True, null=True)
    q_value = models.FloatField(blank=True, null=True)
    coverage_percent = models.FloatField(blank=True, null=True)
    peptide_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("job", "protein"), name="uniq_protein_identification_per_job"),
        )

    def __str__(self) -> str:
        return f"{self.protein} identified in {self.job}"


class PeptideIdentification(TimestampedModel):
    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="peptide_identifications")
    peptide = models.ForeignKey(Peptide, on_delete=models.PROTECT, related_name="identifications")
    score = models.FloatField(blank=True, null=True)
    q_value = models.FloatField(blank=True, null=True)
    retention_time_seconds = models.FloatField(blank=True, null=True)
    mz = models.FloatField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("job", "peptide"), name="uniq_peptide_identification_per_job"),
        )

    def __str__(self) -> str:
        return f"{self.peptide} identified in {self.job}"


class ProteinQuant(TimestampedModel):
    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="protein_quants")
    protein = models.ForeignKey(Protein, on_delete=models.PROTECT, related_name="quants")
    label = models.CharField(max_length=128, default="abundance")
    value = models.FloatField()
    unit = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("job", "protein", "label"), name="uniq_protein_quant_per_job_label"),
        )

    def __str__(self) -> str:
        return f"{self.protein} {self.label}={self.value}"


class PeptideQuant(TimestampedModel):
    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="peptide_quants")
    peptide = models.ForeignKey(Peptide, on_delete=models.PROTECT, related_name="quants")
    label = models.CharField(max_length=128, default="abundance")
    value = models.FloatField()
    unit = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("job", "peptide", "label"), name="uniq_peptide_quant_per_job_label"),
        )

    def __str__(self) -> str:
        return f"{self.peptide} {self.label}={self.value}"
