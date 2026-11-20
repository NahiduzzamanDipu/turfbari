"""Subscription rules.

- Prepaid and never auto-renewed: a period only exists after its invoice is paid.
- Paying while a period is running queues the new one to start the day after the latest paid period
  ends (no overlap, no proration). Paying after expiry starts it today.
- A turf can operate while it has a current period, plus GRACE_DAYS after the last one ends.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Invoice, PaymentTransaction, Plan, PromoCode, Subscription

GRACE_DAYS = 3
EXPIRY_WARNING_DAYS = 10

DEFAULT_PLANS = [
    # period, name, months, price, description
    (Plan.Period.MONTHLY, "Monthly", 1, Decimal("1500.00"), "Pay month by month."),
    (Plan.Period.HALF_YEARLY, "Half-yearly", 6, Decimal("8100.00"), "6 months, save 10%."),
    (Plan.Period.YEARLY, "Yearly", 12, Decimal("15000.00"), "12 months, save 17%."),
]


def ensure_default_plans(plan_model=Plan):
    for period, name, months, price, description in DEFAULT_PLANS:
        plan_model.objects.get_or_create(
            period=period,
            defaults={"name": name, "months": months, "price": price, "description": description},
        )


def period_end(start: date, months: int) -> date:
    return start + relativedelta(months=months) - timedelta(days=1)


def paid_periods(turf):
    return Subscription.objects.filter(turf=turf, status=Subscription.Status.ACTIVE)


def current_subscription(turf, today: date | None = None) -> Subscription | None:
    today = today or timezone.localdate()
    return (
        paid_periods(turf)
        .filter(starts_on__lte=today, ends_on__gte=today)
        .select_related("plan")
        .order_by("ends_on")
        .first()
    )


def paid_until(turf) -> date | None:
    return paid_periods(turf).aggregate(m=Max("ends_on"))["m"]


@dataclass
class Standing:
    state: str  # active | expiring | grace | expired | none
    current: Subscription | None
    paid_until: date | None
    days_left: int | None
    grace_until: date | None

    @property
    def can_operate(self) -> bool:
        return self.state in ("active", "expiring", "grace")


def standing(turf, today: date | None = None) -> Standing:
    today = today or timezone.localdate()
    current = current_subscription(turf, today)
    until = paid_until(turf)
    if current:
        days_left = (until - today).days  # counts queued periods too
        state = "expiring" if days_left < EXPIRY_WARNING_DAYS else "active"
        return Standing(state, current, until, days_left, None)
    if until and until < today:
        grace_until = until + timedelta(days=GRACE_DAYS)
        state = "grace" if today <= grace_until else "expired"
        return Standing(state, None, until, (until - today).days, grace_until)
    return Standing("none", None, until, None, None)


def operating_turf_ids(today: date | None = None):
    """Subquery of turfs allowed to take public bookings / appear on Explore."""
    today = today or timezone.localdate()
    return Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        starts_on__lte=today,
        ends_on__gte=today - timedelta(days=GRACE_DAYS),
    ).values("turf_id")


# --------------------------------------------------------------------- orders
@transaction.atomic
def create_order(turf, plan: Plan, *, created_by=None, note: str = "") -> Invoice:
    """Owner (or admin) picks a plan -> one open, unpaid invoice. A newer choice replaces an unpaid one."""
    if not plan.is_active:
        raise ValidationError({"plan": ["This plan is not available."]})
    open_invoices = Invoice.objects.select_for_update().filter(turf=turf, status__in=Invoice.OPEN)
    if open_invoices.filter(status=Invoice.Status.PENDING_VERIFICATION).exists():
        raise ValidationError(
            {"plan": ["A payment is being reviewed. You can change plan once TurfBari has checked it."]}
        )
    for invoice in open_invoices:
        cancel_order(invoice)
    subscription = Subscription.objects.create(
        turf=turf,
        plan=plan,
        price=plan.price,
        created_by=created_by,
        note=note,
        change_type=change_type_for(turf, plan),
    )
    return Invoice.objects.create(turf=turf, subscription=subscription, amount=plan.price)


def change_type_for(turf, plan: Plan) -> str:
    """new / renewal / upgrade / downgrade compared with the plan the turf has now (or had last)."""
    current = (
        current_subscription(turf) or paid_periods(turf).select_related("plan").order_by("-ends_on").first()
    )
    if current is None:
        return "new"
    if current.plan_id == plan.pk:
        return "renewal"
    # Plans differ by length (and price): longer or pricier = upgrade, shorter or cheaper = downgrade.
    if plan.months != current.plan.months:
        return "upgrade" if plan.months > current.plan.months else "downgrade"
    return "upgrade" if plan.price > current.plan.price else "downgrade"


def payable(invoice: Invoice) -> tuple[Decimal, Decimal]:
    """(fee, total) the owner must send by bKash: invoice amount plus TurfBari's payment charge."""
    from apps.common.models import PlatformSettings

    pct = PlatformSettings.load().subscription_fee_percent
    fee = (invoice.amount * pct / 100).quantize(Decimal("0.01"))
    return fee, invoice.amount + fee


