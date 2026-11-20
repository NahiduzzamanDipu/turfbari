"""Temporary passwords, forced password change and the "forgot password" code flow.

- A temporary password is random, shown once to whoever created it, never stored or logged in plain
  text (only Django's argon2 hash), and works until the user replaces it or it expires
  (TEMP_PASSWORD_HOURS). While `must_change_password` is set, the API refuses everything except
  /api/auth/me, logout and change-password (PasswordChangeRequiredMiddleware).
- Forgot password: a 6-digit code (keyed hash only), valid RESET_CODE_MINUTES, 5 guesses, single use,
  sent by SMS when the account has a phone and SMS is configured, otherwise by email. Requests never
  reveal whether an account exists.
"""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import PasswordResetCode

log = logging.getLogger(__name__)

RESET_CODE_MINUTES = 15
RESET_MAX_ATTEMPTS = 5
RESET_MAX_PER_HOUR = 3


def temp_password_hours() -> int:
    """Admin-configurable (Admin -> API -> Login details by SMS); env TEMP_PASSWORD_HOURS as fallback."""
    from apps.common.models import PlatformSettings

    return max(
        1, int(PlatformSettings.load().temp_password_hours or getattr(settings, "TEMP_PASSWORD_HOURS", 72))
    )


def make_temporary_password() -> str:
    # 12 characters from an unambiguous alphabet: easy to read out over the phone.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def issue_temporary_password(user, *, save: bool = True) -> str:
    """Give `user` a fresh temporary password and require a change at next sign-in. Returns it once."""
    password = make_temporary_password()
    user.set_password(password)
    user.must_change_password = True
    user.temp_password_expires_at = timezone.now() + timedelta(hours=temp_password_hours())
    if save:
        user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])
    return password


def create_user_with_temporary_password(email: str, **extra):
    """New owner/manager account. Returns (user, temporary_password)."""
    User = get_user_model()
    user = User(email=email, **extra)
    password = issue_temporary_password(user, save=False)
    user.save()
    return user, password


def temporary_password_expired(user) -> bool:
    return bool(
        user.must_change_password
        and user.temp_password_expires_at
        and user.temp_password_expires_at <= timezone.now()
    )


def clear_temporary_flags(user) -> None:
    from .credentials import consume

    user.must_change_password = False
    user.temp_password_expires_at = None
    consume(user)  # outstanding temporary passwords (and their encrypted copies) are finished


def end_sessions(user, *, keep_session_key: str | None = None) -> int:
    """Sign `user` out everywhere (optionally keeping the current session). Returns sessions ended."""
    ended = 0
    user_id = str(user.pk)
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.session_key == keep_session_key:
            continue
        try:
            data = session.get_decoded()
        except Exception:  # noqa: BLE001, S112 - corrupt session: leave it to expire
            continue
        if str(data.get("_auth_user_id")) == user_id:
            session.delete()
            ended += 1
    return ended


# ------------------------------------------------------------------ forgot password
def _digest(user_id, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"reset:{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def find_user(identifier: str):
    """Active, non-admin account by email, username or BD mobile number. None if not exactly one."""
    from apps.bookings.phone import BD_MOBILE

    User = get_user_model()
    value = (identifier or "").strip().lower()
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("880"):
        digits = digits[2:]
    if "@" in value:
        q = Q(email=value)
    elif BD_MOBILE.match(digits):
        q = Q(phone__endswith=digits[-10:])
    else:
        q = Q(username=value)
    matches = [
        u
        for u in User.objects.filter(q, is_active=True)
        if "@" in value or not BD_MOBILE.match(digits) or re.sub(r"\D", "", u.phone).endswith(digits[-10:])
    ]
    return matches[0] if len(matches) == 1 else None


def _send_code(user, code: str) -> str | None:
    """SMS first (if the account has a phone and SMS is set up), then email. Returns the channel."""
    text = (
        f"{settings.PLATFORM_NAME} password reset code: {code}. "
        f"Valid {RESET_CODE_MINUTES} minutes. Don't share it with anyone."
    )
    if user.phone:
        try:
            from apps.notifications.services import send_now  # noqa: PLC0415 - optional SMS layer

            if send_now(to=user.phone, body=text, kind="password_reset", dedupe_key=None):
                return "sms"
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 - fall back to email
            log.exception("SMS reset code failed for user %s", user.pk)
    try:
        send_mail(
            subject=f"{code} is your {settings.PLATFORM_NAME} password reset code",
            message=(
                f"Someone asked to reset the password of your {settings.PLATFORM_NAME} account.\n\n"
                f"Your code is {code}. It expires in {RESET_CODE_MINUTES} minutes and works once.\n\n"
                "If this wasn't you, ignore this email — your password stays the same."
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return "email"
    except Exception:  # noqa: BLE001
        log.exception("Could not email a reset code to user %s", user.pk)
        return None


def request_reset(identifier: str) -> None:
    """Send a reset code if the account exists. Same outcome either way (no account enumeration)."""
    user = find_user(identifier)
    if user is None or user.is_platform_admin:
        # Platform admins recover through the break-glass deploy setting, never by a code.
        return
    now = timezone.now()
    recent = PasswordResetCode.objects.filter(user=user, created_at__gte=now - timedelta(hours=1)).count()
    if recent >= RESET_MAX_PER_HOUR:
        return
    code = f"{secrets.randbelow(1_000_000):06d}"
    channel = _send_code(user, code)
    if channel is None:
        return
    with transaction.atomic():
        PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)  # old codes die
        PasswordResetCode.objects.create(
            user=user,
            code_hash=_digest(user.pk, code),
            channel=channel,
            expires_at=now + timedelta(minutes=RESET_CODE_MINUTES),
        )


def confirm_reset(identifier: str, code: str):
    """Returns the user if `code` is their current unused, unexpired code; consumes it. Else None."""
    user = find_user(identifier)
    if user is None or user.is_platform_admin:
        return None
    now = timezone.now()
    with transaction.atomic():
        row = (
            PasswordResetCode.objects.select_for_update()
            .filter(user=user, used_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return None
        if row.attempts >= RESET_MAX_ATTEMPTS:
            row.used_at = now
            row.save(update_fields=["used_at"])
            return None
        if not hmac.compare_digest(row.code_hash, _digest(user.pk, (code or "").strip())):
            row.attempts += 1
            row.save(update_fields=["attempts"])
            return None
        row.used_at = now
        row.save(update_fields=["used_at"])
    return user
