#!/usr/bin/env python3
"""WSL2-side CLI for a native Nextflow/DIA-NN MSConnect processor agent."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def load_env(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or not name.strip().replace("_", "a").isalnum() or not name.strip()[0].isalpha():
            raise SystemExit(f"Invalid .env entry: {raw_line}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[name.strip()] = value


def check(project_dir: Path) -> None:
    problems: list[str] = []
    if not (project_dir / "manage.py").is_file():
        problems.append(f"MSConnect checkout is missing manage.py: {project_dir}")
    required = ("MSCONNECT_AGENT_TOKEN", "MSCONNECT_AGENT_NAME", "MSCONNECT_API_BASE_URL")
    for key in required:
        if not os.environ.get(key):
            problems.append(f"{key} is missing")
    for key in ("RAW_FILE_STORAGE_ROOT", "RESULTS_ROOT", "PROCESSOR_SHARED_STORAGE_ROOT"):
        value = os.environ.get(key, "")
        if not value:
            problems.append(f"{key} is missing")
        elif not Path(value).is_dir():
            problems.append(f"{key} is not mounted or is not a directory: {value}")
    for command in ("python3", "nextflow", "conda"):
        if not shutil.which(command):
            problems.append(f"{command} is not on PATH")
    configured_python = os.environ.get("MSCONNECT_PYTHON", "")
    if configured_python and not Path(configured_python).is_file():
        problems.append(f"MSCONNECT_PYTHON does not exist: {configured_python}")

    workflow = Path(os.environ.get("MSCONNECT_DIANN_NEXTFLOW_WORKFLOW", ""))
    catalog_path = Path(os.environ.get("MSCONNECT_DIANN_VERSION_CATALOG", ""))
    version = os.environ.get("MSCONNECT_DIANN_VERSION", "")
    if not workflow.is_file():
        problems.append(f"Nextflow workflow is missing: {workflow}")
    if not catalog_path.is_file():
        problems.append(f"DIA-NN version catalog is missing: {catalog_path}")
    elif version:
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            entry = catalog["versions"][version]
            executable = Path(entry["executable"])
            environment = workflow.parent / entry["conda_env"]
            if not executable.is_file() or not os.access(executable, os.X_OK):
                problems.append(f"DIA-NN {version} executable is unavailable: {executable}")
            if not environment.is_file():
                problems.append(f"DIA-NN {version} Conda environment file is missing: {environment}")
        except (KeyError, ValueError, TypeError) as exc:
            problems.append(f"DIA-NN version catalog does not define {version}: {exc}")

    api = urlparse(os.environ.get("MSCONNECT_API_BASE_URL", ""))
    if api.hostname:
        try:
            socket.getaddrinfo(api.hostname, api.port or (443 if api.scheme == "https" else 80))
        except OSError as exc:
            problems.append(f"Cannot resolve API host {api.hostname}; check Tailscale: {exc}")

    if problems:
        print("Processor preflight failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Processor preflight passed for {os.environ['MSCONNECT_AGENT_NAME']}.")
    print(f"  API: {os.environ['MSCONNECT_API_BASE_URL']}")
    print(f"  DIA-NN: {version}")
    print(f"  Workflow: {workflow}")
    for key in ("RAW_FILE_STORAGE_ROOT", "RESULTS_ROOT", "PROCESSOR_SHARED_STORAGE_ROOT"):
        print(f"  {key}: {os.environ[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "run", "once"))
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()

    load_env(args.env_file)
    os.environ.setdefault("MSCONNECT_PROCESSOR_ENGINE", "diann")
    os.environ["MSCONNECT_AGENT_ROLE"] = "processor"
    user_bin = Path.home() / ".local" / "bin"
    candidate_bins = [Path.home() / "miniforge3" / "bin", Path.home() / "mambaforge" / "bin", user_bin]
    os.environ["PATH"] = os.pathsep.join(
        [*(str(path) for path in candidate_bins if path.is_dir()), os.environ.get("PATH", "")]
    )
    os.environ["NXF_CONDA_CACHEDIR"] = os.environ.get(
        "NXF_CONDA_CACHEDIR", str(Path.home() / ".cache" / "nextflow" / "conda")
    )
    check(args.project_dir)
    if args.action == "check":
        return 0

    manage_py = args.project_dir / "manage.py"
    command = [os.environ.get("MSCONNECT_PYTHON") or sys.executable, str(manage_py), "run_processor_agent", "--engine", "diann"]
    if args.action == "once":
        command.append("--once")
    return subprocess.run(command, cwd=args.project_dir, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
