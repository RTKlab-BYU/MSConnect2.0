import json
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.agents.processor import prepare_job_execution


class Command(BaseCommand):
    help = "Smoke-test MSConnect processor adapters against one input file using mock engine executables."

    def add_arguments(self, parser):
        parser.add_argument("--raw-file", help="Input file to feed to every adapter. Defaults to a generated tiny .raw file.")
        parser.add_argument("--results-root", help="Output root. Defaults to RESULTS_ROOT/processor-smoke.")
        parser.add_argument("--keep", action="store_true", help="Keep existing smoke outputs instead of overwriting them.")

    def handle(self, *args, **options):
        results_root = Path(options["results_root"] or Path(settings.RESULTS_ROOT) / "processor-smoke").resolve()
        if results_root.exists() and not options["keep"]:
            self._clear_previous(results_root)
        results_root.mkdir(parents=True, exist_ok=True)

        raw_file = Path(options["raw_file"]).resolve() if options.get("raw_file") else results_root / "input" / "smoke.raw"
        raw_file.parent.mkdir(parents=True, exist_ok=True)
        if not raw_file.exists():
            raw_file.write_text("MSConnect processor smoke input\n", encoding="utf-8")

        bin_dir = results_root / "mock-bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        mock_engine = bin_dir / "mock_engine.py"
        mock_engine.write_text(MOCK_ENGINE, encoding="utf-8")
        mock_engine.chmod(0o755)

        cases = self._cases(raw_file=raw_file, mock_engine=mock_engine, results_root=results_root)
        rows = []
        for index, case in enumerate(cases, start=1):
            job_payload = {
                "id": 9000 + index,
                "run": {"name": f"Smoke {case['name']}"},
                "raw_file": {"storage_path": str(raw_file)},
                "pipeline": {
                    "name": case["name"],
                    "version": "smoke",
                    "parameters": case["parameters"],
                },
            }
            execution = prepare_job_execution(job_payload, results_root=results_root)
            completed = subprocess.run(
                execution.command,
                cwd=execution.working_dir,
                env=execution.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            execution.log_path.write_text(completed.stdout, encoding="utf-8")
            ok = completed.returncode == 0
            missing = []
            for artifact in [*execution.derivative_files, *execution.artifact_files]:
                path = Path(str(artifact.get("path") or ""))
                if not path.exists():
                    ok = False
                    missing.append(str(path))
            if not execution.runtime_manifest_path.exists():
                ok = False
                missing.append(str(execution.runtime_manifest_path))
            rows.append(
                {
                    "adapter": case["name"],
                    "ok": ok,
                    "returncode": completed.returncode,
                    "results_dir": str(execution.results_dir),
                    "runtime_manifest": str(execution.runtime_manifest_path),
                    "missing": missing,
                }
            )

        report_path = results_root / "processor-smoke-report.json"
        report_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for row in rows:
            label = self.style.SUCCESS("OK") if row["ok"] else self.style.ERROR("FAIL")
            self.stdout.write(f"{label} {row['adapter']}: {row['results_dir']}")
            if row["missing"]:
                self.stdout.write(f"  missing: {', '.join(row['missing'])}")
        self.stdout.write(f"Report: {report_path}")
        if not all(row["ok"] for row in rows):
            raise CommandError("One or more processor smoke tests failed.")

    def _cases(self, *, raw_file: Path, mock_engine: Path, results_root: Path):
        py = os.environ.get("PYTHON") or "python3"
        prefix = [py, str(mock_engine)]
        return [
            {
                "name": "diann-speclib-build",
                "parameters": {
                    "adapter": "diann",
                    "executable": [*prefix, "diann"],
                    "software_version": "mock-diann 1.0",
                    "version_command": [*prefix, "version", "DIA-NN mock 1.0"],
                    "report": "diann-build-report.tsv",
                    "generate_speclib": True,
                    "fasta_search": True,
                    "fasta": "/data/shared/reference/human.fasta",
                    "out_library": "diann-build.speclib",
                },
            },
            {
                "name": "diann-speclib-reuse",
                "parameters": {
                    "adapter": "diann",
                    "executable": [*prefix, "diann"],
                    "software_version": "mock-diann 1.0",
                    "version_command": [*prefix, "version", "DIA-NN mock 1.0"],
                    "report": "diann-reuse-report.tsv",
                    "library": "/data/shared/reference/human.speclib",
                    "fasta_search": False,
                },
            },
            {
                "name": "fragpipe",
                "parameters": {
                    "adapter": "fragpipe",
                    "executable": [*prefix, "fragpipe"],
                    "software_version": "mock-fragpipe 1.0",
                    "version_command": [*prefix, "version", "FragPipe mock 1.0"],
                    "workflow": str(results_root / "mock.workflow"),
                    "artifact_files": [
                        {
                            "artifact_type": "fragpipe_output",
                            "path": "{results_dir}/fragpipe-output.tsv",
                            "format": "tsv",
                        }
                    ],
                },
            },
            {
                "name": "skyline",
                "parameters": {
                    "adapter": "skyline",
                    "executable": [*prefix, "skyline"],
                    "software_version": "mock-skyline 1.0",
                    "version_command": [*prefix, "version", "Skyline mock 1.0"],
                    "document": str(results_root / "mock.sky"),
                    "report": "skyline-report.csv",
                    "report_name": "Transition Results",
                },
            },
            {
                "name": "spectronaut",
                "parameters": {
                    "adapter": "spectronaut",
                    "executable": [*prefix, "spectronaut"],
                    "software_version": "mock-spectronaut 1.0",
                    "version_command": [*prefix, "version", "Spectronaut mock 1.0"],
                    "command": [*prefix, "enterprise", "{raw_file_path}", "{results_dir}/spectronaut-output.tsv"],
                    "artifact_files": [
                        {
                            "artifact_type": "enterprise_export",
                            "path": "{results_dir}/spectronaut-output.tsv",
                            "format": "tsv",
                        }
                    ],
                },
            },
            {
                "name": "proteome-discoverer",
                "parameters": {
                    "adapter": "proteome-discoverer",
                    "executable": [*prefix, "proteome-discoverer"],
                    "software_version": "mock-proteome-discoverer 1.0",
                    "version_command": [*prefix, "version", "Proteome Discoverer mock 1.0"],
                    "command": [*prefix, "enterprise", "{raw_file_path}", "{results_dir}/pd-output.tsv"],
                    "artifact_files": [
                        {
                            "artifact_type": "enterprise_export",
                            "path": "{results_dir}/pd-output.tsv",
                            "format": "tsv",
                        }
                    ],
                },
            },
        ]

    def _clear_previous(self, path: Path):
        for child in path.iterdir():
            if child.is_dir():
                self._clear_previous(child)
                child.rmdir()
            else:
                child.unlink()


MOCK_ENGINE = """#!/usr/bin/env python3
import sys
from pathlib import Path


def write(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


mode = sys.argv[1]
args = sys.argv[2:]
if mode == "version":
    print(" ".join(args))
elif mode == "diann":
    out = args[args.index("--out") + 1]
    write(out, "protein\\tq_value\\nP001\\t0.001\\n")
    if "--gen-spec-lib" in args and "--out-lib" in args:
        out_lib = args[args.index("--out-lib") + 1]
        write(out_lib, "library\\nmock\\n")
        predicted = str(Path(out_lib).with_suffix(".predicted.speclib"))
        write(predicted, "library\\nmock\\n")
elif mode == "fragpipe":
    workdir = args[args.index("--workdir") + 1]
    write(Path(workdir) / "fragpipe-output.tsv", "protein\\tscore\\nP001\\t100\\n")
elif mode == "skyline":
    report = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--report-file="))
    write(report, "transition,intensity\\ny7,12345\\n")
elif mode == "enterprise":
    write(args[1], "feature\\tvalue\\nmock\\t1\\n")
else:
    raise SystemExit(f"unknown mock mode: {mode}")
"""
