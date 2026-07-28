from pathlib import Path

from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Project
from core.permissions import active_lab_ids, is_admin

from .models import FindingsWorkspace
from .services import default_workspace_root, index_workspace_outputs, prepare_project_workspace


class FindingsWorkspaceSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    walkthrough_path = serializers.SerializerMethodField()
    claude_commands = serializers.SerializerMethodField()

    class Meta:
        model = FindingsWorkspace
        fields = (
            "id",
            "project",
            "project_code",
            "project_title",
            "mode",
            "data_strategy",
            "root_path",
            "workspace_path",
            "status",
            "plugin_marketplace",
            "plugin_name",
            "plugin_version",
            "findings_count",
            "reports_count",
            "latest_report_path",
            "last_indexed_at",
            "error_message",
            "metadata",
            "walkthrough_path",
            "claude_commands",
            "created_at",
            "updated_at",
        )

    def get_walkthrough_path(self, obj):
        return str(Path(obj.workspace_path) / "README.md")

    def get_claude_commands(self, obj):
        return [
            "/plugin marketplace add mriffle/findings-ai-collab-workflow",
            "/plugin install findings-workflow@findings-workflow",
            "/findings-workflow:init",
            "/findings-workflow:setup-env",
            "/findings-workflow:stage0-science",
            "/findings-workflow:status",
        ]


class PrepareWorkspaceSerializer(serializers.Serializer):
    root_path = serializers.CharField(required=False, allow_blank=True)
    mode = serializers.ChoiceField(choices=("personal", "shared"), default="personal")
    data_strategy = serializers.ChoiceField(choices=("manifest", "symlink"), default="manifest")


class FindingsWorkspaceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id: int):
        project = accessible_project(request.user, project_id)
        workspace = getattr(project, "findings_workspace", None)
        if not workspace:
            return Response(
                {
                    "workspace": None,
                    "default_root_path": str(default_workspace_root()),
                    "claude_commands": [
                        "/plugin marketplace add mriffle/findings-ai-collab-workflow",
                        "/plugin install findings-workflow@findings-workflow",
                        "/findings-workflow:init",
                    ],
                }
            )
        return Response({"workspace": FindingsWorkspaceSerializer(workspace).data, "default_root_path": str(default_workspace_root())})

    def post(self, request, project_id: int):
        project = accessible_project(request.user, project_id)
        serializer = PrepareWorkspaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        root = serializer.validated_data.get("root_path") or None
        try:
            summary = prepare_project_workspace(
                project,
                root=Path(root).expanduser() if root else None,
                created_by=request.user,
                mode=serializer.validated_data["mode"],
                data_strategy=serializer.validated_data["data_strategy"],
            )
        except OSError as exc:
            raise ValidationError({"workspace": str(exc)}) from exc

        return Response(
            {
                "workspace": FindingsWorkspaceSerializer(summary.workspace).data,
                "created_paths": summary.created_paths,
                "kept_paths": summary.kept_paths,
            },
            status=status.HTTP_201_CREATED,
        )


class FindingsWorkspaceIndexView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, workspace_id: int):
        workspace = get_object_or_404(FindingsWorkspace.objects.select_related("project"), pk=workspace_id)
        ensure_project_access(request.user, workspace.project)
        workspace = index_workspace_outputs(workspace)
        return Response({"workspace": FindingsWorkspaceSerializer(workspace).data})


def accessible_project(user, project_id: int) -> Project:
    project = get_object_or_404(Project.objects.select_related("lab", "pi"), pk=project_id)
    ensure_project_access(user, project)
    return project


def ensure_project_access(user, project: Project) -> None:
    if is_admin(user):
        return
    if project.lab_id not in active_lab_ids(user):
        raise PermissionDenied("You do not have access to this project.")
