"""Queue, render and deliver SMS. Safe to call from inside booking/payment transactions.

- queue_sms() writes an SmsMessage row (unique dedupe_key => never queued twice) and, after the
  surrounding transaction commits, sends it in a background thread so a slow provider never delays
  the request. The tick (run_tick) retries whatever is still due.
- deliver() takes a row lock and moves QUEUED/FAILED -> SENDING -> SENT/FAILED, so two workers can't
  send the same row. A row stuck in SENDING (worker died mid-call) becomes UNKNOWN and is never
  retried automatically: BulkSMSBD may already have sent it, and a duplicate is worse than a gap.
"""

import logging
import re
import string
import threading
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from . import wallet
from .models import SmsAttempt, SmsConfig, SmsKind, SmsMessage, SmsTemplate
from .providers import bd_msisdn, get_provider, segment_count

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF = (timedelta(minutes=2), timedelta(minutes=10), timedelta(minutes=30))
STALE_SENDING = timedelta(minutes=10)

DEFAULT_TEMPLATES = {
    SmsKind.BOOKING_CONFIRMED: (
        "আপনার {turf}-এ {date} তারিখ {time} সময়ের বুকিং কনফার্ম হয়েছে। বুকিং আইডি: {reference}। ধন্যবাদ — TURFBARI"
    ),
    SmsKind.PAYMENT_REJECTED: (
        "{turf}: {date} {time}-এর বুকিংয়ের পেমেন্ট যাচাই করা যায়নি, তাই বুকিংটি নিশ্চিত হয়নি।{reason} "
        "বুকিং আইডি: {reference}। যোগাযোগ: {phone}"
    ),
    SmsKind.BOOKING_CANCELLED: "{turf}: {date} {time}-এর বুকিং ({reference}) বাতিল করা হয়েছে। যোগাযোগ: {phone}",
    SmsKind.OWNER_BOOKING_CONFIRMED: (
        "TURFBARI: আপনার {turf}-এ {date} তারিখ {time} সময়ের বুকিং কনফার্ম হয়েছে। বুকিং আইডি: {reference}। ধন্যবাদ।"
    ),
    SmsKind.BOOKING_REMINDER: (
        "মনে করিয়ে দিচ্ছি: {date} {time}-এ {turf}-এ আপনার খেলা। বুকিং আইডি: {reference}। — TURFBARI"
    ),
    SmsKind.SUBSCRIPTION_REMINDER: (
        "TURFBARI: {turf}-এর {plan} প্ল্যান {date} তারিখে শেষ হবে ({days} দিন বাকি)। বুকিং চালু রাখতে রিনিউ করুন।"
    ),
    SmsKind.SUBSCRIPTION_EXPIRED: (
        "TURFBARI: {turf}-এর প্ল্যান {date} তারিখে শেষ হয়েছে। বুকিং চালু রাখতে এখনই রিনিউ করুন: {url}"
    ),
}

# Placeholders each template may use (checked when an admin edits a template).
PLACEHOLDERS = {
    SmsKind.BOOKING_CONFIRMED: {"turf", "date", "time", "reference", "phone", "name"},
    SmsKind.PAYMENT_REJECTED: {"turf", "date", "time", "reference", "phone", "name", "reason"},
    SmsKind.BOOKING_CANCELLED: {"turf", "date", "time", "reference", "phone", "name"},
    SmsKind.OWNER_BOOKING_CONFIRMED: {"turf", "date", "time", "reference", "phone", "name"},
    SmsKind.BOOKING_REMINDER: {"turf", "date", "time", "reference", "phone", "name"},
    SmsKind.SUBSCRIPTION_REMINDER: {"turf", "plan", "date", "days", "url"},
    SmsKind.SUBSCRIPTION_EXPIRED: {"turf", "plan", "date", "url"},
}

# Turf-level switches for customer SMS (owner's Notification settings).
TURF_SMS_DEFAULTS = {
    "booking_confirmed": True,
    "payment_rejected": True,
    "booking_cancelled": True,
    "owner_booking_confirmed": True,
    "booking_reminder": False,
    "reminder_hours": 3,
}


def turf_sms_settings(turf) -> dict:
    return {**TURF_SMS_DEFAULTS, **(turf.sms_settings or {})}


