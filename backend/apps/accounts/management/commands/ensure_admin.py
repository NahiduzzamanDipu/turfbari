"""Create (or re-address) the Super Admin on hosts without a shell (e.g. Render's free plan).

Runs on every start:
- no Super Admin yet: create one with a random temporary password printed once to the deploy log;
- TURFBARI_ADMIN_EMAIL set and the only Super Admin has a different email: change it to that address
  (sign-in codes are emailed there). The password is not touched.
"""

import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a Super Admin with a temporary password if none exists, or apply TURFBARI_ADMIN_EMAIL."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=os.environ.get("TURFBARI_ADMIN_EMAIL") or "")

    def handle(self, *args, email, **options):
        User = get_user_model()
        email = email.strip().lower()
        admins = list(User.objects.filter(is_platform_admin=True))
        if not admins:
            email = email or "admin@turfbari.com"
            password = secrets.token_urlsafe(12)
            User.objects.create_superuser(email, password, full_name="TurfBari Admin")
            self.stdout.write(
                self.style.WARNING(
                    f"Created Super Admin {email} with temporary password: {password}  "
                    "(sign in and change it now; this is shown only once)"
                )
            )
            return
        if os.environ.get("TURFBARI_ADMIN_RESET_PASSWORD", "").lower() in {"1", "true", "yes"} and len(admins) == 1:
            # Break-glass: new temporary password + clear login lockouts. Remove the env var afterwards,
            # or every restart resets the password again.
            from axes.utils import reset as reset_lockouts

            password = secrets.token_urlsafe(12)
            admins[0].set_password(password)
            admins[0].save(update_fields=["password"])
            reset_lockouts(username=admins[0].email)
            self.stdout.write(
                self.style.WARNING(
                    f"Reset Super Admin {admins[0].email} password. New temporary password: {password}  "
                    "(remove TURFBARI_ADMIN_RESET_PASSWORD now, then sign in and change it)"
                )
            )
        if email and len(admins) == 1 and admins[0].email != email:
            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.ERROR(f"Can't move the Super Admin to {email}: it's taken."))
                return
            old = admins[0].email
            admins[0].email = email
            admins[0].save(update_fields=["email"])
            self.stdout.write(self.style.SUCCESS(f"Super Admin email changed from {old} to {email}."))
            return
        self.stdout.write("Super Admin already exists; nothing to do.")
