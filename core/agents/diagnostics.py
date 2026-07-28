import json
import socket
import tempfile
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from core.agents.client import AgentApiClient


def agent_token_for_role(role: str) -> str:
    if settings.MSCONNECT_AGENT_TOKEN:
        return settings.MSCONNECT_AGENT_TOKEN
    if role == "watcher":
        return settings.MSCONNECT_WATCHER_TOKEN
    if role == "processor":
        return settings.MSCONNECT_PROCESSOR_TOKEN
    return ""


def marker_path(agent_name: str | None = None) -> Path:
    name = agent_name or settings.MSCONNECT_AGENT_NAME or socket.gethostname()
    safe_name = "".join(character if character.isalnum() or character in "._-" else "_" for character in name)
    return Path(settings.MSCONNECT_AGENT_HEALTH_DIR) / f"{safe_name}.json"


def write_heartbeat_marker(*, agent_name: str, role: str, status: str, node_type: str = ""):
    path = marker_path(agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent_name": agent_name,
        "role": role,
        "node_type": node_type or role,
        "status": status,
        "updated_at": timezone.now().isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def marker_fresh(*, agent_name: str | None = None, max_age_seconds: int = 90):
    path = marker_path(agent_name)
    if not path.exists():
        return False, {"path": str(path), "error": "heartbeat marker does not exist"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated_at = timezone.datetime.fromisoformat(payload["updated_at"])
        if updated_at.tzinfo is None:
            updated_at = timezone.make_aware(updated_at, timezone.get_current_timezone())
        age_seconds = int((timezone.now() - updated_at).total_seconds())
        return age_seconds <= max_age_seconds, {"path": str(path), "age_seconds": age_seconds, "payload": payload}
    except Exception as exc:
        return False, {"path": str(path), "error": str(exc)}


def run_agent_checks(*, role: str, engine: str = "", write_test: bool = False):
    base_url = settings.MSCONNECT_API_BASE_URL.rstrip("/")
    token = agent_token_for_role(role)
    checks = {
        "settings": _settings_check(role=role, base_url=base_url, token=token),
        "dns": _dns_check(base_url),
        "tcp": _tcp_check(base_url),
        "healthz": _http_check(_site_url(base_url, "/healthz/")),
        "agent_ping": _agent_ping_check(base_url=base_url, token=token, role=role),
    }
    if role == "watcher":
        checks["incoming_raw_root"] = _path_check(settings.INCOMING_RAW_ROOT, require_read=True)
        checks["raw_file_storage_root"] = _path_check(
            settings.RAW_FILE_STORAGE_ROOT,
            require_read=True,
            write_test=write_test,
        )
    if role == "processor":
        checks["results_root"] = _path_check(
            settings.RESULTS_ROOT,
            require_read=True,
            write_test=write_test,
            create=True,
        )
        checks["raw_file_storage_root"] = _path_check(settings.RAW_FILE_STORAGE_ROOT, require_read=True)
        checks["processor_shared_storage_root"] = _path_check(
            settings.PROCESSOR_SHARED_STORAGE_ROOT,
            require_read=True,
            write_test=write_test,
            create=True,
        )
        checks["engine"] = {"ok": bool(engine), "engine": engine or settings.MSCONNECT_PROCESSOR_ENGINE}
    ok = all(item["ok"] for item in checks.values())
    return {
        "ok": ok,
        "role": role,
        "engine": engine or settings.MSCONNECT_PROCESSOR_ENGINE,
        "base_url": base_url,
        "checks": checks,
    }


def _settings_check(*, role: str, base_url: str, token: str):
    missing = []
    if role not in {"watcher", "processor"}:
        missing.append("role")
    if not base_url:
        missing.append("MSCONNECT_API_BASE_URL")
    if not token:
        missing.append("MSCONNECT_AGENT_TOKEN")
    return {"ok": not missing, "missing": missing}


def _site_url(base_url: str, path: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _dns_check(base_url: str):
    try:
        parsed = urlparse(base_url)
        socket.getaddrinfo(parsed.hostname or "", parsed.port or _default_port(parsed.scheme))
        return {"ok": True, "host": parsed.hostname}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _tcp_check(base_url: str):
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    port = parsed.port or _default_port(parsed.scheme)
    try:
        with socket.create_connection((host, port), timeout=5):
            return {"ok": True, "host": host, "port": port}
    except Exception as exc:
        return {"ok": False, "host": host, "port": port, "error": str(exc)}


def _http_check(url: str):
    try:
        with request.urlopen(url, timeout=10) as response:
            return {"ok": 200 <= response.status < 400, "status_code": response.status, "url": url}
    except error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "url": url, "error": exc.read().decode("utf-8", errors="replace")}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def _agent_ping_check(*, base_url: str, token: str, role: str):
    if not token:
        return {"ok": False, "error": "agent token is not configured"}
    try:
        payload = AgentApiClient(base_url=base_url, token=token, timeout=10, retries=1).ping()
        return {"ok": payload.get("agent_role") == role, "payload": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _path_check(path_value: str, *, require_read: bool = False, write_test: bool = False, create: bool = False):
    path = Path(path_value)
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return {"ok": False, "path": str(path), "error": "path does not exist"}
        if not path.is_dir():
            return {"ok": False, "path": str(path), "error": "path is not a directory"}
        if require_read:
            next(path.iterdir(), None)
        if write_test:
            with tempfile.NamedTemporaryFile(prefix=".msconnect-preflight-", dir=path, delete=True) as probe:
                probe.write(b"ok")
                probe.flush()
        return {"ok": True, "path": str(path)}
    except StopIteration:
        return {"ok": True, "path": str(path)}
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80
