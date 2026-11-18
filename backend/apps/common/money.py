"""BDT money helpers. All currency math uses Decimal — never float."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models

TWO_PLACES = Decimal("0.01")


def to_money(value) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Money must not be built from float; pass str, int or Decimal.")
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class MoneyField(models.DecimalField):
    """Decimal(12,2) in BDT."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("default", Decimal("0.00"))
        super().__init__(*args, **kwargs)
