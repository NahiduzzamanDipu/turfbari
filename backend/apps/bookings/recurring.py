# ruff: noqa: E501
"""Advance & recurring bookings made by the turf (owner, or a manager with the "advance_bookings" switch).

A BookingSeries is the plan; every date is an ordinary Booking (series + occurrence_number), so the
calendar, payments, reports, reminders and the public availability see each date like any booking.

- `generate_dates` turns the recurrence into concrete Bangladesh-calendar dates (never assumes every day).
- `evaluate` checks every date in a few bulk queries: past/horizon, opening hours or custom slots,
  maintenance blocks, overlapping bookings and live holds/pending requests, and the per-customer daily
  limit (Asia/Dhaka days, all turfs) — and prices each date with the normal pricing engine.
- `create_series` repeats all of that inside one transaction holding the field and customer locks, so
  the preview is only advisory. Unavailable dates must be excluded explicitly; nothing is skipped quietly.
- "Confirm now" makes confirmed bookings; "Awaiting payment" makes pending ones with a hold that expires
  (the existing expiry tick frees them) and they're confirmed only by recording the advance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import Category, record
from apps.common.models import CustomerLock, PlatformSettings
from apps.common.money import to_money
from apps.turfs import schedule
from apps.turfs.models import TurfField
from apps.turfs.pricing import quote

from . import payments
from .models import Booking, BookingSeries, MaintenanceBlock, Payment, new_reference
from .phone import normalize_bd_phone
from .services import get_or_create_customer, record_payment

LIVE = (Booking.Status.PENDING, Booking.Status.CONFIRMED)
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REASONS = {
    "past": "This time has already passed",
    "closed": "The turf is closed at this time",
    "not_offered": "Not one of the turf's listed slots",
    "maintenance": "Blocked for maintenance",
    "booked": "Already booked",
    "held": "Someone is booking it right now / awaiting payment",
    "limit": "Customer's daily booking limit reached",
    "same_series": "Already part of this series",
}


def policy():
    return PlatformSettings.load()


# ------------------------------------------------------------------ dates
def window(day: date, start_time: time, end_time: time) -> tuple[datetime, datetime]:
    """Local start/end for one date; an end at or before the start means it ends the next day."""
    start = schedule.local_dt(day, start_time)
    end_day = day + timedelta(days=1) if end_time <= start_time else day
    return start, schedule.local_dt(end_day, end_time)


def generate_dates(
    recurrence: str, start_date: date, end_date: date, weekdays: list[int] | None = None, custom_dates=None
) -> list[date]:
    weekdays = sorted({int(w) for w in (weekdays or []) if 0 <= int(w) <= 6})
    R = BookingSeries.Recurrence
    if recurrence == R.ONCE:
        return [start_date]
    if recurrence == R.CUSTOM:
        days = sorted({d for d in (custom_dates or [])})
        if not days:
            raise ValidationError({"custom_dates": ["Pick at least one date."]})
        return days
    if end_date < start_date:
        raise ValidationError({"end_date": ["The end date must be on or after the start date."]})
    if recurrence == R.DAILY:
        wanted = set(range(7))
    elif recurrence == R.WEEKDAYS:
        if not weekdays:
            raise ValidationError({"weekdays": ["Choose at least one day of the week."]})
        wanted = set(weekdays)
    elif recurrence == R.WEEKLY:
        wanted = {weekdays[0] if weekdays else start_date.weekday()}
    else:
        raise ValidationError({"recurrence": ["Unknown repeat option."]})
    out, d = [], start_date
    while d <= end_date:
        if d.weekday() in wanted:
            out.append(d)
        d += timedelta(days=1)
    return out


def check_horizon(dates: list[date]) -> None:
    p = policy()
    if not dates:
        raise ValidationError({"start_date": ["These options don't produce any booking dates."]})
    today = timezone.localdate()
    if dates[0] < today:
        raise ValidationError({"start_date": ["Dates can't be in the past."]})
    if dates[-1] > today + timedelta(days=p.recurring_max_days):
        raise ValidationError(
            {"end_date": [f"Advance bookings can be made up to {p.recurring_max_days} days ahead."]}
        )
    if len(dates) > p.recurring_max_occurrences:
        raise ValidationError(
            {"end_date": [f"At most {p.recurring_max_occurrences} dates in one series — shorten the period."]}
        )


# ------------------------------------------------------------------ checking & pricing
@dataclass
class Row:
    day: date
    start: datetime
    end: datetime
    available: bool = True
    reason: str = ""
    detail: str = ""
    price: Decimal = Decimal("0.00")
    snapshot: dict = dc_field(default_factory=dict)
    slots: int = 1

    def as_dict(self) -> dict:
        return {
            "date": self.day.isoformat(),
            "weekday": WEEKDAY_NAMES[self.day.weekday()],
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "available": self.available,
            "reason": self.reason,
            "reason_label": REASONS.get(self.reason, ""),
            "detail": self.detail,
            "price": str(self.price),
            "slots": self.slots,
        }


def _offered(turf, field: TurfField, start: datetime, end: datetime) -> str:
    """'' if staff may book [start, end) by the turf's hours / custom slots, else a reason code."""
    day = timezone.localtime(start).date()
    if schedule.uses_templates(field, day) or schedule.uses_templates(field, day - timedelta(days=1)):
        return "" if schedule.is_offered_range(field, start, end) else "not_offered"
    for d in (day, day - timedelta(days=1)):  # overnight opening windows belong to the day before
        w = schedule.opening_window(turf, d)
        if w and w[0] <= start and end <= w[1]:
            return ""
    return "closed"


