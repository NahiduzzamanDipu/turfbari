from celery import shared_task

from .reminders import send_expiry_reminders


@shared_task(name="subscriptions.send_expiry_reminders")
def send_expiry_reminders_task() -> dict:
    return send_expiry_reminders()
