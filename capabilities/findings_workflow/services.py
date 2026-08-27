import csv
import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import ProcessingJobArtifact, Project, RawFileDerivative

from .models import FindingsWorkspace, FindingsWorkspaceStatus

DEFAULT_ROOT = "MSCONNECT_FINDINGS_WORKSPACE_ROOT"


@dataclass(frozen=True)
class WorkspaceSummary:
    workspace: FindingsWorkspace
    created_paths: list[str]
    kept_paths: list[str]


def default_workspace_root() -> Path:
    configured = getattr(settings, DEFAULT_ROOT, "")
    if configured:
        return Path(configured).expanduser()
    return Path(settings.BASE_DIR) / "findings_workspaces"


def prepare_project_workspace(
    project: Project,
    *,
    root: Path | None = None,
    created_by=None,
    mode: str = "personal",
    data_strategy: str = "manifest",
) -> WorkspaceSummary:
    root = Path(root or default_workspace_root()).expanduser()
    workspace_path = root / safe_slug(project.lab.slug or f"lab-{project.lab_id}") / safe_slug(project.code)
    created_paths: list[str] = []
    kept_paths: list[str] = []

    for relative in ("data", "state", "findings", "scripts/scratch", "scripts/promoted", "results", "figures", "research", "reports"):
        ensure_dir(workspace_path / relative, created_paths, kept_paths)

    write_text_if_changed(workspace_path / "README.md", walkthrough_markdown(project, workspace_path), created_paths, kept_paths)
    write_text_if_changed(workspace_path / "data" / "README.md", data_readme(project), created_paths, kept_paths)

    project_payload = project_payload_for(project)
    write_json(workspace_path / "data" / "msconnect_project.json", project_payload, created_paths, kept_paths)
    write_csv(workspace_path / "data" / "samples.csv", sample_rows(project), created_paths, kept_paths)
    write_csv(workspace_path / "data" / "runs.csv", run_rows(project), created_paths, kept_paths)
    write_csv(workspace_path / "data" / "raw_files.csv", raw_file_rows(project), created_paths, kept_paths)
    write_csv(workspace_path / "data" / "derivatives.csv", derivative_rows(project), created_paths, kept_paths)
    write_csv(workspace_path / "data" / "artifacts.csv", artifact_rows(project), created_paths, kept_paths)
    write_json(workspace_path / "data" / "path_manifest.json", path_manifest(project), created_paths, kept_paths)

    if data_strategy == "symlink":
        link_raw_files(project, workspace_path / "data" / "raw-files", created_paths, kept_paths)

    with transaction.atomic():
        workspace, _ = FindingsWorkspace.objects.update_or_create(
            project=project,
            defaults={
                "created_by": created_by,
                "mode": mode,
                "data_strategy": data_strategy,
                "root_path": str(root),
                "workspace_path": str(workspace_path),
                "status": FindingsWorkspaceStatus.PREPARED,
                "error_message": "",
                "metadata": {
                    "walkthrough": str(workspace_path / "README.md"),
                    "exports": {
                        "project": "data/msconnect_project.json",
                        "samples": "data/samples.csv",
                        "runs": "data/runs.csv",
                        "raw_files": "data/raw_files.csv",
                        "derivatives": "data/derivatives.csv",
                        "artifacts": "data/artifacts.csv",
                        "paths": "data/path_manifest.json",
                    },
                },
            },
        )

    return WorkspaceSummary(workspace=workspace, created_paths=created_paths, kept_paths=kept_paths)


def index_workspace_outputs(workspace: FindingsWorkspace) -> FindingsWorkspace:
    base = Path(workspace.workspace_path)
    findings_dir = base / "findings"
    reports_dir = base / "reports"
    finding_files = sorted(path for path in findings_dir.glob("*.md") if path.name != "manifest.md") if findings_dir.exists() else []
    report_files = sorted(reports_dir.glob("*.md")) if reports_dir.exists() else []
    latest_report = max(report_files, key=lambda path: path.stat().st_mtime) if report_files else None

    workspace.findings_count = len(finding_files)
    workspace.reports_count = len(report_files)
    workspace.latest_report_path = str(latest_report) if latest_report else ""
    workspace.last_indexed_at = timezone.now()
    workspace.status = FindingsWorkspaceStatus.INDEXED if report_files or finding_files else FindingsWorkspaceStatus.PREPARED
    workspace.error_message = ""
    workspace.save(
        update_fields=[
            "findings_count",
            "reports_count",
            "latest_report_path",
            "last_indexed_at",
            "status",
            "error_message",
            "updated_at",
        ]
    )
    return workspace


