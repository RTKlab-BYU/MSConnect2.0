from tempfile import TemporaryDirectory
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import Experiment, Facility, Lab, LabMembership, Project, RawFile, RawFileStatus, Run, Sample, University, UserProfile, UserRole

from .models import FindingsWorkspace
from .services import prepare_project_workspace

User = get_user_model()


class FindingsWorkflowWorkspaceTests(TestCase):
    def setUp(self):
        self.university = University.objects.create(name="BYU")
        self.facility = Facility.objects.create(university=self.university, name="Proteomics Core", slug="proteomics")
        self.lab = Lab.objects.create(facility=self.facility, name="Lab A", slug="lab-a")
        self.user = User.objects.create_user(username="researcher", password="password123")
        UserProfile.objects.create(user=self.user, global_role=UserRole.RESEARCHER)
        LabMembership.objects.create(user=self.user, lab=self.lab, role=UserRole.RESEARCHER)
        self.project = Project.objects.create(lab=self.lab, title="Findings Project", code="FIND", pi=self.user)
        experiment = Experiment.objects.create(project=self.project, name="Discovery")
        sample = Sample.objects.create(experiment=experiment, name="Sample 1", metadata={"condition": "case"})
        run = Run.objects.create(sample=sample, run_name="Run 1", expected_filename="run1.raw")
        RawFile.objects.create(
            run=run,
            source_path="/network/vendor/run1.raw",
            storage_path="/network/msconnect/raw/run1.raw",
            filename="run1.raw",
            checksum_sha256="a" * 64,
            size_bytes=123,
            status=RawFileStatus.IMPORTED,
        )

    def test_prepare_workspace_exports_msconnect_manifests(self):
        with TemporaryDirectory() as temp_dir:
            summary = prepare_project_workspace(self.project, root=Path(temp_dir), created_by=self.user)
            workspace_path = Path(summary.workspace.workspace_path)

            self.assertTrue((workspace_path / "README.md").exists())
            self.assertTrue((workspace_path / "data" / "msconnect_project.json").exists())
            self.assertTrue((workspace_path / "data" / "samples.csv").exists())
            self.assertTrue((workspace_path / "data" / "runs.csv").exists())
            self.assertTrue((workspace_path / "data" / "raw_files.csv").exists())
            self.assertIn("run1.raw", (workspace_path / "data" / "raw_files.csv").read_text(encoding="utf-8"))
            self.assertEqual(summary.workspace.project, self.project)

    @override_settings(MSCONNECT_FINDINGS_WORKSPACE_ROOT="")
    def test_workspace_api_prepare_and_index(self):
        with TemporaryDirectory() as temp_dir:
            self.client.force_login(self.user)
            response = self.client.post(
                f"/api/capabilities/findings-workflow/projects/{self.project.id}/workspace/",
                {"root_path": temp_dir, "mode": "personal", "data_strategy": "manifest"},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 201)
            workspace = FindingsWorkspace.objects.get(project=self.project)
            reports = Path(workspace.workspace_path) / "reports"
            reports.mkdir(parents=True, exist_ok=True)
            (reports / "research-report.md").write_text("# Report\n", encoding="utf-8")

            response = self.client.post(f"/api/capabilities/findings-workflow/workspaces/{workspace.id}/index/")
            self.assertEqual(response.status_code, 200)
            workspace.refresh_from_db()
            self.assertEqual(workspace.reports_count, 1)
            self.assertTrue(workspace.latest_report_path.endswith("research-report.md"))
