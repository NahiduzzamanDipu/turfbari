"""Short-lived, isolated data for public product demonstrations."""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class DemoWorkspace(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"
        EXPIRED = "expired", "Expired"

    name = models.CharField(max_length=100, default="TURFBARI Demo Arena")
    owner_name = models.CharField(max_length=100, default="Demo Turf Owner")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    access_token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    last_access_at = models.DateTimeField(null=True, blank=True)
    reset_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "expires_at"])]


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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "phone"], name="demo_customer_phone_unique")
        ]
        indexes = [models.Index(fields=["workspace", "name"])]


class DemoBooking(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    workspace = models.ForeignKey(DemoWorkspace, related_name="bookings", on_delete=models.CASCADE)
    customer = models.ForeignKey(DemoCustomer, related_name="bookings", on_delete=models.PROTECT)
    slot = models.ForeignKey(DemoSlot, related_name="bookings", on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=24, unique=True)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["date", "start_time"]
        indexes = [models.Index(fields=["workspace", "date", "status"])]


class DemoActivity(BaseModel):
    workspace = models.ForeignKey(DemoWorkspace, related_name="activity", on_delete=models.CASCADE)
    actor_type = models.CharField(max_length=12, default="visitor")
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=240)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "-created_at"])]
