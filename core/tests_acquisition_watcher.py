from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.management.commands.run_staged_upload_agent import Command, State
from core.management.commands.run_watcher_agent import _acquisition_fingerprint
from core.models import (
    AcquisitionAgent,
    AcquisitionRoute,
    AcquisitionRouteMode,
    AcquisitionRouteStatus,
    AcquisitionSourceRootStatus,
    AcquisitionWorklist,
    DirectUploadSession,
    Experiment,
    Facility,
    Lab,
    LabMembership,
    Project,
    Run,
    Sample,
    University,
    UserProfile,
    UserRole,
    WorklistEntry,
    WorklistStatus,
)


@override_settings(
    MSCONNECT_WATCHER_TOKEN="",
    MSCONNECT_WATCHER_TOKENS={"ms01": "token-ms01", "ms02": "token-ms02"},
    MSCONNECT_PROCESSOR_TOKEN="processor-token",
)
class AcquisitionWatcherRoutingTests(TestCase):
    def setUp(self):
        university = University.objects.create(name="Watcher Test University")
        facility = Facility.objects.create(university=university, name="Test Core", slug="watcher-test")
        lab = Lab.objects.create(facility=facility, name="Test Lab", slug="watcher-test")
        self.pi = get_user_model().objects.create_user(username="watcher-test-pi", password="test-password")
        UserProfile.objects.create(user=self.pi, global_role=UserRole.PI)
        LabMembership.objects.create(user=self.pi, lab=lab, role=UserRole.PI)
        self.project = Project.objects.create(lab=lab, title="Watcher Test", code="WATCHER-TEST", pi=self.pi)
        self.experiment_a = Experiment.objects.create(project=self.project, name="Experiment A")
        self.experiment_b = Experiment.objects.create(project=self.project, name="Experiment B")
        self.agent_a = AcquisitionAgent.objects.create(
            name="ms01",
            token_label="ms01",
            source_root="C:/MSData",
            source_root_status=AcquisitionSourceRootStatus.APPROVED,
        )
        self.agent_b = AcquisitionAgent.objects.create(
            name="ms02",
            token_label="ms02",
            source_root="D:/MSData",
            source_root_status=AcquisitionSourceRootStatus.APPROVED,
        )
        self.worklist_a, self.run_a = self._worklist_run(self.experiment_a, "a.raw", "A sample")
        self.worklist_b, self.run_b = self._worklist_run(self.experiment_b, "b.raw", "B sample")
        self.route_a = AcquisitionRoute.objects.create(
            agent=self.agent_a,
            project=self.project,
            name="experiment-a",
            source_prefix="ExperimentA",
            spool_folder="ExperimentA",
            mode=AcquisitionRouteMode.WORKLIST,
            worklist=self.worklist_a,
            status=AcquisitionRouteStatus.ACTIVE,
            quiet_period_seconds=0,
        )
        self.route_b = AcquisitionRoute.objects.create(
            agent=self.agent_b,
            project=self.project,
            name="experiment-b",
            source_prefix="ExperimentB",
            spool_folder="ExperimentB",
            mode=AcquisitionRouteMode.WORKLIST,
            worklist=self.worklist_b,
            status=AcquisitionRouteStatus.ACTIVE,
            quiet_period_seconds=0,
        )

    def _worklist_run(self, experiment, filename, sample_name):
        sample = Sample.objects.create(experiment=experiment, name=sample_name)
        run = Run.objects.create(sample=sample, run_name=Path(filename).stem, expected_filename=filename)
        worklist = AcquisitionWorklist.objects.create(
            experiment=experiment,
            name=f"{experiment.name} worklist",
            status=WorklistStatus.READY,
        )
        WorklistEntry.objects.create(
            worklist=worklist,
            run=run,
            position=1,
            expected_filename=filename,
        )
        return worklist, run

    @staticmethod
    def _agent_client(token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    def test_agent_config_is_scoped_and_includes_only_its_worklist_files(self):
        response_a = self._agent_client("token-ms01").get("/api/agents/config/")
        response_b = self._agent_client("token-ms02").get("/api/agents/config/")

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual([route["id"] for route in response_a.data["routes"]], [self.route_a.id])
        self.assertEqual([route["id"] for route in response_b.data["routes"]], [self.route_b.id])
        self.assertEqual(response_a.data["routes"][0]["expected_files"], [{
            "run_id": self.run_a.id,
            "expected_filename": "a.raw",
            "file_role": "sample",
            "worklist_entry_id": self.worklist_a.entries.get().id,
        }])

    def test_watcher_upload_must_belong_to_its_route_and_worklist(self):
        client_a = self._agent_client("token-ms01")
        denied = client_a.post(
            "/api/direct-uploads/",
            {
                "project": self.project.id,
                "filename": "b.raw",
                "expected_filename": "b.raw",
                "size_bytes": 4,
                "delivery_mode": "direct",
                "metadata": {"importer": "staged_upload_agent", "route_id": self.route_b.id, "mode": "worklist"},
            },
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        not_queued = client_a.post(
            "/api/direct-uploads/",
            {
                "project": self.project.id,
                "filename": "unplanned.raw",
                "expected_filename": "unplanned.raw",
                "size_bytes": 4,
                "delivery_mode": "direct",
                "metadata": {"importer": "staged_upload_agent", "route_id": self.route_a.id, "mode": "worklist"},
            },
            format="json",
        )
        self.assertEqual(not_queued.status_code, 400)

        accepted = client_a.post(
            "/api/direct-uploads/",
            {
                "project": self.project.id,
                "run": self.run_a.id,
                "filename": "a.raw",
                "expected_filename": "a.raw",
                "size_bytes": 4,
                "delivery_mode": "direct",
                "metadata": {
                    "importer": "staged_upload_agent",
                    "route_id": self.route_a.id,
                    "mode": "worklist",
                    "source_relative_path": "a.raw",
                    "source_fingerprint": '["file",4,123]',
                },
            },
            format="json",
        )
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(accepted.data["run"], self.run_a.id)
        self.assertEqual(accepted.data["metadata"]["worklist_id"], self.worklist_a.id)

        retry = client_a.post(
            "/api/direct-uploads/",
            {
                "project": self.project.id,
                "run": self.run_a.id,
                "filename": "a.raw",
                "expected_filename": "a.raw",
                "size_bytes": 4,
                "delivery_mode": "direct",
                "metadata": {
                    "importer": "staged_upload_agent",
                    "route_id": self.route_a.id,
                    "mode": "worklist",
                    "source_relative_path": "a.raw",
                    "source_fingerprint": '["file",4,123]',
                },
            },
            format="json",
        )
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["id"], accepted.data["id"])
        self.assertEqual(DirectUploadSession.objects.count(), 1)


class AcquisitionWatcherSpoolTests(TestCase):
    def test_directory_stage_reuses_failed_upload_spool_copy(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            source = root / "source" / "sample.d"
            (source / "nested").mkdir(parents=True)
            (source / "nested" / "payload.raw").write_bytes(b"small acquisition payload")
            spool = root / "spool"
            expected = _acquisition_fingerprint(source)

            first = Command._stage(source, spool, "sample.d", expected)
            second = Command._stage(source, spool, "sample.d", expected)

            self.assertEqual(first, second)
            self.assertEqual((second / "nested" / "payload.raw").read_bytes(), b"small acquisition payload")

    def test_stability_observations_survive_state_reopen(self):
        with TemporaryDirectory() as root:
            state_path = Path(root) / "state.sqlite3"
            state = State(state_path)
            first_count, first_elapsed = state.observe(1, "sample.raw", ("file", 4, 10))
            state.db.close()

            reopened = State(state_path)
            second_count, second_elapsed = reopened.observe(1, "sample.raw", ("file", 4, 10))
            reopened.db.close()

            self.assertEqual(first_count, 1)
            self.assertEqual(second_count, 2)
            self.assertGreaterEqual(second_elapsed, first_elapsed)
