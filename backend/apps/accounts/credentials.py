# ruff: noqa: E501
"""Temporary passwords delivered by SMS (new accounts and admin resets).

Flow
- `start_delivery(user, password, ...)` is called right after a fresh temporary password was set on a
  user (new account) and `reset(user, ...)` makes a new one (admin reset). Both create a
  TemporaryCredential and, when credential SMS is available, queue one platform SMS (TurfBari pays; no
  turf wallet is touched).
- The SMS row stores the text with the password masked. The real text is put together only inside the
  SMS sender (`provider_text`) from the Fernet-encrypted copy on the credential, which is wiped when the
  provider accepts the SMS, when the user replaces the password, when a newer one is issued, or when it
  expires. The password is never returned by an API, logged, or written to the audit log.
- Resend reuses the same password while its encrypted copy still exists and it hasn't expired;
  otherwise it issues a new one (and the old one stops working).
- When credential SMS is off or SMS isn't connected, the password is shown once to the person who
  created it (the only other way to hand it over) — never an account nobody can sign in to.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import Throttled, ValidationError

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.common import crypto

from .models import TemporaryCredential, User
from .passwords import make_temporary_password

log = logging.getLogger(__name__)

MASK = "*" * 12  # same length/alphabet class as a real temporary password, so SMS parts don't change
MAX_PER_HOUR = 5  # temporary passwords issued per account per hour
MAX_SENDS = 5  # SMS per temporary password
DOUBLE_SUBMIT_SECONDS = 30
PLACEHOLDERS = {"name", "login_url", "username", "password", "expires"}
REQUIRED = {"password", "login_url"}
_FIELD = re.compile(r"\{([a-z_]*)\}")

DEFAULTS = {
    ("account_created", "en"): (
        "TurfBari: Your account has been created.\n"
        "Login: {login_url}\n"
        "Username: {username}\n"
        "Temporary password: {password}\n"
        "Log in and change your password now. Valid for {expires}. Never share your password."
    ),
    ("account_created", "bn"): (
        "TurfBari: আপনার অ্যাকাউন্ট তৈরি হয়েছে।\n"
        "লগইন: {login_url}\n"
        "ইউজারনেম: {username}\n"
        "অস্থায়ী পাসওয়ার্ড: {password}\n"
        "লগইন করে এখনই পাসওয়ার্ড বদলান। মেয়াদ {expires}। পাসওয়ার্ড কাউকে দেবেন না।"
    ),
    ("admin_reset", "en"): (
        "TurfBari: Your password was reset.\n"
        "Login: {login_url}\n"
        "Username: {username}\n"
        "Temporary password: {password}\n"
        "Log in and set a new password now. Valid for {expires}. Never share your password."
    ),
    ("admin_reset", "bn"): (
        "TurfBari: আপনার পাসওয়ার্ড রিসেট করা হয়েছে।\n"
        "লগইন: {login_url}\n"
        "ইউজারনেম: {username}\n"
        "অস্থায়ী পাসওয়ার্ড: {password}\n"
        "লগইন করে এখনই নতুন পাসওয়ার্ড দিন। মেয়াদ {expires}। পাসওয়ার্ড কাউকে দেবেন না।"
    ),
}
SMS_KIND = {"account_created": "account_credentials", "admin_reset": "credential_reset"}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


# ------------------------------------------------------------------ settings & templates
def platform():
    from apps.common.models import PlatformSettings

    return PlatformSettings.load()


def hours() -> int:
    return max(1, int(platform().temp_password_hours or getattr(settings, "TEMP_PASSWORD_HOURS", 72)))


def sms_available() -> bool:
    """Credential SMS can actually go out: switched on, SMS enabled, and a real provider connected."""
    from apps.notifications.models import SmsConfig
    from apps.notifications.providers import get_provider

    return bool(
        platform().credential_sms_enabled and SmsConfig.load().enabled and get_provider().name != "disabled"
    )


def validate_template(text: str) -> str:
    """Only known {placeholders}; {password} and {login_url} must be present."""
    text = (text or "").strip()
    if not text:
        return ""
    found = set(_FIELD.findall(text))
    unknown = found - PLACEHOLDERS
    if unknown or "{}" in text:
        bad = ", ".join("{" + u + "}" for u in sorted(unknown)) or "{}"
        raise ValidationError(
            f"Unknown placeholder {bad}. Use: " + ", ".join("{" + p + "}" for p in sorted(PLACEHOLDERS))
        )
    missing = REQUIRED - found
    if missing:
        raise ValidationError(
            "The message must include " + " and ".join("{" + m + "}" for m in sorted(missing)) + "."
        )
    if text.count("{password}") > 1:
        raise ValidationError("Use {password} only once.")
    return text


def template_for(purpose: str, lang: str | None = None) -> str:
    s = platform()
    lang = lang or (s.credential_sms_language if s.credential_sms_language in ("bn", "en") else "bn")
    field = f"credential_{'created' if purpose == 'account_created' else 'reset'}_{lang}"
    return (getattr(s, field, "") or "").strip() or DEFAULTS[(purpose, lang)]


def expires_label(n_hours: int, lang: str) -> str:
    if lang == "bn":
        return f"{str(n_hours).translate(BN_DIGITS)} ঘণ্টা"
    return f"{n_hours} hour{'s' if n_hours != 1 else ''}"


def render(template: str, *, user, password: str, n_hours: int, lang: str) -> str:
    values = {
        "name": user.full_name or "",
        "login_url": f"{settings.FRONTEND_URL.rstrip('/')}/login",
        "username": login_name(user),
        "password": password,
        "expires": expires_label(n_hours, lang),
    }
    return _FIELD.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def login_name(user) -> str:
    """What the person types in the sign-in box (username if set, else email)."""
    return user.username or user.email


# ------------------------------------------------------------------ issuing
def masked_phone(msisdn: str) -> str:
    digits = re.sub(r"\D", "", msisdn or "")
    if digits.startswith("88"):
        digits = digits[2:]
    return f"{digits[:3]}•••••{digits[-3:]}" if len(digits) >= 8 else ""


def require_phone(phone: str) -> str:
    """When credential SMS is on, the account must have a Bangladeshi mobile number."""
    from apps.notifications.providers import bd_msisdn

    msisdn = bd_msisdn(phone)
    if sms_available() and msisdn is None:
        raise ValidationError(
            {
                "phone": [
                    "Enter the person's Bangladeshi mobile number — their temporary password is sent there by SMS."
                ]
            }
        )
    return msisdn or ""


def _audit(action: str, summary: str, *, user, actor=None, request=None, data=None):
    record(
        f"account.{action}",
        summary,
        category=AuditEvent.Category.ACCOUNT,
        request=request,
        actor=actor,
        target=user,
        data=data,
    )


def _check_rate(user) -> None:
    since = timezone.now() - timedelta(hours=1)
    if TemporaryCredential.objects.filter(user=user, created_at__gte=since).count() >= MAX_PER_HOUR:
        raise Throttled(
            detail="Too many temporary passwords for this account in the last hour. Try again later."
        )


def _supersede(user, *, keep=None) -> None:
    qs = TemporaryCredential.objects.filter(user=user, status__in=TemporaryCredential.ACTIVE)
    if keep is not None:
        qs = qs.exclude(pk=keep.pk)
    qs.update(status=TemporaryCredential.Status.SUPERSEDED, secret="", finished_at=timezone.now())


def start_delivery(user, password: str, *, purpose: str, by=None, request=None, idempotency_key=None) -> dict:
    """`password` was just set as `user`'s temporary password. Deliver it; returns the delivery result
    (status only — plus the password itself solely in the shown-once fallback)."""
    from apps.notifications.providers import bd_msisdn

    msisdn = bd_msisdn(user.phone)
    use_sms = sms_available() and msisdn is not None
    _supersede(user)
    cred = TemporaryCredential.objects.create(
        user=user,
        purpose=purpose,
        channel=TemporaryCredential.Channel.SMS if use_sms else TemporaryCredential.Channel.SHOWN_ONCE,
        status=TemporaryCredential.Status.QUEUED if use_sms else TemporaryCredential.Status.SHOWN,
        secret=crypto.encrypt(password) if use_sms else "",
        phone=msisdn or "",
        expires_at=user.temp_password_expires_at or timezone.now() + timedelta(hours=hours()),
        created_by=by if by is not None and getattr(by, "is_authenticated", False) else None,
        idempotency_key=idempotency_key,
    )
    _audit(
        "temporary_password_issued",
        f"Temporary password issued for {user.email} ({cred.get_purpose_display()}; "
        f"{'SMS to ' + masked_phone(msisdn) if use_sms else 'shown once to ' + (by.email if by else 'the creator')})",
        user=user,
        actor=by,
        request=request,
        data={"credential": str(cred.pk), "channel": cred.channel},
    )
    if use_sms:
        _queue_sms(cred, password)
        cred.refresh_from_db()
    return {"credential": status_payload(cred), "temporary_password": None if use_sms else password}


def reset(user, *, by, request=None, idempotency_key=None, from_resend: bool = False) -> dict:
    """Admin "Reset password & send SMS": new temporary password, old ones stop working at once."""
    from .passwords import end_sessions, temp_password_hours

    key = f"reset:{user.pk}:{idempotency_key}"[:80] if idempotency_key else None
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if key and (done := TemporaryCredential.objects.filter(idempotency_key=key).first()):
            return {"credential": status_payload(done), "temporary_password": None, "duplicate": True}
        # Double click / second tab: the same admin reset this account seconds ago.
        recent = (
            None
            if from_resend
            else TemporaryCredential.objects.filter(
                user=user,
                created_by=by,
                purpose=TemporaryCredential.Purpose.ADMIN_RESET,
                status__in=TemporaryCredential.ACTIVE,
                created_at__gte=timezone.now() - timedelta(seconds=DOUBLE_SUBMIT_SECONDS),
            ).first()
        )
        if recent is not None:
            return {"credential": status_payload(recent), "temporary_password": None, "duplicate": True}
        _check_rate(user)
        if sms_available():
            require_phone(user.phone)
        password = make_temporary_password()
        user.set_password(password)
        user.must_change_password = True
        user.temp_password_expires_at = timezone.now() + timedelta(hours=temp_password_hours())
        user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])
        result = start_delivery(
            user,
            password,
            purpose=TemporaryCredential.Purpose.ADMIN_RESET,
            by=by,
            request=request,
            idempotency_key=key,
        )
    result["sessions_ended"] = end_sessions(user)
    return result


def _queue_sms(cred: TemporaryCredential, password: str) -> None:
    from apps.notifications.services import queue_sms

    lang = platform().credential_sms_language if platform().credential_sms_language in ("bn", "en") else "bn"
    n_hours = (
        max(1, round((cred.expires_at - cred.created_at).total_seconds() / 3600))
        if cred.created_at
        else hours()
    )
    text = render(template_for(cred.purpose, lang), user=cred.user, password=MASK, n_hours=n_hours, lang=lang)
    TemporaryCredential.objects.filter(pk=cred.pk).update(sends=cred.sends + 1)
    cred.sends += 1
    message = queue_sms(
        to=cred.phone,
        body=text,
        kind=SMS_KIND[cred.purpose],
        dedupe_key=f"credential:{cred.pk}:{cred.sends}",
        related_ref=f"credential:{cred.pk}",
        created_by=cred.created_by,
    )
    if message is not None:
        on_sms_result(message)  # skipped at once (e.g. SMS switched off) -> shown as failed


def resend(cred: TemporaryCredential, *, by, request=None) -> dict:
    """Admin "Resend": same password while it's still deliverable, otherwise a new one."""
    from apps.notifications.models import SmsMessage

    with transaction.atomic():
        cred = TemporaryCredential.objects.select_for_update().select_related("user").get(pk=cred.pk)
        user = cred.user
        latest = TemporaryCredential.objects.filter(user=user).order_by("-created_at").first()
        if (
            latest is None
            or latest.pk != cred.pk
            or cred.status
            in (
                TemporaryCredential.Status.USED,
                TemporaryCredential.Status.SUPERSEDED,
            )
        ):
            raise ValidationError({"credential": ["This temporary password is no longer in use."]})
        last_sms = _messages(cred).first()
        if last_sms is not None and last_sms.status in (SmsMessage.Status.QUEUED, SmsMessage.Status.SENDING):
            return {"credential": status_payload(cred), "temporary_password": None, "duplicate": True}
        if last_sms is not None and last_sms.next_attempt_at is not None:
            # A failed SMS still waiting for an automatic retry: cancel that retry, the resend replaces it.
            SmsMessage.objects.filter(pk=last_sms.pk).update(next_attempt_at=None, updated_at=timezone.now())
        secret = crypto.decrypt(cred.secret) if cred.secret else None
        still_valid = cred.expires_at > timezone.now() and user.must_change_password
        if secret and still_valid and cred.channel == TemporaryCredential.Channel.SMS and sms_available():
            if cred.sends >= MAX_SENDS:
                raise Throttled(
                    detail="This temporary password was already sent the maximum number of times."
                )
            cred.status = TemporaryCredential.Status.QUEUED
            cred.save(update_fields=["status", "updated_at"])
            _audit(
                "temporary_password_resent",
                f"Resent the temporary password SMS to {masked_phone(cred.phone)} for {user.email}",
                user=user,
                actor=by,
                request=request,
                data={"credential": str(cred.pk)},
            )
            _queue_sms(cred, secret)
            cred.refresh_from_db()
            return {"credential": status_payload(cred), "temporary_password": None}
    # Already handed to the provider (copy wiped), expired, or SMS unavailable: issue a new one.
    return reset(user, by=by, request=request, from_resend=True)


