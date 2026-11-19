"""Manual bKash payment verification for online bookings.

Flow: the customer picks a slot (10-minute selection hold), sends the advance by bKash "Send Money" to
the turf's number, then submits amount + sender number + transaction ID with the booking request.
The booking is created PENDING ("Awaiting verification") and keeps the slot until
`turf.payment_hold_minutes` pass. An owner (or a manager allowed to) checks the bKash account and
approves — recording a real Payment and confirming the booking — or rejects. Nothing is confirmed or
marked paid automatically. A hold that runs out frees the slot (status EXPIRED); confirmed bookings are
never touched by expiry.

All money rules are checked here on the server; nothing from the browser is trusted.
"""

import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.money import to_money

from .models import Booking, Payment, PaymentSubmission
from .phone import normalize_bd_phone
from .services import SlotUnavailable, overlapping_bookings, overlapping_maintenance, sync_amount_paid

log = logging.getLogger(__name__)

MIN_ADVANCE = Decimal("500.00")  # platform rule: at least ৳500 (or the full price if it's less)
TRX_ID = re.compile(r"^[A-Z0-9]{8,12}$")
ACCEPTED_MESSAGE_BN = (
    "আপনার বুকিং অনুরোধ গ্রহণ করা হয়েছে। টার্ফ কর্তৃপক্ষ আপনার পেমেন্ট যাচাই করে SMS-এর মাধ্যমে বুকিং কনফার্মেশন জানিয়ে দেবে।"
)


def required_advance(turf, total: Decimal) -> Decimal:
    """The least a customer must send: the turf's advance (never under ৳500), capped at the price."""
    wanted = max(to_money(turf.advance_amount or 0), MIN_ADVANCE)
    return min(to_money(total), wanted)


def normalize_trx_id(value: str) -> str:
    trx = re.sub(r"\s", "", value or "").upper()
    if not TRX_ID.match(trx):
        raise ValidationError(
            {"trx_id": ["Enter the bKash Transaction ID exactly as in the bKash SMS (e.g. 9C7A6B5D4E)."]}
        )
    return trx


def validate_payment(turf, *, total: Decimal, amount, sender_number: str, trx_id: str) -> dict:
    amount = to_money(amount)
    need = required_advance(turf, total)
    errors = {}
    if amount < need:
        errors["payment_amount"] = [f"Send at least ৳{need:,.0f} as the advance."]
    elif amount > to_money(total):
        errors["payment_amount"] = [f"The full price is ৳{total:,.0f}; don't send more than that."]
    try:
        sender = "0" + normalize_bd_phone(sender_number)[4:]  # 01XXXXXXXXX, as the bKash app shows it
    except ValidationError:
        errors["bkash_sender"] = ["Enter the bKash number you paid from, e.g. 01712345678."]
        sender = ""
    try:
        trx = normalize_trx_id(trx_id)
    except ValidationError as exc:
        errors.update(exc.detail)
        trx = ""
    if trx and PaymentSubmission.objects.filter(turf=turf, trx_id=trx).exists():
        errors["trx_id"] = ["This Transaction ID was already used for another booking."]
    if errors:
        raise ValidationError(errors)
    return {"amount": amount, "sender_number": sender, "trx_id": trx}


def attach_submission(booking: Booking, payment: dict) -> PaymentSubmission:
    """Called inside the booking-request transaction, right after reserve_slot()."""
    booking.hold_expires_at = timezone.now() + timedelta(minutes=booking.turf.payment_hold_minutes or 60)
    booking.save(update_fields=["hold_expires_at", "updated_at"])
    try:
        with transaction.atomic():
            return PaymentSubmission.objects.create(turf=booking.turf, booking=booking, **payment)
    except IntegrityError:
        raise ValidationError(
            {"trx_id": ["This Transaction ID was already used for another booking."]}
        ) from None


def _sms(booking: Booking, kind: str, **extra) -> None:
    from apps.notifications.services import queue_sms, render, turf_sms_settings

    turf = booking.turf
    if not turf_sms_settings(turf).get(kind, False):
        return
    start, end = timezone.localtime(booking.start), timezone.localtime(booking.end)
    body = render(
        kind,
        turf=turf.name,
        date=f"{start:%d/%m/%Y}",
        time=f"{start:%I:%M %p}–{end:%I:%M %p}".replace(" 0", " ").lstrip("0"),
        reference=booking.reference,
        phone=turf.public_phone or turf.owner_phone,
        name=booking.customer.name,
        **extra,
    )
    queue_sms(
        to=booking.customer.phone,
        body=body,
        kind=kind,
        turf=turf,
        booking=booking,
        dedupe_key=f"booking:{booking.pk}:{kind}",
    )


