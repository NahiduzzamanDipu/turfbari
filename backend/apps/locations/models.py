"""Bangladesh administrative locations used by turf addresses and discovery filters."""

from django.db import models

from apps.common.models import BaseModel


class Division(BaseModel):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class District(BaseModel):
    division = models.ForeignKey(Division, on_delete=models.PROTECT, related_name="districts")
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Area(BaseModel):
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="areas")
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["district", "name"], name="uniq_area_per_district")]

    def __str__(self) -> str:
        return f"{self.name}, {self.district.name}"