# ------------------------------------------------------------------ SMS sender hooks
def _cred_for(message):
    ref = message.related_ref or ""
    if not ref.startswith("credential:"):
        return None
    return TemporaryCredential.objects.filter(pk=ref.split(":", 1)[1]).select_related("user").first()


def _messages(cred):
    from apps.notifications.models import SmsMessage

    return SmsMessage.objects.filter(related_ref=f"credential:{cred.pk}").order_by("-created_at")


def provider_text(message) -> str | None:
    """The real SMS text for the provider, or None if this temporary password must not be sent."""
    cred = _cred_for(message)
    if cred is None or cred.status not in (
        TemporaryCredential.Status.QUEUED,
        TemporaryCredential.Status.FAILED,
    ):
        return None
    if cred.expires_at <= timezone.now() or not cred.user.must_change_password:
        return None
    password = crypto.decrypt(cred.secret)
    if not password or MASK not in message.body:
        return None
    return message.body.replace(MASK, password, 1)


def on_sms_result(message) -> None:
    """After each provider attempt: record the outcome on the credential; wipe the copy once accepted."""
    from apps.notifications.models import SmsMessage

    cred = _cred_for(message)
    if cred is None or cred.status not in (
        TemporaryCredential.Status.QUEUED,
        TemporaryCredential.Status.FAILED,
    ):
        return
    now = timezone.now()
    if message.status == SmsMessage.Status.SENT:
        TemporaryCredential.objects.filter(pk=cred.pk).update(
            status=TemporaryCredential.Status.SUBMITTED, submitted_at=now, secret="", updated_at=now
        )
        _audit(
            "temporary_password_sms_submitted",
            f"Temporary password SMS accepted by the SMS provider for {masked_phone(cred.phone)} ({cred.user.email})",
            user=cred.user,
            data={"credential": str(cred.pk), "sms": str(message.pk)},
        )
    elif message.status in (
        SmsMessage.Status.FAILED,
        SmsMessage.Status.UNKNOWN,
        SmsMessage.Status.SKIPPED,
    ) and (message.next_attempt_at is None):
        TemporaryCredential.objects.filter(pk=cred.pk).update(
            status=TemporaryCredential.Status.FAILED, updated_at=now
        )
        _audit(
            "temporary_password_sms_failed",
            f"Temporary password SMS to {masked_phone(cred.phone)} failed: {message.provider_message[:120]}",
            user=cred.user,
            data={"credential": str(cred.pk), "sms": str(message.pk), "code": message.provider_code},
        )


