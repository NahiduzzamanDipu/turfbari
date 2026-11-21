from django.core.management.base import BaseCommand

from apps.demo.services import cleanup_expired_demo


class Command(BaseCommand):
    help = "Expire demo access and remove stale demo bookings, customers, and slots only."

    def handle(self, *args, **options):
        result = cleanup_expired_demo()
        summary = (
            f"Expired {result['expired']} workspaces; removed {result['records_removed']} stale demo records."
        )
        self.stdout.write(self.style.SUCCESS(summary))
