import hashlib
import mimetypes
import socket
import time
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient, AgentApiError
from core.agents.diagnostics import write_heartbeat_marker
from core.agents.discovery import resolve_api_base_url
from core.management.commands.run_watcher_agent import _acquisition_fingerprint


class Command(BaseCommand):
    help = "Upload stable instrument acquisitions directly to MSConnect over the resumable upload API."

    def add_arguments(self, parser):
        parser.add_argument("--source", default=settings.MSCONNECT_UPLOAD_SOURCE_ROOT)
        parser.add_argument("--project-id", default=settings.MSCONNECT_UPLOAD_PROJECT_ID)
        parser.add_argument("--interval", type=int, default=settings.WATCHER_INTERVAL_SECONDS)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--stability-checks", type=int, default=settings.WATCHER_STABILITY_CHECKS)
        parser.add_argument("--chunk-size", type=int, default=settings.MSCONNECT_UPLOAD_CHUNK_SIZE_BYTES)

    def handle(self, *args, **options):
        if not settings.MSCONNECT_AGENT_TOKEN:
            raise CommandError("MSCONNECT_AGENT_TOKEN must be set for the direct upload agent.")
        source = Path(options["source"])
        if not source.exists():
            raise CommandError(f"Upload source path does not exist: {source}")
        try:
            project_id = int(options["project_id"])
        except (TypeError, ValueError) as exc:
            raise CommandError("--project-id or MSCONNECT_UPLOAD_PROJECT_ID must be a positive integer.") from exc
        if project_id <= 0:
            raise CommandError("--project-id must be a positive integer.")

        base_url = resolve_api_base_url(
            role="watcher",
            token=settings.MSCONNECT_AGENT_TOKEN,
            configured_base_url=settings.MSCONNECT_API_BASE_URL,
        )
        if not base_url:
            raise CommandError("Unable to locate the Django API. Set MSCONNECT_API_BASE_URL.")
        client = AgentApiClient(base_url=base_url, token=settings.MSCONNECT_AGENT_TOKEN)
        agent_name = settings.MSCONNECT_AGENT_NAME or socket.gethostname()
        seen = {}
        stable = {}

        while True:
            candidates = self._discover(source)
            keys = {str(path.resolve()) for path in candidates}
            stable = {key: value for key, value in stable.items() if key in keys}
            seen = {key: value for key, value in seen.items() if key in keys}
            self._heartbeat(client, agent_name, "idle", len(candidates))
            for path in candidates:
                key = str(path.resolve())
                fingerprint = _acquisition_fingerprint(path)
                if fingerprint is None or seen.get(key) == fingerprint:
                    continue
                previous, count = stable.get(key, (None, 0))
                count = count + 1 if previous == fingerprint else 1
                stable[key] = (fingerprint, count)
                if count < max(1, int(options["stability_checks"])):
                    continue
                try:
                    self._upload(client, path, project_id, int(options["chunk_size"]))
                    seen[key] = fingerprint
                    self.stdout.write(f"uploaded {path}")
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"failed {path}: {exc}"))
                    try:
                        client.record_ingestion_failure({"source_path": str(path), "failure_reason": str(exc), "metadata": {"importer": "direct_upload_agent"}})
                    except AgentApiError:
                        pass
            if options["once"]:
                return
            time.sleep(max(1, int(options["interval"])))

    @staticmethod
    def _discover(source: Path):
        if source.is_file() or source.suffix.lower() == ".d":
            return [source]
        paths = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".raw", ".mzml", ".mzxml", ".wiff", ".scan"}:
                paths.append(path)
            elif path.is_dir() and path.suffix.lower() == ".d":
                paths.append(path)
        return paths

    def _upload(self, client: AgentApiClient, path: Path, project_id: int, chunk_size: int):
        upload_path = path
        metadata = {"importer": "direct_upload_agent", "agent_name": settings.MSCONNECT_AGENT_NAME or socket.gethostname()}
        if path.is_dir():
            upload_path = self._bundle_directory(path)
            metadata.update({"directory_bundle": True, "original_directory": path.name})
        size = upload_path.stat().st_size
        content_type = mimetypes.guess_type(upload_path.name)[0] or "application/octet-stream"
        session = client.create_direct_upload({
            "project": project_id,
            "filename": path.name,
            "expected_filename": path.name,
            "size_bytes": size,
            "chunk_size_bytes": chunk_size,
            "content_type": content_type,
            "delivery_mode": "direct",
            "metadata": metadata,
        })
        digest = hashlib.sha256()
        with upload_path.open("rb") as handle:
            for part in session["upload_urls"]:
                length = int(part["end"]) - int(part["start"])
                payload = handle.read(length)
                if len(payload) != length:
                    raise CommandError(f"Unexpected end of file while reading {upload_path}.")
                digest.update(payload)
                client.upload_direct_chunk(session["id"], part["part_number"], payload, content_type)
        client.complete_direct_upload(session["id"], digest.hexdigest())
        if upload_path != path:
            upload_path.unlink(missing_ok=True)

    @staticmethod
    def _bundle_directory(path: Path) -> Path:
        bundle = path.parent / f".{path.name}.msconnect-upload.zip"
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    archive.write(child, Path(path.name) / child.relative_to(path))
        return bundle

    @staticmethod
    def _heartbeat(client, agent_name, status, candidate_count):
        client.heartbeat(
            name=agent_name,
            node_type="watcher",
            status=status,
            container_image=settings.MSCONNECT_IMAGE,
            metadata={"mode": "direct-upload", "candidate_count": candidate_count},
            settings={"source": settings.MSCONNECT_UPLOAD_SOURCE_ROOT, "project_id": settings.MSCONNECT_UPLOAD_PROJECT_ID},
            release_version=settings.MSCONNECT_RELEASE_VERSION,
        )
        write_heartbeat_marker(agent_name=agent_name, role="watcher", status=status, node_type="watcher")
