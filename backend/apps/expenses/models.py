from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.common.money import MoneyField


class Expense(BaseModel):
    class Category(models.TextChoices):
        SALARY = "salary", "Salary"
        ELECTRICITY = "electricity", "Electricity"
        MAINTENANCE = "maintenance", "Maintenance"
        RENT = "rent", "Rent"
        EQUIPMENT = "equipment", "Equipment"
        MARKETING = "marketing", "Marketing"
        OTHER = "other", "Other"

    turf = models.ForeignKey("turfs.Turf", on_delete=models.CASCADE, related_name="expenses")
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    amount = MoneyField()
    spent_on = models.DateField(default=timezone.localdate, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-spent_on", "-created_at"]
