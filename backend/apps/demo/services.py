"""Shared permanent demo workspace services; all records remain demo-only."""

import secrets
from datetime import time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.bookings.phone import normalize_bd_phone

from .models import DemoActivity, DemoBooking, DemoCustomer, DemoSlot, DemoWorkspace

PUBLIC_DEMO_KEY = "public"


def mask_demo_phone(raw: str) -> str:
    """Validate a BD number but retain only a masked display value in the public demo."""
    normalized = normalize_bd_phone(raw)
    return f"{normalized[:5]}*****{normalized[-4:]}"


def seed_workspace(workspace: DemoWorkspace) -> None:
    slots = [
        ("Morning 08:00-09:00", time(8), time(9), DemoSlot.Category.MORNING, "1200.00"),
        ("Evening 17:00-18:00", time(17), time(18), DemoSlot.Category.EVENING, "1800.00"),
        ("Evening 18:00-19:00", time(18), time(19), DemoSlot.Category.EVENING, "1800.00"),
        ("Night 20:00-21:00", time(20), time(21), DemoSlot.Category.NIGHT, "1500.00"),
        ("Midnight 00:00-01:00", time(0), time(1), DemoSlot.Category.MIDNIGHT, "900.00"),
    ]
    for index, (label, start, end, category, price) in enumerate(slots):
        DemoSlot.objects.create(
            workspace=workspace,
            label=label,
            start_time=start,
            end_time=end,
            category=category,
            price=Decimal(price),
            display_order=index,
        )
    sample_slot = workspace.slots.get(start_time=time(18))
    customer = DemoCustomer.objects.create(
        workspace=workspace,
        name="Rahim Uddin (Demo)",
        phone=mask_demo_phone("01800000001"),
    )
    DemoBooking.objects.create(
        workspace=workspace,
        customer=customer,
        slot=sample_slot,
        date=timezone.localdate() + timedelta(days=1),
        start_time=sample_slot.start_time,
        end_time=sample_slot.end_time,
        price=sample_slot.price,
        reference=f"DEMO-{secrets.token_hex(4).upper()}",
        status=DemoBooking.Status.PENDING,
    )


@transaction.atomic
def get_public_workspace() -> DemoWorkspace:
    workspace, created = DemoWorkspace.objects.get_or_create(
        public_key=PUBLIC_DEMO_KEY,
        defaults={"name": "TURFBARI Demo Arena", "owner_name": "Demo Turf Owner"},
    )
    if created:
        seed_workspace(workspace)
    return workspace


@transaction.atomic
def reset_public_workspace(workspace: DemoWorkspace) -> int:
    workspace = DemoWorkspace.objects.select_for_update().get(pk=workspace.pk)
    workspace.bookings.all().delete()
    workspace.customers.all().delete()
    workspace.slots.all().delete()
    workspace.name = "TURFBARI Demo Arena"
    workspace.owner_name = "Demo Turf Owner"
    workspace.status = DemoWorkspace.Status.ACTIVE
    workspace.last_access_at = timezone.now()
    workspace.reset_count += 1
    workspace.save(
        update_fields=["name", "owner_name", "status", "last_access_at", "reset_count", "updated_at"]
    )
    seed_workspace(workspace)
    DemoActivity.objects.create(
        workspace=workspace,
        actor_type="admin",
        action="workspace_reset",
        summary="Admin manually restored the shared demo to its sample state.",
    )
    return workspace.reset_count
