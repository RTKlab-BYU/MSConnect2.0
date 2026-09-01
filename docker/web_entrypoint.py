#!/usr/bin/env python3
"""Bootstrap the web container under a filesystem lock, then start Gunicorn."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd="/app", check=True)


def main() -> None:
    lock_path = Path(os.environ.get("MSCONNECT_WEB_BOOTSTRAP_LOCK", "/app/data/web-bootstrap.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        _run([sys.executable, "manage.py", "migrate", "--noinput"])
        _run([sys.executable, "manage.py", "collectstatic", "--noinput"])

    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "msconnect.wsgi:application",
            "--bind",
            "0.0.0.0:8000",
            "--workers",
            "3",
            "--timeout",
            "120",
        ],
    )


if __name__ == "__main__":
    main()
