import json
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from core.agents.processor import prepare_job_execution
from core.processing.adapters import render_adapter_plan
from core.processing.postprocess import skyline_prtc_postprocess


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
                    "report_format": "csv",
                    "report_invariant": True,
                    "report_conflict_resolution": "overwrite",
                    "save": True,
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
        self.assertIn("--report-format=csv", plan.command)
        self.assertIn("--report-invariant", plan.command)
        self.assertIn("--report-conflict-resolution=overwrite", plan.command)
        self.assertIn("--save", plan.command)
        self.assertEqual(plan.artifact_files[0]["metadata"]["software"], "skyline")

    def test_skyline_prtc_postprocess_writes_normalized_peptides_and_stats(self):
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            report = results_dir / "skyline-prtc-report.csv"
            report.write_text(
                "\n".join(
                    [
                        "Peptide,Precursor Charge,Total Area,Retention Time,Precursor Mz,Library Dot Product",
                        "PEPTIDEA,2,1000,45.5,500.2,0.98",
                        "PEPTIDEB,3,0,52.0,600.3,0.70",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            stats = skyline_prtc_postprocess(
                parameters={
                    "report": "skyline-prtc-report.csv",
                    "result_files": {
                        "peptide_table": "skyline-prtc-peptides.csv",
                        "stats_json": "skyline-prtc-stats.json",
                    },
                    "expected_peptides": [
                        {"sequence": "PEPTIDEA", "charge": 2, "expected_rt_seconds": 45.0},
                        {"sequence": "PEPTIDEB", "charge": 3, "min_area": 10},
                        {"sequence": "PEPTIDEC", "charge": 2},
                    ],
                },
                results_dir=results_dir,
            )

            peptide_table = results_dir / "skyline-prtc-peptides.csv"
            stats_json = results_dir / "skyline-prtc-stats.json"
            self.assertTrue(peptide_table.exists())
            self.assertTrue(stats_json.exists())
            self.assertIn("PEPTIDEA", peptide_table.read_text(encoding="utf-8"))
            payload = json.loads(stats_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["expected_peptide_count"], 3)
            self.assertEqual(payload["detected_peptide_count"], 2)
            self.assertEqual(payload["missing_peptides"], ["PEPTIDEC"])
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(stats["skyline_prtc"]["status"], "fail")

    def test_skyline_adapter_preserves_windows_paths(self):
        with TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            raw_path = r"Z:\msconnect\raw\Sample01.raw"
            document_path = r"Z:\msconnect\shared\skyline\project.sky"
            plan = render_adapter_plan(
                adapter="skyline",
                parameters={
                    "document": document_path,
                    "report": "skyline-report.csv",
                },
                placeholders={
                    "job_id": "9",
                    "raw_file_path": raw_path,
                    "results_dir": str(results_dir),
                    "run_name": "Sample Run",
                },
                results_dir=results_dir,
            )

        self.assertIn(f"--in={document_path}", plan.command)
        self.assertIn(f"--import-file={raw_path}", plan.command)

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
            self.assertEqual(
                manifest["input_fingerprints"][0]["sha256"],
                "d7439bee24773bcbfa2d0a97947ee36227b10d1022b1a55847e928965bb6bfde",
            )

    def test_prepare_job_execution_keeps_command_pipeline_with_engine_label(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_file = root / "sample.raw"
            raw_file.write_text("raw", encoding="utf-8")
            job_payload = {
                "id": 55,
                "run": {"name": "Sample Run"},
                "raw_file": {"storage_path": str(raw_file)},
                "pipeline": {
                    "parameters": {
                        "engine": "diann",
                        "command": [sys.executable, "-c", "print('ok')"],
                    }
                },
            }

            execution = prepare_job_execution(job_payload, results_root=root / "results")

            self.assertEqual(execution.command[:3], [sys.executable, "-c", "print('ok')"])

    def test_processor_registry_cli_resolves_diann_references_for_runtime(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shared_root = root / "shared"
            raw_file = root / "raw" / "sample.raw"
            fasta = root / "refs" / "human.fasta"
            library = root / "refs" / "human.speclib"
            settings_file = root / "diann-settings.json"
            raw_file.parent.mkdir(parents=True)
            fasta.parent.mkdir(parents=True)
            raw_file.write_text("raw", encoding="utf-8")
            fasta.write_text(">P001\nPEPTIDE\n", encoding="utf-8")
            library.write_text("library", encoding="utf-8")
            settings_file.write_text(
                json.dumps(
                    {
                        "executable": "diann",
                        "version_command": [sys.executable, "--version"],
                        "fasta_ref": "human",
                        "library_ref": "human",
                        "options": ["--threads", "4"],
                    }
                ),
                encoding="utf-8",
            )

            with override_settings(
                PROCESSOR_SHARED_STORAGE_ROOT=str(shared_root),
                RAW_FILE_STORAGE_ROOT=str(root / "raw"),
            ):
                call_command("processor_registry", "init", stdout=StringIO())
                call_command(
                    "processor_registry",
                    "add-reference",
                    "--kind",
                    "fasta",
                    "--key",
                    "human",
                    "--path",
                    str(fasta),
                    stdout=StringIO(),
                )
                call_command(
                    "processor_registry",
                    "add-reference",
                    "--kind",
                    "speclib",
                    "--key",
                    "human",
                    "--path",
                    str(library),
                    stdout=StringIO(),
                )
                call_command(
                    "processor_registry",
                    "add-settings",
                    "--engine",
                    "diann",
                    "--key",
                    "standard",
                    "--json-file",
                    str(settings_file),
                    stdout=StringIO(),
                )
                execution = prepare_job_execution(
                    {
                        "id": 77,
                        "run": {"name": "Sample Run"},
                        "raw_file": {"storage_path": str(raw_file)},
                        "pipeline": {
                            "parameters": {
                                "adapter": "diann",
                                "required_engine": "diann",
                                "settings_ref": "standard",
                                "report": "diann-report.tsv",
                            }
                        },
                    },
                    results_root=root / "results",
                )

            self.assertIn("--fasta", execution.command)
            self.assertIn(str(fasta), execution.command)
            self.assertIn("--lib", execution.command)
            self.assertIn(str(library), execution.command)
            manifest = json.loads(execution.runtime_manifest_path.read_text(encoding="utf-8"))
            fingerprint_paths = {item["path"] for item in manifest["input_fingerprints"]}
            self.assertIn(str(raw_file), fingerprint_paths)
            self.assertIn(str(fasta), fingerprint_paths)
            self.assertIn(str(library), fingerprint_paths)

    def test_processor_registry_cli_registers_image_and_external_engine_profiles(self):
        with TemporaryDirectory() as temp_dir:
            shared_root = Path(temp_dir) / "shared"
            with override_settings(PROCESSOR_SHARED_STORAGE_ROOT=str(shared_root)):
                call_command("processor_registry", "init", stdout=StringIO())
                call_command(
                    "processor_registry",
                    "add-engine",
                    "--engine",
                    "diann",
                    "--version",
                    "2.1.0",
                    "--image",
                    "registry.example.org/msconnect/processor-diann:2.1.0",
                    "--executable",
                    "diann",
                    "--version-command",
                    sys.executable,
                    stdout=StringIO(),
                )
                call_command(
                    "processor_registry",
                    "add-engine",
                    "--engine",
                    "proteome-discoverer",
                    "--version",
                    "3.1",
                    "--install-type",
                    "external",
                    "--executable",
                    "ProteomeDiscoverer.exe",
                    stdout=StringIO(),
                )
                registry_output = StringIO()
                call_command("processor_registry", "list", stdout=registry_output)

            registry = json.loads(registry_output.getvalue())
            self.assertEqual(
                registry["engines"]["diann"]["2.1.0"]["image"],
                "registry.example.org/msconnect/processor-diann:2.1.0",
            )
            self.assertEqual(registry["engines"]["proteome-discoverer"]["3.1"]["install_type"], "external")
