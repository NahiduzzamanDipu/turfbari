"""Everything the container does before serving, in one Python process (see the root Dockerfile)."""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Apply migrations, ensure the cache table and the Super Admin exist."

    def handle(self, *args, **options):
        began = time.monotonic()
        call_command("migrate", interactive=False, verbosity=1)
        call_command("createcachetable")
        call_command("ensure_admin")
        self.stdout.write(f"Startup tasks finished in {time.monotonic() - began:.1f}s")
