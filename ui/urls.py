from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path("intake/new", views.IntakeCreateView.as_view(), name="intake_new"),
    path("intake", views.IntakeListView.as_view(), name="intake_list"),
    path("intake/<int:pk>", views.IntakeDetailView.as_view(), name="intake_detail"),
    path("intake/<int:pk>/review", views.IntakeReviewView.as_view(), name="intake_review"),
    path("projects/pre-acq", views.PreAcquisitionProjectListView.as_view(), name="projects_pre_acq"),
]
