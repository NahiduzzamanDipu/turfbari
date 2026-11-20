from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.notifications import tick

        from . import credentials, middleware  # noqa: F401  (middleware connects the sign-in time signal)

        tick.EXTRA_STEPS.append(("expire_temporary_passwords", credentials.expire_due))
