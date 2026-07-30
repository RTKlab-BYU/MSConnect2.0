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
    if adapter in {"skyline", "skylinecmd"}:
        return _skyline_plan(parameters=parameters, placeholders=placeholders, results_dir=results_dir)
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
    if parameters.get("fasta"):
        command.extend(["--fasta", _substitute(str(parameters["fasta"]), placeholders)])
    command.extend(_string_list(parameters.get("options") or [], placeholders))
    return AdapterPlan(
        command=command,
        result_files=dict(parameters.get("result_files") or {}),
        artifact_files=list(parameters.get("artifact_files") or []),
        files_to_write=files_to_write,
    )


def _skyline_plan(*, parameters: dict, placeholders: dict[str, str], results_dir: Path) -> AdapterPlan:
    executable = _command_prefix(parameters.get("executable") or "SkylineCmd")
    document = parameters.get("document")
    if not document:
        raise ValueError("skyline adapter requires parameters.document.")

    report_name = _substitute(str(parameters.get("report") or "skyline-report.csv"), placeholders)
    command = [
        *executable,
        f"--in={_substitute(str(document), placeholders)}",
        f"--import-file={placeholders['raw_file_path']}",
        f"--report-file={str((results_dir / report_name).resolve())}",
    ]
    report_name_value = parameters.get("report_name")
    if report_name_value:
        command.append(f"--report-name={_substitute(str(report_name_value), placeholders)}")
    report_add = parameters.get("report_add")
    if report_add:
        command.append(f"--report-add={_substitute(str(report_add), placeholders)}")
    report_format = parameters.get("report_format")
    if report_format:
        command.append(f"--report-format={_substitute(str(report_format), placeholders)}")
    if parameters.get("report_invariant"):
        command.append("--report-invariant")
    report_conflict_resolution = parameters.get("report_conflict_resolution")
    if report_conflict_resolution:
        command.append(f"--report-conflict-resolution={_substitute(str(report_conflict_resolution), placeholders)}")
    chromatogram_file = parameters.get("chromatogram_file")
    if chromatogram_file:
        command.append(f"--chromatogram-file={_substitute(str(chromatogram_file), placeholders)}")
    for flag in parameters.get("chromatogram_options") or []:
        command.append(_substitute(str(flag), placeholders))
    output_document = parameters.get("out")
    if output_document:
        command.append(f"--out={_substitute(str(output_document), placeholders)}")
    if parameters.get("save"):
        command.append("--save")
    command.extend(_string_list(parameters.get("options") or [], placeholders))
    artifact_files = [
        {
            "artifact_type": "other",
            "path": str((results_dir / report_name).resolve()),
            "format": "csv",
            "metadata": {"software": "skyline", "role": "report"},
        }
    ]
    artifact_files.extend(list(parameters.get("artifact_files") or []))
    return AdapterPlan(
        command=command,
        result_files=dict(parameters.get("result_files") or {}),
        artifact_files=artifact_files,
    )


def _enterprise_handoff_plan(
    *,
    adapter: str,
    parameters: dict,
    placeholders: dict[str, str],
    results_dir: Path,
) -> AdapterPlan:
    results_dir = results_dir.resolve()
    command_template = parameters.get("command")
    if not isinstance(command_template, list) or not command_template:
        raise ValueError(f"{adapter} adapter requires a site-specific parameters.command array.")
    command_placeholders = {**placeholders, "results_dir": str(results_dir)}
    artifact_files = list(parameters.get("artifact_files") or [])
    handoff_name = parameters.get("handoff_manifest") or f"{adapter}-handoff.json"
    handoff_candidate = Path(_substitute(str(handoff_name), command_placeholders))
    if not handoff_candidate.is_absolute():
        handoff_path = (results_dir / handoff_candidate).resolve()
    else:
        handoff_path = handoff_candidate.resolve()
    if not handoff_path.is_relative_to(results_dir):
        raise ValueError("Enterprise handoff manifest must stay under the job results directory.")
    handoff_payload = {
        "adapter": adapter,
        "raw_file_path": placeholders["raw_file_path"],
        "run_name": placeholders.get("run_name", ""),
        "results_dir": str(results_dir),
        "command": [_substitute(str(item), command_placeholders) for item in command_template],
        "site_notes": parameters.get("site_notes", ""),
    }
    artifact_files.append(
        {
            "artifact_type": "enterprise_export",
            "path": str(handoff_path),
            "format": "json",
            "metadata": {"software": adapter, "role": "handoff_manifest"},
        }
    )
    return AdapterPlan(
        command=handoff_payload["command"],
        result_files=dict(parameters.get("result_files") or {}),
        artifact_files=artifact_files,
        files_to_write={str(handoff_path): _json_dump(handoff_payload)},
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


def _json_dump(value: dict) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True) + "\n"
