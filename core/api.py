from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from .models import (
    Experiment,
    Facility,
    Instrument,
    InstrumentConfiguration,
    Lab,
    LabMembership,
    Peptide,
    PeptideIdentification,
    PeptideQuant,
    ProcessingJob,
    ProcessingPipeline,
    Project,
    Protein,
    ProteinIdentification,
    ProteinQuant,
    RawFile,
    Run,
    Sample,
    University,
    UserProfile,
)
from .permissions import RoleScopedWritePermission, active_lab_ids, is_admin


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


class ProcessingPipelineSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProcessingPipeline


class ProcessingJobSerializer(BaseSerializer):
    class Meta(BaseSerializer.Meta):
        model = ProcessingJob


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


class AuthenticatedModelViewSet(viewsets.ModelViewSet):
    permission_classes = (RoleScopedWritePermission,)
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


class UniversityViewSet(AuthenticatedModelViewSet):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    scope_lab_lookup = "facilities__labs__id"


class FacilityViewSet(AuthenticatedModelViewSet):
    queryset = Facility.objects.select_related("university")
    serializer_class = FacilitySerializer
    scope_lab_lookup = "labs__id"


class LabViewSet(AuthenticatedModelViewSet):
    queryset = Lab.objects.select_related("facility", "pi")
    serializer_class = LabSerializer
    scope_lab_lookup = "id"
    write_scope_facility_path = "facility"


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


class InstrumentConfigurationViewSet(AuthenticatedModelViewSet):
    queryset = InstrumentConfiguration.objects.select_related("facility", "lc_instrument", "ms_instrument")
    serializer_class = InstrumentConfigurationSerializer
    scope_lab_lookup = "facility__labs__id"
    write_scope_facility_path = "facility"


class ProjectViewSet(AuthenticatedModelViewSet):
    queryset = Project.objects.select_related("lab", "pi")
    serializer_class = ProjectSerializer
    scope_lab_lookup = "lab_id"
    write_scope_lab_path = "lab"


class ExperimentViewSet(AuthenticatedModelViewSet):
    queryset = Experiment.objects.select_related("project", "created_by")
    serializer_class = ExperimentSerializer
    scope_lab_lookup = "project__lab_id"
    write_scope_lab_path = "project.lab"


class SampleViewSet(AuthenticatedModelViewSet):
    queryset = Sample.objects.select_related("experiment", "submitted_by")
    serializer_class = SampleSerializer
    scope_lab_lookup = "experiment__project__lab_id"
    write_scope_lab_path = "experiment.project.lab"


class RunViewSet(AuthenticatedModelViewSet):
    queryset = Run.objects.select_related("sample", "configuration", "acquired_by")
    serializer_class = RunSerializer
    scope_lab_lookup = "sample__experiment__project__lab_id"
    write_scope_lab_path = "sample.experiment.project.lab"


class RawFileViewSet(AuthenticatedModelViewSet):
    queryset = RawFile.objects.select_related("run")
    serializer_class = RawFileSerializer
    scope_lab_lookup = "run__sample__experiment__project__lab_id"
    write_scope_lab_path = "run.sample.experiment.project.lab"


class ProcessingPipelineViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingPipeline.objects.all()
    serializer_class = ProcessingPipelineSerializer
    write_requires_admin = True


class ProcessingJobViewSet(AuthenticatedModelViewSet):
    queryset = ProcessingJob.objects.select_related("run", "pipeline", "raw_file")
    serializer_class = ProcessingJobSerializer
    scope_lab_lookup = "run__sample__experiment__project__lab_id"
    write_scope_lab_path = "run.sample.experiment.project.lab"


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
