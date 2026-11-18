"""Append-only record of who did what. Rows are never edited; names are snapshotted so history
survives renamed turfs and deleted users."""

import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class Category(models.TextChoices):
        BOOKING = "booking", "Bookings"
        PAYMENT = "payment", "Payments"
        CUSTOMER = "customer", "Customers"
        SETUP = "setup", "Fields, hours & pricing"
        SETTINGS = "settings", "Settings & pictures"
        TEAM = "team", "Team"
        EXPENSE = "expense", "Expenses"
        SUBSCRIPTION = "subscription", "Subscription"
        ACCOUNT = "account", "Sign-in & account"
        PLATFORM = "platform", "Platform admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_label = models.CharField(max_length=254, blank=True)  # email/name at the time; "" = public/system
    turf = models.ForeignKey(
        "turfs.Turf", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    turf_name = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=16, choices=Category.choices, db_index=True)
    action = models.CharField(max_length=60, db_index=True)  # e.g. "booking.status"
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    summary = models.CharField(max_length=255)
    ip = models.GenericIPAddressField(null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["turf", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.summary}"
