from django.apps import AppConfig


class BookingsConfig(AppConfig):
    name = "apps.bookings"
    label = "bookings"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.notifications import tick

        from . import payments

        tick.EXTRA_STEPS.extend(
            [
                ("expire_payment_holds", payments.expire_lapsed),
                ("booking_reminders", payments.booking_reminders),
            ]
        )