def template_placeholders(body: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(body) if name}


class _Blank(dict):
    def __missing__(self, key):
        return ""


def render(kind: str, **values) -> str:
    row = SmsTemplate.objects.filter(kind=kind).first()
    body = row.body if row else DEFAULT_TEMPLATES.get(kind, "")
    try:
        return string.Formatter().vformat(body, (), _Blank({k: str(v) for k, v in values.items()})).strip()
    except (ValueError, IndexError):  # a broken edited template must never block a booking
        log.exception("SMS template %s is invalid; using the default", kind)
        return string.Formatter().vformat(DEFAULT_TEMPLATES[kind], (), _Blank(values)).strip()


def sender_id() -> str:
    return SmsConfig.load().sender_id or settings.BULKSMSBD_SENDER_ID


# Sent on TurfBari's behalf (plan notices, sign-in codes, admin tests): never counted as a turf's usage.
PLATFORM_KINDS = {
    SmsKind.SUBSCRIPTION_REMINDER,
    SmsKind.SUBSCRIPTION_EXPIRED,
    SmsKind.PASSWORD_RESET,
    SmsKind.TEST,
    SmsKind.WALLET_CREDITED,
    SmsKind.WALLET_RECHARGE_REJECTED,
    SmsKind.SUBSCRIPTION_APPROVED,
    SmsKind.SUBSCRIPTION_REJECTED,
}


def month_usage(turf) -> int:
    """Logical messages (not attempts) this turf sent this month — what the monthly limit counts."""
    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return SmsMessage.objects.filter(
        turf=turf,
        scope=SmsMessage.Scope.TENANT,
        created_at__gte=start,
        status__in=[SmsMessage.Status.SENT, SmsMessage.Status.SENDING],
    ).count()


def queue_sms(
    *,
    to: str,
    body: str,
    kind: str,
    turf=None,
    dedupe_key: str | None = None,
    booking=None,
    related_ref: str = "",
    created_by=None,
    auto_dispatch: bool = True,
    campaign=None,
) -> SmsMessage | None:
    """Add an SMS to the outbox. Returns the existing row if `dedupe_key` was already used."""
    if dedupe_key and (existing := SmsMessage.objects.filter(dedupe_key=dedupe_key).first()):
        return existing
    msisdn = bd_msisdn(to)
    config = SmsConfig.load()
    status, reason = SmsMessage.Status.QUEUED, ""
    if msisdn is None:
        status, reason = SmsMessage.Status.SKIPPED, "Not a Bangladeshi mobile number"
    elif not config.enabled:
        status, reason = SmsMessage.Status.SKIPPED, "SMS is switched off by the platform admin"
    elif get_provider().name == "disabled":
        status, reason = SmsMessage.Status.SKIPPED, "SMS isn't connected yet (no BulkSMSBD API key)"
    elif (
        turf is not None
        and kind not in PLATFORM_KINDS
        and config.per_turf_monthly_limit
        and month_usage(turf) >= config.per_turf_monthly_limit
    ):
        status, reason = SmsMessage.Status.SKIPPED, "This turf used its SMS allowance for the month"
    segments = segment_count(body)
    block, price = "", wallet.price_for(kind)
    tenant = turf is not None and kind not in PLATFORM_KINDS
    if status == SmsMessage.Status.QUEUED and tenant:
        limit = wallet.control_for(turf).monthly_limit
        if admin_block := wallet.blocked_by_admin(turf, kind):
            block = admin_block
        elif limit and month_usage(turf) >= limit:
            block = SmsMessage.BlockReason.MONTHLY_LIMIT
        elif price is None:
            block = SmsMessage.BlockReason.NO_PRICING
        elif wallet.wallet_for(turf).balance < wallet.money(price * segments):
            block = SmsMessage.BlockReason.INSUFFICIENT_BALANCE
        if block:
            status, reason = SmsMessage.Status.BLOCKED, SmsMessage.BlockReason(block).label
    try:
        with transaction.atomic():
            message = SmsMessage.objects.create(
                turf=turf,
                to=msisdn or (to or "")[:20],
                body=body,
                kind=kind,
                scope=SmsMessage.Scope.PLATFORM if kind in PLATFORM_KINDS else SmsMessage.Scope.TENANT,
                status=status,
                provider_message=reason,
                block_reason=block,
                price_per_segment=price,
                campaign=campaign,
                dedupe_key=dedupe_key,
                segments=segments,
                booking=booking,
                related_ref=related_ref[:60],
                created_by=created_by,
                next_attempt_at=timezone.now() if status == SmsMessage.Status.QUEUED else None,
            )
    except IntegrityError:  # a parallel request queued the same notification first
        return SmsMessage.objects.filter(dedupe_key=dedupe_key).first()
    if status == SmsMessage.Status.QUEUED and auto_dispatch:
        if settings.SMS_DISPATCH == "immediate":  # tests: no commit ever happens inside a test case
            deliver(message.pk)
            message.refresh_from_db()
        else:
            transaction.on_commit(lambda: dispatch(message.pk))
    return message


