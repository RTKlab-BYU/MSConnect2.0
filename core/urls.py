from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("universities", api.UniversityViewSet)
router.register("facilities", api.FacilityViewSet)
router.register("labs", api.LabViewSet)
router.register("user-profiles", api.UserProfileViewSet)
router.register("lab-memberships", api.LabMembershipViewSet)
router.register("instruments", api.InstrumentViewSet)
router.register("instrument-configurations", api.InstrumentConfigurationViewSet)
router.register("projects", api.ProjectViewSet)
router.register("intake-requests", api.ProjectIntakeRequestViewSet, basename="intake-request")
router.register("experiments", api.ExperimentViewSet)
router.register("samples", api.SampleViewSet)
router.register("runs", api.RunViewSet)
router.register("raw-files", api.RawFileViewSet)
router.register("processing-pipelines", api.ProcessingPipelineViewSet)
router.register("processing-jobs", api.ProcessingJobViewSet)
router.register("proteins", api.ProteinViewSet)
router.register("peptides", api.PeptideViewSet)
router.register("protein-identifications", api.ProteinIdentificationViewSet)
router.register("peptide-identifications", api.PeptideIdentificationViewSet)
router.register("protein-quants", api.ProteinQuantViewSet)
router.register("peptide-quants", api.PeptideQuantViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
