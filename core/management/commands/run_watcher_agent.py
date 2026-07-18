import socket
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient, AgentApiError
from ingest.services import (
    DEFAULT_RAW_SUFFIXES,
    build_storage_path,
    discover_raw_paths,
    ensure_copied_raw_path,
    hash_path,
    parse_filename_metadata,
)


class Command(BaseCommand):
    help = "Run the watched-share ingestion agent that reports imports back to the main API."

    def add_arguments(self, parser):
        parser.add_argument("--source", default=settings.INCOMING_RAW_ROOT)
        parser.add_argument("--storage", default=settings.RAW_FILE_STORAGE_ROOT)
        parser.add_argument("--interval", type=int, default=settings.WATCHER_INTERVAL_SECONDS)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--match-run-by-name", action="store_true")
        parser.add_argument("--suffix", action="append", dest="suffixes")
        parser.add_argument("--heartbeat-seconds", type=int, default=settings.MSCONNECT_AGENT_HEARTBEAT_SECONDS)
        parser.add_argument("--no-recursive", action="store_false", dest="recursive")
        parser.set_defaults(recursive=True)

    def handle(self, *args, **options):
        if not settings.MSCONNECT_AGENT_TOKEN:
            raise CommandError("MSCONNECT_AGENT_TOKEN must be set for the watcher agent.")

        source = Path(options["source"])
        storage = Path(options["storage"])
        if not source.exists():
            raise CommandError(f"Source path does not exist: {source}")

        client = AgentApiClient(base_url=settings.MSCONNECT_API_BASE_URL, token=settings.MSCONNECT_AGENT_TOKEN)
        agent_name = settings.MSCONNECT_AGENT_NAME or socket.gethostname()
        heartbeat_seconds = max(5, int(options["heartbeat_seconds"]))
        suffixes = tuple(options["suffixes"] or DEFAULT_RAW_SUFFIXES)
        last_heartbeat = 0.0

        while True:
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_seconds:
                self._heartbeat(client, agent_name=agent_name, status="idle")
                last_heartbeat = now

            candidates = list(discover_raw_paths(source, suffixes=suffixes, recursive=options["recursive"]))
            for path in candidates:
                self._heartbeat(client, agent_name=agent_name, status="busy")
                last_heartbeat = time.monotonic()
                try:
                    checksum_sha256, size_bytes = hash_path(path)
                    destination = build_storage_path(storage, path, checksum_sha256)
                    copied = ensure_copied_raw_path(path, destination)
                    response = client.import_raw_file(
                        {
                            "source_path": str(path.resolve()),
                            "storage_path": str(destination.resolve()),
                            "filename": path.name,
                            "checksum_sha256": checksum_sha256,
                            "size_bytes": size_bytes,
                            "file_role": "sample",
                            "match_run_by_name": options["match_run_by_name"],
                            "metadata": {
                                "importer": "watcher_agent",
                                "copied": copied,
                                "filename_metadata": parse_filename_metadata(path),
                            },
                        }
                    )
                    action = "created" if response["created"] else "reused"
                    self.stdout.write(f"{action} {path} checksum={checksum_sha256}")
                except Exception as exc:
                    failure_payload = {
                        "source_path": str(path),
                        "failure_reason": str(exc),
                        "metadata": {"importer": "watcher_agent"},
                    }
                    try:
                        client.record_ingestion_failure(failure_payload)
                    except AgentApiError as api_exc:
                        self.stderr.write(self.style.ERROR(f"failure reporting error for {path}: {api_exc}"))
                    self.stderr.write(self.style.ERROR(f"failed {path}: {exc}"))

            self._heartbeat(client, agent_name=agent_name, status="idle")
            last_heartbeat = time.monotonic()
            if options["once"]:
                break
            time.sleep(max(1, int(options["interval"])))

    def _heartbeat(self, client: AgentApiClient, *, agent_name: str, status: str):
        client.heartbeat(
            name=agent_name,
            node_type="watcher",
            status=status,
            container_image=settings.MSCONNECT_IMAGE,
            metadata={"mode": "watched-share"},
            settings={"source": settings.INCOMING_RAW_ROOT, "storage": settings.RAW_FILE_STORAGE_ROOT},
        )
