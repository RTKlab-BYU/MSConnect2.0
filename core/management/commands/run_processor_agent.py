import json
import hashlib
import platform
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.client import AgentApiClient, AgentApiError
from core.agents.diagnostics import run_agent_checks, write_heartbeat_marker
from core.agents.discovery import resolve_api_base_url
from core.agents.processor import prepare_job_execution
from core.agents.upgrade import run_upgrade_hook
from core.models import ProcessingNodeStatus
from core.processing.postprocess import run_postprocess


def _detect_engine_failure(parameters: dict, log_text: str) -> str:
    """Catch engines that emit a fatal input error but still exit zero."""
    adapter = str(parameters.get("adapter") or parameters.get("required_engine") or "").strip().lower()
    if adapter in {"diann", "dia-nn"}:
        markers = (
            "Thermo RAW file format not supported.",
            "ERROR: DIA-NN tried but failed to load the following files:",
            "No MS2 spectra: aborting",
        )
        for marker in markers:
            if marker in log_text:
                return f"DIA-NN reported a fatal input error: {marker}"
    return ""


class Command(BaseCommand):
    help = "Run the processing agent that claims queued jobs from the main API and executes them locally."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=int, default=settings.PROCESSOR_POLL_INTERVAL_SECONDS)
        parser.add_argument("--heartbeat-seconds", type=int, default=settings.MSCONNECT_AGENT_HEARTBEAT_SECONDS)
        parser.add_argument("--engine", default=settings.MSCONNECT_PROCESSOR_ENGINE)

    def handle(self, *args, **options):
        if not settings.MSCONNECT_AGENT_TOKEN:
            raise CommandError("MSCONNECT_AGENT_TOKEN must be set for the processor agent.")

        agent_name = settings.MSCONNECT_AGENT_NAME or socket.gethostname()
        node_type = (options["engine"] or "processor").strip()
        results_root = Path(settings.RESULTS_ROOT)
        results_root.mkdir(parents=True, exist_ok=True)
        heartbeat_seconds = max(5, int(options["heartbeat_seconds"]))
        last_heartbeat = 0.0
        last_control_id = ""
        control_state = "active"
        client = self._resolve_client(role="processor")

        while True:
            try:
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_seconds:
                    node_payload = self._heartbeat(
                        client,
                        agent_name=agent_name,
                        node_type=node_type,
                        status=ProcessingNodeStatus.IDLE,
                        control_state=control_state,
                    )
                    last_control_id, control_state, should_exit = self._handle_control(
                        node_payload,
                        client=client,
                        agent_name=agent_name,
                        node_type=node_type,
                        status=ProcessingNodeStatus.IDLE,
                        control_state=control_state,
                        last_control_id=last_control_id,
                    )
                    last_heartbeat = now
                    if should_exit:
                        break

                if control_state in {"paused", "draining"}:
                    if options["once"]:
                        break
                    time.sleep(max(1, int(options["poll_interval"])))
                    continue

                job = client.claim_next_job(node_name=agent_name)
                if not job:
                    if options["once"]:
                        break
                    time.sleep(max(1, int(options["poll_interval"])))
                    continue

                self._heartbeat(
                    client,
                    agent_name=agent_name,
                    node_type=node_type,
                    status=ProcessingNodeStatus.BUSY,
                    control_state=control_state,
                )
                last_heartbeat = time.monotonic()

                try:
                    execution = prepare_job_execution(job, results_root=results_root)
                    client.start_job(job["id"], node_name=agent_name, lease_token=job.get("lease_token", ""))
                    self._run_job(job, execution, client, agent_name=agent_name)
                except Exception as exc:
                    log_path = (results_root / "jobs" / str(job["id"]) / "process.log").resolve()
                    failure_payload = {
                        "node_name": agent_name,
                        "error_message": str(exc),
                    }
                    if log_path.exists():
                        failure_payload["log_path"] = str(log_path)
                    manifest_path = (results_root / "jobs" / str(job["id"]) / "runtime-manifest.json").resolve()
                    if manifest_path.exists():
                        failure_payload["stats"] = {"runtime_manifest_path": str(manifest_path)}
                    client.fail_job(
                        job["id"],
                        failure_payload,
                    )
                    self.stderr.write(self.style.ERROR(f"job {job['id']} failed: {exc}"))

                node_payload = self._heartbeat(
                    client,
                    agent_name=agent_name,
                    node_type=node_type,
                    status=ProcessingNodeStatus.IDLE,
                    control_state=control_state,
                )
                last_control_id, control_state, should_exit = self._handle_control(
                    node_payload,
                    client=client,
                    agent_name=agent_name,
                    node_type=node_type,
                    status=ProcessingNodeStatus.IDLE,
                    control_state=control_state,
                    last_control_id=last_control_id,
                )
                last_heartbeat = time.monotonic()
                if options["once"] or should_exit:
                    break
            except Exception as exc:
                if isinstance(exc, CommandError):
                    raise
                self.stderr.write(self.style.WARNING(f"processor agent re-discovering Django: {exc}"))
                client = self._resolve_client(role="processor")
                time.sleep(min(10, max(1, int(options["poll_interval"]))))

    def _run_job(self, job: dict, execution, client: AgentApiClient, *, agent_name: str):
        execution.log_path.parent.mkdir(parents=True, exist_ok=True)
        backend = str((job.get("metadata") or {}).get("execution_backend") or "local").strip().lower()
        command = execution.command
        temporary_spec = None
        if backend == "slurm":
            if settings.MSCONNECT_PROCESSOR_EXECUTION_BACKEND != "slurm":
                raise CommandError("This processor node is not configured to execute Slurm-backed jobs.")
            command_inputs = [
                execution.command[index + 1]
                for index, item in enumerate(execution.command[:-1])
                if item == "--f" and Path(execution.command[index + 1]).is_absolute()
            ]
            input_paths = command_inputs or [(job.get("raw_file") or {}).get("storage_path")]
            input_paths.extend(execution.parameters.get("input_files") or [])
            input_paths.extend([execution.parameters.get("library"), execution.parameters.get("fasta")])
            reference_checksums = {
                str(item.get("path")): str(item.get("checksum_sha256"))
                for item in (execution.parameters.get("reference_snapshot") or {}).values()
                if isinstance(item, dict) and item.get("path") and item.get("checksum_sha256")
            }
            for asset_key in ("fasta_asset", "speclib_asset"):
                asset = (execution.parameters.get("reference_assets") or {}).get(asset_key) or {}
                if asset.get("path") and asset.get("checksum_sha256"):
                    reference_checksums[str(asset["path"])] = str(asset["checksum_sha256"])
            input_checksums = {}
            raw_payload = job.get("raw_file") or {}
            if raw_payload.get("storage_path") and raw_payload.get("checksum_sha256"):
                input_checksums[str(raw_payload["storage_path"])] = str(raw_payload["checksum_sha256"])
            for derivative in raw_payload.get("derivatives") or []:
                if derivative.get("path") and derivative.get("checksum_sha256"):
                    input_checksums[str(derivative["path"])] = str(derivative["checksum_sha256"])
            for input_path, checksum in zip(
                (job.get("metadata") or {}).get("input_files") or [],
                (job.get("metadata") or {}).get("input_file_checksums") or [],
            ):
                if input_path and checksum:
                    input_checksums[str(input_path)] = str(checksum)
            spec = {
                "job_id": int(job["id"]),
                "attempt_count": int(job.get("attempt_count") or 1),
                "batch_id": (job.get("metadata") or {}).get("analysis_batch_id"),
                "job_kind": (job.get("metadata") or {}).get("job_kind") or "",
                "agent_name": agent_name,
                "command": execution.command,
                "results_dir": str(execution.results_dir),
                "input_paths": [value for value in input_paths if isinstance(value, str) and value.strip()],
                "reference_checksums": reference_checksums,
                "input_checksums": input_checksums,
                "allowed_source_roots": [
                    settings.RAW_FILE_STORAGE_ROOT,
                    settings.PROCESSOR_SHARED_STORAGE_ROOT,
                    settings.RESULTS_ROOT,
                ],
            }
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as spec_file:
                json.dump(spec, spec_file)
                temporary_spec = Path(spec_file.name)
            runner_path = Path(__file__).resolve().parents[3] / "core" / "agents" / "slurm_runner.py"
            command = [sys.executable, str(runner_path), "--spec", str(temporary_spec)]
        elif backend != "local":
            raise CommandError(f"Unsupported processing execution backend: {backend}")

        try:
            with execution.log_path.open("w", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    command,
                    cwd=execution.working_dir,
                    env=execution.env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                renew_interval = max(15, int(getattr(settings, "MSCONNECT_PROCESSING_LEASE_SECONDS", 300) / 3))
                next_renewal = time.monotonic() + renew_interval
                while process.poll() is None:
                    time.sleep(min(5, max(0.5, next_renewal - time.monotonic())))
                    if process.poll() is not None:
                        break
                    if time.monotonic() >= next_renewal:
                        try:
                            client.renew_job(
                                job["id"],
                                node_name=agent_name,
                                lease_token=job.get("lease_token", ""),
                            )
                        except AgentApiError as exc:
                            self.stderr.write(self.style.WARNING(f"lease renewal deferred for job {job['id']}: {exc}"))
                        next_renewal = time.monotonic() + renew_interval
                completed = type("Completed", (), {"returncode": process.wait()})()
        finally:
            if temporary_spec:
                temporary_spec.unlink(missing_ok=True)

        if completed.returncode != 0:
            client.fail_job(
                job["id"],
                {
                    "node_name": agent_name,
                    "lease_token": job.get("lease_token", ""),
                    "error_message": f"Command exited with status {completed.returncode}.",
                    "log_path": str(execution.log_path.resolve()),
                },
            )
            return

        log_text = execution.log_path.read_text(encoding="utf-8", errors="replace")
        engine_failure = _detect_engine_failure(execution.parameters, log_text)
        if engine_failure:
            client.fail_job(
                job["id"],
                {
                    "node_name": agent_name,
                    "lease_token": job.get("lease_token", ""),
                    "error_message": engine_failure,
                    "log_path": str(execution.log_path.resolve()),
                },
            )
            self.stderr.write(self.style.ERROR(f"job {job['id']} failed: {engine_failure}"))
            return

        postprocess_stats = {}
        if execution.postprocess:
            postprocess_stats = run_postprocess(
                name=execution.postprocess,
                parameters=execution.parameters,
                results_dir=execution.results_dir,
            )

        for artifact in (execution.protein_table_path, execution.peptide_table_path, execution.stats_json_path):
            if artifact and not artifact.exists():
                raise CommandError(f"Expected result artifact was not created: {artifact}")
        derivative_payload = []
        for derivative in execution.derivative_files:
            artifact = Path(str(derivative.get("path") or "")).resolve()
            if not artifact.exists():
                raise CommandError(f"Expected derivative artifact was not created: {artifact}")
            checksum = hashlib.sha256()
            size_bytes = 0
            with artifact.open("rb") as derivative_file:
                for chunk in iter(lambda: derivative_file.read(1024 * 1024), b""):
                    checksum.update(chunk)
                    size_bytes += len(chunk)
            derivative_payload.append(
                {
                    **derivative,
                    "path": str(artifact),
                    "size_bytes": size_bytes,
                    "checksum_sha256": checksum.hexdigest(),
                }
            )
        artifact_payload = []
        for declared_artifact in execution.artifact_files:
            artifact = Path(str(declared_artifact.get("path") or "")).resolve()
            if not artifact.exists():
                raise CommandError(f"Expected processing artifact was not created: {artifact}")
            artifact_payload.append({**declared_artifact, "path": str(artifact)})

        known_artifact_paths = {str(Path(item["path"]).resolve()) for item in artifact_payload}
        known_artifact_paths.update(
            str(Path(path).resolve())
            for path in (
                execution.protein_table_path,
                execution.peptide_table_path,
                execution.stats_json_path,
                execution.log_path,
            )
            if path
        )
        temp_value = ""
        for index, argument in enumerate(execution.command[:-1]):
            if argument == "--temp":
                temp_value = execution.command[index + 1]
                break
        if not temp_value:
            temp_value = str(execution.parameters.get("temp") or "").strip()
        temp_path = Path(temp_value) if temp_value else None
        if temp_path and not temp_path.is_absolute():
            temp_path = execution.working_dir / temp_path
        if temp_path:
            temp_path = temp_path.resolve()
        for output_path in execution.results_dir.rglob("*"):
            if not output_path.is_file() or output_path.is_symlink():
                continue
            resolved_path = output_path.resolve()
            if temp_path and (resolved_path == temp_path or temp_path in resolved_path.parents):
                continue
            if str(resolved_path) in known_artifact_paths:
                continue
            checksum = hashlib.sha256()
            with resolved_path.open("rb") as output_file:
                for chunk in iter(lambda: output_file.read(1024 * 1024), b""):
                    checksum.update(chunk)
            artifact_payload.append(
                {
                    "artifact_type": "raw_output",
                    "path": str(resolved_path),
                    "format": resolved_path.suffix.lstrip(".") or "file",
                    "size_bytes": resolved_path.stat().st_size,
                    "checksum_sha256": checksum.hexdigest(),
                    "metadata": {"role": "auto_collected_output"},
                }
            )
            known_artifact_paths.add(str(resolved_path))

        stats_payload = {}
        if execution.stats_json_path:
            with execution.stats_json_path.open("r", encoding="utf-8") as stats_file:
                stats_payload = json.load(stats_file)
            if not isinstance(stats_payload, dict):
                raise CommandError(f"Expected stats JSON object in {execution.stats_json_path}")
        stats_payload = {**stats_payload, **postprocess_stats}

        client.complete_job(
            job["id"],
            {
                "node_name": agent_name,
                "lease_token": job.get("lease_token", ""),
                "log_path": str(execution.log_path.resolve()),
                "protein_table_path": (
                    str(execution.protein_table_path.resolve()) if execution.protein_table_path else ""
                ),
                "peptide_table_path": (
                    str(execution.peptide_table_path.resolve()) if execution.peptide_table_path else ""
                ),
                "delimiter": execution.delimiter or "",
                "derivatives": derivative_payload,
                "artifacts": artifact_payload,
                "stats": {
                    **stats_payload,
                    "runtime": execution.runtime_metadata,
                    "runtime_manifest_path": str(execution.runtime_manifest_path),
                },
            },
        )
        self.stdout.write(self.style.SUCCESS(f"completed job {job['id']}"))

    def _heartbeat(
        self,
        client: AgentApiClient,
        *,
        agent_name: str,
        node_type: str,
        status: str,
        control_state: str,
        metadata: dict | None = None,
    ):
        local_ip = self._local_ip()
        heartbeat_metadata = {
            "mode": "command-runner",
            "control_state": control_state,
            "host_name": socket.gethostname(),
            "processor_engine_version": settings.MSCONNECT_PROCESSOR_ENGINE_VERSION,
            "processor_engine_profile": settings.MSCONNECT_PROCESSOR_ENGINE_PROFILE,
            "execution_backend": settings.MSCONNECT_PROCESSOR_EXECUTION_BACKEND,
            **(metadata or {}),
        }
        if local_ip:
            heartbeat_metadata["ip_address"] = local_ip
        response = client.heartbeat(
            name=agent_name,
            node_type=node_type,
            status=status,
            container_image=settings.MSCONNECT_IMAGE,
            metadata=heartbeat_metadata,
            settings={
                "processor_engine": node_type,
                "processor_engine_version": settings.MSCONNECT_PROCESSOR_ENGINE_VERSION,
                "processor_engine_profile": settings.MSCONNECT_PROCESSOR_ENGINE_PROFILE,
                "execution_backend": settings.MSCONNECT_PROCESSOR_EXECUTION_BACKEND,
                "results_root": settings.RESULTS_ROOT,
                "raw_file_storage_root": settings.RAW_FILE_STORAGE_ROOT,
                "processor_shared_storage_root": settings.PROCESSOR_SHARED_STORAGE_ROOT,
                "python_version": sys.version.split()[0],
                "platform": platform.platform(),
            },
            release_version=settings.MSCONNECT_RELEASE_VERSION,
        )
        write_heartbeat_marker(agent_name=agent_name, role="processor", status=status, node_type=node_type)
        return response

    def _handle_control(
        self,
        node_payload: dict | None,
        *,
        client: AgentApiClient,
        agent_name: str,
        node_type: str,
        status: str,
        control_state: str,
        last_control_id: str,
    ):
        control = (node_payload or {}).get("active_control") or {}
        control_id = str(control.get("id") or "")
        if not control_id or control_id == last_control_id:
            return last_control_id, control_state, False

        command = str(control.get("command") or "")
        next_state = control_state
        should_exit = False
        if command == "diagnostics":
            result = run_agent_checks(role="processor", engine=node_type, write_test=True)
            self._heartbeat(client, agent_name=agent_name, node_type=node_type, status=status,
                            control_state=control_state,
                            metadata={"ack_control_id": control_id, "diagnostics_result": result})
            self.stdout.write(f"completed processor diagnostics: {'ok' if result['ok'] else 'failed'}")
            return control_id, control_state, False
        if command == "pause":
            next_state = "paused"
        elif command == "drain":
            next_state = "draining"
        elif command in {"resume", "start"}:
            next_state = "active"
        elif command == "restart":
            next_state = "restarting"
            should_exit = True
        elif command == "upgrade":
            result = run_upgrade_hook(settings.MSCONNECT_UPGRADE_HOOK, control.get("parameters") or {})
            next_state = "restarting" if result["status"] == "succeeded" else "error"
            should_exit = result["status"] == "succeeded"
            self._heartbeat(
                client, agent_name=agent_name, node_type=node_type,
                status=ProcessingNodeStatus.OFFLINE if should_exit else ProcessingNodeStatus.ERROR,
                control_state=next_state,
                metadata={"ack_control_id": control_id, "upgrade_result": result},
            )
            return control_id, next_state, should_exit
        elif command in {"stop", "reconfigure"}:
            next_state = "stopped"
            should_exit = True
        else:
            return control_id, control_state, False

        ack_status = ProcessingNodeStatus.OFFLINE if should_exit else status
        self._heartbeat(
            client,
            agent_name=agent_name,
            node_type=node_type,
            status=ack_status,
            control_state=next_state,
            metadata={"ack_control_id": control_id},
        )
        self.stdout.write(f"applied processor control {command}: {next_state}")
        return control_id, next_state, should_exit

    def _local_ip(self):
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return ""

    def _resolve_client(self, *, role: str):
        base_url = resolve_api_base_url(role=role, token=settings.MSCONNECT_AGENT_TOKEN, configured_base_url=settings.MSCONNECT_API_BASE_URL)
        if not base_url:
            raise CommandError("Unable to locate the Django API. Set MSCONNECT_API_BASE_URL or discovery hosts.")
        return AgentApiClient(base_url=base_url, token=settings.MSCONNECT_AGENT_TOKEN)
