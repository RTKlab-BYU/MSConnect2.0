import socket

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient
from core.agents.diagnostics import agent_token_for_role, marker_fresh


class Command(BaseCommand):
    help = "Healthcheck for long-running watcher or processor agent containers."

    def add_arguments(self, parser):
        parser.add_argument("--role", choices=("watcher", "processor"), required=True)
        parser.add_argument("--agent-name", default=settings.MSCONNECT_AGENT_NAME or socket.gethostname())
        parser.add_argument(
            "--max-age-seconds",
            type=int,
            default=max(90, settings.MSCONNECT_AGENT_HEARTBEAT_SECONDS * 3),
        )
        parser.add_argument("--skip-api", action="store_true")

    def handle(self, *args, **options):
        fresh, detail = marker_fresh(
            agent_name=options["agent_name"],
            max_age_seconds=options["max_age_seconds"],
        )
        if not fresh:
            raise CommandError(detail.get("error") or f"Heartbeat marker is stale: {detail}")

        if not options["skip_api"]:
            token = agent_token_for_role(options["role"])
            if not token:
                raise CommandError("Agent token is not configured.")
            payload = AgentApiClient(
                base_url=settings.MSCONNECT_API_BASE_URL,
                token=token,
                timeout=10,
                retries=1,
            ).ping()
            if payload.get("agent_role") != options["role"]:
                raise CommandError(f"Agent ping returned unexpected role: {payload}")

        self.stdout.write("agent healthcheck ok")
