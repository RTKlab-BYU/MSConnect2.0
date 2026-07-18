from django.contrib import admin

from .models import (
    AcquisitionWorklist,
    DirectUploadSession,
    Experiment,
    Facility,
    IngestionFailure,
    Instrument,
    InstrumentConfiguration,
    Lab,
    LabMembership,
    Peptide,
    PeptideIdentification,
    PeptideQuant,
    ProcessingJob,
    ProcessingNode,
    ProcessingPipeline,
    Project,
    ProjectIntakeRequest,
    Protein,
    ProteinIdentification,
    ProteinQuant,
    RawFile,
    Run,
    Sample,
    University,
    UserProfile,
    WorklistEntry,
)


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "active", "updated_at")
    search_fields = ("name", "abbreviation")
    list_filter = ("active",)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "university", "slug", "active")
    search_fields = ("name", "slug", "university__name")
    list_filter = ("active", "university")


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ("name", "facility", "pi", "active")
    search_fields = ("name", "slug", "pi__username", "facility__name")
    list_filter = ("active", "facility")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "global_role", "phone")
    search_fields = ("user__username", "user__email", "phone")
    list_filter = ("global_role",)


@admin.register(LabMembership)
class LabMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "lab", "role", "active")
    search_fields = ("user__username", "lab__name")
    list_filter = ("role", "active", "lab")


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ("nickname", "instrument_type", "manufacturer", "model", "facility", "active")
    search_fields = ("nickname", "manufacturer", "model", "serial_number")
    list_filter = ("instrument_type", "facility", "active")


@admin.register(InstrumentConfiguration)
class InstrumentConfigurationAdmin(admin.ModelAdmin):
    list_display = ("name", "facility", "lc_instrument", "ms_instrument", "active")
    search_fields = ("name", "method_name", "column_description")
    list_filter = ("facility", "active")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "lab", "pi", "status")
    search_fields = ("code", "title", "lab__name", "pi__username")
    list_filter = ("status", "lab")


@admin.register(ProjectIntakeRequest)
class ProjectIntakeRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "requested_title", "lab", "status", "submitted_by", "reviewed_by", "promoted_project")
    search_fields = ("requested_title", "requested_code", "submitted_by__username", "lab__name")
    list_filter = ("status", "lab")


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "started_on", "ended_on")
    search_fields = ("name", "project__code", "project__title")
    list_filter = ("project__lab",)


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("name", "external_id", "experiment", "species", "submitted_by")
    search_fields = ("name", "external_id", "species", "experiment__name")
    list_filter = ("species", "experiment__project__lab")


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("worklist_position", "run_name", "sample", "file_role", "configuration", "status")
    search_fields = ("run_name", "expected_filename", "sample__name", "configuration__name")
    list_filter = ("status", "file_role", "configuration", "sample__experiment__project__lab")


@admin.register(RawFile)
class RawFileAdmin(admin.ModelAdmin):
    list_display = ("filename", "run", "file_role", "status", "match_confidence", "size_bytes", "imported_at")
    search_fields = ("filename", "checksum_sha256", "source_path", "storage_path")
    list_filter = ("status", "file_role", "run__sample__experiment__project__lab")
    readonly_fields = ("checksum_sha256", "size_bytes", "imported_at")


@admin.register(IngestionFailure)
class IngestionFailureAdmin(admin.ModelAdmin):
    list_display = ("filename", "failure_reason", "seen_count", "last_seen_at")
    search_fields = ("filename", "source_path", "failure_reason")
    readonly_fields = ("source_path", "filename", "seen_count", "last_seen_at", "created_at", "updated_at")


@admin.register(DirectUploadSession)
class DirectUploadSessionAdmin(admin.ModelAdmin):
    list_display = ("filename", "project", "status", "file_role", "size_bytes", "completed_raw_file", "updated_at")
    search_fields = ("filename", "storage_key", "checksum_sha256", "project__code", "run__run_name")
    list_filter = ("status", "file_role", "project__lab")
    readonly_fields = ("upload_id", "storage_key", "chunk_count", "completed_raw_file", "created_at", "updated_at")


@admin.register(ProcessingPipeline)
class ProcessingPipelineAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "container_image")
    search_fields = ("name", "version", "container_image")


@admin.register(ProcessingNode)
class ProcessingNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "node_type", "status", "container_image", "last_heartbeat_at")
    search_fields = ("name", "node_type", "container_image", "endpoint_url")
    list_filter = ("node_type", "status")


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("run", "pipeline", "raw_file", "node", "status", "started_at", "finished_at")
    search_fields = ("run__run_name", "pipeline__name", "raw_file__filename", "node__name")
    list_filter = ("status", "pipeline", "node")


@admin.register(AcquisitionWorklist)
class AcquisitionWorklistAdmin(admin.ModelAdmin):
    list_display = ("name", "experiment", "configuration", "status", "generated_by", "updated_at")
    search_fields = ("name", "experiment__name", "experiment__project__code")
    list_filter = ("status", "configuration", "experiment__project__lab")


@admin.register(WorklistEntry)
class WorklistEntryAdmin(admin.ModelAdmin):
    list_display = ("worklist", "position", "expected_filename", "file_role", "run", "hye_pair_label")
    search_fields = ("expected_filename", "run__run_name", "run__sample__name")
    list_filter = ("file_role", "worklist__experiment__project__lab")


@admin.register(Protein)
class ProteinAdmin(admin.ModelAdmin):
    list_display = ("accession", "gene_symbol", "organism")
    search_fields = ("accession", "gene_symbol", "description", "organism")


@admin.register(Peptide)
class PeptideAdmin(admin.ModelAdmin):
    list_display = ("sequence", "modified_sequence", "charge")
    search_fields = ("sequence", "modified_sequence")


admin.site.register(ProteinIdentification)
admin.site.register(PeptideIdentification)
admin.site.register(ProteinQuant)
admin.site.register(PeptideQuant)