def cancel_order(invoice: Invoice):
    if invoice.status == Invoice.Status.PAID:
        raise ValidationError({"invoice": ["A paid invoice cannot be cancelled."]})
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status", "updated_at"])
    invoice.transactions.filter(
        status__in=[PaymentTransaction.Status.INITIATED, PaymentTransaction.Status.PENDING_VERIFICATION]
    ).update(status=PaymentTransaction.Status.CANCELLED)
    Subscription.objects.filter(pk=invoice.subscription_id).update(status=Subscription.Status.CANCELLED)


@transaction.atomic
def mark_paid(invoice: Invoice) -> Subscription:
    """Idempotent: activates the subscription period exactly once."""
    invoice = (
        Invoice.objects.select_for_update().select_related("subscription__plan", "turf").get(pk=invoice.pk)
    )
    subscription = invoice.subscription
    if invoice.status == Invoice.Status.PAID:
        return subscription
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError({"invoice": ["This order was cancelled."]})
    # Lock the turf row so two payments for one turf cannot both compute the same start date.
    type(invoice.turf).objects.select_for_update().get(pk=invoice.turf_id)
    today = timezone.localdate()
    last_end = paid_until(invoice.turf)
    start = max(today, last_end + timedelta(days=1)) if last_end else today
    subscription.starts_on = start
    subscription.ends_on = period_end(start, subscription.plan.months)
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=["starts_on", "ends_on", "status", "updated_at"])
    invoice.status = Invoice.Status.PAID
    invoice.paid_at = timezone.now()
    invoice.save(update_fields=["status", "paid_at", "updated_at"])
    return subscription


# ------------------------------------------------------------- manual payments
def _open_invoice(invoice: Invoice) -> Invoice:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != Invoice.Status.UNPAID:
        raise ValidationError({"invoice": [f"This invoice is {invoice.get_status_display().lower()}."]})
    return invoice


@transaction.atomic
def submit_manual_payment(
    invoice, *, method, reference, sender_number="", user=None, amount_sent=None
) -> PaymentTransaction:
    """Records what the owner says they paid. Nothing changes on the plan until an admin verifies it."""
    invoice = _open_invoice(invoice)
    fee, total = payable(invoice)
    if amount_sent is None or amount_sent != total:
        raise ValidationError(
            {
                "amount_sent": [
                    f"Send the exact amount ৳{total:,.2f} (plan ৳{invoice.amount:,.2f} + charge ৳{fee:,.2f})."
                ]
            }
        )
    reference = reference.strip().upper()
    claimed = PaymentTransaction.objects.filter(
        method=method, reference__iexact=reference, channel=PaymentTransaction.Channel.MANUAL
    ).exclude(status__in=[PaymentTransaction.Status.REJECTED, PaymentTransaction.Status.CANCELLED])
    if claimed.exists():
        raise ValidationError({"reference": ["This transaction ID has already been submitted."]})
    tx = PaymentTransaction.objects.create(
        invoice=invoice,
        method=method,
        channel=PaymentTransaction.Channel.MANUAL,
        amount=invoice.amount,
        status=PaymentTransaction.Status.PENDING_VERIFICATION,
        reference=reference,
        sender_number=sender_number.strip(),
        submitted_by=user,
        amount_sent=amount_sent,
        fee=fee,
    )
    invoice.status = Invoice.Status.PENDING_VERIFICATION
    invoice.save(update_fields=["status", "updated_at"])
    return tx


@transaction.atomic
def review_payment(tx: PaymentTransaction, *, approve: bool, reviewer, note: str = "") -> PaymentTransaction:
    tx = PaymentTransaction.objects.select_for_update().select_related("invoice").get(pk=tx.pk)
    if tx.status != PaymentTransaction.Status.PENDING_VERIFICATION:
        raise ValidationError({"status": ["This payment was already reviewed."]})
    tx.status = PaymentTransaction.Status.VERIFIED if approve else PaymentTransaction.Status.REJECTED
    tx.reviewed_by, tx.reviewed_at, tx.note = reviewer, timezone.now(), note[:255]
    tx.save(update_fields=["status", "reviewed_by", "reviewed_at", "note", "updated_at"])
    if approve:
        subscription = mark_paid(tx.invoice)
        notify_owner_plan(tx.invoice.turf, subscription, approved=True, key=f"subtx:{tx.pk}:approved")
    else:
        Invoice.objects.filter(pk=tx.invoice_id, status=Invoice.Status.PENDING_VERIFICATION).update(
            status=Invoice.Status.UNPAID
        )
        notify_owner_plan(
            tx.invoice.turf,
            tx.invoice.subscription,
            approved=False,
            key=f"subtx:{tx.pk}:rejected",
            reason=note,
        )
    return tx


