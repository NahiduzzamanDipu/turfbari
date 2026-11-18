"""Plan-expiry reminder emails (plans never renew by themselves, so owners must be told in time).

Sent 10, 7, 3 and 1 days before the turf's *paid-until* date. Because that date is the end of the
latest paid period, an owner who already paid for the next period gets no reminders for the
current one. A ReminderLog row per (period, days, channel) makes re-runs and parallel workers safe.
"""

import logging
from datetime import date, timedelta
from html import escape

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.turfs.models import TenantMembership, Turf

from .models import ReminderLog, Subscription

log = logging.getLogger(__name__)
REMINDER_DAYS = (10, 7, 3, 1)
MAX_ATTEMPTS = 3
SENDING = "sending"


def owner_emails(turf) -> list[str]:
    return sorted(
        TenantMembership.objects.filter(
            turf=turf, role=TenantMembership.Role.OWNER, is_active=True, user__is_active=True
        ).values_list("user__email", flat=True)
    )


def due_periods(today: date):
    """(subscription, days_before) for each active turf whose last paid day is 10/7/3/1 days away."""
    targets = {today + timedelta(days=d): d for d in REMINDER_DAYS}
    latest = (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE, turf__status=Turf.Status.ACTIVE)
        .values("turf_id")
        .annotate(last=Max("ends_on"))
        .filter(last__in=list(targets))
    )
    for row in latest:
        sub = (
            Subscription.objects.select_related("plan", "turf")
            .filter(turf_id=row["turf_id"], status=Subscription.Status.ACTIVE, ends_on=row["last"])
            .first()
        )
        if sub:
            yield sub, targets[row["last"]]


def build_message(sub: Subscription, days: int) -> tuple[str, str, str]:
    brand = settings.PLATFORM_NAME
    turf_name, plan_name = sub.turf.name, sub.plan.name
    when = "tomorrow" if days == 1 else f"in {days} days"
    url = f"{settings.FRONTEND_URL.rstrip('/')}/workspace/subscription"
    ends = f"{sub.ends_on:%d %b %Y}"
    bangla = (
        f"আপনার {turf_name}-এর {plan_name} প্ল্যান {ends} তারিখে শেষ হবে। "
        "প্ল্যান নিজে থেকে রিনিউ হয় না — বুকিং চালু রাখতে আগেই রিনিউ করুন।"
    )
    subject = f"{brand}: {turf_name} — {plan_name} plan ends {when}"
    text = "\n".join(
        [
            "Hello,",
            "",
            f"The {plan_name} {brand} plan for {turf_name} ends on {ends} ({when}).",
            "Plans do not renew automatically. Renew before it ends to keep your turf on Explore "
            "and keep taking bookings:",
            url,
            "",
            bangla,
            "",
            f"— {brand}",
        ]
    )
    e = escape
    html = (
        f"<p>Hello,</p><p>The <strong>{e(plan_name)}</strong> {e(brand)} plan for "
        f"<strong>{e(turf_name)}</strong> ends on <strong>{ends}</strong> ({when}).</p>"
        "<p>Plans do not renew automatically. Renew before it ends to keep your turf on Explore "
        f'and keep taking bookings.</p><p><a href="{e(url)}">Renew your plan</a></p>'
        f'<p lang="bn">{e(bangla)}</p><p>— {e(brand)}</p>'
    )
    return subject, text, html


def _claim(sub: Subscription, days: int) -> ReminderLog | None:
    """Reserve the (period, days) slot; None if it was already sent or another worker has it."""
    try:
        with transaction.atomic():
            return ReminderLog.objects.create(
                subscription=sub, days_before=days, status=ReminderLog.Status.FAILED, error=SENDING
            )
    except IntegrityError:
        pass
    with transaction.atomic():
        row = ReminderLog.objects.select_for_update().get(subscription=sub, days_before=days)
        retryable = (
            row.status == ReminderLog.Status.FAILED and row.error != SENDING and row.attempts < MAX_ATTEMPTS
        )
        if not retryable:
            return None
        row.error = SENDING
        row.save(update_fields=["error", "updated_at"])
        return row


def send_expiry_reminders(today: date | None = None) -> dict:
    today = today or timezone.localdate()
    counts = {"sent": 0, "failed": 0, "skipped": 0, "already_done": 0}
    for sub, days in due_periods(today):
        row = _claim(sub, days)
        if row is None:
            counts["already_done"] += 1
            continue
        recipients = owner_emails(sub.turf)
        row.attempts += 1
        row.recipients = ", ".join(recipients)[:500]
        if not recipients:
            row.status, row.error = ReminderLog.Status.SKIPPED, ""
            counts["skipped"] += 1
        else:
            subject, text, html = build_message(sub, days)
            try:
                send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, recipients, html_message=html)
            except Exception as exc:  # noqa: BLE001 - one bad mailbox must not stop the other turfs
                log.warning("Plan reminder for %s (%sd) failed: %s", sub.turf, days, exc)
                row.status, row.error = ReminderLog.Status.FAILED, str(exc)[:255] or "error"
                counts["failed"] += 1
            else:
                row.status, row.error, row.sent_at = ReminderLog.Status.SENT, "", timezone.now()
                counts["sent"] += 1
        row.save()
    return counts
