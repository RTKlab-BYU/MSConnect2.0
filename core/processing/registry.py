import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

from core.processing.diann import validation_errors

REFERENCE_KINDS = {"fasta", "speclib", "skyline_document", "fragpipe_workflow"}
ENGINE_NAMES = {"diann", "fragpipe", "msconvert", "proteome-discoverer", "skyline", "spectronaut"}
IMAGE_ENGINE_NAMES = {"diann", "fragpipe", "skyline"}


def registry_path() -> Path:
    return Path(settings.PROCESSOR_SHARED_STORAGE_ROOT) / "config" / "processor-registry.json"


def default_registry() -> dict:
    return {
        "schema_version": 1,
        "engines": {engine: {} for engine in sorted(ENGINE_NAMES)},
        "references": {kind: {} for kind in sorted(REFERENCE_KINDS)},
        "settings": {engine: {} for engine in sorted(ENGINE_NAMES)},
    }


def load_registry(path: Path | None = None) -> dict:
    path = path or registry_path()
    if not path.exists():
        return default_registry()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"Processor registry is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CommandError(f"Processor registry must contain a JSON object: {path}")
    registry = default_registry()
    registry.update(payload)
    registry["engines"] = {**registry["engines"], **payload.get("engines", {})}
    registry["references"] = {**registry["references"], **payload.get("references", {})}
    registry["settings"] = {**registry["settings"], **payload.get("settings", {})}
    return registry