def project_payload_for(project: Project) -> dict:
    return {
        "id": project.id,
        "code": project.code,
        "title": project.title,
        "description": project.description,
        "status": project.status,
        "lab": {"id": project.lab_id, "name": project.lab.name, "slug": project.lab.slug},
        "pi_id": project.pi_id,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def sample_rows(project: Project) -> list[dict]:
    rows = []
    for sample in project_sample_queryset(project):
        rows.append(
            {
                "sample_id": sample.id,
                "experiment_id": sample.experiment_id,
                "experiment": sample.experiment.name,
                "name": sample.name,
                "external_id": sample.external_id,
                "species": sample.species,
                "matrix": sample.matrix,
                "metadata_json": json.dumps(sample.metadata, sort_keys=True),
            }
        )
    return rows


def run_rows(project: Project) -> list[dict]:
    rows = []
    for run in project_run_queryset(project):
        rows.append(
            {
                "run_id": run.id,
                "sample_id": run.sample_id,
                "sample": run.sample.name,
                "experiment": run.sample.experiment.name,
                "run_name": run.run_name,
                "status": run.status,
                "file_role": run.file_role,
                "expected_filename": run.expected_filename,
                "worklist_position": run.worklist_position or "",
                "hye_pair_label": run.hye_pair_label,
                "metadata_json": json.dumps(run.metadata, sort_keys=True),
            }
        )
    return rows


def raw_file_rows(project: Project) -> list[dict]:
    rows = []
    for raw_file in project_raw_file_queryset(project):
        rows.append(
            {
                "raw_file_id": raw_file.id,
                "run_id": raw_file.run_id or "",
                "filename": raw_file.filename,
                "status": raw_file.status,
                "file_role": raw_file.file_role,
                "size_bytes": raw_file.size_bytes,
                "checksum_sha256": raw_file.checksum_sha256,
                "source_path": raw_file.source_path,
                "storage_path": raw_file.storage_path,
                "imported_at": raw_file.imported_at.isoformat() if raw_file.imported_at else "",
                "metadata_json": json.dumps(raw_file.metadata, sort_keys=True),
            }
        )
    return rows


def derivative_rows(project: Project) -> list[dict]:
    rows = []
    queryset = RawFileDerivative.objects.filter(raw_file__run__sample__experiment__project=project).select_related("raw_file")
    for derivative in queryset.order_by("raw_file__filename", "derivative_type"):
        rows.append(
            {
                "derivative_id": derivative.id,
                "raw_file_id": derivative.raw_file_id,
                "raw_file": derivative.raw_file.filename,
                "derivative_type": derivative.derivative_type,
                "status": derivative.status,
                "format": derivative.format,
                "size_bytes": derivative.size_bytes or "",
                "checksum_sha256": derivative.checksum_sha256,
                "path": derivative.path,
            }
        )
    return rows


def artifact_rows(project: Project) -> list[dict]:
    rows = []
    queryset = ProcessingJobArtifact.objects.filter(job__run__sample__experiment__project=project).select_related("job", "job__raw_file", "job__pipeline")
    for artifact in queryset.order_by("job_id", "artifact_type"):
        rows.append(
            {
                "artifact_id": artifact.id,
                "job_id": artifact.job_id,
                "artifact_type": artifact.artifact_type,
                "format": artifact.format,
                "size_bytes": artifact.size_bytes or "",
                "checksum_sha256": artifact.checksum_sha256,
                "retained": artifact.retained,
                "pipeline": artifact.job.pipeline.name,
                "raw_file": artifact.job.raw_file.filename,
                "path": artifact.path,
            }
        )
    return rows


def path_manifest(project: Project) -> dict:
    return {
        "project": project_payload_for(project),
        "raw_files": [
            {
                "id": raw_file.id,
                "filename": raw_file.filename,
                "storage_path": raw_file.storage_path,
                "checksum_sha256": raw_file.checksum_sha256,
                "read_only": True,
            }
            for raw_file in project_raw_file_queryset(project)
        ],
        "derivatives": [
            {"id": derivative.id, "type": derivative.derivative_type, "path": derivative.path, "read_only": True}
            for derivative in RawFileDerivative.objects.filter(raw_file__run__sample__experiment__project=project).order_by("id")
        ],
        "artifacts": [
            {"id": artifact.id, "type": artifact.artifact_type, "path": artifact.path, "read_only": True}
            for artifact in ProcessingJobArtifact.objects.filter(job__run__sample__experiment__project=project).order_by("id")
        ],
    }


def walkthrough_markdown(project: Project, workspace_path: Path) -> str:
    return f"""# Findings Workflow for {project.code}

This workspace was prepared by MSConnect for Claude Code plus the Findings Workflow plugin.

## 1. Install the Claude plugin

Run these in Claude Code, not in a shell:

```text
/plugin marketplace add mriffle/findings-ai-collab-workflow
/plugin install findings-workflow@findings-workflow
```

Restart Claude Code after installing. Use user scope for personal use across studies, or local scope to pin the plugin to this workspace.

## 2. Open this workspace

```bash
cd {workspace_path}
```

Raw data stays read-only. MSConnect exported project metadata and file manifests under `data/`.

## 3. Initialize the study workflow

Run these in Claude Code from this directory:

```text
/findings-workflow:init
/findings-workflow:setup-env
/findings-workflow:stage0-science
```

Then follow the staged workflow:

```text
/findings-workflow:stage1-metadata
/findings-workflow:stage2-data
/findings-workflow:stage3-loaders
/findings-workflow:stage4-explore
/findings-workflow:stage5-validate <finding-id>
/findings-workflow:stage6-report research
```

Use `/findings-workflow:status` whenever you need to reorient.

## 4. Bring outputs back into MSConnect

After Claude writes findings or reports, use the MSConnect project page action `Index outputs`.
MSConnect counts files in `findings/` and `reports/` and links the latest report path.
"""


def data_readme(project: Project) -> str:
    return f"""# MSConnect data export for {project.code}

This directory contains metadata exports and path manifests for analysis. Treat referenced raw files,
derivatives, and processing artifacts as read-only network storage inputs.

- `msconnect_project.json`: project identity and lab context.
- `samples.csv`: samples and sample metadata JSON.
- `runs.csv`: planned/acquired run metadata.
- `raw_files.csv`: imported raw files and storage paths.
- `derivatives.csv`: derived files such as mzML and spectrum indexes.
- `artifacts.csv`: processing result artifacts.
- `path_manifest.json`: machine-readable read-only input manifest.
"""


def project_sample_queryset(project: Project):
    from core.models import Sample

    return Sample.objects.filter(experiment__project=project).select_related("experiment").order_by("experiment__name", "name")


def project_run_queryset(project: Project):
    from core.models import Run

    return Run.objects.filter(sample__experiment__project=project).select_related("sample", "sample__experiment").order_by("worklist_position", "run_name")


def project_raw_file_queryset(project: Project):
    from core.models import RawFile

    return RawFile.objects.filter(run__sample__experiment__project=project).select_related("run", "run__sample").order_by("filename")


def write_csv(path: Path, rows: list[dict], created_paths: list[str], kept_paths: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row.keys()})
    if not columns:
        columns = ["empty"]
    next_content = csv_text(columns, rows)
    write_text_if_changed(path, next_content, created_paths, kept_paths)


