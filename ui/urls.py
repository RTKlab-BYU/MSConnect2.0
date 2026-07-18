from django.urls import path, re_path
from django.views.generic import RedirectView

app_name = "ui"

urlpatterns = [
    path("", RedirectView.as_view(url="/app/projects", permanent=True), name="project_list"),
    path("projects", RedirectView.as_view(url="/app/projects", permanent=True), name="project_list"),
    path("projects/pre-acq", RedirectView.as_view(url="/app/projects", permanent=True), name="projects_pre_acq"),
    path("projects/<int:pk>", RedirectView.as_view(url="/app/projects/%(pk)s", permanent=True), name="project_detail"),
    path("showcase", RedirectView.as_view(url="/app/projects", permanent=True), name="showcase_dashboard"),
    path("showcase/design", RedirectView.as_view(url="/app/projects", permanent=True), name="showcase_design"),
    path(
        "showcase/acquisition",
        RedirectView.as_view(url="/app/monitoring", permanent=True),
        name="showcase_acquisition",
    ),
    path("showcase/results", RedirectView.as_view(url="/app/projects", permanent=True), name="showcase_results"),
    path(
        "showcase/processing",
        RedirectView.as_view(url="/app/processing", permanent=True),
        name="showcase_processing_default",
    ),
    path("showcase/qc", RedirectView.as_view(url="/app/qc", permanent=True), name="showcase_qc_default"),
    path(
        "showcase/worklists/<int:pk>",
        RedirectView.as_view(url="/app/monitoring", permanent=True),
        name="showcase_worklist",
    ),
    path(
        "showcase/worklists/<int:pk>/acquisition",
        RedirectView.as_view(url="/app/monitoring", permanent=True),
        name="showcase_acquisition",
    ),
    path(
        "showcase/worklists/<int:pk>/results",
        RedirectView.as_view(url="/app/projects", permanent=True),
        name="showcase_results",
    ),
    path(
        "showcase/worklists/<int:pk>/processing",
        RedirectView.as_view(url="/app/processing", permanent=True),
        name="showcase_processing",
    ),
    path("showcase/worklists/<int:pk>/qc", RedirectView.as_view(url="/app/qc", permanent=True), name="showcase_qc"),
    path("intake/new", RedirectView.as_view(url="/app/projects", permanent=True), name="intake_new"),
    path("intake", RedirectView.as_view(url="/app/projects", permanent=True), name="intake_list"),
    path("intake/<int:pk>", RedirectView.as_view(url="/app/projects", permanent=True), name="intake_detail"),
    path("intake/<int:pk>/review", RedirectView.as_view(url="/app/projects", permanent=True), name="intake_review"),
    re_path(r"^.*$", RedirectView.as_view(url="/app/projects", permanent=True), name="ui_fallback"),
]
