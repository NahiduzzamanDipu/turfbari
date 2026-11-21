"""The periodic "tick": everything that must happen without a user clicking anything.

Runs from any of: Celery beat (`notifications.tick`), `manage.py run_tick`, or
POST /api/system/tick/ with the X-Tick-Token header (an external cron such as the Supabase pg_cron
keep-awake job calls it every 10 minutes on the free hosting). Every step is idempotent, so running
the tick twice — or from two places — never sends anything twice. A short cache lock avoids overlap.
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

log = logging.getLogger(__name__)
LOCK_KEY = "tick:running"
EXTRA_STEPS: list = []  # other apps append (name, callable) here (e.g. booking holds, reminders)


def owner_phones(turf) -> list[str]:
    from apps.turfs.models import TenantMembership

    phones = {
        p
        for p in TenantMembership.objects.filter(
            turf=turf, role=TenantMembership.Role.OWNER, is_active=True, user__is_active=True
        ).values_list("user__phone", flat=True)
        if p
    }
    if not phones and turf.owner_phone:
        phones.add(turf.owner_phone)
    return sorted(phones)


def subscription_sms(today=None) -> dict:
    """SMS owners N days before their paid time ends (N from SmsConfig) and once when it has ended."""
    from apps.subscriptions.models import Subscription
    from apps.turfs.models import Turf

    from .models import SmsConfig, SmsKind, SmsMessage
    from .services import queue_sms, render

    today = today or timezone.localdate()
    days = sorted({int(d) for d in (SmsConfig.load().subscription_reminder_days or []) if int(d) > 0})
    url = f"{settings.FRONTEND_URL.rstrip('/')}/workspace/subscription"
    queued = 0
    latest = (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE, turf__status=Turf.Status.ACTIVE)
        .values("turf_id")
        .annotate(last=Max("ends_on"))
    )
    for row in latest:
        left = (row["last"] - today).days
        sub = (
            Subscription.objects.select_related("plan", "turf")
            .filter(turf_id=row["turf_id"], status=Subscription.Status.ACTIVE, ends_on=row["last"])
            .first()
        )
        if sub is None:
            continue
        values = {"turf": sub.turf.name, "plan": sub.plan.name, "date": f"{sub.ends_on:%d %b %Y}", "url": url}
        if 0 < left <= (days[-1] if days else 0):
            threshold = min(d for d in days if d >= left)
            kind, key = SmsKind.SUBSCRIPTION_REMINDER, f"sub:{sub.pk}:{threshold}d"
            body = render(kind, days=left, **values)
        elif -3 <= left < 0:  # ended in the last 3 days (catches a missed tick)
            kind, key = SmsKind.SUBSCRIPTION_EXPIRED, f"sub:{sub.pk}:expired"
            body = render(kind, **values)
        else:
            continue
        for phone in owner_phones(sub.turf):
            dedupe = f"{key}:{phone[-10:]}"
            if SmsMessage.objects.filter(dedupe_key=dedupe).exists():
                continue
            queue_sms(
                to=phone, body=body, kind=kind, turf=sub.turf, dedupe_key=dedupe, related_ref=str(sub.pk)
            )
            queued += 1
    return {"subscription_sms": queued}


def run_tick() -> dict:
    if not cache.add(LOCK_KEY, "1", timeout=120):
        return {"skipped": "another tick is running"}
    results: dict = {}
    try:
        from apps.demo.services import cleanup_expired_demo
        from apps.subscriptions.reminders import send_expiry_reminders

        from .services import retry_due

        steps = [
            ("sms", retry_due),
            ("subscription_sms", subscription_sms),
            ("subscription_email", send_expiry_reminders),
            ("demo_cleanup", cleanup_expired_demo),
            *EXTRA_STEPS,
        ]
        for name, step in steps:
            try:
                outcome = step()
                results[name] = outcome if isinstance(outcome, dict | int | str | None) else str(outcome)
            except Exception as exc:  # noqa: BLE001 - one failing step must not stop the others
                log.exception("Tick step %s failed", name)
                results[name] = {"error": type(exc).__name__}
        cache.set("tick:last", {"at": timezone.now().isoformat(), "results": results}, timeout=None)
    finally:
        cache.delete(LOCK_KEY)
    return results
