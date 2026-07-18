import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.models import IngestionFailure, RawFile, RawFileStatus, Run

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


def import_raw_path(
    source_path: Path,
    *,
    storage_root: Path,
    run=None,
    dry_run: bool = False,
    match_run_by_name: bool = False,
) -> RawFileImportResult:
    source_path = Path(source_path)
    storage_root = Path(storage_root)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    checksum, size_bytes = hash_path(source_path)
    filename_metadata = parse_filename_metadata(source_path)
    matched_run = run
    if matched_run is None and match_run_by_name:
        matched_run = find_run_for_path(source_path)

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
            run=matched_run,
            source_path=str(source_path.resolve()),
            storage_path=str(destination.resolve()),
            filename=source_path.name,
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            imported_at=timezone.now(),
            status=RawFileStatus.IMPORTED,
            metadata={"importer": "ingest_raw_files", "filename_metadata": filename_metadata},
        )

    return RawFileImportResult(
        source_path=source_path,
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        raw_file=raw_file,
        created=True,
    )


def parse_filename_metadata(source_path: Path) -> dict:
    stem = source_path.stem
    tokens = [token for token in re.split(r"[_\-.]+", stem) if token]
    metadata = {"tokens": tokens}

    for token in tokens:
        lowered = token.lower()
        if lowered.startswith(("run", "r")) and len(token) > 1:
            metadata.setdefault("run_token", token)
            metadata.setdefault("run_name", token)
        if lowered.startswith(("sample", "s")) and len(token) > 1:
            metadata.setdefault("sample_token", token)

    date_match = re.search(r"(20\d{2}[01]\d[0-3]\d)", stem)
    if date_match:
        metadata["acquisition_date"] = date_match.group(1)

    return metadata


def find_run_for_path(source_path: Path):
    metadata = parse_filename_metadata(source_path)
    run_name = metadata.get("run_name")
    if not run_name:
        return None

    candidates = Run.objects.filter(run_name__iexact=run_name).order_by("id")
    if candidates.count() == 1:
        return candidates.first()
    return None


def record_ingestion_failure(
    source_path: Path,
    failure_reason: str,
    *,
    metadata: dict | None = None,
) -> IngestionFailure:
    source_path = Path(source_path)
    resolved = str(source_path.resolve(strict=False))

    failure, created = IngestionFailure.objects.get_or_create(
        source_path=resolved,
        defaults={
            "filename": source_path.name,
            "failure_reason": failure_reason,
            "metadata": metadata or {},
        },
    )
    if created:
        return failure

    IngestionFailure.objects.filter(pk=failure.pk).update(
        filename=source_path.name,
        failure_reason=failure_reason,
        metadata=metadata or {},
        seen_count=F("seen_count") + 1,
    )
    return IngestionFailure.objects.get(pk=failure.pk)


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


def ensure_copied_raw_path(source_path: Path, destination: Path) -> bool:
    if destination.exists():
        return False

    copy_raw_path(source_path, destination)
    return True


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
