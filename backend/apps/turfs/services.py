"""Turf provisioning helpers."""

from datetime import time
from decimal import Decimal

from django.utils.text import slugify

from .models import OperatingHours, Turf, TurfField
from .pricing import recompute_min_price


def unique_slug(name: str, model=Turf) -> str:
    base = slugify(name)[:120] or "turf"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def provision_defaults(turf: Turf, *, fields: int = 1, hourly_rate: Decimal = Decimal("1500.00")) -> None:
    """Give a new turf sensible defaults: open 6 AM to midnight daily, N fields."""
    for weekday in range(7):
        OperatingHours.objects.get_or_create(
            turf=turf, weekday=weekday, defaults={"opens_at": time(6, 0), "closes_at": time(0, 0)}
        )
    for i in range(1, max(fields, 1) + 1):
        TurfField.objects.get_or_create(
            turf=turf, name=f"Field {i}", defaults={"sort_order": i, "default_hourly_rate": hourly_rate}
        )
    if not turf.weekend_days:
        turf.weekend_days = [4, 5]
        turf.save(update_fields=["weekend_days", "updated_at"])
    recompute_min_price(turf)
