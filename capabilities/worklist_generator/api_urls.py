from django.urls import path

from . import views


urlpatterns = [
    path("metadata/", views.MetadataTemplateView.as_view(), name="worklist-metadata"),
    path("worklist-template/", views.WorklistTemplateView.as_view(), name="worklist-template"),
    path("generate/", views.WorklistGenerateView.as_view(), name="worklist-generate"),
    path(
        "download/<uuid:job_id>/<str:filename>/",
        views.WorklistDownloadView.as_view(),
        name="worklist-download",
    ),
]
