import socket
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient, AgentApiError
from core.agents.diagnostics import write_heartbeat_marker
from core.agents.discovery import resolve_api_base_url
from core.agents.upgrade import run_upgrade_hook
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
        parser.add_argument("--stability-checks", type=int, default=settings.WATCHER_STABILITY_CHECKS)
        parser.add_argument("--no-recursive", action="store_false", dest="recursive")
        parser.set_defaults(recursive=True)

    def handle(self, *args, **options):
        if not settings.MSCONNECT_AGENT_TOKEN:
            raise CommandError("MSCONNECT_AGENT_TOKEN must be set for the watcher agent.")

        source = Path(options["source"])
        storage = Path(options["storage"])
        if not source.exists():
            raise CommandError(f"Source path does not exist: {source}")

        agent_name = settings.MSCONNECT_AGENT_NAME or socket.gethostname()
        heartbeat_seconds = max(5, int(options["heartbeat_seconds"]))
        suffixes = tuple(options["suffixes"] or DEFAULT_RAW_SUFFIXES)
        last_heartbeat = 0.0
        last_control_id = ""
        control_state = "active"
        stability = {}
        imported_fingerprints = {}
        client = self._resolve_client(role="watcher")

        while True:
            try:
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_seconds:
                    payload = self._heartbeat(client, agent_name=agent_name, status="idle", control_state=control_state)
                    last_control_id, control_state, should_exit = self._handle_control(
                        payload, client=client, agent_name=agent_name, control_state=control_state,
                        last_control_id=last_control_id,
                    )
                    last_heartbeat = now
                    if should_exit:
                        break

                if control_state in {"paused", "draining"}:
                    if options["once"]:
                        break
                    time.sleep(max(1, int(options["interval"])))
                    continue

                candidates = list(discover_raw_paths(source, suffixes=suffixes, recursive=options["recursive"]))
                candidate_paths = {str(path.resolve()) for path in candidates}
                stability = {key: value for key, value in stability.items() if key in candidate_paths}
                imported_fingerprints = {key: value for key, value in imported_fingerprints.items() if key in candidate_paths}
                for path in candidates:
                    key = str(path.resolve())
                    fingerprint = _acquisition_fingerprint(path)
                    if fingerprint is None:
                        continue
                    if imported_fingerprints.get(key) == fingerprint:
                        continue
                    previous_fingerprint, count = stability.get(key, (None, 0))
                    count = count + 1 if previous_fingerprint == fingerprint else 1
                    stability[key] = (fingerprint, count)
                    if count < max(1, int(options["stability_checks"])):
                        self.stdout.write(f"waiting for stable acquisition {path} ({count}/{options['stability_checks']})")
                        continue
                    self._heartbeat(client, agent_name=agent_name, status="busy", control_state=control_state)
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
                        imported_fingerprints[key] = fingerprint
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

                payload = self._heartbeat(client, agent_name=agent_name, status="idle", control_state=control_state)
                last_control_id, control_state, should_exit = self._handle_control(
                    payload, client=client, agent_name=agent_name, control_state=control_state,
                    last_control_id=last_control_id,
                )
                last_heartbeat = time.monotonic()
                if options["once"] or should_exit:
                    break
                time.sleep(max(1, int(options["interval"])))
            except AgentApiError as exc:
                self.stderr.write(self.style.WARNING(f"watcher agent re-discovering Django: {exc}"))
                client = self._resolve_client(role="watcher")
                time.sleep(min(10, max(1, int(options["interval"]))))

    def _heartbeat(self, client: AgentApiClient, *, agent_name: str, status: str, control_state: str, metadata=None):
        response = client.heartbeat(
            name=agent_name,
            node_type="watcher",
            status=status,
            container_image=settings.MSCONNECT_IMAGE,
            metadata={"mode": "watched-share", "control_state": control_state, **(metadata or {})},
            settings={"source": settings.INCOMING_RAW_ROOT, "storage": settings.RAW_FILE_STORAGE_ROOT},
            release_version=settings.MSCONNECT_RELEASE_VERSION,
        )
        write_heartbeat_marker(agent_name=agent_name, role="watcher", status=status, node_type="watcher")
        return response

    def _handle_control(self, payload, *, client, agent_name, control_state, last_control_id):
        control = (payload or {}).get("active_control") or {}
        control_id = str(control.get("id") or "")
        if not control_id or control_id == last_control_id:
            return last_control_id, control_state, False
        command = str(control.get("command") or "")
        if command in {"pause"}:
            next_state, should_exit = "paused", False
        elif command in {"resume", "start"}:
            next_state, should_exit = "active", False
        elif command == "drain":
            next_state, should_exit = "draining", False
        elif command == "restart":
            next_state, should_exit = "restarting", True
        elif command == "upgrade":
            result = run_upgrade_hook(settings.MSCONNECT_UPGRADE_HOOK, control.get("parameters") or {})
            next_state, should_exit = ("restarting", True) if result["status"] == "succeeded" else ("error", False)
            self._heartbeat(
                client, agent_name=agent_name, status="offline" if should_exit else "error",
                control_state=next_state, metadata={"ack_control_id": control_id, "upgrade_result": result},
            )
            return control_id, next_state, should_exit
        elif command in {"stop", "reconfigure"}:
            next_state, should_exit = "stopped", True
        else:
            return control_id, control_state, False
        self._heartbeat(
            client, agent_name=agent_name, status="offline" if should_exit else "idle", control_state=next_state
        )
        return control_id, next_state, should_exit

    def _resolve_client(self, *, role: str):
        base_url = resolve_api_base_url(role=role, token=settings.MSCONNECT_AGENT_TOKEN, configured_base_url=settings.MSCONNECT_API_BASE_URL)
        if not base_url:
            raise CommandError("Unable to locate the Django API. Set MSCONNECT_API_BASE_URL or discovery hosts.")
        return AgentApiClient(base_url=base_url, token=settings.MSCONNECT_AGENT_TOKEN)


def _acquisition_fingerprint(path: Path):
    """Return a cheap completeness fingerprint without reading the acquisition payload."""
    try:
        path = Path(path)
        if path.is_file():
            stat = path.stat()
            return ("file", stat.st_size, stat.st_mtime_ns)
        if path.is_dir():
            count = 0
            total_size = 0
            newest_mtime = 0
            for child in path.rglob("*"):
                if child.is_file():
                    stat = child.stat()
                    count += 1
                    total_size += stat.st_size
                    newest_mtime = max(newest_mtime, stat.st_mtime_ns)
            return ("directory", count, total_size, newest_mtime)
    except OSError:
        return None
    return None