def evaluate(
    turf,
    field: TurfField,
    dates: list[date],
    start_time: time,
    end_time: time,
    phone: str,
    *,
    ignore_ids=(),
    now=None,
) -> list[Row]:
    """Availability + price for every date, in a few bulk queries (no per-date booking lookups)."""
    now = now or timezone.now()
    rows = [Row(d, *window(d, start_time, end_time)) for d in dates]
    if not rows:
        return rows
    if rows[0].end - rows[0].start > timedelta(hours=12):
        raise ValidationError({"end_time": ["A booking can't be longer than 12 hours."]})
    for value in (rows[0].start, rows[0].end):
        if timezone.localtime(value).minute % 15:
            raise ValidationError({"start_time": ["Times must be on 15-minute steps (e.g. 17:00, 17:15)."]})
    lo, hi = min(r.start for r in rows), max(r.end for r in rows)
    taken = list(
        Booking.objects.blocking(now)
        .filter(field=field, start__lt=hi, end__gt=lo)
        .exclude(pk__in=list(ignore_ids))
        .values_list("start", "end", "status", "reference")
    )
    blocks = list(
        MaintenanceBlock.objects.filter(field=field, start__lt=hi, end__gt=lo).values_list("start", "end")
    )
    p = policy()
    used: dict[date, int] = defaultdict(int)
    if phone and not p.recurring_limit_exempt:
        first_day, last_day = timezone.localtime(lo).date(), timezone.localtime(hi).date()
        day_lo, _ = payments.day_bounds(first_day)
        _, day_hi = payments.day_bounds(last_day)
        for start, n in (
            Booking.objects.blocking(now)
            .filter(customer__phone=phone, start__gte=day_lo, start__lt=day_hi)
            .exclude(pk__in=list(ignore_ids))
            .values_list("start", "slot_count")
        ):
            used[timezone.localtime(start).date()] += n
    rules, categories, cache = schedule.turf_rules(turf.pk), schedule.turf_categories(turf.pk), {}
    for r in rows:
        r.slots = payments.slot_count_for(field, r.start, r.end)
        q = quote(field, r.start, r.end, rules, categories=categories, cache=cache)
        r.price, r.snapshot = to_money(q.subtotal), q.as_snapshot()
        if r.start <= now:
            r.available, r.reason = False, "past"
            continue
        if reason := _offered(turf, field, r.start, r.end):
            r.available, r.reason = False, reason
            continue
        if any(s < r.end and e > r.start for s, e in blocks):
            r.available, r.reason = False, "maintenance"
            continue
        clash = next(((s, e, st, ref) for s, e, st, ref in taken if s < r.end and e > r.start), None)
        if clash:
            r.available = False
            r.reason = "booked" if clash[2] != Booking.Status.PENDING else "held"
            r.detail = clash[3]
            continue
        if phone and not p.recurring_limit_exempt:
            day = timezone.localtime(r.start).date()
            if used[day] + r.slots > p.max_slots_per_customer:
                r.available, r.reason = False, "limit"
                r.detail = f"limit {p.max_slots_per_customer} per day"
                continue
            used[day] += r.slots  # later dates in this same request count too
    return rows


