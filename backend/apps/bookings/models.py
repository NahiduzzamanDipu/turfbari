"""Bookings, customers, payments and maintenance blocks. All tenant-scoped by `turf`."""

import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.common.money import MoneyField

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def new_reference() -> str:
    suffix = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(5))
    return f"TRF-{timezone.localdate():%y%m}-{suffix}"


class Customer(BaseModel):
    """Identified per turf by normalised BD phone number. No customer accounts."""

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["turf", "phone"], name="uniq_customer_phone_per_turf")]
        # The per-customer daily booking limit looks a phone up across all turfs.
        indexes = [models.Index(fields=["phone"], name="customer_phone_idx")]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"


class BookingSeries(BaseModel):
    """An advance/recurring booking made by the turf: one row per series; every date is a normal Booking
    (series + occurrence_number) so calendars, payments, reports and SMS treat it like any booking."""

    class Recurrence(models.TextChoices):
        DAILY = "daily", "Every day"
        WEEKDAYS = "weekdays", "Selected days of the week"
        WEEKLY = "weekly", "Every week on one day"
        CUSTOM = "custom", "Custom dates"
        ONCE = "once", "One-time advance booking"

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Payment not received"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="booking_series")
    field = models.ForeignKey("turfs.TurfField", on_delete=models.PROTECT, related_name="booking_series")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="booking_series")
    reference = models.CharField(max_length=20, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()  # earlier than start_time = ends the next day (overnight)
    recurrence = models.CharField(max_length=10, choices=Recurrence.choices)
    weekdays = models.JSONField(default=list, blank=True)  # 0=Monday … 6=Sunday
    custom_dates = models.JSONField(default=list, blank=True)  # ISO dates for CUSTOM
    start_date = models.DateField()
    end_date = models.DateField()
    occurrences_count = models.PositiveSmallIntegerField(default=0)
    total = MoneyField()  # price snapshot of the dates booked at creation
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    team_name = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["turf", "status"]), models.Index(fields=["turf", "start_date"])]

    def __str__(self) -> str:
        return self.reference


class BookingQuerySet(models.QuerySet):
    def blocking(self, now=None):
        """Bookings that occupy their slot right now: confirmed/completed, plus pending ones whose
        payment hold hasn't run out (staff-made pending bookings have no hold and always block)."""
        now = now or timezone.now()
        return self.filter(
            models.Q(status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED])
            | models.Q(status=Booking.Status.PENDING)
            & (models.Q(hold_expires_at__isnull=True) | models.Q(hold_expires_at__gt=now))
        )

    def awaiting_review(self, now=None):
        """Pending bookings an owner/manager still has to act on."""
        return self.blocking(now).filter(status=Booking.Status.PENDING)


class Booking(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting verification"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"
        NO_SHOW = "no_show", "No-show"
        EXPIRED = "expired", "Expired"

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        PHONE = "phone", "Phone"
        ONLINE = "online", "Online request"
        STAFF = "staff", "Staff"

    # Statuses that can hold the slot (PENDING only until hold_expires_at; see BookingQuerySet.blocking).
    BLOCKING = (Status.PENDING, Status.CONFIRMED, Status.COMPLETED)

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="bookings")
    field = models.ForeignKey("turfs.TurfField", on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="bookings")
    reference = models.CharField(max_length=20, unique=True, default=new_reference)
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.STAFF)
    team_name = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    subtotal = MoneyField()
    discount = MoneyField()
    total = MoneyField()
    amount_paid = MoneyField()  # maintained from Payment rows
    price_snapshot = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Online requests keep the slot only until the owner verifies the bKash payment or this passes.
    hold_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Public requests: how many offered slots this booking covers (the per-customer limit counts these),
    # the client's idempotency key (a retried submit returns the same booking) and the agreed terms.
    slot_count = models.PositiveSmallIntegerField(default=1)
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    terms_version = models.ForeignKey(
        "common.TermsVersion", on_delete=models.PROTECT, null=True, blank=True, related_name="bookings"
    )
    terms_agreed_at = models.DateTimeField(null=True, blank=True)
    # Part of an advance/recurring series (null for ordinary bookings).
    series = models.ForeignKey(
        BookingSeries, on_delete=models.PROTECT, null=True, blank=True, related_name="occurrences"
    )
    occurrence_number = models.PositiveSmallIntegerField(null=True, blank=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ["-start"]
        indexes = [
            models.Index(fields=["field", "start", "end"]),
            models.Index(fields=["turf", "start"]),
            models.Index(fields=["series", "start"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["series", "occurrence_number"], name="uniq_series_occurrence"),
        ]

    def __str__(self) -> str:
        return self.reference

    @property
    def due(self) -> Decimal:
        return max(self.total - self.amount_paid, Decimal("0.00"))

    @property
    def payment_status(self) -> str:
        if self.amount_paid <= 0:
            return "unpaid"
        return "paid" if self.amount_paid >= self.total else "partial"


class Payment(BaseModel):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"
        CARD = "card", "Card"
        BANK = "bank", "Bank transfer"

    class Kind(models.TextChoices):
        PAYMENT = "payment", "Payment"
        REFUND = "refund", "Refund"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="payments")
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    amount = MoneyField()
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PAYMENT)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(max_length=80, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-paid_at"]


class MaintenanceBlock(BaseModel):
    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="maintenance_blocks")
    field = models.ForeignKey("turfs.TurfField", on_delete=models.CASCADE, related_name="maintenance_blocks")
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-start"]
        indexes = [models.Index(fields=["field", "start", "end"])]


class SlotHold(BaseModel):
    """A slot a player has selected on the public page, kept for them for HOLD_MINUTES.

    Other players see it as "someone is booking". If no request is sent before it lapses, the slot
    frees up and that visitor's IP must wait COOLDOWN_MINUTES before selecting again (see holds.py).
    Only a keyed hash of the IP is stored.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released by the player"
        CONVERTED = "converted", "Turned into a booking request"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="slot_holds")
    field = models.ForeignKey("turfs.TurfField", on_delete=models.CASCADE, related_name="slot_holds")
    start = models.DateTimeField()
    end = models.DateTimeField()
    token = models.CharField(max_length=64, unique=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    window_started_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["field", "status", "expires_at"])]

    def __str__(self) -> str:
        return f"Hold {self.field_id} {self.start:%Y-%m-%d %H:%M} ({self.status})"


class PaymentSubmission(BaseModel):
    """What a customer says they paid by bKash Send Money. Never trusted until a person verifies it in
    the bKash account and approves; approval records a real Payment and confirms the booking."""

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting verification"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="payment_submissions")
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="payment_submission")
    amount = MoneyField()
    sender_number = models.CharField(max_length=20)  # the bKash account the money came from
    trx_id = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One bKash transaction can pay for one booking only.
            models.UniqueConstraint(fields=["turf", "trx_id"], name="uniq_bkash_trx_per_turf"),
        ]
        indexes = [models.Index(fields=["turf", "status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.trx_id} ৳{self.amount} for {self.booking_id}"
