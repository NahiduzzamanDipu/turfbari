from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.subscriptions.models import Plan, Subscription
from apps.turfs.models import Turf

from .models import clear_client_showcase_cache


@receiver((post_save, post_delete), sender=Turf, dispatch_uid="homepage_showcase_turf_changed")
@receiver(
    (post_save, post_delete), sender=Subscription, dispatch_uid="homepage_showcase_subscription_changed"
)
@receiver((post_save, post_delete), sender=Plan, dispatch_uid="homepage_showcase_plan_changed")
def invalidate_client_showcase_cache(**kwargs):
    clear_client_showcase_cache()
