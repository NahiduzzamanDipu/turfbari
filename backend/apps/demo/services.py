"""Operations for the isolated shared product demo."""

import hashlib
import logging
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, dumps, loads
from django.db import transaction
from django.utils import timezone

from apps.bookings.phone import normalize_bd_phone

from .models import DemoActivity, DemoBooking, DemoCustomer, DemoHold, DemoSlot, DemoSms, DemoWorkspace

log = logging.getLogger(__name__)
PUBLIC_DEMO_KEY = "public"
DEMO_FIELD_ID = "demo-field"
DEMO_HOLD_MINUTES = 10
DEMO_OWNER_COOKIE = "turfbari_demo_owner"
DEMO_OWNER_TTL = 60 * 30
DHAKA = ZoneInfo("Asia/Dhaka")


def mask_demo_phone(raw: str) -> str:
    """Validate a Bangladesh number and retain only a short masked display form."""
    normalized = normalize_bd_phone(raw)
    return f"{normalized[:5]}*****{normalized[-4:]}"


def fingerprint_phone(raw: str) -> str:
    normalized = normalize_bd_phone(raw)
    return hashlib.sha256(f"{settings.SECRET_KEY}:demo-phone:{normalized}".encode()).hexdigest()


def demo_datetime(day, at: time) -> datetime:
    return timezone.make_aware(datetime.combine(day, at), DHAKA)


def issue_owner_session(workspace: DemoWorkspace) -> str:
    return dumps({"workspace": str(workspace.pk), "reset_count": workspace.reset_count}, salt="demo-owner")


def owner_session_valid(raw: str | None, workspace: DemoWorkspace) -> bool:
    if not raw:
        return False
    try:
        payload = loads(raw, salt="demo-owner", max_age=DEMO_OWNER_TTL)
    except (BadSignature, SignatureExpired):
        return False
    return payload == {"workspace": str(workspace.pk), "reset_count": workspace.reset_count}


def seed_workspace(workspace: DemoWorkspace) -> None:
    slots = [
        ("Morning 08:00–09:00", time(8), time(9), DemoSlot.Category.MORNING, "1200.00"),
        ("Evening 17:00–18:00", time(17), time(18), DemoSlot.Category.EVENING, "1800.00"),
        ("Evening 18:00–19:00", time(18), time(19), DemoSlot.Category.EVENING, "1800.00"),
        ("Night 20:00–21:00", time(20), time(21), DemoSlot.Category.NIGHT, "1500.00"),
        ("Midnight 00:00–01:00", time(0), time(1), DemoSlot.Category.MIDNIGHT, "900.00"),
    ]
    created_slots = []
    for index, (label, start, end, category, price) in enumerate(slots):
        created_slots.append(
            DemoSlot.objects.create(
                workspace=workspace,
                label=label,
                start_time=start,
                end_time=end,
                category=category,
                price=Decimal(price),
                display_order=index,
            )
        )

    today = timezone.localdate()
    samples = [
        (created_slots[1], 1, DemoBooking.Status.PENDING, DemoBooking.PaymentStatus.PENDING, "Rahim Uddin"),
        (
            created_slots[2],
            2,
            DemoBooking.Status.CONFIRMED,
            DemoBooking.PaymentStatus.APPROVED,
            "Sabbir Hossain",
        ),
        (
            created_slots[3],
            3,
            DemoBooking.Status.REJECTED,
            DemoBooking.PaymentStatus.REJECTED,
            "Nusrat Jahan",
        ),
    ]
    for slot, offset, status, payment_status, name in samples:
        customer = DemoCustomer.objects.create(
            workspace=workspace,
            name=f"{name} (Demo)",
            phone=mask_demo_phone("01700000000"),
            phone_fingerprint=fingerprint_phone("01700000000"),
        )
        booking = DemoBooking.objects.create(
            workspace=workspace,
            customer=customer,
            slot=slot,
            date=today + timedelta(days=offset),
            start_time=slot.start_time,
            end_time=slot.end_time,
            price=slot.price,
            payment_amount=min(slot.price, Decimal("500.00")),
            sender_phone=mask_demo_phone("01800000000"),
            transaction_reference=f"DEMO-{secrets.token_hex(4).upper()}",
            payment_status=payment_status,
            hold_expires_at=(timezone.now() + timedelta(minutes=10))
            if status == DemoBooking.Status.PENDING
            else None,
            reference=f"DEMO-{secrets.token_hex(4).upper()}",
            status=status,
            reviewed_at=timezone.now() if status != DemoBooking.Status.PENDING else None,
            confirmed_at=timezone.now() if status == DemoBooking.Status.CONFIRMED else None,
            reviewed_by="Demo Owner" if status != DemoBooking.Status.PENDING else "",
        )
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="sample",
            action=f"booking_{status}",
            summary=f"Sample demo booking {booking.reference} is {status}.",
        )
        DemoSms.objects.create(
            workspace=workspace,
            booking=booking,
            kind=(
                DemoSms.Kind.BOOKING_APPROVED
                if status == DemoBooking.Status.CONFIRMED
                else DemoSms.Kind.BOOKING_REQUEST
            ),
            recipient=customer.phone,
            body=f"DEMO ONLY: Sample message for booking {booking.reference}. No SMS was sent.",
        )


