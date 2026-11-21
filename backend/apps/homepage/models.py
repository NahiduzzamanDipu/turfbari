from django.conf import settings
from django.core.cache import cache
from django.db import models

from apps.common.models import BaseModel

CLIENT_SHOWCASE_CACHE_KEY = "homepage:client-showcase:v1"


def clear_client_showcase_cache():
    cache.delete(CLIENT_SHOWCASE_CACHE_KEY)


class ClientShowcaseSettings(BaseModel):
    key = models.CharField(max_length=32, unique=True, default="homepage")
    enabled = models.BooleanField(default=True)
    auto_include = models.BooleanField(default=True)
    eligible_plans = models.ManyToManyField(
        "subscriptions.Plan", blank=True, related_name="showcase_settings"
    )
    heading_en = models.CharField(max_length=120, default="Our Trusted Clients")
    heading_bn = models.CharField(max_length=120, default="আমাদের সম্মানিত গ্রাহক")
    subtitle_en = models.CharField(max_length=200, default="Turf businesses growing with TURFBARI.")
    subtitle_bn = models.CharField(max_length=200, default="যেসব টার্ফ ব্যবসা TURFBARI-এর সঙ্গে এগিয়ে যাচ্ছে।")

    class Meta:
        verbose_name = "homepage client showcase settings"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        clear_client_showcase_cache()


class ClientShowcaseOverride(BaseModel):
    class Mode(models.TextChoices):
        AUTO = "auto", "Automatic"
        INCLUDE = "include", "Include"
        HIDE = "hide", "Hide"

    turf = models.OneToOneField("turfs.Turf", on_delete=models.CASCADE, related_name="showcase_override")
    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.AUTO)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "turf__name"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        clear_client_showcase_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        clear_client_showcase_cache()
        return result


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
