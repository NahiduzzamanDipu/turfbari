"""Idempotent cleanup for expired demo records; audit activity is retained."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import DemoWorkspace


@transaction.atomic
def cleanup_expired_demo() -> dict[str, int]:
    now = timezone.now()
    stale_before = now - timedelta(days=30)
    expired = DemoWorkspace.objects.filter(status=DemoWorkspace.Status.ACTIVE, expires_at__lte=now).update(
        status=DemoWorkspace.Status.EXPIRED
    )
    removed = 0
    for workspace in DemoWorkspace.objects.filter(expires_at__lte=stale_before).iterator():
        removed += workspace.bookings.count() + workspace.customers.count() + workspace.slots.count()
        workspace.bookings.all().delete()
        workspace.customers.all().delete()
        workspace.slots.all().delete()
    return {"expired": expired, "records_removed": removed}
