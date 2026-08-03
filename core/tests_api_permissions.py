import hashlib
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
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
    QcProgram,
    RawFile,
    RawFileDerivative,
    Run,
    RunFileRole,
    Sample,
    University,
    UserProfile,
    UserRole,
)

User = get_user_model()


class HealthEndpointTests(TestCase):
    def test_healthz_is_public(self):
        response = APIClient().get("/healthz/")
        data = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")

    def test_readyz_reports_storage_and_database(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            raw = root / "raw"
            results = root / "results"
            media = root / "media"
            for path in (incoming, raw, results, media):
                path.mkdir()

            with override_settings(
                INCOMING_RAW_ROOT=str(incoming),
                RAW_FILE_STORAGE_ROOT=str(raw),
                RESULTS_ROOT=str(results),
                MEDIA_ROOT=str(media),
            ):
                response = APIClient().get("/readyz/")
                data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["checks"]["database"]["ok"])
        self.assertTrue(data["checks"]["results_root"]["ok"])


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

    def test_quick_start_creates_project_and_default_experiment(self):
        self.client.force_authenticate(user=self.researcher)

        response = self.client.post(
            "/api/projects/quick-start/",
            data={"title": "Researcher Quick Project", "code": "QUICK-01"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        project = Project.objects.get(code="QUICK-01")
        self.assertEqual(project.lab_id, self.lab_a.id)
        self.assertEqual(project.pi_id, self.researcher.id)
        self.assertEqual(Experiment.objects.get(project=project).name, "Default experiment")

    def test_worklist_import_creates_and_updates_project_runs(self):
        self.client.force_authenticate(user=self.researcher)
        quick_response = self.client.post(
            "/api/projects/quick-start/",
            data={"title": "Worklist Import Project", "code": "WL-IMPORT"},
            format="json",
        )
        project_id = quick_response.data["project"]["id"]
        payload = {
            "worklist_name": "Instrument worklist",
            "rows": [
                {
                    "position": 1,
                    "sample_name": "Sample-001",
                    "run_name": "Run-001",
                    "expected_filename": "Run_001.raw",
                    "file_role": "sample",
                    "condition": "healthy",
                    "well": "A01",
                },
                {
                    "position": 2,
                    "sample_name": "HYE-A",
                    "run_name": "HYE-A-001",
                    "expected_filename": "HYE_A_001.raw",
                    "file_role": "qc",
                    "hye_pair_label": "HYE-01",
                    "well": "A02",
                },
            ],
        }

        first = self.client.post(f"/api/projects/{project_id}/import-worklist/", data=payload, format="json")
        second_payload = {
            **payload,
            "rows": [
                {**payload["rows"][0], "expected_filename": "Run_001_REINJECT.raw", "status": "planned"},
                payload["rows"][1],
            ],
        }
        second = self.client.post(f"/api/projects/{project_id}/import-worklist/", data=second_payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        worklist = AcquisitionWorklist.objects.get(name="Instrument worklist")
        self.assertEqual(worklist.entries.count(), 2)
        self.assertEqual(Run.objects.filter(sample__experiment__project_id=project_id).count(), 2)
        first_entry = worklist.entries.get(position=1)
        self.assertEqual(first_entry.expected_filename, "Run_001_REINJECT.raw")
        self.assertEqual(first_entry.run.expected_filename, "Run_001_REINJECT.raw")
        self.assertEqual(first_entry.metadata["well"], "A01")

    def test_researcher_status_returns_single_page_run_rows(self):
        self.client.force_authenticate(user=self.researcher)
        quick_response = self.client.post(
            "/api/projects/quick-start/",
            data={"title": "Status Project", "code": "STATUS-01"},
            format="json",
        )
        project_id = quick_response.data["project"]["id"]
        self.client.post(
            f"/api/projects/{project_id}/import-worklist/",
            data={
                "worklist_name": "Status worklist",
                "rows": [
                    {
                        "position": 1,
                        "sample_name": "Sample-001",
                        "run_name": "Status Run 1",
                        "expected_filename": "Status_Run_1.raw",
                        "file_role": "sample",
                    }
                ],
            },
            format="json",
        )

        response = self.client.get(f"/api/projects/{project_id}/researcher-status/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["project"]["code"], "STATUS-01")
        self.assertEqual(response.data["system_health"]["status"], "yellow")
        self.assertEqual(len(response.data["runs"]), 1)
        self.assertEqual(response.data["runs"][0]["run"]["expected_filename"], "Status_Run_1.raw")
        self.assertEqual(response.data["runs"][0]["worklist_name"], "Status worklist")

    def test_queue_ready_runs_queues_uploaded_unqueued_runs(self):
        self.client.force_authenticate(user=self.researcher)
        quick_response = self.client.post(
            "/api/projects/quick-start/",
            data={"title": "Queue Ready Project", "code": "QUEUE-READY"},
            format="json",
        )
        project_id = quick_response.data["project"]["id"]
        self.client.post(
            f"/api/projects/{project_id}/import-worklist/",
            data={
                "worklist_name": "Queue worklist",
                "rows": [
                    {
                        "position": 1,
                        "sample_name": "Sample-001",
                        "run_name": "Queue Run 1",
                        "expected_filename": "Queue_Run_1.raw",
                        "file_role": "sample",
                    }
                ],
            },
            format="json",
        )
        run = Run.objects.get(run_name="Queue Run 1")
        RawFile.objects.create(
            run=run,
            source_path="/incoming/Queue_Run_1.raw",
            storage_path="/data/raw/Queue_Run_1.raw",
            filename="Queue_Run_1.raw",
            checksum_sha256="b" * 64,
            size_bytes=1024,
            status="imported",
            file_role="sample",
        )

        response = self.client.post(f"/api/projects/{project_id}/queue-ready-runs/", data={}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["queued"], 1)
        self.assertEqual(ProcessingJob.objects.filter(run=run, status=ProcessingStatus.QUEUED).count(), 1)

    def test_queue_runs_only_queues_selected_uploaded_runs(self):
        self.client.force_authenticate(user=self.researcher)
        quick_response = self.client.post(
            "/api/projects/quick-start/",
            data={"title": "Queue Selected Project", "code": "QUEUE-SELECTED"},
            format="json",
        )
        project_id = quick_response.data["project"]["id"]
        self.client.post(
            f"/api/projects/{project_id}/import-worklist/",
            data={
                "worklist_name": "Queue selected worklist",
                "rows": [
                    {
                        "position": 1,
                        "sample_name": "Sample-001",
                        "run_name": "Selected Run 1",
                        "expected_filename": "Selected_Run_1.raw",
                        "file_role": "sample",
                    },
                    {
                        "position": 2,
                        "sample_name": "Sample-002",
                        "run_name": "Selected Run 2",
                        "expected_filename": "Selected_Run_2.raw",
                        "file_role": "sample",
                    },
                ],
            },
            format="json",
        )
        run_1 = Run.objects.get(run_name="Selected Run 1")
        run_2 = Run.objects.get(run_name="Selected Run 2")
        raw_1 = RawFile.objects.create(
            run=run_1,
            source_path="/incoming/Selected_Run_1.raw",
            storage_path="/data/raw/Selected_Run_1.raw",
            filename="Selected_Run_1.raw",
            checksum_sha256="c" * 64,
            size_bytes=1024,
            status="imported",
            file_role="sample",
        )
        RawFile.objects.create(
            run=run_2,
            source_path="/incoming/Selected_Run_2.raw",
            storage_path="/data/raw/Selected_Run_2.raw",
            filename="Selected_Run_2.raw",
            checksum_sha256="d" * 64,
            size_bytes=2048,
            status="imported",
            file_role="sample",
        )

        response = self.client.post(
            f"/api/projects/{project_id}/queue-runs/",
            data={"run_ids": [run_1.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["requested"], 1)
        self.assertEqual(response.data["queued"], 1)
        self.assertTrue(
            ProcessingJob.objects.filter(run=run_1, raw_file=raw_1, status=ProcessingStatus.QUEUED).exists()
        )
        self.assertFalse(ProcessingJob.objects.filter(run=run_2).exists())

    def test_processing_node_control_is_admin_only_and_reports_health(self):
        node = ProcessingNode.objects.create(
            name="diann-win-01",
            node_type="diann",
            status="idle",
            metadata={"ip_address": "10.0.0.7"},
        )

        self.client.force_authenticate(user=self.researcher)
        denied_response = self.client.post(
            f"/api/processing-nodes/{node.id}/control/",
            data={"command": "pause"},
            format="json",
        )
        self.assertEqual(denied_response.status_code, 403)

        self.client.force_authenticate(user=self.admin)
        control_response = self.client.post(
            f"/api/processing-nodes/{node.id}/control/",
            data={"command": "pause", "reason": "maintenance"},
            format="json",
        )
        overview_response = self.client.get("/api/processing-nodes/overview/")

        self.assertEqual(control_response.status_code, 200)
        self.assertEqual(control_response.data["ip_address"], "10.0.0.7")
        self.assertEqual(control_response.data["health"], "red")
        self.assertEqual(control_response.data["active_control"]["command"], "pause")
        self.assertEqual(control_response.data["active_control"]["status"], "requested")
        self.assertEqual(overview_response.status_code, 200)
        self.assertEqual(overview_response.data["stale"], 1)

    def test_system_health_reports_warnings_for_connected_and_downed_nodes(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            raw = root / "raw"
            results = root / "results"
            media = root / "media"
            for path in (incoming, raw, results, media):
                path.mkdir()

            with override_settings(
                INCOMING_RAW_ROOT=str(incoming),
                RAW_FILE_STORAGE_ROOT=str(raw),
                RESULTS_ROOT=str(results),
                MEDIA_ROOT=str(media),
            ):
                experiment = Experiment.objects.create(project=self.project_a, name="Health Check Exp")
                run = Run.objects.create(sample=Sample.objects.create(experiment=experiment, name="Health Sample"), run_name="Health Run")
                pipeline = ProcessingPipeline.objects.create(name="DIA-NN", version="1.0", container_image="diann")
                ProcessingNode.objects.create(
                    name="watcher-1",
                    node_type="watcher",
                    status="idle",
                    last_heartbeat_at=timezone.now() - timedelta(seconds=240),
                )
                processor = ProcessingNode.objects.create(
                    name="processor-1",
                    node_type="diann",
                    status="offline",
                    last_heartbeat_at=timezone.now() - timedelta(seconds=30),
                )
                raw_file = RawFile.objects.create(
                    run=run,
                    source_path="/incoming/sample.raw",
                    storage_path=str(raw / "sample.raw"),
                    filename="sample.raw",
                    status="imported",
                    size_bytes=1,
                    file_role=RunFileRole.SAMPLE,
                )
                ProcessingJob.objects.create(
                    run=run,
                    pipeline=pipeline,
                    raw_file=raw_file,
                    node=processor,
                    status=ProcessingStatus.FAILED,
                    error_message="processor failed",
                )

                self.client.force_authenticate(user=self.admin)
                response = self.client.get("/api/system-health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "red")
        self.assertGreaterEqual(response.data["nodes"]["stale"], 1)
        self.assertGreaterEqual(response.data["nodes"]["offline"], 1)
        self.assertGreaterEqual(response.data["jobs"]["failed"], 1)
        self.assertGreaterEqual(len(response.data["alerts"]), 3)

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
        self.assertEqual(
            worklist.entries.filter(
                file_role=RunFileRole.HYE,
                qc_program=QcProgram.HYE,
                hye_pair_label="HYE-01",
            ).count(),
            2,
        )

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

    def test_direct_upload_session_can_match_expected_filename(self):
        self.client.force_authenticate(user=self.researcher)
        experiment = Experiment.objects.create(project=self.project_a, name="Upload Match Exp")
        sample = Sample.objects.create(experiment=experiment, name="Matched Sample")
        run = Run.objects.create(
            sample=sample,
            run_name="Matched Run",
            expected_filename="Matched_Run.raw",
        )

        create_response = self.client.post(
            "/api/direct-uploads/",
            data={
                "project": self.project_a.id,
                "filename": "Matched_Run.raw",
                "expected_filename": "Matched_Run.raw",
                "size_bytes": 10,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["run"], run.id)
        self.assertEqual(create_response.data["intended_filename"], "Matched_Run.raw")

        upload = DirectUploadSession.objects.get(id=create_response.data["id"])
        complete_response = self.client.post(
            f"/api/direct-uploads/{upload.id}/complete/",
            data={"checksum_sha256": "e" * 64},
            format="json",
        )
        self.assertEqual(complete_response.status_code, 200)
        raw_file = RawFile.objects.get(checksum_sha256="e" * 64)
        self.assertEqual(raw_file.run_id, run.id)
        self.assertEqual(raw_file.metadata["intended_filename"], "Matched_Run.raw")

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
        collaborator = User.objects.get(username="demo-collaborator")
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
        self.assertIn("machine_summaries", details_response.data)
        self.assertIn("machine_series", details_response.data)
        self.assertEqual(collaborator.profile.global_role, UserRole.COLLABORATOR)
        self.assertTrue(LabMembership.objects.filter(user=collaborator, active=True).exists())

    def test_qc_overview_respects_lab_scope(self):
        call_command("seed_demo_showcase", verbosity=0)
        project = Project.objects.get(code="COHORT-DIA-100")
        self.client.force_authenticate(user=self.external)

        response = self.client.get(f"/api/qc/overview/?program=hye&project={project.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["qc_injection_count"], 0)
        self.assertEqual(response.data["complete_pair_count"], 0)

    def test_qc_prtc_returns_skyline_job_stats(self):
        experiment = Experiment.objects.create(project=self.project_a, name="PRTC Exp")
        worklist = AcquisitionWorklist.objects.create(experiment=experiment, name="PRTC Plate")
        sample = Sample.objects.create(experiment=experiment, name="PRTC Std")
        run = Run.objects.create(
            sample=sample,
            run_name="PRTC-01",
            expected_filename="PRTC-01.raw",
            file_role=RunFileRole.PRTC,
            qc_program=QcProgram.PRTC,
        )
        worklist.entries.create(
            position=1,
            run=run,
            expected_filename="PRTC-01.raw",
            file_role=RunFileRole.PRTC,
            qc_program=QcProgram.PRTC,
        )
        raw_file = RawFile.objects.create(
            run=run,
            source_path="/incoming/PRTC-01.raw",
            storage_path="/data/raw/prtc.raw",
            filename="PRTC-01.raw",
            checksum_sha256="d" * 64,
            size_bytes=2048,
            status="processed",
            file_role=RunFileRole.PRTC,
        )
        pipeline = ProcessingPipeline.objects.create(
            name="Skyline PRTC",
            version="26.1",
            parameters={"adapter": "skyline", "required_engine": "skyline"},
        )
        ProcessingJob.objects.create(
            run=run,
            raw_file=raw_file,
            pipeline=pipeline,
            status=ProcessingStatus.COMPLETE,
            finished_at=timezone.now(),
            stats={
                "program": "prtc",
                "status": "pass",
                "expected_peptide_count": 15,
                "detected_peptide_count": 15,
                "missing_peptide_count": 0,
                "out_of_tolerance_peptide_count": 0,
                "total_area": 12345.6,
                "mean_rt_shift_seconds": 0.4,
                "max_abs_rt_shift_seconds": 1.2,
            },
        )

        self.client.force_authenticate(user=self.researcher)
        overview_response = self.client.get(f"/api/qc/overview/?program=prtc&project={self.project_a.id}")
        self.assertEqual(overview_response.status_code, 200)
        self.assertTrue(overview_response.data["configured"])
        self.assertEqual(overview_response.data["qc_injection_count"], 1)
        self.assertEqual(overview_response.data["complete_pair_count"], 1)

        details_response = self.client.get(f"/api/qc/details/?program=prtc&project={self.project_a.id}")
        self.assertEqual(details_response.status_code, 200)
        self.assertEqual(details_response.data["runs"][0]["detected_peptide_count"], 15)
        self.assertEqual(details_response.data["runs"][0]["status"], "pass")


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

    def test_agent_ping_reports_authenticated_role(self):
        watcher_response = self._watcher_client().get("/api/agents/ping/")
        processor_response = self._processor_client().get("/api/agents/ping/")

        self.assertEqual(watcher_response.status_code, 200)
        self.assertEqual(watcher_response.data["status"], "ok")
        self.assertEqual(watcher_response.data["agent_role"], "watcher")
        self.assertEqual(processor_response.status_code, 200)
        self.assertEqual(processor_response.data["agent_role"], "processor")

    def test_processor_heartbeat_accepts_engine_type_and_acknowledges_control(self):
        processor = self._processor_client()
        ProcessingNode.objects.create(
            name="pd-win-01",
            node_type="proteome-discoverer",
            status="idle",
            metadata={"control": {"id": "ctrl-1", "command": "pause", "status": "requested"}},
        )

        response = processor.post(
            "/api/agents/heartbeat/",
            data={
                "name": "pd-win-01",
                "node_type": "proteome-discoverer",
                "status": "idle",
                "metadata": {"ack_control_id": "ctrl-1", "ip_address": "10.0.0.9"},
                "settings": {"processor_shared_storage_root": r"\\nas\msconnect\results"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["node_type"], "proteome-discoverer")
        self.assertEqual(response.data["ip_address"], "10.0.0.9")
        self.assertEqual(response.data["active_control"]["status"], "acknowledged")
        self.assertEqual(response.data["settings"]["processor_shared_storage_root"], r"\\nas\msconnect\results")

    def test_processor_claim_respects_required_engine(self):
        processor = self._processor_client()
        ProcessingNode.objects.create(name="diann-1", node_type="diann", status="idle")
        ProcessingNode.objects.create(name="skyline-1", node_type="skyline", status="idle")
        raw_file = RawFile.objects.create(
            run=self.run,
            source_path="/incoming/SampleA_run07.raw",
            storage_path="/data/raw/aa/sample.raw",
            filename="SampleA_run07.raw",
            checksum_sha256="9" * 64,
            size_bytes=1024,
            status="imported",
        )
        pipeline = ProcessingPipeline.objects.create(
            name="Skyline",
            version="24.1",
            parameters={"adapter": "skyline", "document": "/shared/project.sky"},
        )
        job = ProcessingJob.objects.create(
            run=self.run,
            pipeline=pipeline,
            raw_file=raw_file,
            status=ProcessingStatus.QUEUED,
        )

        incompatible = processor.post(
            "/api/processing-jobs/claim-next/",
            data={"node_name": "diann-1"},
            format="json",
        )
        self.assertEqual(incompatible.status_code, 204)
        job.refresh_from_db()
        self.assertEqual(job.status, ProcessingStatus.QUEUED)

        compatible = processor.post(
            "/api/processing-jobs/claim-next/",
            data={"node_name": "skyline-1"},
            format="json",
        )
        self.assertEqual(compatible.status_code, 200)
        self.assertEqual(compatible.data["id"], job.id)
        self.assertEqual(compatible.data["metadata"]["required_engine"], "skyline")

    def test_processor_claim_respects_required_engine_version(self):
        processor = self._processor_client()
        ProcessingNode.objects.create(
            name="diann-1-9-2",
            node_type="diann",
            status="idle",
            settings={"processor_engine_version": "1.9.2"},
        )
        ProcessingNode.objects.create(
            name="diann-2-1-0",
            node_type="diann",
            status="idle",
            settings={"processor_engine_version": "2.1.0"},
        )
        raw_file = RawFile.objects.create(
            run=self.run,
            source_path="/incoming/SampleA_run08.raw",
            storage_path="/data/raw/aa/sample08.raw",
            filename="SampleA_run08.raw",
            checksum_sha256="8" * 64,
            size_bytes=1024,
            status="imported",
        )
        pipeline = ProcessingPipeline.objects.create(
            name="DIA-NN",
            version="2.1.0",
            parameters={"adapter": "diann", "required_engine_version": "2.1.0"},
        )
        job = ProcessingJob.objects.create(
            run=self.run,
            pipeline=pipeline,
            raw_file=raw_file,
            status=ProcessingStatus.QUEUED,
        )

        incompatible = processor.post(
            "/api/processing-jobs/claim-next/",
            data={"node_name": "diann-1-9-2"},
            format="json",
        )
        self.assertEqual(incompatible.status_code, 204)
        job.refresh_from_db()
        self.assertEqual(job.status, ProcessingStatus.QUEUED)

        compatible = processor.post(
            "/api/processing-jobs/claim-next/",
            data={"node_name": "diann-2-1-0"},
            format="json",
        )
        self.assertEqual(compatible.status_code, 200)
        self.assertEqual(compatible.data["id"], job.id)
        self.assertEqual(compatible.data["metadata"]["required_engine"], "diann")
        self.assertEqual(compatible.data["metadata"]["required_engine_version"], "2.1.0")

    def test_worklist_import_stores_qc_program_and_extended_roles(self):
        self.client.force_authenticate(user=self.pi_user)
        response = self.client.post(
            f"/api/projects/{self.project.id}/import-worklist/",
            data={
                "worklist_name": "Vendor sequence",
                "rows": [
                    {
                        "position": 1,
                        "sample_name": "PRTC-Std",
                        "expected_filename": "PRTC-Std.raw",
                        "file_role": "prtc",
                    },
                    {
                        "position": 2,
                        "sample_name": "Blank-01",
                        "expected_filename": "Blank-01.raw",
                        "file_role": "true blank",
                    },
                    {
                        "position": 3,
                        "sample_name": "HYE-A",
                        "expected_filename": "HYE-A.raw",
                        "file_role": "qc",
                        "qc_program": "hye",
                        "hye_pair_label": "HYE-01",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        prtc_run = Run.objects.get(expected_filename="PRTC-Std.raw")
        blank_run = Run.objects.get(expected_filename="Blank-01.raw")
        hye_run = Run.objects.get(expected_filename="HYE-A.raw")
        self.assertEqual(prtc_run.file_role, RunFileRole.PRTC)
        self.assertEqual(prtc_run.qc_program, QcProgram.PRTC)
        self.assertTrue(prtc_run.metadata["synthetic_peptides_present"])
        self.assertEqual(blank_run.file_role, RunFileRole.TRUE_BLANK)
        self.assertEqual(blank_run.qc_program, QcProgram.NONE)
        self.assertEqual(hye_run.file_role, RunFileRole.QC)
        self.assertEqual(hye_run.qc_program, QcProgram.HYE)

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

    def test_watcher_import_routes_prtc_run_to_configured_skyline_pipeline(self):
        default_pipeline = ProcessingPipeline.objects.create(
            name="DIA-NN",
            version="default",
            parameters={"adapter": "diann", "required_engine": "diann"},
        )
        skyline_pipeline = ProcessingPipeline.objects.create(
            name="Skyline PRTC",
            version="26.1",
            parameters={
                "adapter": "skyline",
                "required_engine": "skyline",
                "required_engine_version": "26.1.0",
                "document": "/data/shared/skyline/prtc-15.sky",
                "postprocess": "skyline_prtc",
            },
        )
        worklist = AcquisitionWorklist.objects.create(
            experiment=self.experiment,
            name="PRTC sequence",
            metadata={"processing_pipeline_id": default_pipeline.id},
        )
        sample = Sample.objects.create(experiment=self.experiment, name="PRTC-Std")
        run = Run.objects.create(
            sample=sample,
            run_name="PRTC-Std",
            expected_filename="PRTC-Std.raw",
            file_role=RunFileRole.PRTC,
            qc_program=QcProgram.PRTC,
        )
        worklist.entries.create(
            position=1,
            run=run,
            expected_filename="PRTC-Std.raw",
            file_role=RunFileRole.PRTC,
            qc_program=QcProgram.PRTC,
        )

        watcher = self._watcher_client()
        with TemporaryDirectory() as storage_dir:
            storage_root = Path(storage_dir)
            file_bytes = b"prtc-raw-data"
            checksum = hashlib.sha256(file_bytes).hexdigest()
            file_path = storage_root / checksum[:2] / f"{checksum}_PRTC-Std.raw"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(file_bytes)

            with override_settings(
                RAW_FILE_STORAGE_ROOT=str(storage_root),
                MSCONNECT_PRTC_SKYLINE_PIPELINE_ID=str(skyline_pipeline.id),
            ):
                import_response = watcher.post(
                    "/api/agents/raw-files/import/",
                    data={
                        "source_path": "/incoming/PRTC-Std.raw",
                        "storage_path": str(file_path),
                        "filename": "PRTC-Std.raw",
                        "checksum_sha256": checksum,
                        "size_bytes": len(file_bytes),
                        "match_run_by_name": True,
                    },
                    format="json",
                )

        self.assertEqual(import_response.status_code, 201)
        raw_file = RawFile.objects.get(checksum_sha256=checksum)
        job = ProcessingJob.objects.get(raw_file=raw_file)
        self.assertEqual(raw_file.file_role, RunFileRole.PRTC)
        self.assertEqual(job.pipeline, skyline_pipeline)
        self.assertEqual(job.metadata["routing"], "prtc_skyline")
        self.assertEqual(job.metadata["required_engine"], "skyline")

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
        ProcessingNode.objects.create(name="proc-2", node_type="msconvert", status="idle")
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
