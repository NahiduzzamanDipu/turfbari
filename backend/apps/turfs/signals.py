"""Drop a turf's cached configuration (see schedule.turf_config) whenever any part of it changes."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import OperatingHours, PriceCategory, PricingRule, SlotTemplate, Turf, TurfField
from .schedule import forget_turf_config


@receiver([post_save, post_delete], sender=OperatingHours)
@receiver([post_save, post_delete], sender=SlotTemplate)
@receiver([post_save, post_delete], sender=PricingRule)
@receiver([post_save, post_delete], sender=PriceCategory)
@receiver([post_save, post_delete], sender=TurfField)
def _turf_config_changed(sender, instance, **kwargs):
    forget_turf_config(instance.turf_id)


@receiver([post_save, post_delete], sender=Turf)
def _turf_changed(sender, instance, **kwargs):
    forget_turf_config(instance.pk)
