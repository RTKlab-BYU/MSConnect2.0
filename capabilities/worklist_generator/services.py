from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from pathlib import Path

from django.conf import settings

from .engine import run_worklist


ALLOWED_SUFFIXES = {".xlsx", ".xlsm"}
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")


def results_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / "worklist_generator_results"
    root.mkdir(parents=True, exist_ok=True)
    return root


def generate_worklists(uploaded_file) -> dict:
    """Persist one generated pair in an isolated, downloadable job directory."""
    original_name = Path(uploaded_file.name or "worklist.xlsx").name
    if Path(original_name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("Upload an Excel workbook with an .xlsx or .xlsm extension.")

    job_id = uuid.uuid4()
    job_dir = results_root() / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=False)
    upload_dir = Path(settings.MEDIA_ROOT) / "worklist_generator_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=Path(original_name).suffix.lower(),
            dir=upload_dir,
            delete=False,
        ) as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
            input_path = Path(destination.name)

        ms_path, lc_path = (Path(path) for path in run_worklist(input_path, output_dir=job_dir))
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        if "input_path" in locals():
            input_path.unlink(missing_ok=True)

    files = [
        {"kind": "ms", "name": ms_path.name, "url_name": ms_path.name},
        {"kind": "lc", "name": lc_path.name, "url_name": lc_path.name},
    ]
    return {"job_id": str(job_id), "files": files}


def result_path(job_id: uuid.UUID, filename: str) -> Path | None:
    if not SAFE_FILENAME.fullmatch(filename) or Path(filename).suffix.lower() != ".csv":
        return None
    root = (results_root() / str(job_id)).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        return None
    return path
