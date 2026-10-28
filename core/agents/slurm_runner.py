"""Stage a processor job to BYU Slurm and return its artifacts to shared storage."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path


class SlurmExecutionError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise SlurmExecutionError(f"{name} must be set for Slurm-backed processing.")
    return value


def _ssh_base() -> list[str]:
    host = _required("MSCONNECT_SLURM_HOST")
    user = str(os.environ.get("MSCONNECT_SLURM_USER") or "").strip()
    target = f"{user}@{host}" if user else host
    port = str(int(os.environ.get("MSCONNECT_SLURM_PORT", "22")))
    return ["ssh", "-p", port, "-o", "BatchMode=yes", target]


def _run(argv: list[str], *, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    completed = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and completed.returncode:
        raise SlurmExecutionError(f"Command failed ({completed.returncode}): {shlex.join(argv)}\n{completed.stdout[-6000:]}")
    return completed


def _ssh(remote_command: str, *, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    return _run([*_ssh_base(), remote_command], check=check, timeout=timeout)


def _remote_target(path: str) -> str:
    host = _required("MSCONNECT_SLURM_HOST")
    user = str(os.environ.get("MSCONNECT_SLURM_USER") or "").strip()
    target = f"{user}@{host}" if user else host
    return f"{target}:{path}"


def _rsync_shell() -> str:
    return shlex.join(_ssh_base()[:-1])


def _ensure_allowed_source(source: Path, roots: list[str]) -> Path:
    resolved = source.resolve(strict=True)
    for root_value in roots:
        if not root_value:
            continue
        root = Path(root_value).resolve()
        if resolved == root or root in resolved.parents:
            return resolved
    raise SlurmExecutionError(f"Input is outside configured raw/reference storage roots: {resolved}")


def _slurm_script(
    *,
    job_id: int,
    remote_job_dir: str,
    remote_batch_dir: str | None,
    remote_reference_cache: str,
    image: str,
    command: list[str],
    spec: dict,
) -> str:
    memory = str(os.environ.get("MSCONNECT_SLURM_MEMORY", "64G")).strip()
    walltime = str(os.environ.get("MSCONNECT_SLURM_TIME", "24:00:00")).strip()
    if not re.fullmatch(r"\d+[KMGTP]?(?:B)?", memory, flags=re.IGNORECASE):
        raise SlurmExecutionError("MSCONNECT_SLURM_MEMORY must look like 64G or 64000M.")
    if not re.fullmatch(r"(?:\d+-)?\d{1,3}:\d{2}:\d{2}", walltime):
        raise SlurmExecutionError("MSCONNECT_SLURM_TIME must use Slurm's [days-]HH:MM:SS format.")
    directives = [
        "#!/bin/bash",
        f"#SBATCH --job-name=mscx-{job_id}",
        f"#SBATCH --cpus-per-task={max(1, int(os.environ.get('MSCONNECT_SLURM_CPUS', '16')))}",
        f"#SBATCH --mem={memory}",
        f"#SBATCH --time={walltime}",
        f"#SBATCH --output={remote_job_dir}/results/slurm-%j.out",
        f"#SBATCH --error={remote_job_dir}/results/slurm-%j.err",
    ]
    for key, option in (("MSCONNECT_SLURM_PARTITION", "partition"), ("MSCONNECT_SLURM_ACCOUNT", "account")):
        value = str(os.environ.get(key) or "").strip()
        if value:
            if any(character.isspace() for character in value):
                raise SlurmExecutionError(f"{key} cannot contain whitespace.")
            directives.append(f"#SBATCH --{option}={value}")
    binds = ["--bind", f"{remote_job_dir}:/work", "--bind", f"{remote_reference_cache}:/ref-cache"]
    if remote_batch_dir:
        binds.extend(["--bind", f"{remote_batch_dir}:/batch"])
    container_command = ["apptainer", "exec", "--cleanenv", *binds, image, *command]
    engine_log = "/work/results/slurm-engine.log"
    return "\n".join(
        [
            *directives,
            "set -euo pipefail",
            f"mkdir -p {shlex.quote(remote_job_dir + '/results')} {shlex.quote(remote_job_dir + '/tmp')}",
            "cd /work",
            f"{shlex.join(container_command)} > {shlex.quote(engine_log)} 2>&1",
            "",
        ]
    )


def execute(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    job_id = int(spec["job_id"])
    local_results = Path(spec["results_dir"]).resolve()
    local_results.mkdir(parents=True, exist_ok=True)
    remote_root = _required("MSCONNECT_SLURM_REMOTE_ROOT").rstrip("/")
    remote_root = posixpath.normpath(remote_root)
    if (
        not remote_root.startswith("/")
        or remote_root == "/"
        or ".." in Path(remote_root).parts
        or any(character.isspace() for character in remote_root)
    ):
        raise SlurmExecutionError("MSCONNECT_SLURM_REMOTE_ROOT must be a dedicated absolute path without whitespace or '..'.")
    agent_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in str(spec.get("agent_name") or "processor"))
    attempt = max(1, int(spec.get("attempt_count") or 1))
    remote_job_dir = posixpath.join(remote_root, agent_name, f"job-{job_id}-attempt-{attempt}")
    batch_id = str(spec.get("batch_id") or "").strip()
    remote_batch_dir = posixpath.join(remote_root, f"batch-{batch_id}") if batch_id.isdigit() else None
    remote_results = posixpath.join(remote_job_dir, "results")
    image = _required("MSCONNECT_SLURM_CONTAINER_IMAGE")
    if any(character.isspace() for character in image):
        raise SlurmExecutionError("MSCONNECT_SLURM_CONTAINER_IMAGE cannot contain whitespace.")
    if shutil.which("ssh") is None or shutil.which("rsync") is None:
        raise SlurmExecutionError("The Slurm processor image requires ssh and rsync executables.")

    allowed_roots = list(spec.get("allowed_source_roots") or [])
    extra_roots = str(os.environ.get("MSCONNECT_SLURM_ALLOWED_SOURCE_ROOTS") or "")
    allowed_roots.extend(value for value in extra_roots.split(os.pathsep) if value)
    source_to_container: dict[str, str] = {}
    remote_reference_cache = posixpath.join(remote_root, "reference-cache")
    directories = [remote_job_dir + "/inputs", remote_results, remote_job_dir + "/tmp", remote_reference_cache]
    if remote_batch_dir:
        directories.append(remote_batch_dir + "/inputs")
    _ssh("mkdir -p " + " ".join(shlex.quote(path) for path in directories))
    reference_checksums = spec.get("reference_checksums") or {}
    input_checksums = spec.get("input_checksums") or {}
    normalized_input_checksums = {str(Path(key).resolve()): value for key, value in input_checksums.items()}
    normalized_reference_checksums = {str(Path(key).resolve()): value for key, value in reference_checksums.items()}
    for index, source_value in enumerate(dict.fromkeys(spec.get("input_paths") or []), start=1):
        source = _ensure_allowed_source(Path(source_value), allowed_roots)
        checksum = str(normalized_reference_checksums.get(str(source)) or "").strip().lower()
        if checksum and len(checksum) == 64 and all(character in "0123456789abcdef" for character in checksum):
            cache_dir = posixpath.join(remote_reference_cache, checksum)
            _ssh(f"mkdir -p {shlex.quote(cache_dir)}")
            _run(
                ["rsync", "-a", "--checksum", "--protect-args", "-e", _rsync_shell(), str(source), _remote_target(cache_dir + "/")]
            )
            source_to_container[str(source)] = f"/ref-cache/{checksum}/{source.name}"
            continue
        checksum = str(normalized_input_checksums.get(str(source)) or "").strip().lower()
        if remote_batch_dir and checksum and len(checksum) == 64 and all(
            character in "0123456789abcdef" for character in checksum
        ):
            cache_dir = posixpath.join(remote_batch_dir, "inputs", checksum)
            _ssh(f"mkdir -p {shlex.quote(cache_dir)}")
            _run(
                ["rsync", "-a", "--checksum", "--protect-args", "-e", _rsync_shell(), str(source), _remote_target(cache_dir + "/")]
            )
            source_to_container[str(source)] = f"/batch/inputs/{checksum}/{source.name}"
            continue
        target_dir = posixpath.join(remote_job_dir, "inputs", f"{index:03d}")
        _ssh(f"mkdir -p {shlex.quote(target_dir)}")
        transfer = _run(
            ["rsync", "-a", "--protect-args", "-e", _rsync_shell(), str(source), _remote_target(target_dir + "/")]
        )
        if transfer.returncode:
            raise SlurmExecutionError(f"rsync failed staging {source}: {transfer.stdout[-4000:]}")
        source_to_container[str(source)] = f"/work/inputs/{index:03d}/{source.name}"

    command = [str(item) for item in spec["command"]]
    replacements = sorted(source_to_container.items(), key=lambda item: len(item[0]), reverse=True)
    results_dir_value = str(local_results)
    rewritten = []
    for argument in command:
        value = argument.replace(results_dir_value, "/work/results")
        for source, destination in replacements:
            value = value.replace(source, destination)
        rewritten.append(value)
    for index, value in enumerate(rewritten[:-1]):
        if value == "--temp":
            rewritten[index + 1] = "/work/tmp"

    script = _slurm_script(
        job_id=job_id,
        remote_job_dir=remote_job_dir,
        remote_batch_dir=remote_batch_dir,
        remote_reference_cache=remote_reference_cache,
        image=image,
        command=rewritten,
        spec=spec,
    )
    local_script = local_results / ".slurm-submit.sh"
    local_script.write_text(script, encoding="utf-8")
    remote_script = posixpath.join(remote_job_dir, "submit.sh")
    _run(["rsync", "-a", "--protect-args", "-e", _rsync_shell(), str(local_script), _remote_target(remote_script)])
    local_script.unlink(missing_ok=True)

    submit_output = _ssh(f"sbatch --parsable {shlex.quote(remote_script)}").stdout.strip()
    slurm_job_id = submit_output.split(";", 1)[0].splitlines()[-1].strip()
    if not slurm_job_id.isdigit():
        raise SlurmExecutionError(f"sbatch did not return a numeric job id: {submit_output[-1000:]}")
    print(f"Submitted Slurm job {slurm_job_id} for msconnect2 job {job_id}", flush=True)
    timeout = max(60, int(os.environ.get("MSCONNECT_SLURM_TIMEOUT_SECONDS", str(3 * 24 * 60 * 60))))
    poll_seconds = max(5, int(os.environ.get("MSCONNECT_SLURM_POLL_SECONDS", "20")))
    started = time.monotonic()
    missing_accounting_polls = 0

    def retrieve_results() -> None:
        _run(
            [
                "rsync", "-a", "--protect-args", "-e", _rsync_shell(),
                _remote_target(remote_results + "/"), str(local_results) + "/",
            ],
            check=False,
        )

    while True:
        if time.monotonic() - started > timeout:
            _ssh(f"scancel {shlex.quote(slurm_job_id)}", check=False)
            retrieve_results()
            raise SlurmExecutionError(f"Slurm job {slurm_job_id} exceeded its {timeout}-second timeout.")
        state = _ssh(f"squeue -h -j {shlex.quote(slurm_job_id)} -o %T", check=False).stdout.strip()
        if state:
            print(f"Slurm job {slurm_job_id}: {state.splitlines()[0]}", flush=True)
            time.sleep(poll_seconds)
            continue
        accounting = _ssh(
            f"sacct -n -P -X -j {shlex.quote(slurm_job_id)} --format=State,ExitCode", check=False
        ).stdout.strip()
        terminal = next((line for line in accounting.splitlines() if line.strip()), "")
        if not terminal:
            missing_accounting_polls += 1
            if missing_accounting_polls <= 6:
                time.sleep(poll_seconds)
                continue
            retrieve_results()
            raise SlurmExecutionError(f"Slurm job {slurm_job_id} left the queue but has no accounting record.")
        state_value, _, exit_value = terminal.partition("|")
        state_value = state_value.split()[0].split("+", 1)[0]
        if state_value in {"PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "SUSPENDED"}:
            time.sleep(poll_seconds)
            continue
        if state_value != "COMPLETED" or not exit_value.startswith("0:"):
            retrieve_results()
            raise SlurmExecutionError(f"Slurm job {slurm_job_id} ended in {terminal}.")
        break

    _run(
        ["rsync", "-a", "--protect-args", "-e", _rsync_shell(), _remote_target(remote_results + "/"), str(local_results) + "/"]
    )
    _ssh(f"rm -rf -- {shlex.quote(remote_job_dir)}", check=False)
    if remote_batch_dir and str(spec.get("job_kind") or "") == "experiment_rollup":
        _ssh(f"rm -rf -- {shlex.quote(remote_batch_dir)}", check=False)
    print(f"Retrieved outputs for Slurm job {slurm_job_id}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    options = parser.parse_args(argv)
    try:
        return execute(Path(options.spec))
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError, SlurmExecutionError) as exc:
        print(f"Slurm execution failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
