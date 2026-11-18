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

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"


class Booking(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"
        NO_SHOW = "no_show", "No-show"

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        PHONE = "phone", "Phone"
        ONLINE = "online", "Online request"
        STAFF = "staff", "Staff"

    # Statuses that hold the slot.
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

    class Meta:
        ordering = ["-start"]
        indexes = [
            models.Index(fields=["field", "start", "end"]),
            models.Index(fields=["turf", "start"]),
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
