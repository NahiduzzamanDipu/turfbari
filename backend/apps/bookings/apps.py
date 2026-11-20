from django.apps import AppConfig


class BookingsConfig(AppConfig):
    name = "apps.bookings"
    label = "bookings"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.notifications import campaigns, tick

        from . import payments, recurring

        tick.EXTRA_STEPS.extend(
            [
                ("expire_payment_holds", payments.expire_lapsed),
                ("expire_unpaid_series", recurring.expire_unpaid),
                ("booking_reminders", payments.booking_reminders),
                ("sms_campaigns", campaigns.finish_campaigns),
            ]
        )
