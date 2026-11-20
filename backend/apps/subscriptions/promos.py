"""Promo code rules shared by plan invoices (existing turfs) and new registrations.

The backend always computes the discount; the browser only shows what comes back. Uses of a code are
counted from (a) invoices that are paid or still open and (b) registration reservations that are still
RESERVED — a redeemed registration is already counted through the paid invoice it created.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.money import to_money

from .models import Invoice, Plan, PromoCode, PromoRedemption

MESSAGES = {
    "invalid": "Invalid promo code.",
    "inactive": "This promo code is not active.",
    "not_started": "This promo code is not active yet.",
    "expired": "This promo code has expired.",
    "used_up": "This promo code's usage limit has been reached.",
    "plan": "This promo code isn't valid for the selected plan.",
    "min_amount": "This promo code needs a larger plan.",
    "new_only": "This promo code is only for new turf registrations.",
    "already_used": "You have already used this promo code.",
}


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def reject(reason: str, **extra) -> ValidationError:
    message = MESSAGES[reason].format(**extra) if extra else MESSAGES[reason]
    return ValidationError({"promo_code": [message], "promo_error": [reason]})


def discount_for(promo: PromoCode, base: Decimal) -> Decimal:
    """Discount on `base` in whole paisa, never more than the price itself."""
    base = to_money(base)
    if promo.discount_type == PromoCode.DiscountType.FIXED:
        d = to_money(promo.amount_off or 0)
    else:
        d = (base * Decimal(promo.percent_off) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if promo.max_discount:
            d = min(d, to_money(promo.max_discount))
    return max(Decimal("0.00"), min(d, base))


def uses(promo: PromoCode, *, exclude_invoice=None, exclude_redemption=None) -> int:
    inv = Invoice.objects.filter(promo_code=promo, status__in=[Invoice.Status.PAID, *Invoice.OPEN])
    if exclude_invoice is not None:
        inv = inv.exclude(pk=exclude_invoice.pk)
    held = PromoRedemption.objects.filter(promo=promo, status=PromoRedemption.Status.RESERVED)
    if exclude_redemption is not None:
        held = held.exclude(pk=exclude_redemption.pk)
    return inv.count() + held.count()


def check(
    code: str,
    *,
    plan: Plan | None,
    price: Decimal,
    turf=None,
    phone: str = "",
    email: str = "",
    registration: bool = False,
    lock: bool = False,
    exclude_invoice=None,
    exclude_redemption=None,
) -> PromoCode:
    """The usable promo for this purchase, or a ValidationError with a specific, readable reason."""
    code = normalize_code(code)
    qs = PromoCode.objects.select_for_update() if lock else PromoCode.objects
    promo = qs.filter(code=code).first() if code else None
    if promo is None or promo.is_archived:
        raise reject("invalid")
    if not promo.is_active:
        raise reject("inactive")
    today = timezone.localdate()
    if promo.valid_from and today < promo.valid_from:
        raise reject("not_started")
    if promo.valid_until and today > promo.valid_until:
        raise reject("expired")
    if promo.new_registrations_only and not registration:
        raise reject("new_only")
    if plan is not None and promo.plans.exists() and not promo.plans.filter(pk=plan.pk).exists():
        raise reject("plan")
    if promo.min_amount and to_money(price) < to_money(promo.min_amount):
        raise reject("min_amount")
    limit = max(1, promo.max_per_account or 1)
    if turf is not None:
        paid = Invoice.objects.filter(turf=turf, promo_code=promo, status=Invoice.Status.PAID).count()
        if paid >= limit:
            raise reject("already_used")
    if registration:
        mine = PromoRedemption.objects.filter(
            promo=promo,
            status__in=[PromoRedemption.Status.RESERVED, PromoRedemption.Status.REDEEMED],
        ).filter(Q(phone=phone) | Q(email__iexact=email))
        if exclude_redemption is not None:
            mine = mine.exclude(pk=exclude_redemption.pk)
        if mine.count() >= limit:
            raise reject("already_used")
    if (
        promo.max_uses is not None
        and uses(promo, exclude_invoice=exclude_invoice, exclude_redemption=exclude_redemption)
        >= promo.max_uses
    ):
        raise reject("used_up")
    return promo


def stats(promo: PromoCode) -> dict:
    paid = Invoice.objects.filter(promo_code=promo, status=Invoice.Status.PAID)
    used = uses(promo)
    reserved = PromoRedemption.objects.filter(promo=promo, status=PromoRedemption.Status.RESERVED)
    return {
        "times_used": used,
        "redeemed": paid.count(),
        "reserved": reserved.count(),
        "remaining": None if promo.max_uses is None else max(0, promo.max_uses - used),
        "total_discount": str(to_money(paid.aggregate(t=Sum("discount"))["t"] or 0)),
    }
