from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    name = "apps.applications"
    label = "applications"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.notifications import tick

        from . import registration

        tick.EXTRA_STEPS.append(("expire_promo_reservations", registration.expire_reservations))
