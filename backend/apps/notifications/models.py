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
    OWNER_BOOKING_CONFIRMED = "owner_booking_confirmed", "Booking made by the turf"
    CUSTOM = "custom", "Single SMS"
    CAMPAIGN = "campaign", "Bulk SMS"
    WALLET_CREDITED = "wallet_credited", "SMS wallet recharged"
    WALLET_RECHARGE_REJECTED = "wallet_recharge_rejected", "SMS wallet recharge rejected"
    SUBSCRIPTION_APPROVED = "subscription_approved", "Plan approved"
    SUBSCRIPTION_REJECTED = "subscription_rejected", "Plan payment rejected"
    ACCOUNT_CREDENTIALS = "account_credentials", "New account login details"
    CREDENTIAL_RESET = "credential_reset", "Password reset by TurfBari"
    SERIES_CONFIRMED = "series_confirmed", "Advance/recurring booking confirmed"
    SERIES_UPDATED = "series_updated", "Advance/recurring booking changed"
    SERIES_CANCELLED = "series_cancelled", "Advance/recurring booking cancelled"


class SmsMessage(BaseModel):
    """One logical message (what usage is counted on). Each provider call is an SmsAttempt."""

    class Scope(models.TextChoices):
        TENANT = "tenant", "Turf (customer SMS)"
        PLATFORM = "platform", "TurfBari (plan notices, sign-in codes)"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"  # accepted by BulkSMSBD (it has no delivery-report API)
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Unknown — check before retrying"
        SKIPPED = "skipped", "Not sent"
        BLOCKED = "blocked", "Blocked"  # wallet empty / turned off by admin; can be retried later

    class BlockReason(models.TextChoices):
        INSUFFICIENT_BALANCE = "insufficient_balance", "Not enough SMS wallet balance"
        ACCOUNT_DISABLED = "account_disabled", "SMS turned off for this account by TurfBari"
        TYPE_DISABLED = "type_disabled", "This SMS type is turned off by TurfBari"
        NO_PRICING = "no_pricing", "SMS price not set by TurfBari yet"
        MONTHLY_LIMIT = "monthly_limit", "Monthly SMS limit reached"
        PLAN_DISABLED = "plan_disabled", "SMS not included in this plan"
        CANCELLED = "cancelled", "Campaign cancelled"

    turf = models.ForeignKey(
        "turfs.Turf", on_delete=models.SET_NULL, null=True, blank=True, related_name="sms_messages"
    )
    to = models.CharField(max_length=20)  # 8801XXXXXXXXX, the format the provider wants
    body = models.TextField()
    kind = models.CharField(max_length=30, choices=SmsKind.choices)
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.TENANT, db_index=True)
    provider_ref = models.CharField(max_length=64, blank=True)  # BulkSMSBD message id, when it returns one
    block_reason = models.CharField(max_length=24, choices=BlockReason.choices, blank=True)
    # Billing: the price snapshot taken when queued, and the net amount charged (the ledger is the truth).
    price_per_segment = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    charged_amount = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    campaign = models.ForeignKey(
        "notifications.SmsCampaign", on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
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


class SmsAttempt(models.Model):
    """One call to the provider for a message. Retries add attempts; usage counts messages, not attempts."""

    message = models.ForeignKey(SmsMessage, on_delete=models.CASCADE, related_name="attempt_log")
    number = models.PositiveSmallIntegerField()
    ok = models.BooleanField(default=False)
    provider_code = models.CharField(max_length=20, blank=True)
    provider_message = models.CharField(max_length=255, blank=True)
    provider_ref = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["message", "number"]
        constraints = [models.UniqueConstraint(fields=["message", "number"], name="uniq_sms_attempt_number")]

    def __str__(self) -> str:
        return f"Attempt {self.number} for {self.message_id}"


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
    # Saved from Admin -> API, Fernet-encrypted. Overrides BULKSMSBD_API_KEY; never sent to browsers.
    api_key_encrypted = models.TextField(blank=True)
    sender_is_masking = models.BooleanField(default=False)  # masking (brand-name) sender IDs cost more
    per_turf_monthly_limit = models.PositiveIntegerField(default=0, help_text="0 = no limit")
    subscription_reminder_days = models.JSONField(default=list, blank=True)  # e.g. [7, 3, 1]
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "SMS settings"

    @classmethod
    def load(cls) -> "SmsConfig":
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"subscription_reminder_days": [7, 3, 1]})
        return obj