@transaction.atomic
def approve(submission: PaymentSubmission, *, user) -> Booking:
    from apps.turfs.models import TurfField

    submission = (
        PaymentSubmission.objects.select_for_update().select_related("booking", "turf").get(pk=submission.pk)
    )
    booking = (
        Booking.objects.select_for_update()
        .select_related("customer", "field", "turf")
        .get(pk=submission.booking_id)
    )
    if submission.status not in (
        PaymentSubmission.Status.PENDING,
        PaymentSubmission.Status.EXPIRED,
    ) or booking.status not in (
        Booking.Status.PENDING,
        Booking.Status.EXPIRED,
    ):
        raise ValidationError(
            {"status": [f"This payment was already {submission.get_status_display().lower()}."]}
        )
    # Same field lock as every booking write: nobody can take the slot while we confirm.
    TurfField.objects.select_for_update().get(pk=booking.field_id)
    if overlapping_bookings(booking.field_id, booking.start, booking.end, exclude_id=booking.pk).exists():
        raise SlotUnavailable(
            {"start": ["Another booking now holds this slot. Reject this payment and refund the customer."]}
        )
    if overlapping_maintenance(booking.field_id, booking.start, booking.end).exists():
        raise SlotUnavailable({"start": ["This slot is blocked for maintenance now."]})
    if booking.start <= timezone.now():
        raise ValidationError({"start": ["This slot has already started; it can't be confirmed now."]})

    now = timezone.now()
    booking.status, booking.confirmed_at, booking.hold_expires_at = Booking.Status.CONFIRMED, now, None
    booking.save(update_fields=["status", "confirmed_at", "hold_expires_at", "updated_at"])
    Payment.objects.create(
        turf=booking.turf,
        booking=booking,
        amount=submission.amount,
        method=Payment.Method.BKASH,
        kind=Payment.Kind.PAYMENT,
        reference=f"bKash {submission.trx_id} from {submission.sender_number}",
        received_by=user,
    )
    sync_amount_paid(booking)
    submission.status, submission.reviewed_by, submission.reviewed_at = (
        PaymentSubmission.Status.APPROVED,
        user,
        now,
    )
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    _sms(booking, "booking_confirmed")
    return booking


@transaction.atomic
def reject(submission: PaymentSubmission, *, user, reason: str = "") -> Booking:
    submission = PaymentSubmission.objects.select_for_update().get(pk=submission.pk)
    booking = (
        Booking.objects.select_for_update().select_related("customer", "turf").get(pk=submission.booking_id)
    )
    if submission.status not in (
        PaymentSubmission.Status.PENDING,
        PaymentSubmission.Status.EXPIRED,
    ) or booking.status not in (
        Booking.Status.PENDING,
        Booking.Status.EXPIRED,
    ):
        raise ValidationError(
            {"status": [f"This payment was already {submission.get_status_display().lower()}."]}
        )
    now = timezone.now()
    booking.status, booking.hold_expires_at = Booking.Status.REJECTED, None
    booking.save(update_fields=["status", "hold_expires_at", "updated_at"])
    submission.status, submission.reviewed_by, submission.reviewed_at = (
        PaymentSubmission.Status.REJECTED,
        user,
        now,
    )
    submission.rejection_reason = reason.strip()[:200]
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
    _sms(
        booking,
        "payment_rejected",
        reason=f" কারণ: {submission.rejection_reason}।" if submission.rejection_reason else "",
    )
    return booking


def expire_lapsed(now=None) -> dict:
    """Tick step: PENDING online bookings whose hold ran out become EXPIRED (slot freed)."""
    now = now or timezone.now()
    ids = list(
        Booking.objects.filter(status=Booking.Status.PENDING, hold_expires_at__lte=now).values_list(
            "pk", flat=True
        )[:500]
    )
    expired = 0
    for pk in ids:
        with transaction.atomic():
            booking = (
                Booking.objects.select_for_update()
                .filter(pk=pk, status=Booking.Status.PENDING, hold_expires_at__lte=now)
                .first()
            )
            if booking is None:
                continue  # approved/rejected meanwhile
            booking.status = Booking.Status.EXPIRED
            booking.save(update_fields=["status", "updated_at"])
            PaymentSubmission.objects.filter(booking=booking, status=PaymentSubmission.Status.PENDING).update(
                status=PaymentSubmission.Status.EXPIRED, updated_at=now
            )
            expired += 1
    return {"expired_holds": expired}


def booking_reminders(now=None) -> dict:
    """Tick step: SMS customers N hours before a confirmed booking (turfs that switched it on)."""
    from apps.notifications.services import turf_sms_settings

    now = now or timezone.now()
    queued = 0
    candidates = (
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED, start__gt=now, start__lte=now + timedelta(hours=24)
        )
        .exclude(sms_messages__kind="booking_reminder")
        .select_related("turf", "customer")
    )
    for booking in candidates:
        settings_ = turf_sms_settings(booking.turf)
        if not settings_["booking_reminder"]:
            continue
        if booking.start - now > timedelta(hours=int(settings_["reminder_hours"])):
            continue
        if booking.confirmed_at and booking.start - booking.confirmed_at < timedelta(hours=1):
            continue  # booked at the last minute: they already know
        _sms(booking, "booking_reminder")
        queued += 1
    return {"booking_reminders": queued}


def notify_cancelled(booking: Booking, previous_status: str) -> None:
    if previous_status == Booking.Status.CONFIRMED and booking.status == Booking.Status.CANCELLED:
        _sms(booking, "booking_cancelled")
