"""Short-lived, isolated data for public product demonstrations."""

import uuid

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class DemoWorkspace(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    name = models.CharField(max_length=100, default="TURFBARI Demo Arena")
    owner_name = models.CharField(max_length=100, default="Demo Turf Owner")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    public_key = models.CharField(max_length=20, unique=True, null=True, blank=True)
    last_access_at = models.DateTimeField(null=True, blank=True)
    last_reset_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reset_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "public_key"], name="demo_demowo_status_public_idx")]


class DemoSlot(BaseModel):
    class Category(models.TextChoices):
        MORNING = "morning", "Morning"
        EVENING = "evening", "Evening"
        NIGHT = "night", "Night"
        MIDNIGHT = "midnight", "Midnight"

    workspace = models.ForeignKey(DemoWorkspace, related_name="slots", on_delete=models.CASCADE)
    label = models.CharField(max_length=80)
    start_time = models.TimeField()
    end_time = models.TimeField()
    category = models.CharField(max_length=10, choices=Category.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    enabled = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "start_time"]
        indexes = [models.Index(fields=["workspace", "enabled", "start_time"])]


class DemoCustomer(BaseModel):
    workspace = models.ForeignKey(DemoWorkspace, related_name="customers", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    phone_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["workspace", "name"])]


class DemoBooking(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Awaiting demo verification"
        APPROVED = "approved", "Approved in demo"
        REJECTED = "rejected", "Rejected in demo"

    workspace = models.ForeignKey(DemoWorkspace, related_name="bookings", on_delete=models.CASCADE)
    customer = models.ForeignKey(DemoCustomer, related_name="bookings", on_delete=models.PROTECT)
    slot = models.ForeignKey(DemoSlot, related_name="bookings", on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    slot_count = models.PositiveSmallIntegerField(default=1)
    reference = models.CharField(max_length=24, unique=True)
    note = models.CharField(max_length=500, blank=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sender_phone = models.CharField(max_length=20, blank=True)
    transaction_reference = models.CharField(max_length=32, blank=True)
    payment_status = models.CharField(
        max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    terms_version_ids = models.JSONField(default=list)
    terms_agreed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True)
    reviewed_by = models.CharField(max_length=80, blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    hold_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["date", "start_time"]
        indexes = [models.Index(fields=["workspace", "date", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="demo_booking_idempotency_unique",
            ),
        ]


class DemoHold(BaseModel):
    """A short-lived slot lock kept entirely separate from production bookings."""

    workspace = models.ForeignKey(DemoWorkspace, related_name="holds", on_delete=models.CASCADE)
    slot = models.ForeignKey(DemoSlot, related_name="holds", on_delete=models.CASCADE)
    date = models.DateField()
    visitor_id = models.CharField(max_length=64)
    token = models.UUIDField(default=uuid.uuid4, db_index=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "date", "slot"], name="demo_hold_slot_day_unique")
        ]
        indexes = [models.Index(fields=["workspace", "date", "expires_at"])]


class DemoSms(BaseModel):
    """An in-app simulated SMS; this model never dispatches to a provider or charges a wallet."""

    class Kind(models.TextChoices):
        BOOKING_REQUEST = "booking_request", "Booking request"
        BOOKING_APPROVED = "booking_approved", "Booking approved"
        BOOKING_REJECTED = "booking_rejected", "Booking rejected"
        BOOKING_CANCELLED = "booking_cancelled", "Booking cancelled"

    workspace = models.ForeignKey(DemoWorkspace, related_name="sms_messages", on_delete=models.CASCADE)
    booking = models.ForeignKey(
        DemoBooking, related_name="sms_messages", null=True, blank=True, on_delete=models.CASCADE
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    recipient = models.CharField(max_length=20, blank=True)
    body = models.CharField(max_length=500)
    status = models.CharField(max_length=20, default="simulated")

    class Meta:
        ordering = ["-created_at"]


class DemoActivity(BaseModel):
    workspace = models.ForeignKey(DemoWorkspace, related_name="activity", on_delete=models.CASCADE)
    actor_type = models.CharField(max_length=12, default="visitor")
    actor_id = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=240)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "-created_at"])]
