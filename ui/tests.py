from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import (
    AcquisitionWorklist,
    Facility,
    IntakeRequestStatus,
    Lab,
    LabMembership,
    Project,
    ProjectIntakeRequest,
    University,
    UserProfile,
    UserRole,
)

User = get_user_model()


class UiIntakeIntegrationTests(TestCase):
    def setUp(self):
        self.university = University.objects.create(name="BYU")
        self.facility = Facility.objects.create(university=self.university, name="Proteomics Core", slug="proteomics")
        self.lab = Lab.objects.create(facility=self.facility, name="Lab A", slug="lab-a")

        self.pi = self._create_user("pi-user", UserRole.PI)
        self.researcher = self._create_user("researcher", UserRole.RESEARCHER)
        self.collaborator = self._create_user("collaborator", UserRole.COLLABORATOR)

        LabMembership.objects.create(user=self.pi, lab=self.lab, role=UserRole.PI)
        LabMembership.objects.create(user=self.researcher, lab=self.lab, role=UserRole.RESEARCHER)
        LabMembership.objects.create(user=self.collaborator, lab=self.lab, role=UserRole.COLLABORATOR)

    def _create_user(self, username, role):
        user = User.objects.create_user(username=username, password="password123")
        UserProfile.objects.create(user=user, global_role=role)
        return user

    def test_create_form_posts_successfully(self):
        self.client.force_login(self.researcher)
        response = self.client.post(
            "/ui/intake/new",
            data={
                "lab": self.lab.id,
                "requested_title": "UI Submitted Intake",
                "requested_code": "",
                "objective": "Placeholder UI submission",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProjectIntakeRequest.objects.filter(requested_title="UI Submitted Intake").exists())

    def test_intake_queue_redirects_to_rendered_login(self):
        response = self.client.get("/ui/intake")
        self.assertRedirects(response, "/accounts/login/?next=/ui/intake", fetch_redirect_response=False)

        login_response = self.client.get(response["Location"])
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "MSConnect Login")

    def test_review_actions_hidden_for_collaborator(self):
        intake = ProjectIntakeRequest.objects.create(
            lab=self.lab,
            requested_title="Needs review",
            submitted_by=self.researcher,
        )
        self.client.force_login(self.collaborator)
        response = self.client.get(f"/ui/intake/{intake.id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Review Actions")

    def test_queue_reflects_state_change(self):
        intake = ProjectIntakeRequest.objects.create(
            lab=self.lab,
            requested_title="Queue Item",
            submitted_by=self.researcher,
        )
        self.client.force_login(self.pi)
        self.client.post(
            f"/ui/intake/{intake.id}/review",
            data={"status": IntakeRequestStatus.IN_REVIEW, "review_note": "Investigating"},
        )

        queue_response = self.client.get("/ui/intake")
        self.assertEqual(queue_response.status_code, 200)
        self.assertContains(queue_response, "In Review")

    def test_seeded_showcase_pages_render(self):
        call_command("seed_demo_showcase", verbosity=0)
        demo_user = User.objects.get(username="parkerreyes")
        project = Project.objects.get(code="HYE-DIA-DEMO")
        worklist = AcquisitionWorklist.objects.get(name="Plate 1 DIA acquisition order")
        self.client.force_login(demo_user)

        pages = (
            "/ui/projects",
            f"/ui/projects/{project.id}",
            "/ui/showcase",
            "/ui/showcase/design",
            "/ui/showcase/acquisition",
            "/ui/showcase/results",
            "/ui/showcase/qc",
            f"/ui/showcase/worklists/{worklist.id}",
            f"/ui/showcase/worklists/{worklist.id}/processing",
            f"/ui/showcase/worklists/{worklist.id}/qc",
        )
        for path in pages:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

        project_response = self.client.get(f"/ui/projects/{project.id}")
        self.assertContains(project_response, "Sample Registry")
        self.assertContains(project_response, "Worklists and Raw File State")
        self.assertContains(project_response, "S06-Treated")

        response = self.client.get(f"/ui/showcase/worklists/{worklist.id}")
        self.assertContains(response, "Run File Order vs Uploaded Raw Files")
        self.assertContains(response, "HYE_DIA_DEMO_012_S06-Treated.raw")
        self.assertContains(response, "Missing upload")

        qc_response = self.client.get("/ui/showcase/qc")
        self.assertContains(qc_response, "Shared Proteins")
        self.assertContains(qc_response, "Homo sapiens")
        self.assertContains(qc_response, "Saccharomyces cerevisiae")
        self.assertContains(qc_response, "Escherichia coli")