def summary(turf, rows: list[Row], excluded: set[date]) -> dict:
    chosen = [r for r in rows if r.available and r.day not in excluded]
    total = sum((r.price for r in chosen), Decimal("0.00"))
    advance = sum((payments.required_advance(turf, r.price) for r in chosen), Decimal("0.00"))
    return {
        "dates": len(rows),
        "available": sum(1 for r in rows if r.available),
        "unavailable": [r.day.isoformat() for r in rows if not r.available],
        "booking": len(chosen),
        "minutes_each": int((rows[0].end - rows[0].start).total_seconds() // 60) if rows else 0,
        "total": str(to_money(total)),
        "advance_required": str(to_money(advance)),
        "advance_rule": f"Same as single bookings: ৳{to_money(max(turf.advance_amount or 0, payments.MIN_ADVANCE))} per booking (or its price if lower)",
        "remaining": str(to_money(total - advance)),
    }


# ------------------------------------------------------------------ input
def parse_plan(turf, data: dict) -> dict:
    """Validated plan from request data (shared by preview and create)."""
    from rest_framework import serializers

    class PlanSerializer(serializers.Serializer):
        field = serializers.PrimaryKeyRelatedField(
            queryset=TurfField.objects.filter(turf=turf, is_active=True)
        )
        start_time = serializers.TimeField()
        end_time = serializers.TimeField()
        recurrence = serializers.ChoiceField(choices=BookingSeries.Recurrence.choices)
        weekdays = serializers.ListField(
            child=serializers.IntegerField(min_value=0, max_value=6), required=False
        )
        custom_dates = serializers.ListField(child=serializers.DateField(), required=False, max_length=400)
        start_date = serializers.DateField()
        end_date = serializers.DateField(required=False)
        customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
        exclude_dates = serializers.ListField(child=serializers.DateField(), required=False)

    s = PlanSerializer(data=data)
    s.is_valid(raise_exception=True)
    v = dict(s.validated_data)
    if v["start_time"] == v["end_time"]:
        raise ValidationError({"end_time": ["End time must differ from the start time."]})
    v["end_date"] = v.get("end_date") or v["start_date"]
    v["dates"] = generate_dates(
        v["recurrence"], v["start_date"], v["end_date"], v.get("weekdays"), v.get("custom_dates")
    )
    check_horizon(v["dates"])
    v["phone"] = normalize_bd_phone(v["customer_phone"]) if v.get("customer_phone") else ""
    v["excluded"] = set(v.get("exclude_dates") or [])
    return v


def preview(turf, data: dict) -> dict:
    v = parse_plan(turf, data)
    rows = evaluate(turf, v["field"], v["dates"], v["start_time"], v["end_time"], v["phone"])
    return {"rows": [r.as_dict() for r in rows], "summary": summary(turf, rows, v["excluded"])}


def _ref() -> str:
    ref = new_reference().replace("TRF-", "SER-")
    while BookingSeries.objects.filter(reference=ref).exists():
        ref = new_reference().replace("TRF-", "SER-")
    return ref


def _lock(field: TurfField, phone: str) -> TurfField:
    field = TurfField.objects.select_for_update().get(pk=field.pk)
    if phone:
        CustomerLock.objects.get_or_create(phone=phone)
        CustomerLock.objects.select_for_update().get(phone=phone)
    return field


def _allocate(bookings: list[Booking], amount: Decimal, method: str, reference: str, user) -> None:
    """Spread a payment over the occurrences, earliest first (each one up to its own total)."""
    left = to_money(amount)
    for b in sorted(bookings, key=lambda x: x.start):
        if left <= 0:
            break
        part = min(left, b.total - b.amount_paid)
        if part > 0:
            record_payment(
                b, amount=part, method=method, kind=Payment.Kind.PAYMENT, reference=reference, user=user
            )
            left -= part


def _conflict_error(rows: list[Row]) -> ValidationError:
    bad = [r for r in rows if not r.available]
    return ValidationError(
        {
            "dates": [
                "Some dates are no longer available. Exclude them (or change the schedule) and submit again: "
                + ", ".join(f"{r.day:%d %b} ({REASONS.get(r.reason, r.reason)})" for r in bad[:12])
                + (" …" if len(bad) > 12 else "")
            ],
            "code": ["dates_unavailable"],
            "unavailable": [r.day.isoformat() for r in bad],
        }
    )


@transaction.atomic
def create_series(turf, data: dict, *, user, request=None, idempotency_key: str | None = None):
    """Create the series and one booking per chosen date — all or nothing. Returns (series, sms)."""
    key = f"{turf.pk}:{idempotency_key}"[:64] if idempotency_key else None
    if key and (done := BookingSeries.objects.filter(idempotency_key=key, turf=turf).first()):
        return done, None
    v = parse_plan(turf, data)
    name = (data.get("customer_name") or "").strip()
    if not name or not v["phone"]:
        raise ValidationError({"customer_name": ["Enter the customer's name and mobile number."]})
    mode = data.get("mode", "confirm")
    if mode not in ("confirm", "pending"):
        raise ValidationError({"mode": ["Choose confirm now or awaiting payment."]})
    field = _lock(v["field"], v["phone"])
    customer = get_or_create_customer(turf, name=name, phone=v["phone"], email=data.get("customer_email", ""))
    rows = evaluate(turf, field, v["dates"], v["start_time"], v["end_time"], v["phone"])
    if any(not r.available and r.day not in v["excluded"] for r in rows):
        raise _conflict_error([r for r in rows if r.day not in v["excluded"]])
    chosen = [r for r in rows if r.available and r.day not in v["excluded"]]
    if not chosen:
        raise ValidationError({"dates": ["No dates left to book."]})
    now = timezone.now()
    pending = mode == "pending"
    hold_until = now + timedelta(hours=policy().recurring_hold_hours) if pending else None
    series = BookingSeries.objects.create(
        turf=turf,
        field=field,
        customer=customer,
        reference=_ref(),
        start_time=v["start_time"],
        end_time=v["end_time"],
        recurrence=v["recurrence"],
        weekdays=sorted(set(v.get("weekdays") or [])),
        custom_dates=[d.isoformat() for d in v["dates"]]
        if v["recurrence"] == BookingSeries.Recurrence.CUSTOM
        else [],
        start_date=chosen[0].day,
        end_date=chosen[-1].day,
        occurrences_count=len(chosen),
        total=sum((r.price for r in chosen), Decimal("0.00")),
        status=BookingSeries.Status.PENDING_PAYMENT if pending else BookingSeries.Status.ACTIVE,
        team_name=(data.get("team_name") or "")[:120],
        notes=data.get("notes") or "",
        created_by=user,
        idempotency_key=key,
    )
    bookings = Booking.objects.bulk_create(
        [
            Booking(
                turf=turf,
                field=field,
                customer=customer,
                reference=new_reference(),
                start=r.start,
                end=r.end,
                status=Booking.Status.PENDING if pending else Booking.Status.CONFIRMED,
                source=Booking.Source.STAFF,
                team_name=series.team_name,
                notes=series.notes,
                subtotal=r.price,
                total=r.price,
                price_snapshot=r.snapshot,
                created_by=user,
                confirmed_at=None if pending else now,
                hold_expires_at=hold_until,
                slot_count=r.slots,
                series=series,
                occurrence_number=i,
            )
            for i, r in enumerate(chosen, start=1)
        ]
    )
    advance = to_money(data.get("advance_amount") or 0)
    if advance > 0:
        if pending:
            raise ValidationError({"advance_amount": ["Record the payment with “Confirm series” instead."]})
        if advance > series.total:
            raise ValidationError({"advance_amount": ["Advance can't be more than the series total."]})
        _allocate(
            bookings, advance, data.get("advance_method") or "cash", data.get("advance_reference", ""), user
        )
    excluded = [d for d in sorted(v["excluded"]) if d in {r.day for r in rows}]
    record(
        "booking.series_created",
        f"Advance booking {series.reference}: {len(chosen)} date(s) {series.start_date:%d %b}–{series.end_date:%d %b}, "
        f"{v['start_time']:%H:%M}–{v['end_time']:%H:%M}, ৳{series.total} "
        f"({'awaiting payment' if pending else 'confirmed'})",
        category=Category.BOOKING,
        request=request,
        target=series,
        data={"excluded": [d.isoformat() for d in excluded], "advance": str(advance)},
    )
    sms = None if pending else notify(series, "confirmed")
    return series, sms


# ------------------------------------------------------------------ managing a series
def _future_live(series: BookingSeries, now=None):
    now = now or timezone.now()
    return series.occurrences.filter(status__in=LIVE, start__gt=now)


def required_for(series: BookingSeries, bookings) -> Decimal:
    return sum((payments.required_advance(series.turf, b.total) for b in bookings), Decimal("0.00"))


@transaction.atomic
def confirm_series(series: BookingSeries, *, amount, method: str, reference: str, user, request=None):
    """Awaiting-payment series: the advance was received — confirm every still-held date."""
    series = BookingSeries.objects.select_for_update().get(pk=series.pk)
    if series.status != BookingSeries.Status.PENDING_PAYMENT:
        raise ValidationError({"status": ["This series isn't awaiting payment."]})
    now = timezone.now()
    held = list(
        series.occurrences.select_for_update().filter(status=Booking.Status.PENDING, hold_expires_at__gt=now)
    )
    if not held:
        series.status = BookingSeries.Status.EXPIRED
        series.save(update_fields=["status", "updated_at"])
        raise ValidationError(
            {"status": ["The payment time ran out and the dates were released. Create it again."]}
        )
    amount = to_money(amount or 0)
    need = required_for(series, held)
    if amount < need:
        raise ValidationError({"amount": [f"The advance for {len(held)} date(s) is at least ৳{need}."]})
    if method == Payment.Method.BKASH and not (reference or "").strip():
        raise ValidationError({"reference": ["Enter the bKash Transaction ID."]})
    Booking.objects.filter(pk__in=[b.pk for b in held]).update(
        status=Booking.Status.CONFIRMED, confirmed_at=now, hold_expires_at=None, updated_at=now
    )
    for b in held:
        b.refresh_from_db()
    _allocate(held, amount, method, reference.strip(), user)
    series.status = BookingSeries.Status.ACTIVE
    series.occurrences_count = series.occurrences.filter(status__in=LIVE).count()
    series.save(update_fields=["status", "occurrences_count", "updated_at"])
    record(
        "booking.series_confirmed",
        f"Advance booking {series.reference} confirmed — ৳{amount} received ({method}), {len(held)} date(s)",
        category=Category.BOOKING,
        request=request,
        target=series,
    )
    return notify(series, "confirmed")


@transaction.atomic
def cancel(series: BookingSeries, *, booking_ids=None, all_future=False, user=None, request=None):
    """Cancel chosen future dates (or every future date). Past and finished bookings never change."""
    series = BookingSeries.objects.select_for_update().get(pk=series.pk)
    qs = _future_live(series).select_for_update()
    if not all_future:
        ids = [str(i) for i in (booking_ids or [])]
        if not ids:
            raise ValidationError({"booking_ids": ["Choose the dates to cancel."]})
        qs = qs.filter(pk__in=ids)
        if qs.count() != len(set(ids)):
            raise ValidationError(
                {"booking_ids": ["Only upcoming, active dates of this series can be cancelled."]}
            )
    targets = list(qs.order_by("start"))
    if not targets:
        raise ValidationError({"booking_ids": ["There are no upcoming dates to cancel."]})
    now = timezone.now()
    had_confirmed = any(b.status == Booking.Status.CONFIRMED for b in targets)
    Booking.objects.filter(pk__in=[b.pk for b in targets]).update(
        status=Booking.Status.CANCELLED, updated_at=now
    )
    remaining = series.occurrences.filter(status__in=LIVE).count()
    series.occurrences_count = series.occurrences.exclude(
        status__in=[Booking.Status.CANCELLED, Booking.Status.REJECTED, Booking.Status.EXPIRED]
    ).count()
    if all_future or remaining == 0:
        series.status, series.cancelled_at = BookingSeries.Status.CANCELLED, now
    series.save(update_fields=["status", "cancelled_at", "occurrences_count", "updated_at"])
    paid = sum((b.amount_paid for b in targets), Decimal("0.00"))
    record(
        "booking.series_cancelled",
        f"Cancelled {len(targets)} date(s) of {series.reference}: "
        + ", ".join(f"{timezone.localtime(b.start):%d %b}" for b in targets[:10])
        + (" …" if len(targets) > 10 else "")
        + (f" (৳{paid} was paid on them — refund per your policy)" if paid else ""),
        category=Category.BOOKING,
        request=request,
        target=series,
        data={"bookings": [b.reference for b in targets], "paid": str(paid)},
    )
    sms = notify(series, "cancelled", dates=targets) if had_confirmed else None
    return {"cancelled": len(targets), "paid_on_cancelled": str(paid), "sms": sms}


@transaction.atomic
def add_date(series: BookingSeries, day: date, *, user=None, request=None, dry_run=False):
    series = BookingSeries.objects.select_for_update().get(pk=series.pk)
    if series.status not in (BookingSeries.Status.ACTIVE, BookingSeries.Status.PENDING_PAYMENT):
        raise ValidationError({"status": ["Dates can only be added to an active series."]})
    check_horizon([day])
    if series.occurrences.filter(
        status__in=LIVE, start__gte=payments.day_bounds(day)[0], start__lt=payments.day_bounds(day)[1]
    ).exists():
        raise ValidationError({"date": [REASONS["same_series"]]})
    field = _lock(series.field, series.customer.phone)
    row = evaluate(series.turf, field, [day], series.start_time, series.end_time, series.customer.phone)[0]
    if dry_run or not row.available:
        return {"row": row.as_dict(), "added": False}
    pending = series.status == BookingSeries.Status.PENDING_PAYMENT
    now = timezone.now()
    number = (
        series.occurrences.order_by("-occurrence_number").values_list("occurrence_number", flat=True).first()
        or 0
    ) + 1
    hold = (
        series.occurrences.filter(status=Booking.Status.PENDING)
        .values_list("hold_expires_at", flat=True)
        .first()
    )
    booking = Booking.objects.create(
        turf=series.turf,
        field=field,
        customer=series.customer,
        start=row.start,
        end=row.end,
        status=Booking.Status.PENDING if pending else Booking.Status.CONFIRMED,
        source=Booking.Source.STAFF,
        team_name=series.team_name,
        notes=series.notes,
        subtotal=row.price,
        total=row.price,
        price_snapshot=row.snapshot,
        created_by=user,
        confirmed_at=None if pending else now,
        hold_expires_at=(hold or now + timedelta(hours=policy().recurring_hold_hours)) if pending else None,
        slot_count=row.slots,
        series=series,
        occurrence_number=number,
    )
    series.occurrences_count = series.occurrences.filter(status__in=LIVE).count()
    series.total = series.occurrences.filter(status__in=LIVE).aggregate(t=Sum("total"))["t"] or Decimal("0")
    series.start_date = min(series.start_date, day)
    series.end_date = max(series.end_date, day)
    series.save(update_fields=["occurrences_count", "total", "start_date", "end_date", "updated_at"])
    record(
        "booking.series_date_added",
        f"Added {day:%d %b %Y} to {series.reference} ({booking.reference}, ৳{booking.total})",
        category=Category.BOOKING,
        request=request,
        target=series,
    )
    sms = None if pending else notify(series, "updated", detail=f"{day:%d/%m/%Y} যোগ করা হয়েছে")
    return {"row": row.as_dict(), "added": True, "booking": booking.reference, "sms": sms}


@transaction.atomic
def reschedule(
    series: BookingSeries,
    *,
    start_time: time,
    end_time: time,
    from_date: date | None = None,
    keep_dates=(),
    user=None,
    request=None,
    dry_run=True,
):
    """Move upcoming dates (from `from_date`) to a new time. Dry run first; dates that can't move must be
    listed in `keep_dates` (they keep their current time) before anything changes."""
    series = BookingSeries.objects.select_for_update().get(pk=series.pk)
    if start_time == end_time:
        raise ValidationError({"end_time": ["End time must differ from the start time."]})
    qs = _future_live(series).select_for_update().order_by("start")
    if from_date:
        qs = qs.filter(start__gte=payments.day_bounds(from_date)[0])
    targets = list(qs)
    if not targets:
        raise ValidationError({"from_date": ["There are no upcoming dates to change."]})
    field = _lock(series.field, series.customer.phone)
    days = [timezone.localtime(b.start).date() for b in targets]
    rows = evaluate(
        series.turf,
        field,
        days,
        start_time,
        end_time,
        series.customer.phone,
        ignore_ids=[b.pk for b in targets],
    )
    keep = {d if isinstance(d, date) else date.fromisoformat(str(d)) for d in keep_dates}
    blocking = [r for r in rows if not r.available and r.day not in keep]
    result = {"rows": [r.as_dict() for r in rows], "changed": 0}
    if dry_run:
        return result
    if blocking:
        raise _conflict_error(blocking)
    now = timezone.now()
    moved = []
    for b, r in zip(targets, rows, strict=True):
        if r.day in keep or not r.available:
            continue
        b.start, b.end = r.start, r.end
        b.subtotal, b.total, b.price_snapshot = r.price, to_money(r.price - b.discount), r.snapshot
        b.slot_count = r.slots
        b.updated_at = now
        moved.append(b)
    Booking.objects.bulk_update(
        moved, ["start", "end", "subtotal", "total", "price_snapshot", "slot_count", "updated_at"]
    )
    if not keep and not from_date:
        series.start_time, series.end_time = start_time, end_time
    series.total = series.occurrences.filter(status__in=LIVE).aggregate(t=Sum("total"))["t"] or Decimal("0")
    series.save(update_fields=["start_time", "end_time", "total", "updated_at"])
    record(
        "booking.series_rescheduled",
        f"Moved {len(moved)} upcoming date(s) of {series.reference} to {start_time:%H:%M}–{end_time:%H:%M}",
        category=Category.BOOKING,
        request=request,
        target=series,
        data={"kept": sorted(d.isoformat() for d in keep), "bookings": [b.reference for b in moved]},
    )
    confirmed = any(b.status == Booking.Status.CONFIRMED for b in moved)
    result["changed"] = len(moved)
    result["sms"] = (
        notify(series, "updated", detail=f"{len(moved)}টি বুকিংয়ের সময় এখন {_clock(start_time, end_time)}")
        if confirmed
        else None
    )
    return result


def expire_unpaid(now=None) -> dict:
    """Tick step (after the hold expiry step): awaiting-payment series with no held date left."""
    now = now or timezone.now()
    n = 0
    for s in BookingSeries.objects.filter(status=BookingSeries.Status.PENDING_PAYMENT):
        if not s.occurrences.filter(status=Booking.Status.PENDING, hold_expires_at__gt=now).exists():
            s.status = BookingSeries.Status.EXPIRED
            s.save(update_fields=["status", "updated_at"])
            n += 1
    return {"expired_series": n}


# ------------------------------------------------------------------ SMS
def _clock(start_time: time, end_time: time) -> str:
    fmt = lambda t: f"{t:%I:%M %p}".lstrip("0")  # noqa: E731
    return f"{fmt(start_time)}–{fmt(end_time)}"


TURF_SWITCH = {
    "confirmed": "owner_booking_confirmed",
    "updated": "owner_booking_confirmed",
    "cancelled": "booking_cancelled",
}


def notify(series: BookingSeries, event: str, *, dates=None, detail: str = ""):
    """One SMS per series event (never one per date). Uses the turf's SMS wallet and switches; a blocked
    SMS (e.g. empty wallet) is recorded and shown to the owner but never fails the booking."""
    from apps.notifications.models import SmsKind, SmsMessage
    from apps.notifications.services import queue_sms, render, turf_sms_settings

    turf = series.turf
    if not turf_sms_settings(turf).get(TURF_SWITCH[event], True):
        return None
    live = series.occurrences.filter(status__in=LIVE).order_by("start")
    count = live.count()
    common = {
        "turf": turf.name,
        "reference": series.reference,
        "phone": turf.public_phone or turf.owner_phone,
        "name": series.customer.name,
        "count": str(count),
    }
    if event == "confirmed":
        first, last = live.first(), live.last()
        if first is None:
            return None
        kind = SmsKind.SERIES_CONFIRMED
        body = render(
            kind,
            start_date=f"{timezone.localtime(first.start):%d/%m/%Y}",
            end_date=f"{timezone.localtime(last.start):%d/%m/%Y}",
            time=_clock(series.start_time, series.end_time),
            **common,
        )
        key = f"series:{series.pk}:confirmed"
    elif event == "cancelled":
        kind = SmsKind.SERIES_CANCELLED
        ds = sorted(timezone.localtime(b.start).date() for b in dates or [])
        common["count"] = str(len(ds))
        body = render(
            kind, dates=", ".join(f"{d:%d/%m}" for d in ds[:8]) + (" …" if len(ds) > 8 else ""), **common
        )
        key = f"series:{series.pk}:cancel:{'-'.join(sorted(str(b.pk)[:8] for b in dates or []))}"[:120]
    else:
        kind = SmsKind.SERIES_UPDATED
        body = render(kind, detail=detail, **common)
        n = SmsMessage.objects.filter(related_ref=f"series:{series.pk}", kind=kind).count() + 1
        key = f"series:{series.pk}:updated:{n}"
    return queue_sms(
        to=series.customer.phone,
        body=body,
        kind=kind,
        turf=turf,
        dedupe_key=key,
        related_ref=f"series:{series.pk}",
    )


# ------------------------------------------------------------------ output
def display_status(series: BookingSeries, now=None) -> str:
    now = now or timezone.now()
    if series.status in (BookingSeries.Status.CANCELLED, BookingSeries.Status.EXPIRED):
        return series.status
    if series.status == BookingSeries.Status.PENDING_PAYMENT:
        held = series.occurrences.filter(status=Booking.Status.PENDING, hold_expires_at__gt=now).exists()
        return series.status if held else BookingSeries.Status.EXPIRED
    if not series.occurrences.filter(status__in=LIVE, end__gt=now).exists():
        return "completed"
    return series.status


def series_payload(series: BookingSeries, *, occurrences=True) -> dict:
    now = timezone.now()
    occ = list(series.occurrences.order_by("start")) if occurrences else []
    live = [b for b in occ if b.status in LIVE]
    data = {
        "id": str(series.pk),
        "reference": series.reference,
        "customer": {
            "id": str(series.customer_id),
            "name": series.customer.name,
            "phone": series.customer.phone,
        },
        "field": {"id": str(series.field_id), "name": series.field.name},
        "start_time": f"{series.start_time:%H:%M}",
        "end_time": f"{series.end_time:%H:%M}",
        "overnight": series.end_time <= series.start_time,
        "recurrence": series.recurrence,
        "recurrence_label": series.get_recurrence_display(),
        "weekdays": series.weekdays,
        "start_date": series.start_date,
        "end_date": series.end_date,
        "occurrences_count": series.occurrences_count,
        "total": str(series.total),
        "status": display_status(series, now),
        "team_name": series.team_name,
        "notes": series.notes,
        "created_by": (series.created_by.full_name or series.created_by.email)
        if series.created_by_id
        else None,
        "created_at": series.created_at,
    }
    if occurrences:
        pending = [
            b
            for b in occ
            if b.status == Booking.Status.PENDING and b.hold_expires_at and b.hold_expires_at > now
        ]
        data.update(
            {
                "occurrences": [
                    {
                        "id": str(b.pk),
                        "reference": b.reference,
                        "number": b.occurrence_number,
                        "start": b.start,
                        "end": b.end,
                        "status": b.status,
                        "status_label": b.get_status_display(),
                        "total": str(b.total),
                        "paid": str(b.amount_paid),
                        "payment_status": b.payment_status,
                        "upcoming": b.start > now,
                        "can_cancel": b.start > now and b.status in LIVE,
                        "hold_expires_at": b.hold_expires_at,
                    }
                    for b in occ
                ],
                "live_total": str(sum((b.total for b in live), Decimal("0.00"))),
                "paid_total": str(sum((b.amount_paid for b in occ), Decimal("0.00"))),
                "due_total": str(sum((b.due for b in live), Decimal("0.00"))),
                "advance_required": str(required_for(series, pending)) if pending else "0.00",
                "hold_expires_at": min((b.hold_expires_at for b in pending), default=None),
            }
        )
    return data
