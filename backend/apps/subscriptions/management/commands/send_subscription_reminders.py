"""Send plan-expiry reminder emails now (the same job Celery beat runs daily). Safe to run repeatedly."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.subscriptions.reminders import send_expiry_reminders


class Command(BaseCommand):
    help = "Email turf owners whose plan ends in 10, 7, 3 or 1 days."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="on", help="Pretend today is YYYY-MM-DD (for testing).")

    def handle(self, *args, on=None, **options):
        try:
            today = date.fromisoformat(on) if on else None
        except ValueError:
            raise CommandError("Use --date YYYY-MM-DD") from None
        counts = send_expiry_reminders(today)
        self.stdout.write(self.style.SUCCESS(", ".join(f"{k}: {v}" for k, v in counts.items())))
