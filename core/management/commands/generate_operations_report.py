from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import ProcessingJob, ProcessingNode, RawFile, RawFileArchive, RawFileArchiveCopy
from core.storage_ops import capacity_report, configured_roots


class Command(BaseCommand):
    help = "Generate a text operations report for storage, archives, agents, and processing jobs."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="")
        parser.add_argument("--project-code", default="")
        parser.add_argument("--tail", type=int, default=20)

    def handle(self, *args, **options):
        lines = []
        self._write(lines, "MSConnect Operations Report")
        self._write(lines, "")
        self._storage(lines)
        self._agents(lines)
        self._raw_files(lines, project_code=options["project_code"], tail=max(1, int(options["tail"])))
        self._archives(lines, project_code=options["project_code"], tail=max(1, int(options["tail"])))
        self._jobs(lines, project_code=options["project_code"], tail=max(1, int(options["tail"])))

        output = "\n".join(lines) + "\n"
        if options["output"]:
            target = Path(options["output"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output, encoding="utf-8")
            self.stdout.write(str(target))
        else:
            self.stdout.write(output)

    def _storage(self, lines):
        self._write(lines, "== Storage Roots ==")
        roots = [
            ("incoming", Path(settings.INCOMING_RAW_ROOT)),
            ("raw", Path(settings.RAW_FILE_STORAGE_ROOT)),
            ("results", Path(settings.RESULTS_ROOT)),
            *[(f"archive:{index}", root) for index, root in enumerate(configured_roots(settings.MSCONNECT_ARCHIVE_ROOTS), 1)],
            *[(f"backup:{index}", root) for index, root in enumerate(configured_roots(settings.MSCONNECT_BACKUP_ROOTS), 1)],
        ]
        for label, root in roots:
            report = capacity_report(root)
            self._write(
                lines,
                f"{label:12} exists={report.exists} used={self._fmt(report.used_bytes)} "
                f"free={self._fmt(report.free_bytes)} total={self._fmt(report.total_bytes)} "
                f"used={report.used_percent:.2f}% path={report.root}",
            )
        self._write(lines, "")

    def _agents(self, lines):
        self._write(lines, "== Agent / Processor Nodes ==")
        for node in ProcessingNode.objects.order_by("-last_heartbeat_at", "name")[:50]:
            self._write(
                lines,
                f"{node.name:24} type={node.node_type:12} status={node.status:8} "
                f"last_heartbeat={node.last_heartbeat_at} image={node.container_image}",
            )
        self._write(lines, "")

    def _raw_files(self, lines, *, project_code, tail):
        self._write(lines, "== Recent Raw Files ==")
        queryset = RawFile.objects.select_related("run", "run__sample", "run__sample__experiment", "run__sample__experiment__project")
        if project_code:
            queryset = queryset.filter(run__sample__experiment__project__code=project_code)
        for raw_file in queryset.order_by("-id")[:tail]:
            project = raw_file.run.sample.experiment.project.code if raw_file.run_id else "unmatched"
            self._write(
                lines,
                f"{raw_file.id:5} project={project:16} file={raw_file.filename} "
                f"status={raw_file.status} role={raw_file.file_role} size={self._fmt(raw_file.size_bytes)}",
            )
        self._write(lines, "")

    def _archives(self, lines, *, project_code, tail):
        self._write(lines, "== Recent Archives ==")
        queryset = RawFileArchive.objects.select_related("raw_file", "raw_file__run", "raw_file__run__sample", "raw_file__run__sample__experiment", "raw_file__run__sample__experiment__project")
        if project_code:
            queryset = queryset.filter(raw_file__run__sample__experiment__project__code=project_code)
        for archive in queryset.order_by("-id")[:tail]:
            copies = RawFileArchiveCopy.objects.filter(archive=archive).count()
            self._write(
                lines,
                f"{archive.id:5} raw={archive.raw_file.filename} status={archive.status} "
                f"copies={copies} size={self._fmt(archive.size_bytes or 0)} path={archive.archive_path}",
            )
        self._write(lines, "")

    def _jobs(self, lines, *, project_code, tail):
        self._write(lines, "== Recent Processing Jobs ==")
        queryset = ProcessingJob.objects.select_related("run", "run__sample", "run__sample__experiment", "run__sample__experiment__project", "raw_file", "pipeline", "node")
        if project_code:
            queryset = queryset.filter(run__sample__experiment__project__code=project_code)
        for job in queryset.order_by("-id")[:tail]:
            self._write(
                lines,
                f"{job.id:5} project={job.run.sample.experiment.project.code:16} status={job.status:8} "
                f"pipeline={job.pipeline.name} node={job.node.name if job.node_id else ''} "
                f"raw={job.raw_file.filename} log={job.log_path}",
            )
        self._write(lines, "")

    def _write(self, lines, value):
        lines.append(value)

    def _fmt(self, value):
        value = float(value or 0)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if value < 1024 or unit == "PB":
                return f"{value:.1f}{unit}"
            value /= 1024
        return f"{value:.1f}PB"
