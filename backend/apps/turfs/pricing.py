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


def quote(
    field: TurfField,
    start: datetime,
    end: datetime,
    rules: list[PricingRule] | None = None,
    *,
    categories: list | None = None,
    cache: dict | None = None,
    anchor=None,
) -> Quote:
    """Price [start, end) in 15-minute segments. Precedence for each segment:

    1. a special-date price rule (holiday/event) covering it;
    2. the fixed price of the custom slot it belongs to;
    3. the turf's Morning/Evening/Night/Midnight rate for the time its *slot starts*;
    4. (turfs without categories) the older weekday/field price rules;
    5. the field's default hourly rate.
    """
    from .schedule import category_at, slot_containing, turf_categories

    if end <= start:
        raise ValueError("Booking end must be after start.")
    if rules is None:
        from .schedule import turf_rules

        rules = turf_rules(field.turf_id)
    if categories is None:
        categories = turf_categories(field.turf_id)
    cache = {} if cache is None else cache
    tz = timezone.get_current_timezone()
    segments: list[dict] = []
    cursor = start
    while cursor < end:
        seg_end = min(cursor + SEGMENT, end)
        local = timezone.localtime(cursor, tz)
        matching = [r for r in rules if rule_matches(r, local, field.id)]
        dated = [r for r in matching if r.date]
        slot = anchor if anchor is not None and anchor.start <= cursor < anchor.end else None
        if not dated and slot is None:
            slot = slot_containing(field, cursor, cache=cache)
        if dated:
            best = max(dated, key=_rank)
            rate, label = Decimal(best.hourly_rate), best.label
        elif slot is not None and slot.template is not None and slot.template.price is not None:
            rate, label = Decimal(slot.template.price) * 60 / slot.minutes, "Slot price"
        elif categories:
            when = timezone.localtime(slot.start, tz).time() if slot is not None else local.time()
            category = category_at(categories, when)
            rate, label = Decimal(category.hourly_rate), category.get_key_display()
        elif matching:
            best = max(matching, key=_rank)
            rate, label = Decimal(best.hourly_rate), best.label
        else:
            rate, label = Decimal(field.default_hourly_rate), "Standard"
        minutes = int((seg_end - cursor).total_seconds() // 60)
        if segments and segments[-1]["label"] == label and segments[-1]["_rate"] == rate:
            segments[-1]["end"] = timezone.localtime(seg_end, tz).isoformat()
            segments[-1]["minutes"] += minutes
        else:
            segments.append(
                {
                    "label": label,
                    "_rate": rate,
                    "rate": str(to_money(rate)),
                    "start": local.isoformat(),
                    "end": timezone.localtime(seg_end, tz).isoformat(),
                    "minutes": minutes,
                }
            )
        cursor = seg_end
    subtotal = Decimal("0")
    for seg in segments:
        seg["amount"] = str(to_money(seg.pop("_rate") * seg["minutes"] / 60))
        subtotal += Decimal(seg["amount"])
    return Quote(subtotal=to_money(subtotal), segments=segments)


def recompute_min_price(turf: Turf) -> None:
    field_min = turf.fields.filter(is_active=True).aggregate(m=Min("default_hourly_rate"))["m"]
    rule_min = (
        turf.pricing_rules.filter(is_active=True)
        .filter(Q(field__isnull=True) | Q(field__is_active=True))
        .aggregate(m=Min("hourly_rate"))["m"]
    )
    category_min = turf.price_categories.aggregate(m=Min("hourly_rate"))["m"]
    values = [v for v in (field_min, rule_min, category_min) if v is not None and v > 0]
    turf.min_public_price = min(values) if values else None
    turf.save(update_fields=["min_public_price", "updated_at"])


def local_dt(day: date, at: time) -> datetime:
    return timezone.make_aware(datetime.combine(day, at), timezone.get_current_timezone())
