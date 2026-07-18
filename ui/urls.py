from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="project_list"),
    path("projects", views.ProjectListView.as_view(), name="project_list"),
    path("projects/<int:pk>", views.ProjectDetailView.as_view(), name="project_detail"),
    path("showcase", views.ShowcaseDashboardView.as_view(), name="showcase_dashboard"),
    path("showcase/design", views.ExperimentalDesignView.as_view(), name="showcase_design"),
    path("showcase/acquisition", views.AcquisitionMonitorView.as_view(), name="showcase_acquisition"),
    path("showcase/results", views.ResultsTelemetryView.as_view(), name="showcase_results"),
    path("showcase/processing", views.ProcessingOverviewView.as_view(), name="showcase_processing_default"),
    path("showcase/qc", views.QCDashboardView.as_view(), name="showcase_qc_default"),
    path("showcase/worklists/<int:pk>", views.WorklistDetailView.as_view(), name="showcase_worklist"),
    path(
        "showcase/worklists/<int:pk>/acquisition",
        views.AcquisitionMonitorView.as_view(),
        name="showcase_acquisition",
    ),
    path("showcase/worklists/<int:pk>/results", views.ResultsTelemetryView.as_view(), name="showcase_results"),
    path("showcase/worklists/<int:pk>/processing", views.ProcessingOverviewView.as_view(), name="showcase_processing"),
    path("showcase/worklists/<int:pk>/qc", views.QCDashboardView.as_view(), name="showcase_qc"),
    path("intake/new", views.IntakeCreateView.as_view(), name="intake_new"),
    path("intake", views.IntakeListView.as_view(), name="intake_list"),
    path("intake/<int:pk>", views.IntakeDetailView.as_view(), name="intake_detail"),
    path("intake/<int:pk>/review", views.IntakeReviewView.as_view(), name="intake_review"),
    path("projects/pre-acq", views.PreAcquisitionProjectListView.as_view(), name="projects_pre_acq"),
]
