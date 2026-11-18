"""Create the first Super Admin on hosts without a shell (e.g. Render's free plan).

Runs on every start and does nothing once any Super Admin exists. The first time, it creates one
with a random temporary password and prints it to the deploy log; change it after signing in.
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a Super Admin with a temporary password if none exists yet."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@turfbari.com")

    def handle(self, *args, email, **options):
        User = get_user_model()
        if User.objects.filter(is_platform_admin=True).exists():
            self.stdout.write("Super Admin already exists; nothing to do.")
            return
        password = secrets.token_urlsafe(12)
        User.objects.create_superuser(email, password, full_name="TurfBari Admin")
        self.stdout.write(
            self.style.WARNING(
                f"Created Super Admin {email} with temporary password: {password}  "
                "(sign in and change it now; this is shown only once)"
            )
        )