def save_registry(registry: dict, path: Path | None = None) -> Path:
    path = path or registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def add_reference(
    *,
    kind: str,
    key: str,
    source_path: str,
    copy: bool = False,
    force: bool = False,
    registry_file: Path | None = None,
) -> dict:
    kind = normalize_kind(kind)
    key = normalize_key(key)
    source = Path(source_path)
    stored_path = str(source)
    if copy:
        if not source.exists():
            raise CommandError(f"Reference source path does not exist: {source}")
        target = _reference_target(kind=kind, key=key, source=source)
        if target.exists() and not force:
            raise CommandError(f"Reference target already exists: {target}. Use --force to replace it.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        stored_path = str(target)

    registry = load_registry(registry_file)
    registry.setdefault("references", {}).setdefault(kind, {})[key] = {
        "kind": kind,
        "key": key,
        "path": stored_path,
        "updated_at": _timestamp(),
    }
    save_registry(registry, registry_file)
    return registry["references"][kind][key]


def add_settings(
    *,
    engine: str,
    key: str,
    values: dict,
    registry_file: Path | None = None,
) -> dict:
    engine = normalize_engine(engine)
    key = normalize_key(key)
    if not isinstance(values, dict):
        raise CommandError("Settings JSON must contain an object.")
    registry = load_registry(registry_file)
    registry.setdefault("settings", {}).setdefault(engine, {})[key] = {
        "engine": engine,
        "key": key,
        "values": values,
        "updated_at": _timestamp(),
    }
    save_registry(registry, registry_file)
    return registry["settings"][engine][key]


def add_engine_profile(
    *,
    engine: str,
    version: str,
    image: str = "",
    executable: str = "",
    version_command: list[str] | None = None,
    install_type: str = "",
    image_digest: str = "",
    source: str = "",
    source_sha256: str = "",
    license_note: str = "",
    registry_file: Path | None = None,
) -> dict:
    engine = normalize_engine(engine)
    version = normalize_version(version)
    install_type = normalize_install_type(install_type or ("image" if engine in IMAGE_ENGINE_NAMES else "external"))
    if install_type == "image" and engine not in IMAGE_ENGINE_NAMES:
        raise CommandError(f"{engine} is configured as an external worker engine, not a bundled image engine.")
    registry = load_registry(registry_file)
    entry = {
        "engine": engine,
        "version": version,
        "install_type": install_type,
        "image": str(image or "").strip(),
        "image_digest": str(image_digest or "").strip(),
        "executable": str(executable or "").strip() or _default_executable(engine),
        "version_command": version_command or [],
        "software_version": f"{_engine_label(engine)} {version}",
        "source": str(source or "").strip(),
        "source_sha256": str(source_sha256 or "").strip(),
        "license_note": str(license_note or "").strip(),
        "updated_at": _timestamp(),
    }
    registry.setdefault("engines", {}).setdefault(engine, {})[version] = entry
    save_registry(registry, registry_file)
    return entry


def resolve_pipeline_parameters(parameters: dict, *, engine: str | None = None) -> dict:
    if not isinstance(parameters, dict):
        return parameters
    registry = load_registry()
    normalized_engine = normalize_engine(engine or parameters.get("required_engine") or parameters.get("adapter") or "")
    resolved = deepcopy(parameters)
    engine_version = resolved.get("required_engine_version") or resolved.get("engine_version")
    if engine_version and normalized_engine:
        try:
            profile = engine_profile(registry=registry, engine=normalized_engine, version=str(engine_version))
        except CommandError:
            profile = None
        if profile:
            resolved.setdefault("executable", profile.get("executable") or _default_executable(normalized_engine))
            if profile.get("version_command"):
                resolved.setdefault("version_command", profile["version_command"])
            resolved.setdefault("software_version", profile.get("software_version") or str(engine_version))
            resolved.setdefault("required_engine_version", profile["version"])
            resolved.setdefault(
                "engine_profile",
                {
                    "engine": profile["engine"],
                    "version": profile["version"],
                    "install_type": profile["install_type"],
                    "image": profile.get("image", ""),
                    "image_digest": profile.get("image_digest", ""),
                },
            )
        else:
            resolved.setdefault("required_engine_version", str(engine_version))
            resolved.setdefault("software_version", f"{_engine_label(normalized_engine)} {engine_version}")

    settings_ref = resolved.get("settings_ref")
    if settings_ref:
        settings_values = _settings_values(registry=registry, engine=normalized_engine, key=str(settings_ref))
        resolved = {**deepcopy(settings_values), **resolved}

    if normalized_engine in {"diann", "dia-nn"}:
        resolved["adapter"] = resolved.get("adapter") or "diann"
        _resolve_reference_key(resolved, registry=registry, source_key="fasta_ref", target_key="fasta", kind="fasta")
        _resolve_reference_key(
            resolved,
            registry=registry,
            source_key="library_ref",
            target_key="library",
            kind="speclib",
        )
        _append_input_files(resolved, ["fasta", "library"])
    elif normalized_engine == "fragpipe":
        resolved["adapter"] = resolved.get("adapter") or "fragpipe"
        _resolve_reference_key(
            resolved,
            registry=registry,
            source_key="workflow_ref",
            target_key="workflow",
            kind="fragpipe_workflow",
        )
        _resolve_reference_key(resolved, registry=registry, source_key="fasta_ref", target_key="fasta", kind="fasta")
        _append_input_files(resolved, ["workflow", "fasta"])
    elif normalized_engine == "skyline":
        resolved["adapter"] = resolved.get("adapter") or "skyline"
        _resolve_reference_key(
            resolved,
            registry=registry,
            source_key="document_ref",
            target_key="document",
            kind="skyline_document",
        )
        _append_input_files(resolved, ["document"])

    return resolved


def validate_diann_pipeline_settings(settings_payload: dict | None, *, allow_performance_tags: bool) -> list[str]:
    return validation_errors(settings_payload, allow_performance_tags=allow_performance_tags)


def validate_registry_selection(*, engine: str, settings_key: str = "", require_executable: bool = False) -> list[str]:
    engine = normalize_engine(engine)
    registry = load_registry()
    errors = []
    if settings_key:
        try:
            values = _settings_values(registry=registry, engine=engine, key=settings_key)
        except CommandError as exc:
            return [str(exc)]
    else:
        values = {}

    for ref_key, kind in _reference_requirements(engine).items():
        if values.get(ref_key):
            try:
                path = _reference_path(registry=registry, kind=kind, key=str(values[ref_key]))
            except CommandError as exc:
                errors.append(str(exc))
                continue
            if not Path(path).exists():
                errors.append(f"Processor reference path does not exist: {kind}/{values[ref_key]} -> {path}")

    for path_key in _path_requirements(engine):
        if values.get(path_key) and not Path(str(values[path_key])).exists():
            errors.append(f"Processor settings path does not exist: {path_key} -> {values[path_key]}")

    if require_executable:
        executable = values.get("executable") or _default_executable(engine)
        if isinstance(executable, list):
            executable = executable[0] if executable else ""
        if not _executable_available(str(executable or "")):
            errors.append(f"Executable is not available for {engine}: {executable}")
    return errors


def validate_engine_profile(
    *,
    engine: str,
    version: str,
    require_image: bool = False,
    require_executable: bool = False,
) -> list[str]:
    registry = load_registry()
    errors = []
    try:
        profile = engine_profile(registry=registry, engine=engine, version=version)
    except CommandError as exc:
        return [str(exc)]

    if require_image and not profile.get("image"):
        errors.append(f"Engine profile is missing an image: {profile['engine']} {profile['version']}")
    if require_executable and not _executable_available(str(profile.get("executable") or "")):
        errors.append(
            f"Executable is not available for {profile['engine']} {profile['version']}: "
            f"{profile.get('executable')}"
        )
    return errors


def normalize_kind(value: str) -> str:
    kind = str(value or "").strip().lower().replace("-", "_")
    if kind not in REFERENCE_KINDS:
        raise CommandError(f"Unsupported reference kind: {value}")
    return kind


def normalize_engine(value: str) -> str:
    engine = str(value or "").strip().lower().replace("_", "-")
    if engine == "dia-nn":
        engine = "diann"
    if engine in {"pd", "proteomediscoverer", "proteome_discoverer"}:
        engine = "proteome-discoverer"
    if engine and engine not in ENGINE_NAMES:
        raise CommandError(f"Unsupported processor engine: {value}")
    return engine


def normalize_install_type(value: str) -> str:
    install_type = str(value or "").strip().lower().replace("_", "-")
    if install_type not in {"image", "external"}:
        raise CommandError(f"Unsupported engine install type: {value}")
    return install_type


def normalize_key(value: str) -> str:
    key = str(value or "").strip()
    if not key:
        raise CommandError("Registry key is required.")
    if any(character in key for character in "/\\"):
        raise CommandError("Registry keys must not contain path separators.")
    return key


def normalize_version(value: str) -> str:
    version = str(value or "").strip()
    if not version:
        raise CommandError("Engine version is required.")
    if any(character in version for character in "/\\"):
        raise CommandError("Engine versions must not contain path separators.")
    return version


def engine_profile(*, registry: dict, engine: str, version: str) -> dict:
    engine = normalize_engine(engine)
    version = normalize_version(version)
    entry = (registry.get("engines") or {}).get(engine, {}).get(version)
    if not entry:
        raise CommandError(f"Engine profile does not exist: {engine}/{version}")
    if not isinstance(entry, dict):
        raise CommandError(f"Engine profile must contain an object: {engine}/{version}")
    return entry


def _settings_values(*, registry: dict, engine: str, key: str) -> dict:
    engine = normalize_engine(engine)
    key = normalize_key(key)
    entry = (registry.get("settings") or {}).get(engine, {}).get(key)
    if not entry:
        raise CommandError(f"Processor settings key does not exist: {engine}/{key}")
    values = entry.get("values") or {}
    if not isinstance(values, dict):
        raise CommandError(f"Processor settings entry must contain an object: {engine}/{key}")
    return values


def _resolve_reference_key(resolved: dict, *, registry: dict, source_key: str, target_key: str, kind: str) -> None:
    key = resolved.get(source_key)
    if not key or resolved.get(target_key):
        return
    resolved[target_key] = _reference_path(registry=registry, kind=kind, key=str(key))


def _append_input_files(resolved: dict, keys: list[str]) -> None:
    input_files = list(resolved.get("input_files") or [])
    for key in keys:
        value = resolved.get(key)
        if value and value not in input_files:
            input_files.append(value)
    if input_files:
        resolved["input_files"] = input_files


def _reference_path(*, registry: dict, kind: str, key: str) -> str:
    kind = normalize_kind(kind)
    key = normalize_key(key)
    entry = (registry.get("references") or {}).get(kind, {}).get(key)
    if not entry:
        raise CommandError(f"Processor reference key does not exist: {kind}/{key}")
    path = str(entry.get("path") or "").strip()
    if not path:
        raise CommandError(f"Processor reference key has no path: {kind}/{key}")
    return path


def _reference_target(*, kind: str, key: str, source: Path) -> Path:
    root_names = {
        "fasta": ("reference", "fasta"),
        "speclib": ("reference", "speclib"),
        "skyline_document": ("skyline",),
        "fragpipe_workflow": ("workflows", "fragpipe"),
    }
    suffix = source.suffix if source.is_file() else ""
    return Path(settings.PROCESSOR_SHARED_STORAGE_ROOT).joinpath(*root_names[kind], f"{key}{suffix}")


def _reference_requirements(engine: str) -> dict[str, str]:
    if engine == "diann":
        return {"fasta_ref": "fasta", "library_ref": "speclib"}
    if engine == "fragpipe":
        return {"fasta_ref": "fasta", "workflow_ref": "fragpipe_workflow"}
    if engine == "skyline":
        return {"document_ref": "skyline_document"}
    return {}


def _path_requirements(engine: str) -> list[str]:
    if engine == "diann":
        return ["fasta", "library"]
    if engine == "fragpipe":
        return ["fasta", "workflow"]
    if engine == "skyline":
        return ["document"]
    return []


def _default_executable(engine: str) -> str:
    return {
        "diann": "diann",
        "fragpipe": "fragpipe",
        "proteome-discoverer": "ProteomeDiscoverer.exe",
        "skyline": "SkylineCmd",
        "spectronaut": "Spectronaut.exe",
    }.get(engine, engine)


def _engine_label(engine: str) -> str:
    return {
        "diann": "DIA-NN",
        "fragpipe": "FragPipe",
        "proteome-discoverer": "Proteome Discoverer",
        "skyline": "Skyline",
        "spectronaut": "Spectronaut",
    }.get(engine, engine)


def _executable_available(executable: str) -> bool:
    if not executable:
        return False
    if shutil.which(executable):
        return True
    return Path(executable).exists()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
