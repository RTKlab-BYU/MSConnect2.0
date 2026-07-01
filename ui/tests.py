from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import (
    Facility,
    IntakeRequestStatus,
    Lab,
    LabMembership,
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
