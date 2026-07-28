from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Project

from ...services import prepare_project_workspace


class Command(BaseCommand):
    help = "Prepare a Claude Findings Workflow workspace for an MSConnect project."

    def add_arguments(self, parser):
        parser.add_argument("project", help="Project ID or project code.")
        parser.add_argument("--root", help="Workspace root. Defaults to MSCONNECT_FINDINGS_WORKSPACE_ROOT or ./findings_workspaces.")
        parser.add_argument("--mode", choices=("personal", "shared"), default="personal")
        parser.add_argument("--data-strategy", choices=("manifest", "symlink"), default="manifest")

    def handle(self, *args, **options):
        project = self._project(options["project"])
        summary = prepare_project_workspace(
            project,
            root=Path(options["root"]).expanduser() if options.get("root") else None,
            mode=options["mode"],
            data_strategy=options["data_strategy"],
        )
        self.stdout.write(self.style.SUCCESS(f"Workspace ready: {summary.workspace.workspace_path}"))
        self.stdout.write(f"Created paths: {len(summary.created_paths)}")
        self.stdout.write(f"Kept/updated paths: {len(summary.kept_paths)}")
        self.stdout.write("Open Claude Code in that directory and run /findings-workflow:init.")

    def _project(self, value: str) -> Project:
        queryset = Project.objects.select_related("lab", "pi")
        if value.isdigit():
            project = queryset.filter(pk=int(value)).first()
        else:
            project = queryset.filter(code=value).first()
        if not project:
            raise CommandError(f"Project not found: {value}")
        return project
