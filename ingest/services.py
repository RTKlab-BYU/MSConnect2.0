import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from core.models import RawFile, RawFileStatus

DEFAULT_RAW_SUFFIXES = (".raw", ".RAW", ".mzML", ".mzXML", ".wiff", ".scan", ".d")


@dataclass(frozen=True)
class RawFileImportResult:
    source_path: Path
    checksum_sha256: str
    size_bytes: int
    raw_file: RawFile | None = None
    created: bool = False
    skipped: bool = False


def discover_raw_paths(source_root: Path, *, suffixes=DEFAULT_RAW_SUFFIXES, recursive: bool = False):
    source_root = Path(source_root)
    normalized_suffixes = {suffix.lower() for suffix in suffixes}

    if source_root.is_file() or _is_raw_directory(source_root, normalized_suffixes):
        if source_root.suffix.lower() in normalized_suffixes:
            yield source_root
        return

    for root, dirs, files in _walk_source(source_root, recursive=recursive):
        root_path = Path(root)

        raw_dirs = [directory for directory in dirs if Path(directory).suffix.lower() in normalized_suffixes]
        for directory in raw_dirs:
            yield root_path / directory

        dirs[:] = [directory for directory in dirs if directory not in raw_dirs]

        for filename in files:
            path = root_path / filename
            if path.suffix.lower() in normalized_suffixes:
                yield path


def import_raw_path(source_path: Path, *, storage_root: Path, run=None, dry_run: bool = False) -> RawFileImportResult:
    source_path = Path(source_path)
    storage_root = Path(storage_root)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    checksum, size_bytes = hash_path(source_path)

    existing = RawFile.objects.filter(checksum_sha256=checksum, size_bytes=size_bytes).first()
    if existing:
        return RawFileImportResult(
            source_path=source_path,
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            raw_file=existing,
            skipped=True,
        )

    destination = build_storage_path(storage_root, source_path, checksum)
    if dry_run:
        return RawFileImportResult(source_path=source_path, checksum_sha256=checksum, size_bytes=size_bytes)

    copy_raw_path(source_path, destination)

    with transaction.atomic():
        raw_file = RawFile.objects.create(
            run=run,
            source_path=str(source_path.resolve()),
            storage_path=str(destination.resolve()),
            filename=source_path.name,
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            imported_at=timezone.now(),
            status=RawFileStatus.IMPORTED,
            metadata={"importer": "ingest_raw_files"},
        )

    return RawFileImportResult(
        source_path=source_path,
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        raw_file=raw_file,
        created=True,
    )


def hash_path(path: Path) -> tuple[str, int]:
    path = Path(path)
    if path.is_file():
        return _hash_file(path)

    digest = hashlib.sha256()
    total_size = 0

    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative_name = child.relative_to(path).as_posix().encode()
        digest.update(relative_name)
        file_digest, file_size = _hash_file(child)
        digest.update(file_digest.encode())
        total_size += file_size

    return digest.hexdigest(), total_size


def build_storage_path(storage_root: Path, source_path: Path, checksum: str) -> Path:
    storage_root = Path(storage_root)
    shard = checksum[:2]
    return storage_root / shard / f"{checksum}_{Path(source_path).name}"


def copy_raw_path(source_path: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path.is_dir():
        shutil.copytree(source_path, destination)
    else:
        shutil.copy2(source_path, destination)


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0

    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)

    return digest.hexdigest(), size


def _walk_source(source_root: Path, *, recursive: bool):
    for root, dirs, files in source_root.walk():
        yield root, dirs, files
        if not recursive:
            dirs[:] = []


def _is_raw_directory(path: Path, suffixes: set[str]) -> bool:
    return path.is_dir() and path.suffix.lower() in suffixes

