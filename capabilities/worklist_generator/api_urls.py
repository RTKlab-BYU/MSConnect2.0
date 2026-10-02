from django.urls import path

from . import views


urlpatterns = [
    path("generate/", views.WorklistGenerateView.as_view(), name="worklist-generate"),
    path(
        "download/<uuid:job_id>/<str:filename>/",
        views.WorklistDownloadView.as_view(),
        name="worklist-download",
    ),
]
