"""Which slots a field offers on a day, and which price category a moment falls in.

Two ways to define slots:
- automatic (default): fixed-length slots (field.slot_minutes) from the day's opening time to closing;
- custom: the owner's SlotTemplate rows for that weekday (any start/end, any length, enable/disable,
  optional fixed price). If a field has templates for a weekday, only those are offered that day.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .models import OperatingHours, PriceCategory, SlotTemplate, Turf, TurfField

DAY_MINUTES = 24 * 60

# Suggested defaults, editable by the owner.
DEFAULT_CATEGORY_STARTS = {
    PriceCategory.Key.MORNING: time(6, 0),
    PriceCategory.Key.EVENING: time(12, 0),
    PriceCategory.Key.NIGHT: time(18, 0),
    PriceCategory.Key.MIDNIGHT: time(0, 0),
}


def local_dt(day: date, at: time) -> datetime:
    return timezone.make_aware(datetime.combine(day, at), timezone.get_current_timezone())


def opening_window(turf: Turf, day: date) -> tuple[datetime, datetime] | None:
    hours = OperatingHours.objects.filter(turf=turf, weekday=day.weekday()).first()
    if hours is None or hours.is_closed:
        return None
    opens = local_dt(day, hours.opens_at)
    closes_day = day + timedelta(days=1) if hours.closes_at <= hours.opens_at else day
    return opens, local_dt(closes_day, hours.closes_at)


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime
    template: SlotTemplate | None = None

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def templates_for(field: TurfField, weekday: int, *, cache: dict | None = None) -> list[SlotTemplate] | None:
    """The field's templates for a weekday (active and inactive), or None if it uses the grid."""
    if cache is not None and (field.pk, weekday) in cache:
        return cache[(field.pk, weekday)]
    rows = list(SlotTemplate.objects.filter(field=field, weekday=weekday).order_by("start_time"))
    result = rows or None
    if cache is not None:
        cache[(field.pk, weekday)] = result
    return result


def template_window(day: date, template: SlotTemplate) -> tuple[datetime, datetime]:
    start = local_dt(day, template.start_time)
    return start, start + timedelta(minutes=template.minutes)


def day_slots(field: TurfField, day: date, *, cache: dict | None = None) -> list[Slot]:
    templates = templates_for(field, day.weekday(), cache=cache)
    if templates is not None:
        return [Slot(*template_window(day, t), t) for t in templates if t.is_active]
    window = opening_window(field.turf, day)
    if window is None:
        return []
    opens, closes = window
    step = timedelta(minutes=field.slot_minutes or 60)
    slots, cursor = [], opens
    while cursor + step <= closes:
        slots.append(Slot(cursor, cursor + step))
        cursor += step
    return slots


def slot_containing(field: TurfField, moment: datetime, *, cache: dict | None = None) -> Slot | None:
    """The offered slot that contains `moment` (checks the previous day too, for overnight slots)."""
    local = timezone.localtime(moment)
    found = [
        slot
        for day in (local.date() - timedelta(days=1), local.date())
        for slot in day_slots(field, day, cache=cache)
        if slot.start <= moment < slot.end
    ]
    # A custom slot carrying over from yesterday beats today's automatic grid at the same moment.
    return next((s for s in found if s.template is not None), found[0] if found else None)


def is_offered_range(field: TurfField, start: datetime, end: datetime) -> bool:
    """For custom-slot days: True only if [start, end) is one or more back-to-back offered slots.
    Days on the automatic grid are not restricted here (opening hours are checked elsewhere)."""
    day = timezone.localtime(start).date()
    days = [day - timedelta(days=1), day, day + timedelta(days=1)]
    if not any(uses_templates(field, d) for d in days):
        return True
    slots = sorted({s for d in days for s in day_slots(field, d)}, key=lambda s: s.start)
    cursor = start
    for slot in slots:
        if slot.start == cursor:
            cursor = slot.end
            if cursor == end:
                return True
        elif slot.start > cursor:
            break
    return False


def uses_templates(field: TurfField, day: date) -> bool:
    return templates_for(field, day.weekday()) is not None


# ------------------------------------------------------------------ categories
def turf_categories(turf_id) -> list[PriceCategory]:
    return list(PriceCategory.objects.filter(turf_id=turf_id).order_by("starts_at"))


def category_at(categories: list[PriceCategory], at: time) -> PriceCategory | None:
    """The category whose band contains `at`: the latest start <= at, else the one that wraps midnight."""
    if not categories:
        return None
    ordered = sorted(categories, key=lambda c: c.starts_at)
    current = ordered[-1]  # before the first start of the day we're still in the last band (wraps)
    for c in ordered:
        if c.starts_at <= at:
            current = c
    return current


def category_bands(categories: list[PriceCategory]) -> list[dict]:
    """[{key, label, start, end, hourly_rate}] in Morning→Midnight order, ends filled in."""
    ordered = sorted(categories, key=lambda c: c.starts_at)
    bands = []
    for i, c in enumerate(ordered):
        nxt = ordered[(i + 1) % len(ordered)]
        bands.append(
            {
                "key": c.key,
                "label": c.get_key_display(),
                "start": c.starts_at.strftime("%H:%M"),
                "end": nxt.starts_at.strftime("%H:%M"),
                "hourly_rate": str(c.hourly_rate),
            }
        )
    order = {k: i for i, k in enumerate(PriceCategory.ORDER)}
    return sorted(bands, key=lambda b: order[b["key"]])


def crosses_boundary(categories: list[PriceCategory], start: datetime, end: datetime) -> PriceCategory | None:
    """If [start, end) runs into a different category, return the one it runs into."""
    if not categories:
        return None
    first = category_at(categories, timezone.localtime(start).time())
    cursor = start + timedelta(minutes=15)
    while cursor < end:
        c = category_at(categories, timezone.localtime(cursor).time())
        if c and first and c.pk != first.pk:
            return c
        cursor += timedelta(minutes=15)
    return None