PLAN_APPROVED_BN = "TURFBARI: আপনার {plan} সাবস্ক্রিপশন {what} হয়েছে। মেয়াদ: {start} থেকে {end}। ধন্যবাদ।"
PLAN_REJECTED_BN = "TURFBARI: আপনার {plan} প্ল্যানের পেমেন্ট যাচাই করা যায়নি, তাই সাবস্ক্রিপশন পরিবর্তন হয়নি।{reason}"


def notify_owner_plan(turf, subscription, *, approved: bool, key: str, reason: str = "") -> None:
    """SMS to the owner from TurfBari's own (platform) SMS — never charged to the turf's wallet."""
    from apps.common.models import PlatformSettings
    from apps.notifications.models import SmsKind
    from apps.notifications.services import queue_sms
    from apps.notifications.tick import owner_phones

    if not PlatformSettings.load().platform_owner_sms:
        return
    if approved:
        what = {"renewal": "রিনিউ", "upgrade": "আপগ্রেড", "downgrade": "পরিবর্তন"}.get(
            subscription.change_type, "চালু"
        )
        body = PLAN_APPROVED_BN.format(
            plan=subscription.plan.name,
            what=what,
            start=f"{subscription.starts_on:%d/%m/%Y}",
            end=f"{subscription.ends_on:%d/%m/%Y}",
        )
        kind = SmsKind.SUBSCRIPTION_APPROVED
    else:
        body = PLAN_REJECTED_BN.format(
            plan=subscription.plan.name, reason=f" কারণ: {reason}।" if reason else ""
        )
        kind = SmsKind.SUBSCRIPTION_REJECTED
    for phone in owner_phones(turf):
        queue_sms(to=phone, body=body, kind=kind, turf=turf, dedupe_key=f"{key}:{phone[-10:]}")


@transaction.atomic
def assign_plan(turf, plan: Plan, *, paid: bool, by=None, method="cash", reference="", note="") -> Invoice:
    """Super Admin sets a turf's plan (at creation or later). `paid` records the money as received."""
    invoice = create_order(turf, plan, created_by=by, note=note or "Set by TurfBari admin")
    if paid:
        PaymentTransaction.objects.create(
            invoice=invoice,
            method=method,
            channel=PaymentTransaction.Channel.ADMIN,
            amount=invoice.amount,
            status=PaymentTransaction.Status.VERIFIED,
            reference=reference,
            submitted_by=by,
            reviewed_by=by,
            reviewed_at=timezone.now(),
        )
        mark_paid(invoice)
        invoice.refresh_from_db()
    return invoice


# ------------------------------------------------------------- promo codes
from . import promos  # noqa: E402  (shared promo rules: invoices + registrations)

normalize_code = promos.normalize_code


def promo_uses(promo: PromoCode, exclude_invoice=None) -> int:
    """Uses = paid/open invoices + registration reservations still held."""
    return promos.uses(promo, exclude_invoice=exclude_invoice)


def check_promo(code: str, turf, *, exclude_invoice=None, lock=False, plan=None, price=None) -> PromoCode:
    """Return the usable promo code for this turf's invoice, or raise a ValidationError the owner can read."""
    try:
        return promos.check(
            code,
            plan=plan,
            price=price if price is not None else Decimal("0"),
            turf=turf,
            lock=lock,
            exclude_invoice=exclude_invoice,
        )
    except ValidationError as exc:  # invoice screens show promo errors under "code"
        raise ValidationError(
            {"code": exc.detail.get("promo_code", ["This promo code is not valid."])}
        ) from None


def _reprice(invoice: Invoice, promo: PromoCode | None):
    base = invoice.amount + invoice.discount  # the plan price on this order
    discount = promos.discount_for(promo, base) if promo else Decimal("0.00")
    invoice.discount, invoice.amount, invoice.promo_code = discount, base - discount, promo
    invoice.save(update_fields=["discount", "amount", "promo_code", "updated_at"])
    Subscription.objects.filter(pk=invoice.subscription_id).update(price=invoice.amount)


@transaction.atomic
def apply_promo(invoice: Invoice, code: str, *, user=None) -> Invoice:
    invoice = _open_invoice(invoice)
    promo = check_promo(
        code,
        invoice.turf,
        exclude_invoice=invoice,
        lock=True,
        plan=invoice.subscription.plan,
        price=invoice.amount + invoice.discount,
    )
    _reprice(invoice, promo)
    if invoice.amount == 0:  # 100% off: nothing to pay, but TurfBari still approves the plan change
        PaymentTransaction.objects.create(
            invoice=invoice,
            method=PaymentTransaction.Method.PROMO,
            channel=PaymentTransaction.Channel.PROMO,
            amount=Decimal("0.00"),
            status=PaymentTransaction.Status.PENDING_VERIFICATION,
            reference=promo.code,
            submitted_by=user,
            note=f"100% promo code {promo.code}",
        )
        invoice.status = Invoice.Status.PENDING_VERIFICATION
        invoice.save(update_fields=["status", "updated_at"])
    invoice.refresh_from_db()
    return invoice


@transaction.atomic
def remove_promo(invoice: Invoice) -> Invoice:
    invoice = _open_invoice(invoice)
    _reprice(invoice, None)
    return invoice
