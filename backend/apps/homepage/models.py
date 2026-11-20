from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class HomepageFAQ(BaseModel):
    question_en = models.CharField(max_length=240)
    question_bn = models.CharField(max_length=240, blank=True)
    answer_en = models.TextField()
    answer_bn = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return self.question_en


class TurfOnboarding(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending onboarding"
        CONTACTED = "contacted", "Contacted"
        SCHEDULED = "scheduled", "Training scheduled"
        IN_PROGRESS = "in_progress", "Training in progress"
        COMPLETED = "completed", "Completed"

    turf = models.OneToOneField("turfs.Turf", on_delete=models.CASCADE, related_name="onboarding")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_onboardings",
    )
    training_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    topics = models.JSONField(default=list, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_onboardings",
    )

    class Meta:
        ordering = ["status", "-created_at"]


class TurfOnboardingEvent(BaseModel):
    onboarding = models.ForeignKey(TurfOnboarding, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=240)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