# ------------------------------------------------------------------ lifecycle
def consume(user) -> None:
    """The user chose their own password: every outstanding temporary password is finished."""
    n = TemporaryCredential.objects.filter(user=user, status__in=TemporaryCredential.ACTIVE).update(
        status=TemporaryCredential.Status.USED, secret="", finished_at=timezone.now()
    )
    if n:
        _audit(
            "temporary_password_replaced",
            f"{user.email} replaced their temporary password",
            user=user,
            actor=user,
        )


def expire_due() -> int:
    """Tick step: expired temporary passwords lose their encrypted copy and are marked expired."""
    now = timezone.now()
    due = list(
        TemporaryCredential.objects.filter(
            status__in=TemporaryCredential.ACTIVE, expires_at__lte=now
        ).select_related("user")[:200]
    )
    for cred in due:
        TemporaryCredential.objects.filter(pk=cred.pk).update(
            status=TemporaryCredential.Status.EXPIRED, secret="", finished_at=now
        )
        _audit(
            "temporary_password_expired",
            f"Temporary password for {cred.user.email} expired unused",
            user=cred.user,
        )
    return len(due)


def status_payload(cred: TemporaryCredential | None) -> dict | None:
    if cred is None:
        return None
    from apps.notifications.models import SmsMessage

    sms = _messages(cred).first() if cred.channel == TemporaryCredential.Channel.SMS else None
    expired = cred.expires_at <= timezone.now() and cred.status in TemporaryCredential.ACTIVE
    state = TemporaryCredential.Status.EXPIRED.value if expired else cred.status
    if (
        state == TemporaryCredential.Status.QUEUED
        and sms is not None
        and sms.status == SmsMessage.Status.FAILED
    ):
        state = "retrying"
    return {
        "id": str(cred.pk),
        "purpose": cred.purpose,
        "channel": cred.channel,
        "status": state,
        "status_label": "Retrying" if state == "retrying" else TemporaryCredential.Status(state).label,
        "masked_phone": masked_phone(cred.phone),
        "created_at": cred.created_at,
        "expires_at": cred.expires_at,
        "submitted_at": cred.submitted_at,
        "sends": cred.sends,
        "sms_status": sms.status if sms else None,
        "sms_detail": (sms.provider_message or "")[:160] if sms else "",
        # BulkSMSBD confirms only that it accepted the message; there is no delivery report.
        "delivery_reports": False,
        "can_resend": cred.channel == TemporaryCredential.Channel.SMS
        and state in ("failed", "expired", "submitted", "queued", "retrying")
        and cred.user.must_change_password,
    }


def latest_for(user) -> dict | None:
    return status_payload(TemporaryCredential.objects.filter(user=user).order_by("-created_at").first())
