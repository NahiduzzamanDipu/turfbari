"""'Register your turf' applications reviewed by the Super Admin."""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.common.money import MoneyField

REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_registration_reference() -> str:
    return f"REG-{timezone.localdate():%y%m}-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(5))


class TurfApplication(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        CONTACTED = "contacted", "Contacted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PAYMENT_REVIEW = "payment_review", "Payment under review"
        PAYMENT_REJECTED = "payment_rejected", "Payment not accepted"

    turf_name = models.CharField(max_length=120)
    owner_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    district = models.ForeignKey("locations.District", on_delete=models.PROTECT, related_name="+")
    area = models.ForeignKey(
        "locations.Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    address = models.CharField(max_length=255)
    turf_type = models.CharField(max_length=10, default="outdoor")
    sector = models.ForeignKey(
        "legal.Sector", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    number_of_fields = models.PositiveSmallIntegerField(default=1)
    message = models.TextField(blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    # Registration with payment: reference shown to the applicant (status page) and the chosen plan.
    reference = models.CharField(max_length=20, unique=True, null=True, blank=True)
    plan = models.ForeignKey(
        "subscriptions.Plan", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    turf = models.OneToOneField(
        "turfs.Turf", on_delete=models.SET_NULL, null=True, blank=True, related_name="source_application"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.turf_name} ({self.get_status_display()})"


class RegistrationPayment(BaseModel):
    """One bKash payment submission for a registration. TurfBari checks it by hand; nothing activates on
    submission. Rejected submissions are kept forever; a corrected one is a new row. Prices and the promo
    are frozen here, so later edits to plans or promo codes never change history."""

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Awaiting verification"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    application = models.ForeignKey(TurfApplication, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey("subscriptions.Plan", on_delete=models.PROTECT, related_name="+")
    list_price = MoneyField()
    discount = MoneyField()
    amount_due = MoneyField()
    promo = models.ForeignKey(
        "subscriptions.PromoCode", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    promo_snapshot = models.JSONField(default=dict, blank=True)
    redemption = models.ForeignKey(
        "subscriptions.PromoRedemption", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    method = models.CharField(max_length=10, default="bkash")
    sender_number = models.CharField(max_length=20, blank=True)
    amount_sent = MoneyField()
    trx_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True
    )  # null only for ৳0 (100% off)
    note = models.CharField(max_length=255, blank=True)
    receiving_number = models.CharField(max_length=20, blank=True)  # snapshot at submission
    instructions = models.TextField(blank=True)  # snapshot at submission
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING_VERIFICATION, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    can_resubmit = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.application.reference} ({self.status})"
