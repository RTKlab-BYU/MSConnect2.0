import os
from dataclasses import dataclass
from pathlib import Path

from core.processing.adapters import render_adapter_plan


@dataclass(frozen=True)
class PreparedJobExecution:
    command: list[str]
    env: dict[str, str]
    working_dir: Path
    results_dir: Path
    log_path: Path
    protein_table_path: Path | None
    peptide_table_path: Path | None
    stats_json_path: Path | None
    delimiter: str | None
    derivative_files: list[dict]
    artifact_files: list[dict]


def prepare_job_execution(job_payload: dict, *, results_root: Path) -> PreparedJobExecution:
    pipeline = job_payload.get("pipeline") or {}
    raw_file = job_payload.get("raw_file") or {}
    run = job_payload.get("run") or {}
    parameters = pipeline.get("parameters") or {}
    results_dir = (results_root / "jobs" / str(job_payload["id"])).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    log_path = (results_dir / "process.log").resolve()

    placeholders = {
        "job_id": str(job_payload["id"]),
        "raw_file_path": str(raw_file.get("storage_path") or ""),
        "results_dir": str(results_dir),
        "run_name": str(run.get("name") or ""),
    }

    adapter = parameters.get("adapter")
    derivative_files = []
    files_to_write = {}
    if adapter:
        adapter_plan = render_adapter_plan(
            adapter=str(adapter),
            parameters=parameters,
            placeholders=placeholders,
            results_dir=results_dir,
        )
        command = adapter_plan.command
        result_files = adapter_plan.result_files
        derivative_files = adapter_plan.derivative_files
        artifact_files = adapter_plan.artifact_files
        files_to_write = adapter_plan.files_to_write
    else:
        command_template = parameters.get("command")
        if not isinstance(command_template, list) or not command_template or not all(
            isinstance(item, str) and item for item in command_template
        ):
            raise ValueError("Processing pipeline parameters.command must be a non-empty string array.")
        command = [_substitute_string(item, placeholders, field_name="command") for item in command_template]
        result_files = parameters.get("result_files") or {}
        artifact_files = list(parameters.get("artifact_files") or [])

    for path, contents in files_to_write.items():
        target = Path(path).resolve()
        if not target.is_relative_to(results_dir):
            raise ValueError("Adapter generated files must stay under the job results directory.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    env = os.environ.copy()
    for key, value in (parameters.get("env") or {}).items():
        env[str(key)] = _substitute_string(str(value), placeholders, field_name=f"env.{key}")

    working_dir_value = parameters.get("working_dir")
    working_dir = _resolve_working_dir(working_dir_value, results_dir=results_dir, placeholders=placeholders)

    protein_table_path = _resolve_relative_artifact(result_files.get("protein_table"), results_dir=results_dir)
    peptide_table_path = _resolve_relative_artifact(result_files.get("peptide_table"), results_dir=results_dir)
    stats_json_path = _resolve_relative_artifact(result_files.get("stats_json"), results_dir=results_dir)
    delimiter = result_files.get("delimiter")
    if delimiter is not None and not isinstance(delimiter, str):
        raise ValueError("Processing pipeline parameters.result_files.delimiter must be a string when provided.")

    return PreparedJobExecution(
        command=command,
        env=env,
        working_dir=working_dir,
        results_dir=results_dir,
        log_path=log_path,
        protein_table_path=protein_table_path,
        peptide_table_path=peptide_table_path,
        stats_json_path=stats_json_path,
        delimiter=delimiter,
        derivative_files=derivative_files,
        artifact_files=_resolve_declared_artifacts(artifact_files, results_dir=results_dir, placeholders=placeholders),
    )


def _substitute_string(value: str, placeholders: dict[str, str], *, field_name: str) -> str:
    try:
        return value.format(**placeholders)
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder {exc.args[0]!r} in {field_name}.") from exc


def _resolve_working_dir(value, *, results_dir: Path, placeholders: dict[str, str]) -> Path:
    if not value:
        return results_dir
    if not isinstance(value, str):
        raise ValueError("Processing pipeline parameters.working_dir must be a string when provided.")

    substituted = _substitute_string(value, placeholders, field_name="working_dir")
    candidate = Path(substituted)
    if not candidate.is_absolute():
        candidate = (results_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _resolve_relative_artifact(value, *, results_dir: Path) -> Path | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise ValueError("Processing pipeline result file paths must be strings.")

    candidate = (results_dir / value).resolve()
    if not candidate.is_relative_to(results_dir):
        raise ValueError("Processing pipeline result file paths must stay under the job results directory.")
    return candidate


def _resolve_declared_artifacts(values, *, results_dir: Path, placeholders: dict[str, str]) -> list[dict]:
    if not values:
        return []
    if not isinstance(values, list):
        raise ValueError("Processing pipeline artifact_files must be a list.")
    resolved = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Processing pipeline artifact_files[{index}] must be an object.")
        path_value = item.get("path")
        if not path_value:
            raise ValueError(f"Processing pipeline artifact_files[{index}] is missing path.")
        substituted_path = _substitute_string(str(path_value), placeholders, field_name=f"artifact_files[{index}].path")
        candidate = Path(substituted_path)
        if not candidate.is_absolute():
            candidate = (results_dir / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if not candidate.is_relative_to(results_dir):
            raise ValueError("Processing pipeline artifact files must stay under the job results directory.")
        resolved.append({**item, "path": str(candidate)})
    return resolved
