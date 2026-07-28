import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_VERSION_ARGS = {
    "diann": ["--version"],
    "fragpipe": ["--version"],
    "skyline": ["--version"],
    "skylinecmd": ["--version"],
    "msconvert": ["--version"],
    "proteome-discoverer": ["--version"],
    "proteomediscoverer": ["--version"],
    "spectronaut": ["--version"],
}


def capture_runtime_metadata(
    *,
    command: list[str],
    env: dict[str, str],
    working_dir: Path,
    results_dir: Path,
    raw_file_path: str,
    parameters: dict,
    shared_roots: dict[str, str],
) -> dict:
    executable = command[0] if command else ""
    version_probe = parameters.get("version_command") or version_command_for(executable)
    software = {
        "adapter": parameters.get("adapter") or "command",
        "executable": executable,
        "resolved_executable": shutil.which(executable, path=env.get("PATH")) or executable,
        "declared_version": parameters.get("software_version") or parameters.get("version") or "",
        "version_command": version_probe,
        "detected_version": probe_version(version_probe, env=env, cwd=working_dir) if version_probe else "",
    }
    return {
        "schema_version": 1,
        "software": software,
        "command": redact_command(command),
        "working_dir": str(working_dir),
        "results_dir": str(results_dir),
        "raw_file_path": raw_file_path,
        "shared_storage": shared_roots,
        "system": system_metadata(),
        "environment": selected_environment(env),
        "input_fingerprints": fingerprint_inputs([raw_file_path, *parameters.get("input_files", [])]),
        "pipeline_parameters": scrub_parameters(parameters),
    }


def write_runtime_manifest(path: Path, metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def version_command_for(executable: str) -> list[str]:
    name = Path(executable).name.lower()
    stem = Path(name).stem
    args = DEFAULT_VERSION_ARGS.get(name) or DEFAULT_VERSION_ARGS.get(stem)
    if not args:
        return []
    return [executable, *args]


def probe_version(command: list[str], *, env: dict[str, str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"version probe failed: {exc}"
    output = (completed.stdout or "").strip()
    if not output:
        return f"version probe exited {completed.returncode} with no output"
    return output[:4000]


def system_metadata() -> dict:
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version,
        "cpu_count": os.cpu_count(),
    }


def selected_environment(env: dict[str, str]) -> dict:
    keys = [
        "PATH",
        "PROCESSOR_SHARED_STORAGE_ROOT",
        "RAW_FILE_STORAGE_ROOT",
        "RESULTS_ROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERNAME",
        "USER",
        "COMPUTERNAME",
        "HOSTNAME",
    ]
    return {key: env[key] for key in keys if key in env}


def fingerprint_inputs(paths: list[str]) -> list[dict]:
    fingerprints = []
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(str(raw_path))
        item = {"path": str(path)}
        try:
            stat = path.stat()
        except OSError as exc:
            item["error"] = str(exc)
            fingerprints.append(item)
            continue
        item["size_bytes"] = stat.st_size
        item["mtime_ns"] = stat.st_mtime_ns
        if path.is_file() and stat.st_size <= 512 * 1024 * 1024:
            item["sha256"] = sha256_file(path)
        elif path.is_file():
            item["sha256"] = ""
            item["sha256_skipped"] = "file larger than 512MiB"
        fingerprints.append(item)
    return fingerprints


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_command(command: list[str]) -> list[str]:
    redacted = []
    redact_next = False
    sensitive_flags = {"--password", "--token", "--license", "--apikey", "--api-key"}
    for item in command:
        lower = item.lower()
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
        elif lower in sensitive_flags:
            redacted.append(item)
            redact_next = True
        elif any(token in lower for token in ("password=", "token=", "apikey=", "api-key=", "license=")):
            redacted.append("[REDACTED]")
        else:
            redacted.append(item)
    return redacted


def scrub_parameters(parameters: dict) -> dict:
    scrubbed = {}
    for key, value in parameters.items():
        lower = str(key).lower()
        if any(token in lower for token in ("password", "token", "secret", "license", "apikey", "api_key")):
            scrubbed[key] = "[REDACTED]"
        else:
            scrubbed[key] = value
    return scrubbed
