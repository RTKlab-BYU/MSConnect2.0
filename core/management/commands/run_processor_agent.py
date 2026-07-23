import json
import socket
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient
from core.agents.processor import prepare_job_execution


class Command(BaseCommand):
    help = "Run the processing agent that claims queued jobs from the main API and executes them locally."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=int, default=settings.PROCESSOR_POLL_INTERVAL_SECONDS)
        parser.add_argument("--heartbeat-seconds", type=int, default=settings.MSCONNECT_AGENT_HEARTBEAT_SECONDS)

    def handle(self, *args, **options):
        if not settings.MSCONNECT_AGENT_TOKEN:
            raise CommandError("MSCONNECT_AGENT_TOKEN must be set for the processor agent.")

        client = AgentApiClient(base_url=settings.MSCONNECT_API_BASE_URL, token=settings.MSCONNECT_AGENT_TOKEN)
        agent_name = settings.MSCONNECT_AGENT_NAME or socket.gethostname()
        results_root = Path(settings.RESULTS_ROOT)
        results_root.mkdir(parents=True, exist_ok=True)
        heartbeat_seconds = max(5, int(options["heartbeat_seconds"]))
        last_heartbeat = 0.0

        while True:
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_seconds:
                self._heartbeat(client, agent_name=agent_name, status="idle")
                last_heartbeat = now

            job = client.claim_next_job(node_name=agent_name)
            if not job:
                if options["once"]:
                    break
                time.sleep(max(1, int(options["poll_interval"])))
                continue

            self._heartbeat(client, agent_name=agent_name, status="busy")
            last_heartbeat = time.monotonic()

            try:
                execution = prepare_job_execution(job, results_root=results_root)
                client.start_job(job["id"], node_name=agent_name)
                self._run_job(job, execution, client, agent_name=agent_name)
            except Exception as exc:
                log_path = (results_root / "jobs" / str(job["id"]) / "process.log").resolve()
                failure_payload = {
                    "node_name": agent_name,
                    "error_message": str(exc),
                }
                if log_path.exists():
                    failure_payload["log_path"] = str(log_path)
                client.fail_job(
                    job["id"],
                    failure_payload,
                )
                self.stderr.write(self.style.ERROR(f"job {job['id']} failed: {exc}"))

            self._heartbeat(client, agent_name=agent_name, status="idle")
            last_heartbeat = time.monotonic()
            if options["once"]:
                break

    def _run_job(self, job: dict, execution, client: AgentApiClient, *, agent_name: str):
        execution.log_path.parent.mkdir(parents=True, exist_ok=True)
        with execution.log_path.open("w", encoding="utf-8") as log_file:
            completed = subprocess.run(
                execution.command,
                cwd=execution.working_dir,
                env=execution.env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

        if completed.returncode != 0:
            client.fail_job(
                job["id"],
                {
                    "node_name": agent_name,
                    "error_message": f"Command exited with status {completed.returncode}.",
                    "log_path": str(execution.log_path.resolve()),
                },
            )
            return

        for artifact in (execution.protein_table_path, execution.peptide_table_path, execution.stats_json_path):
            if artifact and not artifact.exists():
                raise CommandError(f"Expected result artifact was not created: {artifact}")
        derivative_payload = []
        for derivative in execution.derivative_files:
            artifact = Path(str(derivative.get("path") or "")).resolve()
            if not artifact.exists():
                raise CommandError(f"Expected derivative artifact was not created: {artifact}")
            derivative_payload.append({**derivative, "path": str(artifact)})
        artifact_payload = []
        for declared_artifact in execution.artifact_files:
            artifact = Path(str(declared_artifact.get("path") or "")).resolve()
            if not artifact.exists():
                raise CommandError(f"Expected processing artifact was not created: {artifact}")
            artifact_payload.append({**declared_artifact, "path": str(artifact)})

        stats_payload = {}
        if execution.stats_json_path:
            with execution.stats_json_path.open("r", encoding="utf-8") as stats_file:
                stats_payload = json.load(stats_file)
            if not isinstance(stats_payload, dict):
                raise CommandError(f"Expected stats JSON object in {execution.stats_json_path}")

        client.complete_job(
            job["id"],
            {
                "node_name": agent_name,
                "log_path": str(execution.log_path.resolve()),
                "protein_table_path": (
                    str(execution.protein_table_path.resolve()) if execution.protein_table_path else ""
                ),
                "peptide_table_path": (
                    str(execution.peptide_table_path.resolve()) if execution.peptide_table_path else ""
                ),
                "delimiter": execution.delimiter or "",
                "derivatives": derivative_payload,
                "artifacts": artifact_payload,
                "stats": stats_payload,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"completed job {job['id']}"))

    def _heartbeat(self, client: AgentApiClient, *, agent_name: str, status: str):
        client.heartbeat(
            name=agent_name,
            node_type="processor",
            status=status,
            container_image=settings.MSCONNECT_IMAGE,
            metadata={"mode": "command-runner"},
            settings={"results_root": settings.RESULTS_ROOT},
        )
