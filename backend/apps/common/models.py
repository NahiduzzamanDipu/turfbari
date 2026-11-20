"""Abstract base models shared by every TurfBari app."""

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """UUID primary key so internal IDs are not guessable or sequential."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class PlatformSettings(models.Model):
    """Single row of platform-wide settings the Super Admin manages (Admin -> API / Terms)."""

    youtube_video_id = models.CharField(max_length=11, blank=True)  # "how to book" video on every turf page
    youtube_url = models.CharField(max_length=300, blank=True)  # as pasted, for display only
    max_slots_per_customer = models.PositiveSmallIntegerField(default=2)
    terms_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "Platform settings"

    def save(self, *args, **kwargs):
        from django.core.cache import cache

        super().save(*args, **kwargs)
        cache.delete("platform:settings")

    @classmethod
    def load(cls) -> "PlatformSettings":
        from django.core.cache import cache

        cached = cache.get("platform:settings")
        if cached is not None:
            return cached
        obj, _ = cls.objects.get_or_create(pk=1)
        cache.set("platform:settings", obj, 300)
        return obj


class TermsVersion(models.Model):
    """One revision of the platform Terms & Conditions + Booking Rules. Published revisions are never
    edited (bookings keep a reference to the exact one the customer agreed to); edits make a new draft."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Replaced"

    version = models.PositiveIntegerField(unique=True)
    terms_body = models.TextField()
    rules_body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"Terms v{self.version} ({self.status})"

    @classmethod
    def current(cls) -> "TermsVersion | None":
        """The published revision customers must agree to (None when there is none or terms are off)."""
        if not PlatformSettings.load().terms_enabled:
            return None
        return cls.objects.filter(status=cls.Status.PUBLISHED).order_by("-version").first()


class CustomerLock(models.Model):
    """One row per customer phone, locked (SELECT ... FOR UPDATE) while checking the booking limit so two
    parallel requests from the same number can't both pass."""

    phone = models.CharField(max_length=20, primary_key=True)

    def __str__(self) -> str:
        return self.phone
