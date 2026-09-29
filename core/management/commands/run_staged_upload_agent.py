"""API-configured acquisition-PC uploader with a local, restart-safe spool."""

import hashlib
import mimetypes
import shutil
import socket
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path, PurePath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient, AgentApiError
from core.agents.diagnostics import write_heartbeat_marker
from core.agents.discovery import resolve_api_base_url
from core.management.commands.run_watcher_agent import _acquisition_fingerprint


class State:
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename))
        self.db.execute("CREATE TABLE IF NOT EXISTS uploads (route_id INTEGER, source_rel TEXT, fingerprint TEXT, status TEXT, staged_path TEXT, updated_at REAL, PRIMARY KEY(route_id, source_rel))")
        self.db.commit()

    def get(self, route_id, source_rel):
        return self.db.execute("SELECT fingerprint,status,staged_path FROM uploads WHERE route_id=? AND source_rel=?", (route_id, source_rel)).fetchone()

    def put(self, route_id, source_rel, fingerprint, status, staged_path):
        self.db.execute("INSERT OR REPLACE INTO uploads VALUES (?,?,?,?,?,?)", (route_id, source_rel, str(fingerprint), status, str(staged_path), time.time()))
        self.db.commit()


class Command(BaseCommand):
    help = "Poll server-managed acquisition routes, stage stable files, and upload verified spool copies."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=settings.WATCHER_INTERVAL_SECONDS)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--stability-checks", type=int, default=settings.WATCHER_STABILITY_CHECKS)
        parser.add_argument("--chunk-size", type=int, default=settings.MSCONNECT_UPLOAD_CHUNK_SIZE_BYTES)

    def handle(self, *args, **options):
        if not settings.MSCONNECT_AGENT_TOKEN:
            raise CommandError("MSCONNECT_AGENT_TOKEN must be set for the staged upload agent.")
        agent_name = settings.MSCONNECT_AGENT_NAME or socket.gethostname()
        base_url = resolve_api_base_url(role="watcher", token=settings.MSCONNECT_AGENT_TOKEN, configured_base_url=settings.MSCONNECT_API_BASE_URL)
        if not base_url:
            raise CommandError("Unable to locate the Django API. Set MSCONNECT_API_BASE_URL.")
        client = AgentApiClient(base_url=base_url, token=settings.MSCONNECT_AGENT_TOKEN)
        state_path = Path(settings.MSCONNECT_AGENT_STATE_DB)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state = State(state_path)
        stability = {}
        while True:
            try:
                config = client.get_config()
                root = Path(config.get("source_root") or settings.MSCONNECT_ACQUISITION_SOURCE_ROOT)
                self._validate_root(root)
                candidates = 0
                for route in config.get("routes", []):
                    if route.get("status") == "paused":
                        continue
                    source_base = self._safe_join(root, route.get("source_prefix", ""))
                    source_base.mkdir(parents=True, exist_ok=True)
                    spool_base = self._safe_join(Path(settings.MSCONNECT_SPOOL_ROOT), route["spool_folder"])
                    spool_base.mkdir(parents=True, exist_ok=True)
                    for path in self._discover(source_base):
                        candidates += 1
                        rel = path.relative_to(source_base).as_posix()
                        fingerprint = _acquisition_fingerprint(path)
                        if fingerprint is None:
                            continue
                        key = (route["id"], rel)
                        previous, count = stability.get(key, (None, 0))
                        count = count + 1 if previous == fingerprint else 1
                        stability[key] = (fingerprint, count)
                        receipt = state.get(route["id"], rel)
                        if receipt and receipt[0] == str(fingerprint) and receipt[1] == "complete":
                            continue
                        if count < max(1, int(options["stability_checks"])):
                            continue
                        staged = self._stage(path, spool_base, rel, fingerprint)
                        state.put(route["id"], rel, fingerprint, "staged", staged)
                        try:
                            self._upload(client, staged, path.name, route, rel, int(options["chunk_size"]))
                            state.put(route["id"], rel, fingerprint, "complete", staged)
                            if route.get("delete_spool_after_upload", settings.MSCONNECT_DELETE_SPOOL_AFTER_UPLOAD):
                                self._remove(staged)
                            self.stdout.write(f"uploaded {path} via {route['name']}")
                        except Exception as exc:
                            state.put(route["id"], rel, fingerprint, "failed", staged)
                            self.stderr.write(self.style.ERROR(f"failed {path}: {exc}"))
                            try:
                                client.record_ingestion_failure({"source_path": str(path), "failure_reason": str(exc), "metadata": {"importer": "staged_upload_agent", "route_id": route["id"]}})
                            except AgentApiError:
                                pass
                self._heartbeat(client, agent_name, candidates, config, root)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"configuration/scan failure: {exc}"))
            if options["once"]:
                return
            time.sleep(max(1, int(options["interval"])))

    @staticmethod
    def _validate_root(root):
        if not root.exists() or not root.is_dir():
            raise CommandError(f"Approved acquisition source root does not exist: {root}")
        allowed = [Path(item) for item in settings.MSCONNECT_ALLOWED_SOURCE_ROOTS if item]
        if allowed and not any(root.resolve() == item.resolve() or root.resolve().is_relative_to(item.resolve()) for item in allowed if item.exists()):
            raise CommandError(f"Acquisition source root is outside MSCONNECT_ALLOWED_SOURCE_ROOTS: {root}")

    @staticmethod
    def _safe_join(base, relative):
        candidate = PurePath(str(relative or "").replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise CommandError(f"Unsafe relative acquisition path: {relative}")
        return Path(base).joinpath(*candidate.parts)

    @staticmethod
    def _discover(source):
        if source.is_file() or source.suffix.lower() == ".d":
            return [source]
        suffixes = {".raw", ".mzml", ".mzxml", ".wiff", ".scan"}
        return [p for p in sorted(source.rglob("*")) if (p.is_file() and p.suffix.lower() in suffixes) or (p.is_dir() and p.suffix.lower() == ".d")]

    @staticmethod
    def _stage(source, spool_base, rel, fingerprint):
        destination = spool_base / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.parent / f".{destination.name}.copying-{uuid.uuid4().hex}"
        if source.is_dir():
            shutil.copytree(source, temp)
        else:
            shutil.copy2(source, temp)
        if _acquisition_fingerprint(source) != fingerprint:
            Command._remove(temp)
            raise CommandError(f"Source changed while staging: {source}")
        temp.replace(destination)
        return destination

    def _upload(self, client, staged, original_name, route, relative, chunk_size):
        upload_path = staged
        metadata = {
            "importer": "staged_upload_agent",
            "agent_name": settings.MSCONNECT_AGENT_NAME or socket.gethostname(),
            "route_id": route["id"],
            "route_name": route["name"],
            "source_relative_path": relative,
            "mode": route["mode"],
            "experiment_id": route.get("experiment_id"),
            "processing_pipeline_id": route.get("processing_pipeline_id"),
        }
        if staged.is_dir():
            upload_path = self._bundle_directory(staged)
            metadata["directory_bundle"] = True
        size = upload_path.stat().st_size
        content_type = mimetypes.guess_type(upload_path.name)[0] or "application/octet-stream"
        session = client.create_direct_upload(
            {
                "project": route["project_id"],
                "filename": original_name,
                "expected_filename": original_name,
                "size_bytes": size,
                "chunk_size_bytes": chunk_size,
                "content_type": content_type,
                "delivery_mode": "direct",
                "metadata": metadata,
            }
        )
        digest = hashlib.sha256()
        with upload_path.open("rb") as handle:
            for part in session["upload_urls"]:
                length = int(part["end"]) - int(part["start"])
                payload = handle.read(length)
                if len(payload) != length:
                    raise CommandError(f"Unexpected end of staged file: {upload_path}")
                digest.update(payload)
                client.upload_direct_chunk(session["id"], part["part_number"], payload, content_type)
        client.complete_direct_upload(session["id"], digest.hexdigest())
        if upload_path != staged:
            upload_path.unlink(missing_ok=True)

    @staticmethod
    def _bundle_directory(path):
        bundle = path.parent / f".{path.name}.msconnect-upload.zip"
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    archive.write(child, Path(path.name) / child.relative_to(path))
        return bundle

    @staticmethod
    def _remove(path):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _heartbeat(client, agent_name, candidates, config, root):
        validation = {"ok": root.exists() and root.is_dir(), "path": str(root), "config_version": config.get("config_version"), "checked_at": time.time()}
        try:
            client.report_config_validation(validation)
            client.heartbeat(
                name=agent_name,
                node_type="watcher",
                status="idle",
                container_image=settings.MSCONNECT_IMAGE,
                metadata={
                    "mode": "staged-direct-upload",
                    "candidate_count": candidates,
                    "config_version": config.get("config_version"),
                    "source_root_validation": validation,
                },
                settings={"source_root": str(root), "spool_root": settings.MSCONNECT_SPOOL_ROOT},
                release_version=settings.MSCONNECT_RELEASE_VERSION,
            )
        finally:
            write_heartbeat_marker(agent_name=agent_name, role="watcher", status="idle", node_type="watcher")