# ======================================================================= prepaid SMS wallet
class SmsPricing(models.Model):
    """BDT price per billable SMS segment. A new row (with its effective time) replaces the old price
    from then on; each charge stores the price it used, so history never changes."""

    price_per_segment = models.DecimalField(max_digits=8, decimal_places=4)  # non-masking sender
    masking_price_per_segment = models.DecimalField(max_digits=8, decimal_places=4)
    bulk_price_per_segment = models.DecimalField(max_digits=8, decimal_places=4)  # campaigns
    effective_from = models.DateTimeField(db_index=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-id"]

    def __str__(self) -> str:
        return f"BDT {self.price_per_segment}/segment from {self.effective_from:%Y-%m-%d}"


class SmsWallet(BaseModel):
    """Prepaid SMS balance of one turf. Only ever changed together with a WalletTransaction row."""

    turf = models.OneToOneField("turfs.Turf", on_delete=models.CASCADE, related_name="sms_wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="sms_wallet_not_negative")
        ]

    def __str__(self) -> str:
        return f"{self.turf} BDT {self.balance}"


class WalletTransaction(models.Model):
    """Immutable ledger entry. Credits are positive, debits negative; corrections are new entries."""

    class Kind(models.TextChoices):
        RECHARGE = "recharge", "Recharge (bKash, approved)"
        ADMIN_CREDIT = "admin_credit", "Credit by TurfBari"
        SMS_CHARGE = "sms_charge", "SMS charge"
        SMS_REFUND = "sms_refund", "SMS refund"
        ADJUSTMENT = "adjustment", "Adjustment by TurfBari"

    wallet = models.ForeignKey(SmsWallet, on_delete=models.PROTECT, related_name="transactions")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=4)
    balance_after = models.DecimalField(max_digits=12, decimal_places=4)
    idempotency_key = models.CharField(max_length=100, unique=True)
    sms = models.ForeignKey(
        "notifications.SmsMessage", on_delete=models.PROTECT, null=True, blank=True, related_name="ledger"
    )
    recharge = models.ForeignKey(
        "notifications.SmsRechargeRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger",
    )
    segments = models.PositiveSmallIntegerField(default=0)
    price_per_segment = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["wallet", "created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount} -> {self.balance_after}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Wallet ledger entries are immutable; add an adjustment instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Wallet ledger entries can't be deleted.")


class SmsAccountControl(models.Model):
    """Super Admin switches for one turf's SMS. No row = everything on."""

    turf = models.OneToOneField("turfs.Turf", on_delete=models.CASCADE, related_name="sms_control")
    all_enabled = models.BooleanField(default=True)
    booking_confirmed = models.BooleanField(default=True)
    rejection_cancellation = models.BooleanField(default=True)
    reminder = models.BooleanField(default=True)
    owner_booking = models.BooleanField(default=True)
    single = models.BooleanField(default=True)
    bulk = models.BooleanField(default=True)
    monthly_limit = models.PositiveIntegerField(default=0, help_text="0 = no account-specific limit")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"SMS controls for {self.turf}"


class SmsRechargeRequest(BaseModel):
    """A turf owner's bKash payment to TurfBari for SMS credit. Credited only after admin approval."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for TurfBari"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="sms_recharges")
    wallet_amount = models.DecimalField(max_digits=12, decimal_places=2)  # credited on approval
    fee_percent = models.DecimalField(max_digits=5, decimal_places=2)  # bKash charge rate at submission
    fee = models.DecimalField(max_digits=12, decimal_places=2)  # bKash charge: never wallet money
    total_expected = models.DecimalField(max_digits=12, decimal_places=2)
    amount_sent = models.DecimalField(max_digits=12, decimal_places=2)
    sender_number = models.CharField(max_length=20)
    trx_id = models.CharField(max_length=20, unique=True)
    note = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Recharge BDT {self.wallet_amount} for {self.turf} ({self.status})"


class SmsCampaign(BaseModel):
    """A bulk SMS from one turf: one SmsMessage per recipient, sent in batches by the tick."""

    class Status(models.TextChoices):
        SENDING = "sending", "Sending"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="sms_campaigns")
    name = models.CharField(max_length=120)
    template = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENDING, db_index=True)
    recipients_count = models.PositiveIntegerField(default=0)
    estimated_segments = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    price_per_segment = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    idempotency_key = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.turf})"
