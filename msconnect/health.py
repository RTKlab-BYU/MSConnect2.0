from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def healthz(_request):
    return JsonResponse({"status": "ok", "server_time": timezone.now().isoformat()})


def readyz(_request):
    checks = {
        "database": _database_check(),
        "incoming_raw_root": _path_check(settings.INCOMING_RAW_ROOT, require_read=True),
        "raw_file_storage_root": _path_check(settings.RAW_FILE_STORAGE_ROOT, require_read=True, require_write=True),
        "results_root": _path_check(settings.RESULTS_ROOT, require_read=True, require_write=True),
        "media_root": _path_check(settings.MEDIA_ROOT, require_read=True, require_write=True),
    }
    ok = all(item["ok"] for item in checks.values())
    return JsonResponse(
        {
            "status": "ok" if ok else "error",
            "server_time": timezone.now().isoformat(),
            "checks": checks,
        },
        status=200 if ok else 503,
    )


def _database_check():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _path_check(path_value, *, require_read=False, require_write=False):
    path = Path(path_value)
    result = {"ok": True, "path": str(path)}
    if not path.exists():
        return {**result, "ok": False, "error": "path does not exist"}
    if not path.is_dir():
        return {**result, "ok": False, "error": "path is not a directory"}
    if require_read:
        try:
            next(path.iterdir(), None)
        except StopIteration:
            pass
        except Exception as exc:
            return {**result, "ok": False, "error": f"path is not readable: {exc}"}
    if require_write:
        probe = path / ".msconnect-readyz"
        try:
            probe.write_text(timezone.now().isoformat(), encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            return {**result, "ok": False, "error": f"path is not writable: {exc}"}
    return result
