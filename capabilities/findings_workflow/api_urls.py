from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:project_id>/workspace/", views.FindingsWorkspaceView.as_view(), name="findings-workspace"),
    path("workspaces/<int:workspace_id>/index/", views.FindingsWorkspaceIndexView.as_view(), name="findings-workspace-index"),
]
