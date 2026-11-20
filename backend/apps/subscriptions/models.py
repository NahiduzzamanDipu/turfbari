"""TurfBari platform plans. Subscriptions never auto-renew: each period is a separate, prepaid order."""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.common.money import MoneyField

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_invoice_number() -> str:
    suffix = "".join(secrets.choice(ALPHABET) for _ in range(6))
    return f"INV-{timezone.localdate():%y%m}-{suffix}"


def new_tran_id() -> str:
    return "TXN" + secrets.token_hex(10).upper()


class Plan(BaseModel):
    class Period(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        HALF_YEARLY = "half_yearly", "Half-yearly"
        YEARLY = "yearly", "Yearly"

    MONTHS = {Period.MONTHLY: 1, Period.HALF_YEARLY: 6, Period.YEARLY: 12}

    period = models.CharField(max_length=12, choices=Period.choices, unique=True)
    name = models.CharField(max_length=60)
    months = models.PositiveSmallIntegerField()
    price = MoneyField()
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["months"]

    def __str__(self) -> str:
        return self.name


class Subscription(BaseModel):
    """One prepaid period for one turf. `active` + dates decide whether it is current, scheduled or over."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        ACTIVE = "active", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True
    )
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)  # inclusive
    price = MoneyField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # new | renewal | upgrade | downgrade, decided when the owner asks (compared with the plan they had).
    change_type = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["-ends_on", "-created_at"]
        indexes = [models.Index(fields=["turf", "status", "ends_on"])]

    def __str__(self) -> str:
        return f"{self.turf} · {self.plan} ({self.status})"


class PromoCode(BaseModel):
    """A TurfBari-issued discount code an owner can apply to an unpaid subscription invoice.

    A use is counted while the invoice is open (reserved) or paid; cancelling the invoice releases it.
    Each turf can pay with the same code only once.
    """

    code = models.CharField(max_length=30, unique=True)  # stored upper-case
    percent_off = models.PositiveSmallIntegerField()  # 1-100
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)  # inclusive
    max_uses = models.PositiveIntegerField(null=True, blank=True)  # blank = unlimited
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.percent_off}%)"


class Invoice(BaseModel):
    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING_VERIFICATION = "pending_verification", "Payment under review"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    OPEN = (Status.UNPAID, Status.PENDING_VERIFICATION)

    number = models.CharField(max_length=20, unique=True, default=new_invoice_number)
    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="invoices")
    subscription = models.OneToOneField(Subscription, on_delete=models.CASCADE, related_name="invoice")
    amount = MoneyField()  # what the owner pays (after any promo discount)
    discount = MoneyField()  # promo discount taken off the plan price
    promo_code = models.ForeignKey(
        PromoCode, on_delete=models.PROTECT, null=True, blank=True, related_name="invoices"
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.UNPAID, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    @property
    def list_amount(self):
        return self.amount + self.discount


class PaymentTransaction(BaseModel):
    class Method(models.TextChoices):
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"
        BANK = "bank", "Bank transfer"
        ONLINE = "online", "Card / mobile banking (online)"
        CASH = "cash", "Cash"
        PROMO = "promo", "Promo code (100% off)"

    class Channel(models.TextChoices):
        MANUAL = "manual", "Sent manually, verified by TurfBari"
        GATEWAY = "gateway", "Online payment gateway"
        ADMIN = "admin", "Recorded by TurfBari admin"
        PROMO = "promo", "Fully covered by a promo code"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Started"
        PENDING_VERIFICATION = "pending_verification", "Under review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="transactions")
    method = models.CharField(max_length=10, choices=Method.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    amount = MoneyField()
    status = models.CharField(max_length=24, choices=Status.choices, db_index=True)
    tran_id = models.CharField(max_length=40, unique=True, default=new_tran_id)  # gateway idempotency key
    reference = models.CharField(
        max_length=60, blank=True
    )  # bKash/Nagad TrxID, bank ref, gateway bank_tran_id
    sender_number = models.CharField(max_length=20, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=255, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # Manual bKash payments: what the owner says they sent and the payment charge included in it.
    amount_sent = MoneyField(null=True, blank=True, default=None)
    fee = MoneyField()

    class Meta:
        ordering = ["-created_at"]
        # MariaDB has no partial unique indexes: "a TrxID is claimed once" is enforced in services.
        indexes = [models.Index(fields=["method", "reference"])]

    def __str__(self) -> str:
        return f"{self.tran_id} {self.method} {self.amount}"


class ReminderLog(BaseModel):
    """One row per (paid period, days-before, channel): the unique key makes reminders idempotent."""

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (no owner email)"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="reminders")
    days_before = models.PositiveSmallIntegerField()
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    status = models.CharField(max_length=10, choices=Status.choices)
    recipients = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "days_before", "channel"], name="uniq_subscription_reminder"
            )
        ]

    def __str__(self) -> str:
        return f"{self.subscription} -{self.days_before}d {self.status}"
