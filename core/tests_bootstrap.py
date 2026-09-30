from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import UserProfile, UserRole


class BootstrapSuperuserTests(TestCase):
    def test_creates_configured_superuser_and_admin_profile(self):
        output = StringIO()
        call_command(
            "bootstrap_superuser",
            username="first-admin",
            email="first-admin@example.test",
            password="A-long-enough-bootstrap-password-123!",
            stdout=output,
        )

        user = get_user_model().objects.get(username="first-admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("A-long-enough-bootstrap-password-123!"))
        self.assertEqual(user.profile.global_role, UserRole.ADMIN)
        self.assertIn("Created initial superuser", output.getvalue())

    def test_does_not_reset_existing_superuser_on_restart(self):
        user = get_user_model().objects.create_superuser(
            username="existing-admin",
            email="existing@example.test",
            password="Original-password-123!",
        )

        with patch.dict("os.environ", {"MSCONNECT_BOOTSTRAP_SUPERUSER_PASSWORD": "New-password-123!"}):
            call_command("bootstrap_superuser")

        user.refresh_from_db()
        self.assertTrue(user.check_password("Original-password-123!"))
        self.assertFalse(UserProfile.objects.filter(user__username="existing-admin").exists())
