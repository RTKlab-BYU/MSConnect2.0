"""Create the one-time installation administrator for a new database."""

import os
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError

from core.models import UserProfile, UserRole


class Command(BaseCommand):
    help = "Create the initial superuser without changing an existing account."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("MSCONNECT_BOOTSTRAP_SUPERUSER_USERNAME", "admin"))
        parser.add_argument("--email", default=os.environ.get("MSCONNECT_BOOTSTRAP_SUPERUSER_EMAIL", ""))
        parser.add_argument("--password", default=os.environ.get("MSCONNECT_BOOTSTRAP_SUPERUSER_PASSWORD"))

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"].strip()
        email = options["email"].strip().lower()
        if not username:
            raise CommandError("MSCONNECT_BOOTSTRAP_SUPERUSER_USERNAME cannot be empty.")

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("A superuser already exists; bootstrap skipped.")
            return

        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f"A non-superuser account already uses username '{username}'.")

        password = options["password"] or self._generate_password()
        try:
            validate_password(password, user=User(username=username, email=email))
        except Exception as exc:
            raise CommandError(f"Bootstrap superuser password is invalid: {exc}") from exc

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
        UserProfile.objects.update_or_create(user=user, defaults={"global_role": UserRole.ADMIN})

        self.stdout.write(self.style.SUCCESS(f"Created initial superuser '{username}'."))
        if not options["password"]:
            self.stdout.write(self.style.WARNING("No bootstrap password was configured."))
            self.stdout.write(f"Generated one-time password: {password}")
            self.stdout.write("Set MSCONNECT_BOOTSTRAP_SUPERUSER_PASSWORD before a fresh install to choose it.")

    @staticmethod
    def _generate_password():
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        return "".join(secrets.choice(alphabet) for _ in range(32))
