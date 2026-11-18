"""Turf = the tenant. Everything a turf owns carries a `turf` FK and is filtered by it server-side."""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.common.money import MoneyField


class Amenity(BaseModel):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "amenities"

    def __str__(self) -> str:
        return self.name


class TurfQuerySet(models.QuerySet):
    def publicly_listed(self):
        """The only queryset public endpoints may read from."""
        return self.filter(status=Turf.Status.ACTIVE, is_listed=True)


class Turf(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        ARCHIVED = "archived", "Archived"

    class TurfType(models.TextChoices):
        OUTDOOR = "outdoor", "Outdoor"
        INDOOR = "indoor", "Indoor"
        ROOFTOP = "rooftop", "Rooftop"

    class Surface(models.TextChoices):
        ARTIFICIAL = "artificial", "Artificial grass"
        NATURAL = "natural", "Natural grass"
        HYBRID = "hybrid", "Hybrid"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    # Location
    district = models.ForeignKey("locations.District", on_delete=models.PROTECT, related_name="turfs")
    area = models.ForeignKey(
        "locations.Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="turfs"
    )
    address = models.CharField(max_length=255)
    maps_url = models.URLField(max_length=500, blank=True)

    turf_type = models.CharField(max_length=10, choices=TurfType.choices, default=TurfType.OUTDOOR)
    surface = models.CharField(max_length=10, choices=Surface.choices, default=Surface.ARTIFICIAL)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="turfs")

    # Private (never in public serializers)
    owner_name = models.CharField(max_length=120, blank=True)
    owner_phone = models.CharField(max_length=20, blank=True)
    contract_notes = models.TextField(blank=True)

    # Public profile
    short_description = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    public_phone = models.CharField(max_length=20, blank=True)
    public_email = models.EmailField(blank=True)
    booking_instructions = models.TextField(blank=True)
    cancellation_policy = models.TextField(blank=True)
    payment_methods_text = models.CharField(max_length=200, blank=True)
    is_listed = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    public_booking_enabled = models.BooleanField(default=True)
    show_pricing = models.BooleanField(default=True)
    min_public_price = MoneyField(null=True, blank=True, default=None)  # denormalised for sorting

    # Python weekday numbers (Mon=0). Bangladesh weekend: Friday + Saturday.
    weekend_days = models.JSONField(default=list, blank=True)

    objects = TurfQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "is_listed"]),
            models.Index(fields=["district", "area"]),
            models.Index(fields=["turf_type"]),
            models.Index(fields=["min_public_price"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_operational(self) -> bool:
        return self.status == self.Status.ACTIVE


class TenantMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["turf__name"]
        constraints = [models.UniqueConstraint(fields=["user", "turf"], name="uniq_membership")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.turf} ({self.role})"


class TurfField(BaseModel):
    """A bookable pitch inside a turf."""

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=60)
    size = models.CharField(max_length=30, blank=True, help_text="e.g. 5-a-side, 7-a-side")
    surface = models.CharField(max_length=10, choices=Turf.Surface.choices, default=Turf.Surface.ARTIFICIAL)
    is_indoor = models.BooleanField(default=False)
    has_lighting = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    slot_minutes = models.PositiveSmallIntegerField(default=60)
    default_hourly_rate = MoneyField()

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [models.UniqueConstraint(fields=["turf", "name"], name="uniq_field_name_per_turf")]

    def __str__(self) -> str:
        return f"{self.turf.name} — {self.name}"


class OperatingHours(BaseModel):
    """Opening hours per weekday. closes_at <= opens_at means the turf closes after midnight."""

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="hours")
    weekday = models.PositiveSmallIntegerField()  # 0 = Monday
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["weekday"]
        constraints = [models.UniqueConstraint(fields=["turf", "weekday"], name="uniq_hours_per_weekday")]


class PricingRule(BaseModel):
    """Hourly rate for a time band. Most specific wins: date > field > priority."""

    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name="pricing_rules")
    field = models.ForeignKey(
        TurfField,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pricing_rules",
        help_text="Empty = applies to every field.",
    )
    label = models.CharField(max_length=60, help_text="e.g. Peak, Off-peak, Weekend")
    weekdays = models.JSONField(default=list, blank=True, help_text="Empty = every day.")
    date = models.DateField(null=True, blank=True, help_text="Special date (holiday, event).")
    start_time = models.TimeField()
    end_time = models.TimeField(help_text="end <= start wraps past midnight")
    hourly_rate = MoneyField()
    priority = models.SmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority", "start_time"]

    def __str__(self) -> str:
        return f"{self.label} ({self.start_time:%H:%M}–{self.end_time:%H:%M})"
