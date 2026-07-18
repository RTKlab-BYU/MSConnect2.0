from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import (
    AcquisitionWorklist,
    Facility,
    Lab,
    LabMembership,
    Project,
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

    def test_intake_queue_redirects_to_rendered_login(self):
        login_response = self.client.get("/accounts/login/")
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "MSConnect Login")

    def test_legacy_ui_routes_redirect_to_react_routes(self):
        project = Project.objects.create(lab=self.lab, title="Migration Project", code="MIG", pi=self.pi)
        worklist = AcquisitionWorklist.objects.create(experiment=project.experiments.create(name="Exp 1"))

        redirects = (
            ("/ui/", "/app/projects"),
            ("/ui/projects", "/app/projects"),
            (f"/ui/projects/{project.id}", f"/app/projects/{project.id}"),
            ("/ui/projects/pre-acq", "/app/projects"),
            ("/ui/showcase", "/app/projects"),
            ("/ui/showcase/design", "/app/projects"),
            ("/ui/showcase/acquisition", "/app/monitoring"),
            ("/ui/showcase/results", "/app/projects"),
            ("/ui/showcase/processing", "/app/processing"),
            ("/ui/showcase/qc", "/app/qc"),
            (f"/ui/showcase/worklists/{worklist.id}", "/app/monitoring"),
            (f"/ui/showcase/worklists/{worklist.id}/processing", "/app/processing"),
            (f"/ui/showcase/worklists/{worklist.id}/qc", "/app/qc"),
            ("/ui/intake/new", "/app/projects"),
            ("/ui/intake", "/app/projects"),
            ("/ui/intake/1", "/app/projects"),
            ("/ui/intake/1/review", "/app/projects"),
        )
        for path, target in redirects:
            response = self.client.get(path)
            self.assertRedirects(response, target, status_code=301, fetch_redirect_response=False)
