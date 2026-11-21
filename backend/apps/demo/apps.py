from django.apps import AppConfig


class DemoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.demo"
    verbose_name = "Isolated product demonstrations"

    def ready(self):
        from apps.notifications import tick

        from .services import reset_demo_if_due

        tick.EXTRA_STEPS.append(("demo_reset", reset_demo_if_due))
