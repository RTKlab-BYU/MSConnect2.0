import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.diagnostics import run_agent_checks


class Command(BaseCommand):
    help = "Check agent networking, auth, and shared storage before running watcher or processor loops."

    def add_arguments(self, parser):
        parser.add_argument("--role", choices=("watcher", "processor"), required=True)
        parser.add_argument("--engine", default=settings.MSCONNECT_PROCESSOR_ENGINE)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--write-test", action="store_true")

    def handle(self, *args, **options):
        result = run_agent_checks(
            role=options["role"],
            engine=options["engine"],
            write_test=options["write_test"],
        )
        if options["json"]:
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"agent runtime preflight: {'ok' if result['ok'] else 'failed'}")
            for name, check in result["checks"].items():
                marker = "ok" if check["ok"] else "failed"
                detail = check.get("error") or check.get("path") or check.get("host") or ""
                self.stdout.write(f"- {name}: {marker} {detail}".rstrip())
        if not result["ok"]:
            raise CommandError("Agent runtime preflight failed.")
