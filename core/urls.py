from django.http import HttpResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view

from . import api
from .project_assistant import ProjectAssistantMessageView, ProjectAssistantThreadView, ProjectAssistantView


def api_docs(_request):
    return HttpResponse(
        "<!doctype html><html><head><title>MSConnect API</title></head><body>"
        "<h1>MSConnect API</h1><p>Authenticated REST API schema:</p>"
        '<p><a href="/api/schema/">OpenAPI schema</a></p></body></html>',
        content_type="text/html; charset=utf-8",
    )

router = DefaultRouter()
router.register("universities", api.UniversityViewSet)
router.register("facilities", api.FacilityViewSet)
router.register("labs", api.LabViewSet)
router.register("user-profiles", api.UserProfileViewSet)
router.register("lab-memberships", api.LabMembershipViewSet)
router.register("instruments", api.InstrumentViewSet)
router.register("instrument-configurations", api.InstrumentConfigurationViewSet)
router.register("projects", api.ProjectViewSet)
router.register("analysis-presets", api.AnalysisPresetViewSet)
router.register("intake-requests", api.ProjectIntakeRequestViewSet, basename="intake-request")
router.register("experiments", api.ExperimentViewSet)
router.register("samples", api.SampleViewSet)
router.register("runs", api.RunViewSet)
router.register("raw-files", api.RawFileViewSet)
router.register("raw-file-derivatives", api.RawFileDerivativeViewSet)
router.register("raw-file-archives", api.RawFileArchiveViewSet)
router.register("raw-file-archive-copies", api.RawFileArchiveCopyViewSet)
router.register("processing-job-artifacts", api.ProcessingJobArtifactViewSet)
router.register("direct-uploads", api.DirectUploadSessionViewSet)
router.register("sample-manifests", api.SampleManifestViewSet)
router.register("file-match-exceptions", api.FileMatchExceptionViewSet)
router.register("acquisition-worklists", api.AcquisitionWorklistViewSet)
router.register("hye-target-profiles", api.HyeTargetProfileViewSet)
router.register("reference-assets", api.ReferenceAssetViewSet, basename="reference-asset")
router.register("analysis-batches", api.AnalysisBatchViewSet, basename="analysis-batch")
router.register("worklist-entries", api.WorklistEntryViewSet)
router.register("pipeline-events", api.PipelineEventViewSet, basename="pipeline-event")
router.register("processing-pipelines", api.ProcessingPipelineViewSet)
router.register("deployment-releases", api.DeploymentReleaseViewSet)
router.register("processing-nodes", api.ProcessingNodeViewSet)
router.register("acquisition-agents", api.AcquisitionAgentViewSet)
router.register("acquisition-routes", api.AcquisitionRouteViewSet)
router.register("processing-jobs", api.ProcessingJobViewSet)
router.register("proteins", api.ProteinViewSet)
router.register("peptides", api.PeptideViewSet)
router.register("protein-identifications", api.ProteinIdentificationViewSet)
router.register("peptide-identifications", api.PeptideIdentificationViewSet)
router.register("protein-quants", api.ProteinQuantViewSet)
router.register("peptide-quants", api.PeptideQuantViewSet)

urlpatterns = [
    path("schema/", get_schema_view(title="MSConnect API", version="1.0"), name="api-schema"),
    path("docs/", api_docs, name="api-docs"),
    path("projects/<int:project_id>/assistant/", ProjectAssistantView.as_view(), name="project-assistant"),
    path("projects/<int:project_id>/assistant/threads/<int:thread_id>/", ProjectAssistantThreadView.as_view(), name="project-assistant-thread"),
    path("projects/<int:project_id>/assistant/threads/<int:thread_id>/messages/", ProjectAssistantMessageView.as_view(), name="project-assistant-message"),
    path("auth/me/", api.CurrentUserView.as_view()),
    path("auth/signup/", api.SignupView.as_view()),
    path("auth/accept-invitation/", api.AcceptInvitationView.as_view()),
    path("auth/resend-verification/", api.ResendMyVerificationView.as_view()),
    path("admin/user-access/", api.AdminUserAccessView.as_view()),
    path("admin/user-access/<int:user_id>/", api.AdminUserAccessView.as_view()),
    path("admin/user-access/<int:user_id>/resend-email/", api.AdminUserVerificationView.as_view()),
    path("admin/lab-directory/", api.AdminLabDirectoryView.as_view()),
    path("admin/runtime-settings/", api.AdminRuntimeSettingsView.as_view()),
    path("deployment-settings/", api.DeploymentSettingsView.as_view()),
    path("deployment-releases/audit/", api.DeploymentReleaseAuditView.as_view()),
    path("notifications/test/", api.NotificationTestView.as_view()),
    path("intake-requests/metrics/", api.ProjectIntakeRequestViewSet.as_view({"get": "metrics"})),
    path("system-health/", api.SystemHealthView.as_view()),
    path("agents/ping/", api.AgentPingView.as_view()),
    path("agents/config/", api.AgentConfigView.as_view()),
    path("agents/heartbeat/", api.AgentHeartbeatView.as_view()),
    path("agents/raw-files/import/", api.AgentRawFileImportView.as_view()),
    path("agents/ingestion-failures/", api.AgentIngestionFailureView.as_view()),
    path("processing-jobs/claim-next/", api.ProcessingJobClaimView.as_view()),
    path("processing-jobs/<int:pk>/start/", api.ProcessingJobStartView.as_view()),
    path("processing-jobs/<int:pk>/renew/", api.ProcessingJobRenewView.as_view()),
    path("processing-jobs/<int:pk>/complete/", api.ProcessingJobCompleteView.as_view()),
    path("processing-jobs/<int:pk>/fail/", api.ProcessingJobFailView.as_view()),
    path("qc/overview/", api.QcOverviewView.as_view()),
    path("qc/details/", api.QcDetailsView.as_view()),
    path("", include(router.urls)),
]
