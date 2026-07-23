import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import (
    AcquisitionWorklist,
    DirectUploadSession,
    Experiment,
    Facility,
    InstrumentConfiguration,
    Lab,
    LabMembership,
    PeptideQuant,
    ProcessingJob,
    ProcessingNode,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    ProteinQuant,
    RawFile,
    RawFileDerivative,
    Run,
    Sample,
    University,
    UserProfile,
    UserRole,
)

User = get_user_model()


class ApiPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.university = University.objects.create(name="BYU")
        self.facility = Facility.objects.create(university=self.university, name="Proteomics Core", slug="proteomics")
        self.lab_a = Lab.objects.create(facility=self.facility, name="Lab A", slug="lab-a")
        self.lab_b = Lab.objects.create(facility=self.facility, name="Lab B", slug="lab-b")

        self.pi_user = self._create_user("pi-user", UserRole.PI)
        self.researcher = self._create_user("researcher", UserRole.RESEARCHER)
        self.collaborator = self._create_user("collaborator", UserRole.COLLABORATOR)
        self.admin = self._create_user("admin-user", UserRole.ADMIN)
        self.external = self._create_user("external", UserRole.RESEARCHER)

        LabMembership.objects.create(user=self.pi_user, lab=self.lab_a, role=UserRole.PI)
        LabMembership.objects.create(user=self.researcher, lab=self.lab_a, role=UserRole.RESEARCHER)
        LabMembership.objects.create(user=self.collaborator, lab=self.lab_a, role=UserRole.COLLABORATOR)
        LabMembership.objects.create(user=self.external, lab=self.lab_b, role=UserRole.RESEARCHER)

        self.project_a = Project.objects.create(lab=self.lab_a, title="Project A", code="P-A", pi=self.pi_user)
        self.project_b = Project.objects.create(lab=self.lab_b, title="Project B", code="P-B", pi=self.external)

    def _create_user(self, username, role):
        user = User.objects.create_user(username=username, password="password123")
        UserProfile.objects.create(user=user, global_role=role)
        return user

    def test_researcher_only_sees_projects_for_member_labs(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.data}, {self.project_a.id})

    def test_collaborator_can_read_but_cannot_write(self):
        self.client.force_authenticate(user=self.collaborator)

        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.data}, {self.project_a.id})

        create_response = self.client.post(
            "/api/projects/",
            data={
                "lab": self.lab_a.id,
                "title": "Should Fail",
                "code": "P-C",
                "pi": self.pi_user.id,
                "status": "active",
                "description": "",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 403)

    def test_admin_sees_all_projects(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.data}, {self.project_a.id, self.project_b.id})

    def test_project_pagination_search_and_summary_are_additive(self):
        self.client.force_authenticate(user=self.admin)

        unpaginated_response = self.client.get("/api/projects/")
        self.assertEqual(unpaginated_response.status_code, 200)
        self.assertIsInstance(unpaginated_response.data, list)

        paginated_response = self.client.get("/api/projects/?page=1&page_size=1&search=P-A")
        self.assertEqual(paginated_response.status_code, 200)
        self.assertIn("results", paginated_response.data)
        self.assertEqual(paginated_response.data["count"], 1)
        self.assertEqual(paginated_response.data["results"][0]["id"], self.project_a.id)

        summary_response = self.client.get(f"/api/projects/{self.project_a.id}/summary/")
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data["project_id"], self.project_a.id)
        self.assertEqual(summary_response.data["raw_file_count"], 0)
        self.assertEqual(summary_response.data["processing_job_count"], 0)

    def test_pre_acquisition_setup_creates_expected_worklist_and_processing_plan(self):
        self.client.force_authenticate(user=self.researcher)

        response = self.client.post(
            "/api/projects/pre-acquisition-setup/",
            data={
                "title": "Smoke Test DIA Cohort",
                "code": "SMOKE-DIA",
                "sample_count": 4,
                "healthy_count": 2,
                "diseased_count": 2,
                "hye_interval": 2,
                "fasta_path": "/data/reference/hye.fasta",
                "speclib_path": "/data/reference/hye.speclib",
                "diann_version": "1.9",
                "diann_settings": {"q_value": 0.01, "threads": 8},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["samples_created"], 6)
        self.assertEqual(response.data["runs_created"], 8)
        self.assertEqual(response.data["worklist_entries_created"], 8)
        self.assertEqual(len(response.data["expected_filenames"]), 8)
        self.assertTrue(response.data["expected_filenames"][0].startswith("SMOKE_DIA_001_"))

        project = Project.objects.get(code="SMOKE-DIA")
        worklist = AcquisitionWorklist.objects.get(experiment__project=project)
        self.assertEqual(worklist.status, "ready")
        self.assertEqual(worklist.entries.count(), 8)
        self.assertEqual(worklist.entries.filter(file_role="qc", hye_pair_label="HYE-01").count(), 2)

        pipeline = ProcessingPipeline.objects.get(name="DIA-NN", version="1.9")
        self.assertEqual(pipeline.parameters["fasta_path"], "/data/reference/hye.fasta")
        self.assertEqual(pipeline.parameters["speclib_path"], "/data/reference/hye.speclib")
        self.assertTrue(pipeline.parameters["project_level_rollup"]["enabled"])

    def test_pre_acquisition_setup_accepts_sample_rows_plate_and_reference_presets(self):
        self.client.force_authenticate(user=self.researcher)
        configuration = InstrumentConfiguration.objects.create(
            facility=self.facility,
            name="Exploris 480 DIA",
            method_name="60SPD DIA",
            column_description="Aurora 25cm",
        )

        response = self.client.post(
            "/api/projects/pre-acquisition-setup/",
            data={
                "title": "Wizard Smoke Cohort",
                "code": "WIZ-DIA",
                "sample_rows": [
                    {"sample_id": "H-001", "condition": "healthy", "well": "A01", "subject_id": "S-001"},
                    {"sample_id": "D-001", "condition": "diseased", "well": "A02", "subject_id": "S-002"},
                    {"sample_id": "H-002", "condition": "healthy", "well": "A03", "subject_id": "S-003"},
                    {"sample_id": "D-002", "condition": "diseased", "well": "A04", "subject_id": "S-004"},
                ],
                "plate_type": "96",
                "hye_interval": 2,
                "instrument_configuration": configuration.id,
                "organisms": ["human", "yeast", "ecoli"],
                "processing_preset": "Standard DIA-NN plasma",
                "diann_version": "1.9",
                "diann_settings": {"q_value": 0.01, "threads": 8},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["samples_created"], 6)
        self.assertEqual(response.data["runs_created"], 8)
        self.assertEqual(response.data["worklist_entries_created"], 8)

        worklist = AcquisitionWorklist.objects.get(experiment__project__code="WIZ-DIA")
        self.assertEqual(worklist.metadata["plate_type"], "96")
        self.assertEqual(worklist.metadata["export_targets"], ["thermo_ms_sequence", "lc_injection_sequence"])
        first_entry = worklist.entries.order_by("position").first()
        self.assertEqual(first_entry.metadata["well"], "A01")
        self.assertEqual(first_entry.metadata["condition"], "healthy")
        self.assertEqual(first_entry.run.configuration_id, configuration.id)

        pipeline = ProcessingPipeline.objects.get(name="DIA-NN", version="1.9")
        self.assertEqual(pipeline.parameters["reference_assets"]["organisms"], ["human", "yeast", "ecoli"])
        self.assertEqual(pipeline.parameters["reference_assets"]["refresh_policy"], "quarterly")
        self.assertEqual(pipeline.parameters["processing_preset"], "Standard DIA-NN plasma")

    def test_direct_upload_session_issues_signed_urls_and_records_completion(self):
        self.client.force_authenticate(user=self.researcher)

        create_response = self.client.post(
            "/api/direct-uploads/",
            data={
                "project": self.project_a.id,
                "filename": "Sample_A.raw",
                "size_bytes": 10_000_000,
                "content_type": "application/octet-stream",
                "chunk_size_bytes": 5_000_000,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["chunk_count"], 2)
        self.assertEqual(len(create_response.data["upload_urls"]), 2)
        self.assertEqual(create_response.data["upload_urls"][0]["method"], "PUT")

        upload = DirectUploadSession.objects.get(id=create_response.data["id"])
        checksum = "a" * 64
        complete_response = self.client.post(
            f"/api/direct-uploads/{upload.id}/complete/",
            data={"checksum_sha256": checksum},
            format="json",
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.data["status"], "complete")
        self.assertTrue(RawFile.objects.filter(checksum_sha256=checksum, filename="Sample_A.raw").exists())

    def test_direct_upload_session_respects_project_scope(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.post(
            "/api/direct-uploads/",
            data={"project": self.project_b.id, "filename": "Denied.raw", "size_bytes": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_non_admin_only_sees_own_profile(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.get("/api/user-profiles/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["user"], self.researcher.id)

    def test_researcher_cannot_create_project_in_non_member_lab(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.post(
            "/api/projects/",
            data={
                "lab": self.lab_b.id,
                "title": "Cross-lab Project",
                "code": "P-X",
                "pi": self.pi_user.id,
                "status": "active",
                "description": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_researcher_cannot_move_project_to_non_member_lab(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.patch(
            f"/api/projects/{self.project_a.id}/",
            data={"lab": self.lab_b.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_researcher_can_update_project_in_member_lab(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.patch(
            f"/api/projects/{self.project_a.id}/",
            data={"title": "Project A Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.project_a.refresh_from_db()
        self.assertEqual(self.project_a.title, "Project A Updated")

    def test_qc_overview_and_details_return_hye_metrics(self):
        call_command("seed_demo_showcase", verbosity=0)
        demo_user = User.objects.get(username="parkerreyes")
        project = Project.objects.get(code="COHORT-DIA-100")
        worklist = AcquisitionWorklist.objects.get(name="Plate 1 DIA acquisition order")

        self.client.force_authenticate(user=demo_user)

        overview_response = self.client.get(
            f"/api/qc/overview/?program=hye&project={project.id}&worklist={worklist.id}"
        )
        self.assertEqual(overview_response.status_code, 200)
        self.assertEqual(overview_response.data["program"], "hye")
        self.assertEqual(overview_response.data["qc_injection_count"], 22)
        self.assertGreaterEqual(overview_response.data["complete_pair_count"], 1)

        details_response = self.client.get(
            f"/api/qc/details/?program=hye&project={project.id}&worklist={worklist.id}"
        )
        self.assertEqual(details_response.status_code, 200)
        self.assertEqual(details_response.data["program"], "hye")
        self.assertGreater(len(details_response.data["pairs"]), 0)
        self.assertEqual(details_response.data["pairs"][0]["organisms"][0]["organism"], "Homo sapiens")

    def test_qc_overview_respects_lab_scope(self):
        call_command("seed_demo_showcase", verbosity=0)
        project = Project.objects.get(code="COHORT-DIA-100")
        self.client.force_authenticate(user=self.external)

        response = self.client.get(f"/api/qc/overview/?program=hye&project={project.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["qc_injection_count"], 0)
        self.assertEqual(response.data["complete_pair_count"], 0)


@override_settings(
    MSCONNECT_WATCHER_TOKEN="watcher-token",
    MSCONNECT_PROCESSOR_TOKEN="processor-token",
)
class AgentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.university = University.objects.create(name="BYU")
        self.facility = Facility.objects.create(university=self.university, name="Proteomics Core", slug="proteomics")
        self.lab = Lab.objects.create(facility=self.facility, name="Lab A", slug="lab-a")
        self.pi_user = User.objects.create_user(username="pi-agent", password="password123")
        UserProfile.objects.create(user=self.pi_user, global_role=UserRole.PI)
        LabMembership.objects.create(user=self.pi_user, lab=self.lab, role=UserRole.PI)
        self.project = Project.objects.create(lab=self.lab, title="Project A", code="P-A", pi=self.pi_user)
        self.experiment = Experiment.objects.create(project=self.project, name="Exp 1")
        self.sample = Sample.objects.create(experiment=self.experiment, name="Sample A")
        self.run = Run.objects.create(sample=self.sample, run_name="run07")

    def _watcher_client(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer watcher-token")
        return client

    def _processor_client(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer processor-token")
        return client

    def test_human_auth_cannot_call_agent_endpoint(self):
        self.client.force_authenticate(user=self.pi_user)
        response = self.client.post("/api/agents/heartbeat/", data={"name": "human", "node_type": "watcher"})
        self.assertEqual(response.status_code, 403)

    def test_invalid_agent_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        response = self.client.post("/api/agents/heartbeat/", data={"name": "bad", "node_type": "watcher"})
        self.assertEqual(response.status_code, 401)

    def test_watcher_import_endpoint_is_idempotent(self):
        watcher = self._watcher_client()
        with TemporaryDirectory() as storage_dir:
            storage_root = Path(storage_dir)
            file_path = storage_root / "aa" / f"{'a' * 64}_SampleA_run07.raw"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"raw-data")

            with override_settings(RAW_FILE_STORAGE_ROOT=str(storage_root)):
                create_response = watcher.post(
                    "/api/agents/raw-files/import/",
                    data={
                        "source_path": "/incoming/SampleA_run07.raw",
                        "storage_path": str(file_path),
                        "filename": "SampleA_run07.raw",
                        "checksum_sha256": "a" * 64,
                        "size_bytes": len(b"raw-data"),
                        "match_run_by_name": True,
                    },
                    format="json",
                )
                self.assertEqual(create_response.status_code, 201)
                self.assertTrue(create_response.data["created"])
                raw_file = RawFile.objects.get(checksum_sha256="a" * 64)
                self.assertEqual(raw_file.run_id, self.run.id)

                second_response = watcher.post(
                    "/api/agents/raw-files/import/",
                    data={
                        "source_path": "/incoming/SampleA_run07.raw",
                        "storage_path": str(file_path),
                        "filename": "SampleA_run07.raw",
                        "checksum_sha256": "a" * 64,
                        "size_bytes": len(b"raw-data"),
                    },
                    format="json",
                )
                self.assertEqual(second_response.status_code, 200)
                self.assertFalse(second_response.data["created"])
                self.assertEqual(RawFile.objects.count(), 1)

    def test_watcher_import_queues_processing_job_for_pre_acquisition_run(self):
        self.client.force_authenticate(user=self.pi_user)
        setup_response = self.client.post(
            "/api/projects/pre-acquisition-setup/",
            data={
                "title": "Agent Smoke Cohort",
                "code": "AGENT-SMOKE",
                "sample_count": 1,
                "healthy_count": 1,
                "diseased_count": 0,
                "hye_interval": 0,
                "diann_version": "smoke-1.9",
            },
            format="json",
        )
        self.assertEqual(setup_response.status_code, 201)
        expected_filename = setup_response.data["expected_filenames"][0]

        watcher = self._watcher_client()
        with TemporaryDirectory() as storage_dir:
            storage_root = Path(storage_dir)
            file_bytes = b"raw-data"
            checksum = hashlib.sha256(file_bytes).hexdigest()
            file_path = storage_root / checksum[:2] / f"{checksum}_{expected_filename}"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(file_bytes)

            with override_settings(RAW_FILE_STORAGE_ROOT=str(storage_root)):
                import_response = watcher.post(
                    "/api/agents/raw-files/import/",
                    data={
                        "source_path": f"/incoming/{expected_filename}",
                        "storage_path": str(file_path),
                        "filename": expected_filename,
                        "checksum_sha256": checksum,
                        "size_bytes": len(file_bytes),
                        "match_run_by_name": True,
                    },
                    format="json",
                )

        self.assertEqual(import_response.status_code, 201)
        self.assertTrue(import_response.data["created"])
        self.assertIsNotNone(import_response.data["processing_job"])

        raw_file = RawFile.objects.get(checksum_sha256=checksum)
        raw_file.run.refresh_from_db()
        job = ProcessingJob.objects.get(raw_file=raw_file)
        self.assertEqual(raw_file.file_role, raw_file.run.file_role)
        self.assertEqual(raw_file.status, "imported")
        self.assertEqual(raw_file.run.status, "imported")
        self.assertEqual(job.status, ProcessingStatus.QUEUED)
        self.assertEqual(job.pipeline.name, "DIA-NN")
        self.assertIn("command", job.pipeline.parameters)

    def test_watcher_failure_endpoint_increments_seen_count(self):
        watcher = self._watcher_client()
        first = watcher.post(
            "/api/agents/ingestion-failures/",
            data={"source_path": "/incoming/missing.raw", "failure_reason": "missing"},
            format="json",
        )
        second = watcher.post(
            "/api/agents/ingestion-failures/",
            data={"source_path": "/incoming/missing.raw", "failure_reason": "still missing"},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["seen_count"], 2)

    def test_processor_claim_start_and_complete_job(self):
        processor = self._processor_client()
        raw_file = RawFile.objects.create(
            run=self.run,
            source_path="/incoming/SampleA_run07.raw",
            storage_path="/data/raw/aa/sample.raw",
            filename="SampleA_run07.raw",
            checksum_sha256="b" * 64,
            size_bytes=1024,
            status="imported",
        )
        pipeline = ProcessingPipeline.objects.create(
            name="DIA-NN",
            version="1.0",
            parameters={
                "command": ["echo", "ok"],
                "result_files": {"protein_table": "proteins.csv", "peptide_table": "peptides.tsv"},
            },
        )
        job = ProcessingJob.objects.create(
            run=self.run,
            pipeline=pipeline,
            raw_file=raw_file,
            status=ProcessingStatus.QUEUED,
        )

        claim_response = processor.post("/api/processing-jobs/claim-next/", data={"node_name": "proc-1"}, format="json")
        self.assertEqual(claim_response.status_code, 200)
        self.assertEqual(claim_response.data["id"], job.id)
        second_claim = processor.post("/api/processing-jobs/claim-next/", data={"node_name": "proc-1"}, format="json")
        self.assertEqual(second_claim.status_code, 204)

        start_response = processor.post(
            f"/api/processing-jobs/{job.id}/start/",
            data={"node_name": "proc-1"},
            format="json",
        )
        self.assertEqual(start_response.status_code, 200)

        with TemporaryDirectory() as results_dir:
            proteins = Path(results_dir) / "proteins.csv"
            peptides = Path(results_dir) / "peptides.tsv"
            log_path = Path(results_dir) / "process.log"
            proteins.write_text("accession,value\nP12345,10.5\n", encoding="utf-8")
            peptides.write_text("sequence\tvalue\nPEPTIDE\t9.9\n", encoding="utf-8")
            log_path.write_text("done\n", encoding="utf-8")

            with override_settings(RESULTS_ROOT=results_dir):
                complete_response = processor.post(
                    f"/api/processing-jobs/{job.id}/complete/",
                    data={
                        "node_name": "proc-1",
                        "protein_table_path": str(proteins),
                        "peptide_table_path": str(peptides),
                        "log_path": str(log_path),
                    },
                    format="json",
                )

        self.assertEqual(complete_response.status_code, 200)
        job.refresh_from_db()
        raw_file.refresh_from_db()
        self.assertEqual(job.status, ProcessingStatus.COMPLETE)
        self.assertEqual(raw_file.status, "processed")
        self.assertEqual(ProteinQuant.objects.filter(job=job).count(), 1)
        self.assertEqual(PeptideQuant.objects.filter(job=job).count(), 1)
        self.assertEqual(ProcessingNode.objects.get(name="proc-1").status, "idle")

    def test_processor_complete_records_derivative_and_spectra_api_reads_index(self):
        processor = self._processor_client()
        raw_file = RawFile.objects.create(
            run=self.run,
            source_path="/incoming/SampleA_run07.raw",
            storage_path="/data/raw/aa/sample.raw",
            filename="SampleA_run07.raw",
            checksum_sha256="c" * 64,
            size_bytes=1024,
            status="imported",
        )
        pipeline = ProcessingPipeline.objects.create(
            name="ProteoWizard msconvert",
            version="test",
            parameters={"adapter": "msconvert", "output_format": "mzML"},
        )
        job = ProcessingJob.objects.create(
            run=self.run,
            pipeline=pipeline,
            raw_file=raw_file,
            status=ProcessingStatus.QUEUED,
        )

        claim_response = processor.post("/api/processing-jobs/claim-next/", data={"node_name": "proc-2"}, format="json")
        self.assertEqual(claim_response.status_code, 200)

        with TemporaryDirectory() as results_dir:
            index_path = Path(results_dir) / "spectrum-index.json"
            log_path = Path(results_dir) / "process.log"
            index_path.write_text(
                json.dumps(
                    {
                        "spectra": [
                            {
                                "id": "scan=1",
                                "index": 0,
                                "scan_number": 1,
                                "ms_level": 2,
                                "retention_time_seconds": 42.5,
                                "base_peak_mz": 445.2,
                                "base_peak_intensity": 12000,
                                "tic": 45000,
                                "precursor_mz": 678.9,
                                "peaks": [[445.2, 12000], [500.1, 3000]],
                            }
                        ],
                        "chromatograms": {"tic": [[42.5, 45000]], "bpc": [[42.5, 12000]]},
                    }
                ),
                encoding="utf-8",
            )
            log_path.write_text("done\n", encoding="utf-8")

            with override_settings(RESULTS_ROOT=results_dir):
                complete_response = processor.post(
                    f"/api/processing-jobs/{job.id}/complete/",
                    data={
                        "node_name": "proc-2",
                        "log_path": str(log_path),
                        "derivatives": [
                            {
                                "derivative_type": "spectrum_index",
                                "path": str(index_path),
                                "format": "json",
                            }
                        ],
                    },
                    format="json",
                )
                self.assertEqual(complete_response.status_code, 200)
                self.client.force_authenticate(user=self.pi_user)
                spectra_response = self.client.get(f"/api/raw-files/{raw_file.id}/spectra/")
                spectrum_response = self.client.get(f"/api/raw-files/{raw_file.id}/spectra/scan=1/")
                chromatograms_response = self.client.get(f"/api/raw-files/{raw_file.id}/chromatograms/")

        self.assertEqual(
            RawFileDerivative.objects.filter(raw_file=raw_file, derivative_type="spectrum_index").count(),
            1,
        )
        self.assertEqual(spectra_response.status_code, 200)
        self.assertEqual(spectra_response.data["count"], 1)
        self.assertEqual(spectrum_response.status_code, 200)
        self.assertEqual(spectrum_response.data["spectrum"]["peaks"][0], [445.2, 12000])
        self.assertEqual(chromatograms_response.status_code, 200)
        self.assertEqual(chromatograms_response.data["chromatograms"]["tic"][0], [42.5, 45000])
