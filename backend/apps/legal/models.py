"""Platform legal documents: sectors, versioned documents and immutable acceptance records.

- A LegalDocument is one policy (e.g. "Privacy Policy", or "Booking rules" for one sector). Documents with
  no sector apply to the whole platform; sector documents apply only to businesses in that sector and add
  to (never replace) the platform documents.
- Each change is a LegalDocumentVersion. Published versions are immutable; editing creates a new draft.
  The "current" version is the newest published one whose effective time has passed.
- Every agreement is a LegalAcceptance row pointing at the exact version accepted, with who/which
  business/what action/which booking. Rows are never edited or deleted.
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Sector(BaseModel):
    """A business sector TurfBari serves (admin-managed; nothing about sectors is hard-coded)."""

    name_en = models.CharField(max_length=120)
    name_bn = models.CharField(max_length=120, blank=True)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name_en"]

    def __str__(self) -> str:
        return self.name_en


class Audience(models.TextChoices):
    CUSTOMER = "customer", "Customers (public)"
    OWNER = "owner", "Business owners"
    MANAGER = "manager", "Managers & staff"
    ADMIN = "admin", "Platform administrators"


class Action(models.TextChoices):
    REGISTRATION = "registration", "Registering a business / account"
    ACCOUNT = "account", "Using an account (sign-in)"
    BOOKING = "booking", "Making a booking / reservation"
    SUBSCRIPTION = "subscription", "Buying or renewing a plan"
    SMS_RECHARGE = "sms_recharge", "Recharging the SMS wallet"


class LegalDocument(BaseModel):
    class Category(models.TextChoices):
        TERMS = "terms", "General Terms & Conditions"
        PRIVACY = "privacy", "Privacy Policy"
        RULES = "rules", "Platform Rules & Regulations"
        SECTOR_TERMS = "sector_terms", "Sector Terms & Conditions"
        SECTOR_RULES = "sector_rules", "Sector Rules & Regulations"
        BOOKING = "booking", "Booking & Reservation Policy"
        REFUND = "refund", "Payment, Refund & Cancellation Policy"
        SUBSCRIPTION = "subscription", "Subscription & Billing Policy"
        SMS = "sms", "SMS Wallet & Communication Policy"
        ACCOUNT_USAGE = "account_usage", "Account Usage Policy"
        PROHIBITED = "prohibited", "Prohibited Activities & User Responsibilities"

    category = models.CharField(max_length=16, choices=Category.choices)
    sector = models.ForeignKey(
        Sector, on_delete=models.PROTECT, null=True, blank=True, related_name="documents"
    )
    slug = models.SlugField(max_length=80)  # public URL part: /legal/<slug> or /legal/sector/<sector>/<slug>
    audiences = models.JSONField(default=list)  # Audience values this document is for
    actions = models.JSONField(default=list)  # Action values that need agreement to it
    is_mandatory = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_archived = models.BooleanField(default=False)  # retired: no longer shown or required

    class Meta:
        ordering = ["sector__sort_order", "sort_order", "category"]
        constraints = [
            models.UniqueConstraint(fields=["category", "sector"], name="uniq_legal_doc_category_sector"),
            models.UniqueConstraint(
                fields=["category"], condition=models.Q(sector__isnull=True), name="uniq_platform_legal_doc"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_category_display()}{f' ({self.sector})' if self.sector_id else ''}"


class LegalDocumentVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Reaccept(models.TextChoices):
        ALL = "all", "Everyone it applies to must accept again"
        SECTOR = "sector", "Only accounts in this document's sector"
        BUSINESS = "business", "Only business owners and managers"
        NEXT_ACTION = "next_action", "Only at the next relevant action (bookings, orders…)"
        NONE = "none", "No re-acceptance; applies to future actions"

    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    title_en = models.CharField(max_length=200)
    title_bn = models.CharField(max_length=200, blank=True)
    body_en = models.TextField(blank=True)  # sanitised HTML
    body_bn = models.TextField(blank=True)  # sanitised HTML
    change_summary = models.CharField(max_length=300, blank=True)
    reacceptance = models.CharField(max_length=12, choices=Reaccept.choices, default=Reaccept.ALL)
    # With reacceptance=sector on a platform-wide document: which sector must accept again.
    reaccept_sector = models.ForeignKey(
        Sector, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    effective_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document", "-version"]
        constraints = [models.UniqueConstraint(fields=["document", "version"], name="uniq_legal_version")]

    def __str__(self) -> str:
        return f"{self.document} v{self.version} ({self.status})"

    def save(self, *args, **kwargs):
        """Published text is frozen: only the status (archive) may change after publication."""
        if self.pk:
            old = (
                type(self)
                .objects.filter(pk=self.pk)
                .values("status", "body_en", "body_bn", "title_en", "title_bn")
                .first()
            )
            if old and old["status"] != self.Status.DRAFT:
                frozen = ("body_en", "body_bn", "title_en", "title_bn")
                if any(old[f] != getattr(self, f) for f in frozen):
                    raise ValueError("A published legal version can't be edited; create a new version.")
        super().save(*args, **kwargs)


class LegalAcceptance(models.Model):
    """Proof that someone agreed to one exact document version. Never edited or deleted."""

    version = models.ForeignKey(LegalDocumentVersion, on_delete=models.PROTECT, related_name="acceptances")
    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT, related_name="acceptances")
    category = models.CharField(max_length=16)
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="legal_acceptances",
    )
    turf = models.ForeignKey("turfs.Turf", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, null=True, blank=True, related_name="legal_acceptances"
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    related_ref = models.CharField(max_length=80, blank=True)  # application / invoice / recharge id
    accepted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-accepted_at"]
        indexes = [models.Index(fields=["user", "document"]), models.Index(fields=["turf", "accepted_at"])]

    def __str__(self) -> str:
        return f"{self.version} accepted ({self.action})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Acceptance records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Acceptance records can't be deleted.")
