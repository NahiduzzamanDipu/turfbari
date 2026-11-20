"""'Register your turf' applications reviewed by the Super Admin."""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class TurfApplication(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        CONTACTED = "contacted", "Contacted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

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

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
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