@transaction.atomic
def get_public_workspace() -> DemoWorkspace:
    workspace, created = DemoWorkspace.objects.get_or_create(
        public_key=PUBLIC_DEMO_KEY,
        defaults={
            "name": "TURFBARI Demo Arena",
            "owner_name": "Demo Turf Owner",
            "last_reset_at": timezone.now(),
        },
    )
    if created:
        seed_workspace(workspace)
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="system",
            action="workspace_seeded",
            summary="The demo baseline was created.",
        )
    return workspace


@transaction.atomic
def reset_public_workspace(workspace: DemoWorkspace, *, actor_type: str = "admin") -> int:
    workspace = DemoWorkspace.objects.select_for_update().get(pk=workspace.pk)
    log.info("Starting demo reset workspace=%s reset_count=%s", workspace.pk, workspace.reset_count)
    DemoHold.objects.filter(workspace=workspace).delete()
    workspace.sms_messages.all().delete()
    workspace.bookings.all().delete()
    workspace.customers.all().delete()
    workspace.slots.all().delete()
    workspace.activity.all().delete()
    workspace.name = "TURFBARI Demo Arena"
    workspace.owner_name = "Demo Turf Owner"
    workspace.last_reset_at = timezone.now()
    workspace.reset_count += 1
    workspace.save(update_fields=["name", "owner_name", "last_reset_at", "reset_count", "updated_at"])
    seed_workspace(workspace)
    DemoActivity.objects.create(
        workspace=workspace,
        actor_type=actor_type,
        action="workspace_reset",
        summary="The demo was restored to its baseline. Demo sessions from before this reset expired.",
    )
    log.info("Completed demo reset workspace=%s reset_count=%s", workspace.pk, workspace.reset_count)
    return workspace.reset_count


def reset_demo_if_due(now=None) -> dict:
    """Called by the system tick; resets only the dedicated public demo every ten minutes."""
    now = now or timezone.now()
    with transaction.atomic():
        workspace = DemoWorkspace.objects.select_for_update().filter(public_key=PUBLIC_DEMO_KEY).first()
        if workspace is None:
            return {"status": "not_initialized"}
        if workspace.status != DemoWorkspace.Status.ACTIVE:
            return {"status": "disabled"}
        if workspace.last_reset_at is None:
            workspace.last_reset_at = now
            workspace.save(update_fields=["last_reset_at", "updated_at"])
            return {"status": "initialized", "reset_count": workspace.reset_count}
        if now - workspace.last_reset_at < timedelta(minutes=10):
            return {"status": "not_due", "reset_count": workspace.reset_count}
        reset_count = reset_public_workspace(workspace, actor_type="scheduler")
        return {"status": "reset", "reset_count": reset_count}
