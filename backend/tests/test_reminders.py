"""Plan-expiry reminder emails: right days, right people, never twice, retried on failure."""

from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.subscriptions.models import Plan, ReminderLog, Subscription
from apps.subscriptions.reminders import send_expiry_reminders
from apps.subscriptions.services import create_order, mark_paid
from apps.subscriptions.tasks import send_expiry_reminders_task
from apps.turfs.models import Turf

from .test_core import make_turf

pytestmark = pytest.mark.django_db


def ends_in(turf, days):
    today = timezone.localdate()
    Subscription.objects.filter(turf=turf, status="active").update(
        starts_on=today - timedelta(days=20), ends_on=today + timedelta(days=days)
    )


@pytest.mark.parametrize("days", [10, 7, 3, 1])
def test_reminder_sent_on_each_reminder_day_once(days):
    turf, owner = make_turf()
    ends_in(turf, days)
    assert send_expiry_reminders()["sent"] == 1
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [owner.email]
    assert turf.name in msg.subject and "Monthly" in msg.subject
    assert "do not renew automatically" in msg.body and "/workspace/subscription" in msg.body
    assert "রিনিউ" in msg.body  # Bangla line included
    assert msg.alternatives and "Renew your plan" in msg.alternatives[0][0]

    # Running again the same day (or a second worker) sends nothing more.
    assert send_expiry_reminders()["already_done"] == 1
    assert len(mail.outbox) == 1
    log = ReminderLog.objects.get()
    assert (log.days_before, log.status, log.attempts) == (days, "sent", 1)


@pytest.mark.parametrize("days", [0, 2, 5, 11, 30])
def test_no_reminder_on_other_days(days):
    turf, _ = make_turf()
    ends_in(turf, days)
    assert send_expiry_reminders()["sent"] == 0 and mail.outbox == []


def test_no_reminder_when_next_period_already_paid():
    turf, _ = make_turf()
    ends_in(turf, 3)
    mark_paid(create_order(turf, Plan.objects.get(period="yearly")))  # queued after the current one
    assert send_expiry_reminders()["sent"] == 0
    assert mail.outbox == []


def test_reminders_follow_the_last_paid_day_across_days():
    turf, _ = make_turf()
    ends_in(turf, 10)
    today = timezone.localdate()
    sent_days = []
    for offset in range(11):
        if send_expiry_reminders(today + timedelta(days=offset))["sent"]:
            sent_days.append(10 - offset)
    assert sent_days == [10, 7, 3, 1]
    assert ReminderLog.objects.count() == 4


def test_suspended_turfs_and_ownerless_turfs():
    turf, _ = make_turf()
    ends_in(turf, 7)
    Turf.objects.filter(pk=turf.pk).update(status=Turf.Status.SUSPENDED)
    assert send_expiry_reminders()["sent"] == 0

    other, owner = make_turf("Other", "other@example.com")
    ends_in(other, 7)
    owner.is_active = False
    owner.save()
    assert send_expiry_reminders()["skipped"] == 1
    assert ReminderLog.objects.get().status == "skipped"


def test_failed_send_is_retried_then_given_up():
    turf, _ = make_turf()
    ends_in(turf, 3)
    with mock.patch("apps.subscriptions.reminders.send_mail", side_effect=OSError("smtp down")):
        assert send_expiry_reminders()["failed"] == 1
    log = ReminderLog.objects.get()
    assert (log.status, log.error, log.attempts) == ("failed", "smtp down", 1)

    assert send_expiry_reminders()["sent"] == 1  # retried on the next run
    assert ReminderLog.objects.get().status == "sent" and len(mail.outbox) == 1

    ReminderLog.objects.all().delete()
    with mock.patch("apps.subscriptions.reminders.send_mail", side_effect=OSError("down")):
        for _ in range(5):
            send_expiry_reminders()
    assert ReminderLog.objects.get().attempts == 3  # MAX_ATTEMPTS, then stop hammering


def test_task_and_management_command():
    turf, _ = make_turf()
    ends_in(turf, 1)
    assert send_expiry_reminders_task.delay().get()["sent"] == 1
    assert "tomorrow" in mail.outbox[0].subject

    out = StringIO()
    target = (timezone.localdate() + timedelta(days=-2)).isoformat()  # paid-until is 3 days after that
    call_command("send_subscription_reminders", "--date", target, stdout=out)
    assert "sent: 1" in out.getvalue()
    assert len(mail.outbox) == 2


def test_beat_schedule_registered(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["plan-expiry-reminders"]
    assert entry["task"] == "subscriptions.send_expiry_reminders"
