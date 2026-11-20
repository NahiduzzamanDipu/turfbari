"""Booking write paths. Every create/reschedule goes through reserve_slot().

Overlap safety without exclusion constraints: inside one transaction we lock the TurfField row
(SELECT ... FOR UPDATE), which serialises all writers for that field in InnoDB, then check for
overlapping bookings and maintenance blocks before inserting.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.money import to_money
from apps.turfs.models import Turf, TurfField
from apps.turfs.pricing import quote
from apps.turfs.schedule import category_at, day_slots, opening_window, turf_categories, turf_rules  # noqa: F401

from .models import Booking, Customer, MaintenanceBlock, Payment
from .phone import normalize_bd_phone


class SlotUnavailable(ValidationError):
    default_code = "slot_unavailable"


def overlapping_bookings(field_id, start: datetime, end: datetime, exclude_id=None):
    qs = Booking.objects.blocking().filter(field_id=field_id, start__lt=end, end__gt=start)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs


def overlapping_maintenance(field_id, start: datetime, end: datetime):
    return MaintenanceBlock.objects.filter(field_id=field_id, start__lt=end, end__gt=start)


def get_or_create_customer(turf: Turf, *, name: str, phone: str, email: str = "") -> Customer:
    phone = normalize_bd_phone(phone)
    customer, created = Customer.objects.get_or_create(
        turf=turf, phone=phone, defaults={"name": name.strip(), "email": email or ""}
    )
    if not created:
        changed = []
        if name and customer.name != name.strip():
            customer.name = name.strip()
            changed.append("name")
        if email and customer.email != email:
            customer.email = email
            changed.append("email")
        if changed:
            customer.save(update_fields=[*changed, "updated_at"])
    return customer


def _validate_window(field: TurfField, start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValidationError({"end": ["End time must be after the start time."]})
    if end - start > timedelta(hours=12):
        raise ValidationError({"end": ["A single booking cannot be longer than 12 hours."]})
    for value in (start, end):
        local = timezone.localtime(value)
        if local.minute % 15 or local.second:
            raise ValidationError({"start": ["Bookings must start and end on 15-minute boundaries."]})
    if not field.is_active:
        raise ValidationError({"field": ["This field is not accepting bookings."]})


@transaction.atomic
def reserve_slot(
    *,
    turf: Turf,
    field_id,
    start: datetime,
    end: datetime,
    customer: Customer,
    status: str = Booking.Status.CONFIRMED,
    source: str = Booking.Source.STAFF,
    team_name: str = "",
    notes: str = "",
    discount: Decimal = Decimal("0"),
    created_by=None,
    booking: Booking | None = None,
) -> Booking:
    # Lock the field row: concurrent writers for this field queue here.
    try:
        field = TurfField.objects.select_for_update().get(pk=field_id, turf=turf)
    except (TurfField.DoesNotExist, ValueError):
        raise ValidationError({"field": ["Unknown field."]}) from None
    _validate_window(field, start, end)

    if overlapping_bookings(field.id, start, end, exclude_id=booking.pk if booking else None).exists():
        raise SlotUnavailable({"start": ["This time overlaps another booking on this field."]})
    if overlapping_maintenance(field.id, start, end).exists():
        raise SlotUnavailable({"start": ["This field is blocked for maintenance at that time."]})

    q = quote(field, start, end)
    discount = to_money(discount or 0)
    if discount < 0 or discount > q.subtotal:
        raise ValidationError({"discount": ["Discount must be between 0 and the price."]})

    if booking is None:
        booking = Booking(turf=turf, created_by=created_by, source=source, status=status)
        if status == Booking.Status.CONFIRMED:
            booking.confirmed_at = timezone.now()
    booking.field = field
    booking.customer = customer
    booking.start, booking.end = start, end
    booking.team_name, booking.notes = team_name, notes
    booking.subtotal, booking.discount = q.subtotal, discount
    booking.total = q.subtotal - discount
    booking.price_snapshot = q.as_snapshot()
    booking.save()
    return booking


ALLOWED_TRANSITIONS = {
    Booking.Status.PENDING: {Booking.Status.CONFIRMED, Booking.Status.REJECTED, Booking.Status.CANCELLED},
    Booking.Status.CONFIRMED: {Booking.Status.COMPLETED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW},
    Booking.Status.COMPLETED: set(),
    Booking.Status.CANCELLED: set(),
    Booking.Status.REJECTED: set(),
    Booking.Status.NO_SHOW: {Booking.Status.COMPLETED},
    Booking.Status.EXPIRED: set(),  # an expired online request can still be approved via verification
}


@transaction.atomic
def change_status(booking: Booking, new_status: str) -> Booking:
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if new_status not in ALLOWED_TRANSITIONS.get(booking.status, set()):
        raise ValidationError(
            {"status": [f"Cannot change a {booking.get_status_display().lower()} booking to {new_status}."]}
        )
    booking.status = new_status
    fields = ["status", "updated_at"]
    if new_status == Booking.Status.CONFIRMED:
        booking.confirmed_at = timezone.now()
        fields.append("confirmed_at")
    booking.save(update_fields=fields)
    return booking


@transaction.atomic
def record_payment(
    booking: Booking, *, amount, method: str, kind: str, reference: str = "", user=None
) -> Payment:
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    amount = to_money(amount)
    if amount <= 0:
        raise ValidationError({"amount": ["Amount must be greater than zero."]})
    if kind == Payment.Kind.REFUND and amount > booking.amount_paid:
        raise ValidationError({"amount": ["Refund cannot exceed the amount paid."]})
    payment = Payment.objects.create(
        turf=booking.turf,
        booking=booking,
        amount=amount,
        method=method,
        kind=kind,
        reference=reference,
        received_by=user,
    )
    sync_amount_paid(booking)
    return payment


def sync_amount_paid(booking: Booking) -> None:
    paid = booking.payments.filter(kind=Payment.Kind.PAYMENT).aggregate(s=Sum("amount"))["s"] or 0
    refunded = booking.payments.filter(kind=Payment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or 0
    booking.amount_paid = to_money(Decimal(paid) - Decimal(refunded))
    booking.save(update_fields=["amount_paid", "updated_at"])


# ------------------------------------------------------------------ availability
def availability(
    field: TurfField, day: date, *, include_price: bool = True, context: dict | None = None
) -> list[dict]:
    """The day's offered slots (custom templates or the automatic grid) with price and category."""
    cache: dict = {}
    slots_today = day_slots(field, day, cache=cache)
    if not slots_today:
        return []
    first, last = slots_today[0].start, max(s.end for s in slots_today)
    bookings = list(overlapping_bookings(field.id, first, last).values_list("start", "end", "status"))
    blocks = list(overlapping_maintenance(field.id, first, last).values_list("start", "end"))
    if context is not None:  # callers that also need these (public slot states) reuse them
        context.update(bookings=bookings, blocks=blocks, first=first, last=last)
    busy = [(s, e) for s, e, _ in bookings] + blocks
    rules = turf_rules(field.turf_id) if include_price else []
    categories = turf_categories(field.turf_id)
    now = timezone.now()
    result = []
    for s in slots_today:
        category = category_at(categories, timezone.localtime(s.start).time()) if categories else None
        free = s.start > now and not any(b < s.end and e > s.start for b, e in busy)
        slot = {
            "start": timezone.localtime(s.start).isoformat(),
            "end": timezone.localtime(s.end).isoformat(),
            "available": free,
            "category": category.key if category else None,
        }
        if include_price:
            slot["price"] = str(
                quote(field, s.start, s.end, rules, categories=categories, cache=cache, anchor=s).subtotal
            )
        result.append(slot)
    return result
