import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a Django capability app under capabilities/ and add MSConnect starter files."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Python package name, for example diann_tools or spectral_library")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow adding starter files to an existing app folder.",
        )

    def handle(self, *args, **options):
        app_name = options["name"].strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", app_name):
            raise CommandError("Capability name must be a valid lowercase Python package name.")

        capabilities_root = Path(settings.BASE_DIR) / "capabilities"
        target = capabilities_root / app_name
        if target.exists() and not options["force"]:
            raise CommandError(f"{target} already exists. Use --force to add/update starter files.")

        capabilities_root.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.mkdir()
            call_command("startapp", app_name, str(target))

        (target / "apps.py").write_text(_apps_template(app_name), encoding="utf-8")
        self._write_if_missing(target / "api_urls.py", _api_urls_template(app_name))
        self._write_if_missing(target / "services.py", _services_template(app_name))
        management_commands = target / "management" / "commands"
        management_commands.mkdir(parents=True, exist_ok=True)
        self._write_if_missing(target / "management" / "__init__.py", "")
        self._write_if_missing(management_commands / "__init__.py", "")
        self._write_if_missing(management_commands / f"run_{app_name}.py", _command_template(app_name))
        self._write_if_missing(target / "README.md", _readme_template(app_name))
        self.stdout.write(self.style.SUCCESS(f"Capability app ready: capabilities/{app_name}"))
        self.stdout.write("Restart/rebuild the Django container so settings can discover the new app.")

    def _write_if_missing(self, path: Path, contents: str):
        if path.exists():
            return
        path.write_text(contents, encoding="utf-8")


def _api_urls_template(app_name: str) -> str:
    return f'''"""API routes for the {app_name} capability.

Add DRF routers or path() entries here. MSConnect auto-includes this module at:
/api/capabilities/{app_name.replace("_", "-")}/
"""

from django.urls import path

urlpatterns = [
    # path("status/", views.StatusView.as_view(), name="{app_name}-status"),
]
'''


def _apps_template(app_name: str) -> str:
    class_name = "".join(part.capitalize() for part in app_name.split("_"))
    return f"""from django.apps import AppConfig


class {class_name}Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "capabilities.{app_name}"
    label = "{app_name}"
"""


def _services_template(app_name: str) -> str:
    return f'''"""Service-layer code for the {app_name} capability.

Keep tool-specific command construction, file parsing, and external-service calls here.
Core models should be imported at the boundary rather than copied into this app.
"""
'''


def _command_template(app_name: str) -> str:
    class_name = "".join(part.capitalize() for part in app_name.split("_"))
    return f'''from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the {app_name} capability worker or one-shot task."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("{class_name} capability command is installed."))
'''


def _readme_template(app_name: str) -> str:
    return f"""# {app_name}

This is an MSConnect capability app.

Expected layout:

- `models.py`: capability-specific persisted data only.
- `services.py`: tool wrappers, parsers, and pure service logic.
- `api_urls.py`: API routes auto-mounted under `/api/capabilities/{app_name.replace("_", "-")}/`.
- `management/commands/`: Django commands for workers, imports, one-shot processors, and maintenance tasks.
- `tests.py` or `tests/`: capability tests.

Use core models such as `ProcessingPipeline`, `ProcessingJob`, `RawFile`, `RawFileDerivative`,
and `ProcessingJobArtifact` instead of duplicating project/run/raw-file concepts.
"""