def csv_text(columns: list[str], rows: list[dict]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def write_json(path: Path, payload: dict, created_paths: list[str], kept_paths: list[str]) -> None:
    write_text_if_changed(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", created_paths, kept_paths)


def write_text_if_changed(path: Path, content: str, created_paths: list[str], kept_paths: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        kept_paths.append(str(path))
        return
    if path.exists():
        kept_paths.append(str(path))
    else:
        created_paths.append(str(path))
    path.write_text(content, encoding="utf-8")


def ensure_dir(path: Path, created_paths: list[str], kept_paths: list[str]) -> None:
    if path.exists():
        kept_paths.append(str(path))
        return
    path.mkdir(parents=True, exist_ok=True)
    created_paths.append(str(path))


def link_raw_files(project: Project, target_dir: Path, created_paths: list[str], kept_paths: list[str]) -> None:
    ensure_dir(target_dir, created_paths, kept_paths)
    for raw_file in project_raw_file_queryset(project):
        source = Path(raw_file.storage_path)
        target = target_dir / raw_file.filename
        if target.exists() or target.is_symlink():
            kept_paths.append(str(target))
            continue
        target.symlink_to(source)
        created_paths.append(str(target))


def safe_slug(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in ("-", "_") else "-" for character in value.strip())
    return cleaned.strip("-") or "workspace"
