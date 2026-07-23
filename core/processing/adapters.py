from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AdapterPlan:
    command: list[str]
    result_files: dict[str, str] = field(default_factory=dict)
    derivative_files: list[dict] = field(default_factory=list)
    artifact_files: list[dict] = field(default_factory=list)
    files_to_write: dict[str, str] = field(default_factory=dict)


def render_adapter_plan(
    *,
    adapter: str,
    parameters: dict,
    placeholders: dict[str, str],
    results_dir: Path,
) -> AdapterPlan:
    adapter = adapter.strip().lower()
    if adapter in {"msconvert", "proteowizard"}:
        return _msconvert_plan(parameters=parameters, placeholders=placeholders, results_dir=results_dir)
    if adapter in {"diann", "dia-nn"}:
        return _diann_plan(parameters=parameters, placeholders=placeholders, results_dir=results_dir)
    if adapter == "fragpipe":
        return _fragpipe_plan(parameters=parameters, placeholders=placeholders, results_dir=results_dir)
    if adapter in {"proteome-discoverer", "proteome_discoverer", "spectronaut", "enterprise-handoff"}:
        return _enterprise_handoff_plan(
            adapter=adapter,
            parameters=parameters,
            placeholders=placeholders,
            results_dir=results_dir,
        )
    raise ValueError(f"Unknown processing adapter: {adapter}")


def _msconvert_plan(*, parameters: dict, placeholders: dict[str, str], results_dir: Path) -> AdapterPlan:
    executable = _command_prefix(parameters.get("executable") or "msconvert")
    output_format = str(parameters.get("output_format") or "mzML")
    output_extension = output_format.lower().replace(".", "")
    if output_extension == "mzml":
        output_flag = "--mzML"
        derivative_type = "mzml"
        extension = "mzML"
    elif output_extension == "mzmlb":
        output_flag = "--mzMLb"
        derivative_type = "mzmlb"
        extension = "mzMLb"
    elif output_extension == "mgf":
        output_flag = "--mgf"
        derivative_type = "mgf"
        extension = "mgf"
    else:
        raise ValueError("msconvert adapter output_format must be mzML, mzMLb, or mgf.")

    output_name = _substitute(
        str(parameters.get("output_name") or f"{Path(placeholders['raw_file_path']).stem}.{extension}"),
        placeholders,
    )
    command = [
        *executable,
        placeholders["raw_file_path"],
        "-o",
        str(results_dir),
        output_flag,
        "--outfile",
        output_name,
    ]
    for item in parameters.get("filters") or []:
        command.extend(["--filter", _substitute(str(item), placeholders)])
    command.extend(_string_list(parameters.get("options") or [], placeholders))

    derivative_files = [
        {
            "derivative_type": derivative_type,
            "path": str((results_dir / output_name).resolve()),
            "format": output_format,
        }
    ]
    index_name = parameters.get("spectrum_index")
    if index_name:
        derivative_files.append(
            {
                "derivative_type": "spectrum_index",
                "path": str((results_dir / _substitute(str(index_name), placeholders)).resolve()),
                "format": "json",
            }
        )
    return AdapterPlan(command=command, derivative_files=derivative_files)


def _diann_plan(*, parameters: dict, placeholders: dict[str, str], results_dir: Path) -> AdapterPlan:
    executable = _command_prefix(parameters.get("executable") or "diann")
    report_name = _substitute(str(parameters.get("report") or "diann-report.tsv"), placeholders)
    command = [
        *executable,
        "--f",
        placeholders["raw_file_path"],
        "--out",
        str((results_dir / report_name).resolve()),
    ]
    library = parameters.get("library")
    if library:
        command.extend(["--lib", _substitute(str(library), placeholders)])
    fasta = parameters.get("fasta")
    if fasta:
        command.extend(["--fasta", _substitute(str(fasta), placeholders)])
    command.extend(_string_list(parameters.get("options") or [], placeholders))
    artifact_files = [
        {
            "artifact_type": "diann_report",
            "path": str((results_dir / report_name).resolve()),
            "format": "tsv",
        }
    ]
    artifact_files.extend(list(parameters.get("artifact_files") or []))
    return AdapterPlan(
        command=command,
        result_files=dict(parameters.get("result_files") or {}),
        artifact_files=artifact_files,
    )


def _fragpipe_plan(*, parameters: dict, placeholders: dict[str, str], results_dir: Path) -> AdapterPlan:
    executable = _command_prefix(parameters.get("executable") or "fragpipe")
    workflow = parameters.get("workflow")
    if not workflow:
        raise ValueError("fragpipe adapter requires parameters.workflow.")
    manifest = parameters.get("manifest")
    files_to_write = {}
    if manifest:
        manifest_path = Path(_substitute(str(manifest), placeholders))
    else:
        manifest_path = (results_dir / "fragpipe-manifest.tsv").resolve()
        files_to_write[str(manifest_path)] = (
            f"{placeholders['raw_file_path']}\t{placeholders['run_name'] or 'sample'}\t1\t"
            f"{parameters.get('data_type') or 'DDA'}\n"
        )

    command = [
        *executable,
        "--headless",
        "--workflow",
        _substitute(str(workflow), placeholders),
        "--manifest",
        str(manifest_path),
        "--workdir",
        str(results_dir),
    ]
    if parameters.get("ram_gb"):
        command.extend(["--ram", str(parameters["ram_gb"])])
    if parameters.get("threads"):
        command.extend(["--threads", str(parameters["threads"])])
    command.extend(_string_list(parameters.get("options") or [], placeholders))
    return AdapterPlan(
        command=command,
        result_files=dict(parameters.get("result_files") or {}),
        artifact_files=list(parameters.get("artifact_files") or []),
        files_to_write=files_to_write,
    )


def _enterprise_handoff_plan(
    *,
    adapter: str,
    parameters: dict,
    placeholders: dict[str, str],
    results_dir: Path,
) -> AdapterPlan:
    command_template = parameters.get("command")
    if not isinstance(command_template, list) or not command_template:
        raise ValueError(f"{adapter} adapter requires a site-specific parameters.command array.")
    command_placeholders = {**placeholders, "results_dir": str(results_dir)}
    return AdapterPlan(
        command=[_substitute(str(item), command_placeholders) for item in command_template],
        result_files=dict(parameters.get("result_files") or {}),
        artifact_files=list(parameters.get("artifact_files") or []),
    )


def _command_prefix(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return value
    raise ValueError("Adapter executable must be a string or non-empty string array.")


def _string_list(values, placeholders: dict[str, str]) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("Adapter options must be a string array.")
    return [_substitute(str(item), placeholders) for item in values]


def _substitute(value: str, placeholders: dict[str, str]) -> str:
    try:
        return value.format(**placeholders)
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder {exc.args[0]!r} in adapter parameters.") from exc
