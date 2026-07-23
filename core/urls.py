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
router.register("raw-file-derivatives", api.RawFileDerivativeViewSet)
router.register("processing-job-artifacts", api.ProcessingJobArtifactViewSet)
router.register("direct-uploads", api.DirectUploadSessionViewSet)
router.register("acquisition-worklists", api.AcquisitionWorklistViewSet)
router.register("worklist-entries", api.WorklistEntryViewSet)
router.register("processing-pipelines", api.ProcessingPipelineViewSet)
router.register("processing-nodes", api.ProcessingNodeViewSet)
router.register("processing-jobs", api.ProcessingJobViewSet)
router.register("proteins", api.ProteinViewSet)
router.register("peptides", api.PeptideViewSet)
router.register("protein-identifications", api.ProteinIdentificationViewSet)
router.register("peptide-identifications", api.PeptideIdentificationViewSet)
router.register("protein-quants", api.ProteinQuantViewSet)
router.register("peptide-quants", api.PeptideQuantViewSet)

urlpatterns = [
    path("agents/heartbeat/", api.AgentHeartbeatView.as_view()),
    path("agents/raw-files/import/", api.AgentRawFileImportView.as_view()),
    path("agents/ingestion-failures/", api.AgentIngestionFailureView.as_view()),
    path("processing-jobs/claim-next/", api.ProcessingJobClaimView.as_view()),
    path("processing-jobs/<int:pk>/start/", api.ProcessingJobStartView.as_view()),
    path("processing-jobs/<int:pk>/complete/", api.ProcessingJobCompleteView.as_view()),
    path("processing-jobs/<int:pk>/fail/", api.ProcessingJobFailView.as_view()),
    path("qc/overview/", api.QcOverviewView.as_view()),
    path("qc/details/", api.QcDetailsView.as_view()),
    path("", include(router.urls)),
]
