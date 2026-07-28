import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from core.agents.processor import prepare_job_execution
from core.processing.adapters import render_adapter_plan


class ProcessorAdapterTests(SimpleTestCase):
    def test_skyline_adapter_builds_skylinecmd_report_command(self):
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            plan = render_adapter_plan(
                adapter="skyline",
                parameters={
                    "document": "/shared/templates/project.sky",
                    "report": "skyline-report.csv",
                    "report_name": "Transition Results",
                },
                placeholders={
                    "job_id": "7",
                    "raw_file_path": "/data/raw/sample.raw",
                    "results_dir": str(results_dir),
                    "run_name": "Sample Run",
                },
                results_dir=results_dir,
            )

        self.assertEqual(plan.command[0], "SkylineCmd")
        self.assertIn("--in=/shared/templates/project.sky", plan.command)
        self.assertIn("--import-file=/data/raw/sample.raw", plan.command)
        self.assertTrue(any(item.startswith("--report-file=") for item in plan.command))
        self.assertEqual(plan.artifact_files[0]["metadata"]["software"], "skyline")

    def test_enterprise_adapter_writes_handoff_manifest(self):
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            plan = render_adapter_plan(
                adapter="spectronaut",
                parameters={
                    "command": ["Spectronaut.exe", "-i", "{raw_file_path}", "-o", "{results_dir}"],
                    "handoff_manifest": "spectronaut-handoff.json",
                },
                placeholders={
                    "job_id": "8",
                    "raw_file_path": "Z:/raw/sample.raw",
                    "results_dir": str(results_dir),
                    "run_name": "Sample Run",
                },
                results_dir=results_dir,
            )

        manifest_path = results_dir.resolve() / "spectronaut-handoff.json"
        self.assertIn(str(manifest_path), plan.files_to_write)
        self.assertEqual(plan.command, ["Spectronaut.exe", "-i", "Z:/raw/sample.raw", "-o", str(results_dir.resolve())])
        self.assertEqual(plan.artifact_files[-1]["artifact_type"], "enterprise_export")

    @override_settings(
        RAW_FILE_STORAGE_ROOT="/shared/raw",
        PROCESSOR_SHARED_STORAGE_ROOT="/shared",
    )
    def test_prepare_job_execution_writes_runtime_manifest(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_file = root / "sample.raw"
            raw_file.write_text("raw", encoding="utf-8")
            job_payload = {
                "id": 42,
                "run": {"name": "Sample Run"},
                "raw_file": {"storage_path": str(raw_file)},
                "pipeline": {
                    "parameters": {
                        "adapter": "diann",
                        "executable": "diann",
                        "report": "diann-report.tsv",
                        "software_version": "site-pinned",
                    }
                },
            }

            execution = prepare_job_execution(job_payload, results_root=root / "results")

            self.assertTrue(execution.runtime_manifest_path.exists())
            manifest = json.loads(execution.runtime_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["software"]["adapter"], "diann")
            self.assertEqual(manifest["software"]["declared_version"], "site-pinned")
            self.assertEqual(manifest["shared_storage"]["raw_file_storage_root"], "/shared/raw")
            self.assertEqual(manifest["shared_storage"]["processor_shared_storage_root"], "/shared")
            self.assertEqual(manifest["input_fingerprints"][0]["sha256"], "d7439bee24773bcbfa2d0a97947ee36227b10d1022b1a55847e928965bb6bfde")
