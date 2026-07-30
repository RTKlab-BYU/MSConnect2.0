import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageRootReport:
    root: Path
    exists: bool
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float


def configured_roots(values: list[str]) -> list[Path]:
    roots = []
    seen = set()
    for value in values:
        path = Path(value).expanduser().resolve()
        if str(path) in seen:
            continue
        roots.append(path)
        seen.add(str(path))
    return roots


def capacity_report(root: Path) -> StorageRootReport:
    root = Path(root).expanduser().resolve()
    if not root.exists():
        return StorageRootReport(root=root, exists=False, total_bytes=0, used_bytes=0, free_bytes=0, used_percent=0.0)
    usage = shutil.disk_usage(root)
    used = usage.total - usage.free
    used_percent = round((used / usage.total) * 100, 2) if usage.total else 0.0
    return StorageRootReport(
        root=root,
        exists=True,
        total_bytes=usage.total,
        used_bytes=used,
        free_bytes=usage.free,
        used_percent=used_percent,
    )


def choose_storage_root(roots: list[Path], *, required_bytes: int = 0, block_percent: int = 95) -> Path:
    candidates = []
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        report = capacity_report(root)
        if report.free_bytes < required_bytes:
            continue
        if report.used_percent >= block_percent:
            continue
        candidates.append(report)
    if not candidates:
        raise RuntimeError("No configured storage root has enough free space.")
    candidates.sort(key=lambda item: (item.used_percent, -item.free_bytes, str(item.root)))
    return candidates[0].root


def safe_archive_name(filename: str, checksum: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in filename)
    return f"{checksum[:16]}_{safe}.zip"


def zip_raw_path(source_path: Path, target_path: Path) -> None:
    source_path = Path(source_path)
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_suffix(target_path.suffix + ".tmp")
    if temporary_path.exists():
        temporary_path.unlink()

    with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        if source_path.is_dir():
            for child in sorted(item for item in source_path.rglob("*") if item.is_file()):
                archive.write(child, arcname=Path(source_path.name) / child.relative_to(source_path))
        else:
            archive.write(source_path, arcname=source_path.name)
    temporary_path.replace(target_path)


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def copy_and_verify(source_path: Path, target_path: Path, expected_checksum: str) -> tuple[str, int]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_suffix(target_path.suffix + ".tmp")
    if temporary_path.exists():
        temporary_path.unlink()
    shutil.copy2(source_path, temporary_path)
    checksum, size_bytes = sha256_file(temporary_path)
    if checksum != expected_checksum:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch while copying {source_path} to {target_path}.")
    temporary_path.replace(target_path)
    return checksum, size_bytes
