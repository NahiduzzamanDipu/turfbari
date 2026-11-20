from django.apps import AppConfig


class TurfsConfig(AppConfig):
    name = "apps.turfs"
    label = "turfs"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401