def dispatch(message_id) -> None:
    """Send soon without blocking the caller (inline in tests / when SMS_DISPATCH='inline')."""
    if settings.SMS_DISPATCH == "inline":
        deliver(message_id)
        return

    def run():
        try:
            deliver(message_id)
        except Exception:  # noqa: BLE001 - the tick will retry
            log.exception("Background SMS send failed for %s", message_id)
        finally:
            close_old_connections()

    threading.Thread(target=run, name=f"sms-{message_id}", daemon=True).start()


def deliver(message_id) -> SmsMessage | None:
    now = timezone.now()
    with transaction.atomic():
        message = (
            SmsMessage.objects.select_for_update()
            .filter(
                pk=message_id,
                status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.FAILED],
                attempts__lt=MAX_ATTEMPTS,
            )
            .first()
        )
        if message is None:
            return None  # already sent, being sent, given up, or skipped
        tenant = message.scope == SmsMessage.Scope.TENANT and message.turf_id is not None
        # Provider calls are numbered from the attempt log (never reused, even after a manual retry);
        # the charge for each call is keyed on this number, so it can't be taken twice.
        attempt_no = message.attempt_log.count() + 1
        if tenant:
            block = wallet.blocked_by_admin(message.turf, message.kind)
            if block is None and message.price_per_segment is None:
                block = SmsMessage.BlockReason.NO_PRICING
            if block is None:
                try:
                    wallet.charge(message, attempt_no)
                except wallet.InsufficientBalance:
                    block = SmsMessage.BlockReason.INSUFFICIENT_BALANCE
            if block:  # nothing goes to BulkSMSBD and nothing is charged
                message.status, message.block_reason = SmsMessage.Status.BLOCKED, block
                message.provider_message, message.next_attempt_at = SmsMessage.BlockReason(block).label, None
                message.save(
                    update_fields=[
                        "status",
                        "block_reason",
                        "provider_message",
                        "next_attempt_at",
                        "updated_at",
                    ]
                )
                return message
        message.status = SmsMessage.Status.SENDING
        message.attempts += 1
        message.save(update_fields=["status", "attempts", "updated_at"])

    result = get_provider().send(message.to, message.body, sender_id())
    if tenant and not result.ok and result.code != "timeout":
        # BulkSMSBD clearly did not take it: give the money back (a timeout keeps the charge for review).
        wallet.refund(message, attempt_no, f"Refund: not sent ({result.code} {result.message})")
    SmsAttempt.objects.create(
        message=message,
        number=attempt_no,
        ok=result.ok,
        provider_code=result.code[:20],
        provider_message=result.message[:255],
        provider_ref=result.ref,
    )
    if result.ref:
        message.provider_ref = result.ref

    message.provider_code, message.provider_message = result.code[:20], result.message[:255]
    if result.ok:
        message.status, message.sent_at, message.next_attempt_at = (
            SmsMessage.Status.SENT,
            timezone.now(),
            None,
        )
    elif result.code == "timeout":
        message.status, message.next_attempt_at = SmsMessage.Status.UNKNOWN, None
    elif result.retryable and message.attempts < MAX_ATTEMPTS:
        message.status = SmsMessage.Status.FAILED
        message.next_attempt_at = now + BACKOFF[min(message.attempts - 1, len(BACKOFF) - 1)]
    else:
        message.status, message.next_attempt_at = SmsMessage.Status.FAILED, None
    message.save(
        update_fields=[
            "status",
            "sent_at",
            "next_attempt_at",
            "provider_code",
            "provider_message",
            "provider_ref",
            "updated_at",
        ]
    )
    if tenant:
        message.charged_amount = wallet.net_charged(message)
    elif result.ok:  # TurfBari's own message: recorded as a platform expense, no turf wallet involved
        message.charged_amount = wallet.money((wallet.price_for(message.kind) or 0) * message.segments)
    message.save(update_fields=["charged_amount"])
    if not result.ok:
        log.warning("SMS %s to %s failed: %s %s", message.pk, message.masked_to, result.code, result.message)
    return message


