from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.models import DeploymentSetting

PERFORMANCE_SETTING_KEYS = {"threads", "temp"}
EXPERIMENTAL_SETTING_KEYS = {
    "report",
    "q_value",
    "matrices",
    "individual_reports",
    "individual_mass_acc",
    "individual_windows",
    "generate_speclib",
    "fasta_search",
    "out_library",
    "direct_quant",
    "matrix_qvalue",
    "mass_acc",
    "mass_acc_ms1",
    "mass_acc_cal",
    "extra_options",
    "options",
    "fasta",
    "library",
    "executable",
    "version_command",
    "software_version",
    "required_engine_version",
}


def normalize_diann_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(settings or {})
    tags = _normalize_tag_groups(payload.pop("tags", None))
    tags["performance"].update(_normalize_tag_group(payload.pop("performance_tags", None)))
    tags["experimental"].update(_normalize_tag_group(payload.pop("experimental_tags", None)))

    for key in list(payload.keys()):
        if key in PERFORMANCE_SETTING_KEYS:
            tags["performance"][key] = payload.pop(key)
        elif key in EXPERIMENTAL_SETTING_KEYS:
            tags["experimental"][key] = payload.pop(key)

    payload["tags"] = tags
    return payload


def diann_effective_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_diann_settings(settings)
    tags = normalized.get("tags") or {}
    effective = {key: value for key, value in normalized.items() if key != "tags"}
    effective.update(tags.get("experimental") or {})
    effective.update(tags.get("performance") or {})
    return effective


def build_diann_command_options(settings: dict[str, Any] | None) -> list[str]:
    effective = diann_effective_settings(settings)
    options: list[str] = []
    if _boolish(effective.get("matrices")):
        options.append("--matrices")
    if _boolish(effective.get("individual_reports")):
        options.append("--individual-reports")
    if _boolish(effective.get("individual_mass_acc")):
        options.append("--individual-mass-acc")
    if _boolish(effective.get("individual_windows")):
        options.append("--individual-windows")
    if _boolish(effective.get("direct_quant")):
        options.append("--direct-quant")
    if _boolish(effective.get("fasta_search")):
        options.append("--fasta-search")
    if effective.get("q_value") not in (None, ""):
        options.extend(["--qvalue", str(effective["q_value"])])
    if effective.get("matrix_qvalue") not in (None, ""):
        options.extend(["--matrix-qvalue", str(effective["matrix_qvalue"])])
    if effective.get("mass_acc") not in (None, ""):
        options.extend(["--mass-acc", str(effective["mass_acc"])])
    if effective.get("mass_acc_ms1") not in (None, ""):
        options.extend(["--mass-acc-ms1", str(effective["mass_acc_ms1"])])
    if effective.get("mass_acc_cal") not in (None, ""):
        options.extend(["--mass-acc-cal", str(effective["mass_acc_cal"])])
    if effective.get("threads") not in (None, ""):
        options.extend(["--threads", str(effective["threads"])])
    options.extend(_string_list(effective.get("options") or []))
    options.extend(_string_list(effective.get("extra_options") or []))
    return options


def validation_errors(
    settings: dict[str, Any] | None,
    *,
    allow_performance_tags: bool,
) -> list[str]:
    if settings is None:
        return []
    if not isinstance(settings, dict):
        return ["DIA-NN settings must be a JSON object."]

    normalized = normalize_diann_settings(settings)
    tags = normalized.get("tags") or {}
    errors: list[str] = []

    performance = tags.get("performance") or {}
    experimental = tags.get("experimental") or {}
    if not allow_performance_tags and performance:
        errors.append("Performance tags are admin-controlled and cannot be set here.")

    for key, value in performance.items():
        if key not in PERFORMANCE_SETTING_KEYS:
            errors.append(f"Unsupported performance tag: {key}.")
            continue
        if key == "threads" and _positive_int(value) is None:
            errors.append("Performance tag threads must be a positive integer.")
        if key == "temp" and not str(value or "").strip():
            errors.append("Performance tag temp must be a non-empty path.")

    for key, value in experimental.items():
        if key in PERFORMANCE_SETTING_KEYS:
            errors.append(f"Performance tag {key} must be moved to the admin-controlled performance tags.")
            continue
        if key == "threads" and _positive_int(value) is None:
            errors.append("threads must be a positive integer when provided.")
        if key == "temp" and not str(value or "").strip():
            errors.append("temp must be a non-empty path when provided.")

    for key in ("options", "extra_options"):
        value = normalized.get(key) or experimental.get(key)
        if value and not isinstance(value, list):
            errors.append(f"DIA-NN {key} must be a list when provided.")

    return errors


def site_performance_tags() -> dict[str, Any]:
    deployment = DeploymentSetting.objects.filter(scope="site").first()
    metadata = deployment.metadata if deployment else {}
    if not isinstance(metadata, dict):
        return {}
    diann_metadata = metadata.get("diann") if isinstance(metadata.get("diann"), dict) else {}
    if not isinstance(diann_metadata, dict):
        diann_metadata = {}
    candidate = diann_metadata.get("performance_tags")
    if candidate is None:
        candidate = metadata.get("diann_performance_tags")
    return _normalize_tag_group(candidate)


def _normalize_tag_groups(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {"performance": {}, "experimental": {}}
    return {
        "performance": _normalize_tag_group(value.get("performance") or value.get("performance_tags")),
        "experimental": _normalize_tag_group(value.get("experimental") or value.get("experimental_tags")),
    }


def _normalize_tag_group(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key).strip(): item for key, item in value.items() if str(key).strip()}


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item).strip()]


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
