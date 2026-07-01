from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
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


class ProjectIntakeModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="submitter", password="password123")
        self.pi_user = User.objects.create_user(username="pi-user", password="password123")
        UserProfile.objects.create(user=self.user, global_role=UserRole.RESEARCHER)
        UserProfile.objects.create(user=self.pi_user, global_role=UserRole.PI)

        self.university = University.objects.create(name="BYU")
        self.facility = Facility.objects.create(university=self.university, name="Proteomics Core", slug="proteomics")
        self.lab = Lab.objects.create(facility=self.facility, name="Lab A", slug="lab-a", pi=self.pi_user)

    def test_valid_transitions(self):
        intake = ProjectIntakeRequest.objects.create(
            lab=self.lab,
            requested_title="Trial Study",
            submitted_by=self.user,
        )

        intake.transition_to(new_status=IntakeRequestStatus.IN_REVIEW, reviewer=self.pi_user, note="Opened")
        intake.refresh_from_db()
        self.assertEqual(intake.status, IntakeRequestStatus.IN_REVIEW)

        intake.transition_to(new_status=IntakeRequestStatus.APPROVED, reviewer=self.pi_user, note="Good to go")
        intake.refresh_from_db()
        self.assertEqual(intake.status, IntakeRequestStatus.APPROVED)

    def test_invalid_transition_rejected(self):
        intake = ProjectIntakeRequest.objects.create(
            lab=self.lab,
            requested_title="Trial Study",
            submitted_by=self.user,
        )

        with self.assertRaises(ValidationError):
            intake.transition_to(new_status=IntakeRequestStatus.APPROVED, reviewer=self.pi_user)

    def test_promotion_is_idempotent_and_creates_single_project(self):
        intake = ProjectIntakeRequest.objects.create(
            lab=self.lab,
            requested_title="Trial Study",
            requested_code="TRIAL-01",
            submitted_by=self.user,
            status=IntakeRequestStatus.APPROVED,
            reviewed_by=self.pi_user,
        )

        first_project = intake.promote_to_project()
        second_project = intake.promote_to_project()

        self.assertEqual(first_project.id, second_project.id)
        intake.refresh_from_db()
        self.assertEqual(intake.promoted_project_id, first_project.id)
        self.assertEqual(Project.objects.filter(source_intake_request=intake).count(), 1)


class IntakeApiTests(TestCase):
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

        self.intake = ProjectIntakeRequest.objects.create(
            lab=self.lab_a,
            requested_title="Initial Intake",
            submitted_by=self.researcher,
        )

    def _create_user(self, username, role):
        user = User.objects.create_user(username=username, password="password123")
        UserProfile.objects.create(user=user, global_role=role)
        return user

    def test_collaborator_can_submit_intake_for_member_lab(self):
        self.client.force_authenticate(user=self.collaborator)
        response = self.client.post(
            "/api/intake-requests/",
            data={
                "lab": self.lab_a.id,
                "requested_title": "Collab Intake",
                "requested_code": "",
                "objective": "Explore pilot cohort",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_collaborator_cannot_submit_cross_lab(self):
        self.client.force_authenticate(user=self.collaborator)
        response = self.client.post(
            "/api/intake-requests/",
            data={
                "lab": self.lab_b.id,
                "requested_title": "Cross Lab",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_researcher_cannot_review_intake(self):
        self.client.force_authenticate(user=self.researcher)
        response = self.client.post(
            f"/api/intake-requests/{self.intake.id}/review/",
            data={"status": IntakeRequestStatus.IN_REVIEW},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_pi_can_review_and_promote(self):
        self.client.force_authenticate(user=self.pi_user)

        review_response = self.client.post(
            f"/api/intake-requests/{self.intake.id}/review/",
            data={"status": IntakeRequestStatus.IN_REVIEW, "review_note": "Checking requirements"},
            format="json",
        )
        self.assertEqual(review_response.status_code, 200)

        approval_response = self.client.post(
            f"/api/intake-requests/{self.intake.id}/review/",
            data={"status": IntakeRequestStatus.APPROVED, "review_note": "Approved"},
            format="json",
        )
        self.assertEqual(approval_response.status_code, 200)

        promote_response = self.client.post(
            f"/api/intake-requests/{self.intake.id}/promote/",
            data={},
            format="json",
        )
        self.assertEqual(promote_response.status_code, 200)
        self.assertIn("project_id", promote_response.data)

    def test_queue_filters_by_status_and_lab_scope(self):
        ProjectIntakeRequest.objects.create(
            lab=self.lab_a,
            requested_title="Approved Intake",
            submitted_by=self.researcher,
            status=IntakeRequestStatus.APPROVED,
        )
        ProjectIntakeRequest.objects.create(
            lab=self.lab_b,
            requested_title="External Intake",
            submitted_by=self.external,
            status=IntakeRequestStatus.APPROVED,
        )

        self.client.force_authenticate(user=self.researcher)
        response = self.client.get("/api/intake-requests/?status=approved")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["requested_title"], "Approved Intake")

    def test_promote_endpoint_is_idempotent(self):
        self.client.force_authenticate(user=self.pi_user)
        self.intake.transition_to(new_status=IntakeRequestStatus.IN_REVIEW, reviewer=self.pi_user)
        self.intake.transition_to(new_status=IntakeRequestStatus.APPROVED, reviewer=self.pi_user)

        first = self.client.post(f"/api/intake-requests/{self.intake.id}/promote/", data={}, format="json")
        second = self.client.post(f"/api/intake-requests/{self.intake.id}/promote/", data={}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["project_id"], second.data["project_id"])