def retry_blocked(message: SmsMessage, *, user=None) -> SmsMessage:
    """Owner/admin "retry" for a blocked SMS (e.g. after a recharge): re-check, then send."""
    with transaction.atomic():
        message = SmsMessage.objects.select_for_update().get(pk=message.pk)
        if (
            message.status != SmsMessage.Status.BLOCKED
            or message.block_reason == SmsMessage.BlockReason.CANCELLED
        ):
            return message
        if message.price_per_segment is None:
            message.price_per_segment = wallet.price_for(message.kind)
        message.status, message.block_reason, message.provider_message = SmsMessage.Status.QUEUED, "", ""
        message.next_attempt_at = timezone.now()
        message.save(
            update_fields=[
                "status",
                "block_reason",
                "provider_message",
                "next_attempt_at",
                "price_per_segment",
                "updated_at",
            ]
        )
    return deliver(message.pk) or message


def retry_due(limit: int = 50) -> dict:
    """Tick step: send queued/failed messages whose time has come; park stale SENDING rows."""
    now = timezone.now()
    stale = SmsMessage.objects.filter(
        status=SmsMessage.Status.SENDING, updated_at__lt=now - STALE_SENDING
    ).update(
        status=SmsMessage.Status.UNKNOWN,
        provider_message="Sending was interrupted — check BulkSMSBD before retrying",
        updated_at=now,
    )
    due = list(
        SmsMessage.objects.filter(
            status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.FAILED],
            attempts__lt=MAX_ATTEMPTS,
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:limit]
    )
    sent = sum(1 for pk in due if (m := deliver(pk)) and m.status == SmsMessage.Status.SENT)
    return {"sms_due": len(due), "sms_sent": sent, "sms_stale": stale}


def manual_retry(message: SmsMessage, *, user=None) -> SmsMessage:
    """Admin "retry" for FAILED/UNKNOWN rows: one more attempt, now."""
    with transaction.atomic():
        message = SmsMessage.objects.select_for_update().get(pk=message.pk)
        if message.status not in (SmsMessage.Status.FAILED, SmsMessage.Status.UNKNOWN):
            return message
        if message.status == SmsMessage.Status.UNKNOWN and message.turf_id:
            # The admin checked BulkSMSBD and it never went out: return that attempt's charge first.
            last = message.attempt_log.order_by("-number").first()
            if last:
                wallet.refund(message, last.number, "Refund: admin confirmed it was not sent", user=user)
        message.status = SmsMessage.Status.QUEUED
        message.attempts = min(message.attempts, MAX_ATTEMPTS - 1)
        message.next_attempt_at = timezone.now()
        message.save(update_fields=["status", "attempts", "next_attempt_at", "updated_at"])
    return deliver(message.pk) or message


def send_now(*, to: str, body: str, kind: str, dedupe_key: str | None = None, turf=None) -> bool:
    """Synchronous send for flows that need the answer (password-reset codes). True if accepted.

    One-time codes are blanked out of the stored log once the attempt is over."""
    message = queue_sms(to=to, body=body, kind=kind, turf=turf, dedupe_key=dedupe_key, auto_dispatch=False)
    if message is None or message.status == SmsMessage.Status.SKIPPED:
        return False
    deliver(message.pk)
    message.refresh_from_db()
    if kind == SmsKind.PASSWORD_RESET:
        message.body = re.sub(r"\d{4,8}", "******", message.body)
        message.save(update_fields=["body", "updated_at"])
    return message.status == SmsMessage.Status.SENT


def sms_configured() -> bool:
    return get_provider().name not in ("disabled",)
