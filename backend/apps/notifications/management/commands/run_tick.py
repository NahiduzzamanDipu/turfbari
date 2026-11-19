import json

from django.core.management.base import BaseCommand

from apps.notifications.tick import run_tick


class Command(BaseCommand):
    help = "Run the periodic tick once: SMS retries, hold expiry, reminders."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(run_tick(), default=str))
