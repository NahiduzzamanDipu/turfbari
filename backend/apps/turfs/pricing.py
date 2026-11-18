"""Price quote engine.

A booking is split into 15-minute segments; each segment takes the rate of the most specific
active rule that covers it (special date > field-specific > higher priority), falling back to the
field's default hourly rate. Consecutive segments at the same rate are merged in the snapshot that
is stored on the booking, so later rule changes never alter an existing booking's price.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Min, Q
from django.utils import timezone

from apps.common.money import to_money

from .models import PricingRule, Turf, TurfField

SEGMENT = timedelta(minutes=15)


def time_in_band(value: time, start: time, end: time) -> bool:
    if start == end:
        return True  # whole day
    if start < end:
        return start <= value < end
    return value >= start or value < end  # wraps past midnight


def rule_matches(rule: PricingRule, local: datetime, field_id) -> bool:
    if not rule.is_active:
        return False
    if rule.field_id and rule.field_id != field_id:
        return False
    if rule.date:
        if rule.date != local.date():
            return False
    elif rule.weekdays and local.weekday() not in rule.weekdays:
        return False
    return time_in_band(local.time(), rule.start_time, rule.end_time)


def _rank(rule: PricingRule) -> tuple:
    return (rule.date is not None, rule.field_id is not None, rule.priority)


@dataclass
class Quote:
    subtotal: Decimal
    segments: list[dict]

    def as_snapshot(self) -> dict:
        return {"subtotal": str(self.subtotal), "segments": self.segments}


def quote(field: TurfField, start: datetime, end: datetime, rules: list[PricingRule] | None = None) -> Quote:
    if end <= start:
        raise ValueError("Booking end must be after start.")
    if rules is None:
        rules = list(PricingRule.objects.filter(turf_id=field.turf_id, is_active=True))
    tz = timezone.get_current_timezone()
    segments: list[dict] = []
    cursor = start
    while cursor < end:
        seg_end = min(cursor + SEGMENT, end)
        local = timezone.localtime(cursor, tz)
        matching = [r for r in rules if rule_matches(r, local, field.id)]
        best = max(matching, key=_rank) if matching else None
        rate = best.hourly_rate if best else field.default_hourly_rate
        label = best.label if best else "Standard"
        minutes = int((seg_end - cursor).total_seconds() // 60)
        if segments and segments[-1]["label"] == label and segments[-1]["rate"] == str(rate):
            segments[-1]["end"] = timezone.localtime(seg_end, tz).isoformat()
            segments[-1]["minutes"] += minutes
        else:
            segments.append(
                {
                    "label": label,
                    "rate": str(rate),
                    "start": local.isoformat(),
                    "end": timezone.localtime(seg_end, tz).isoformat(),
                    "minutes": minutes,
                }
            )
        cursor = seg_end
    subtotal = Decimal("0")
    for seg in segments:
        seg["amount"] = str(to_money(Decimal(seg["rate"]) * seg["minutes"] / 60))
        subtotal += Decimal(seg["amount"])
    return Quote(subtotal=to_money(subtotal), segments=segments)


def recompute_min_price(turf: Turf) -> None:
    field_min = turf.fields.filter(is_active=True).aggregate(m=Min("default_hourly_rate"))["m"]
    rule_min = (
        turf.pricing_rules.filter(is_active=True)
        .filter(Q(field__isnull=True) | Q(field__is_active=True))
        .aggregate(m=Min("hourly_rate"))["m"]
    )
    values = [v for v in (field_min, rule_min) if v is not None and v > 0]
    turf.min_public_price = min(values) if values else None
    turf.save(update_fields=["min_public_price", "updated_at"])


def local_dt(day: date, at: time) -> datetime:
    return timezone.make_aware(datetime.combine(day, at), timezone.get_current_timezone())
