from django.conf import settings
from django.db import models

from core.models import Project, TimestampedModel


class FindingsWorkspaceStatus(models.TextChoices):
    PREPARED = "prepared", "Prepared"
    ACTIVE = "active", "Active"
    INDEXED = "indexed", "Indexed"
    ERROR = "error", "Error"


class FindingsWorkspace(TimestampedModel):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="findings_workspace")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="findings_workspaces",
        blank=True,
        null=True,
    )
    mode = models.CharField(max_length=32, default="personal")
    data_strategy = models.CharField(max_length=32, default="manifest")
    root_path = models.TextField()
    workspace_path = models.TextField(unique=True)
    status = models.CharField(
        max_length=32,
        choices=FindingsWorkspaceStatus.choices,
        default=FindingsWorkspaceStatus.PREPARED,
    )
    plugin_marketplace = models.CharField(max_length=255, default="mriffle/findings-ai-collab-workflow")
    plugin_name = models.CharField(max_length=128, default="findings-workflow")
    plugin_version = models.CharField(max_length=64, blank=True)
    findings_count = models.PositiveIntegerField(default=0)
    reports_count = models.PositiveIntegerField(default=0)
    latest_report_path = models.TextField(blank=True)
    last_indexed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("project__code",)

    def __str__(self) -> str:
        return f"{self.project.code} Findings Workflow"
