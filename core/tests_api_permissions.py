from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Facility,
    Lab,
    LabMembership,
    Project,
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
