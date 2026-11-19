"""SMS outbox, editable message templates and the platform SMS switchboard.

Every SMS TurfBari sends is an SmsMessage row first (an outbox): it is written in the same transaction
as the event that caused it, sent after commit, retried by the tick, and kept as the log. A unique
`dedupe_key` (e.g. "booking:<id>:confirmed") makes the same notification impossible to queue twice.
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class SmsKind(models.TextChoices):
    BOOKING_CONFIRMED = "booking_confirmed", "Booking confirmed"
    PAYMENT_REJECTED = "payment_rejected", "Payment rejected"
    BOOKING_CANCELLED = "booking_cancelled", "Booking cancelled"
    BOOKING_REMINDER = "booking_reminder", "Booking reminder"
    SUBSCRIPTION_REMINDER = "subscription_reminder", "Plan ends soon"
    SUBSCRIPTION_EXPIRED = "subscription_expired", "Plan ended"
    PASSWORD_RESET = "password_reset", "Password reset code"
    TEST = "test", "Test message"


class SmsMessage(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"  # accepted by BulkSMSBD (it has no delivery-report API)
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Unknown — check before retrying"
        SKIPPED = "skipped", "Not sent"

    turf = models.ForeignKey(
        "turfs.Turf", on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_messages"
    )
    to = models.CharField(max_length=20)  # 8801XXXXXXXXX, the format the provider wants
    body = models.TextField()
    kind = models.CharField(max_length=30, choices=SmsKind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    dedupe_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    segments = models.PositiveSmallIntegerField(default=1)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    provider_code = models.CharField(max_length=20, blank=True)
    provider_message = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_messages"
    )
    related_ref = models.CharField(max_length=60, blank=True)  # e.g. subscription id
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["turf", "created_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
        ]

    def __str__(self) -> str:
        return f"SMS {self.kind} to {self.to} ({self.status})"

    @property
    def masked_to(self) -> str:
        return f"{self.to[:-6]}***{self.to[-3:]}" if len(self.to) > 8 else self.to


class SmsTemplate(models.Model):
    """Platform-wide wording for each automatic SMS. Placeholders like {turf} are filled per message."""

    kind = models.CharField(max_length=30, choices=SmsKind.choices, unique=True)
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self) -> str:
        return self.get_kind_display()


class SmsConfig(models.Model):
    """Single row: platform switches the Super Admin controls. The API key itself lives only in the
    environment (BULKSMSBD_API_KEY) and is never stored in the database or shown in the UI."""

    enabled = models.BooleanField(default=True)
    sender_id = models.CharField(max_length=20, blank=True, help_text="Blank = BULKSMSBD_SENDER_ID")
    per_turf_monthly_limit = models.PositiveIntegerField(default=0, help_text="0 = no limit")
    subscription_reminder_days = models.JSONField(default=list, blank=True)  # e.g. [7, 3, 1]
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "SMS settings"

    @classmethod
    def load(cls) -> "SmsConfig":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"subscription_reminder_days": [7, 3, 1]})
        return obj
