"""10-minute slot holds for the public booking page, with a cooldown for visitors who let them lapse.

- Selecting slots places (or moves/extends) one hold per visitor; others see "someone is booking".
- Sending the booking request converts the hold. Deselecting releases it with no penalty.
- A hold that runs out without a request frees the slot and blocks that IP from selecting again for
  COOLDOWN_MINUTES. Re-selecting the same slots after releasing them keeps the original 10-minute
  window, so a slot can't be kept indefinitely by releasing and re-taking it.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.audit.services import client_ip

from .models import SlotHold

HOLD_MINUTES = 10
COOLDOWN_MINUTES = 10


class HoldRefused(APIException):
    status_code = 409
    default_code = "slot_held"
    default_detail = "That slot isn't available right now."

    def __init__(self, detail, code="slot_held", retry_at: datetime | None = None):
        super().__init__(detail, code)
        self.retry_at = retry_at


def ip_hash(request) -> str:
    ip = client_ip(request) or "unknown"
    return hmac.new(settings.SECRET_KEY.encode(), f"hold:{ip}".encode(), hashlib.sha256).hexdigest()


VISITOR_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def visitor_key(request) -> str:
    """Who is holding: the browser's own random id (X-Visitor-Id, kept in localStorage) so people
    sharing one IP (same Wi-Fi, mobile carrier NAT) are told apart; the IP only as a fallback.
    Stored as a keyed hash in SlotHold.ip_hash (historic column name)."""
    raw = (request.headers.get("X-Visitor-Id") or "").strip().lower()
    if VISITOR_ID.match(raw):
        return hmac.new(settings.SECRET_KEY.encode(), f"visitor:{raw}".encode(), hashlib.sha256).hexdigest()
    return ip_hash(request)


def latest_hold(key: str, now: datetime | None = None) -> SlotHold | None:
    """This visitor's live hold even if the page lost its token (reload, new tab)."""
    now = now or timezone.now()
    return (
        SlotHold.objects.filter(ip_hash=key, status=SlotHold.Status.ACTIVE, expires_at__gt=now)
        .order_by("-updated_at")
        .first()
    )


def active_holds(field_id, start: datetime, end: datetime, now: datetime | None = None):
    now = now or timezone.now()
    return SlotHold.objects.filter(
        field_id=field_id, status=SlotHold.Status.ACTIVE, expires_at__gt=now, start__lt=end, end__gt=start
    )


def cooldown_until(ip: str, now: datetime | None = None) -> datetime | None:
    """When this IP may select again, if a hold of theirs lapsed in the last COOLDOWN_MINUTES."""
    now = now or timezone.now()
    lapsed = (
        SlotHold.objects.filter(
            ip_hash=ip,
            status=SlotHold.Status.ACTIVE,
            expires_at__lte=now,
            expires_at__gt=now - timedelta(minutes=COOLDOWN_MINUTES),
        )
        .order_by("-expires_at")
        .first()
    )
    return lapsed.expires_at + timedelta(minutes=COOLDOWN_MINUTES) if lapsed else None


def find_hold(token: str | None, ip: str | None = None, now: datetime | None = None) -> SlotHold | None:
    if not token:
        return None
    now = now or timezone.now()
    qs = SlotHold.objects.filter(token=token, status=SlotHold.Status.ACTIVE, expires_at__gt=now)
    if ip:
        qs = qs.filter(ip_hash=ip)
    return qs.first()


def place_hold(*, turf, field, start: datetime, end: datetime, ip: str, token: str | None) -> SlotHold:
    """Create, move or extend this visitor's hold. Caller validates opening hours and horizon."""
    from .services import overlapping_bookings, overlapping_maintenance

    now = timezone.now()
    with transaction.atomic():
        # Same lock as reserve_slot(): holds and bookings for one field are decided one at a time.
        type(field).objects.select_for_update().get(pk=field.pk)
        retry = cooldown_until(ip, now)
        if retry:
            raise HoldRefused(
                "Your last selection timed out without a booking request. "
                f"You can select a slot again at {timezone.localtime(retry):%I:%M %p}.",
                code="hold_cooldown",
                retry_at=retry,
            )
        if (
            overlapping_bookings(field.id, start, end).exists()
            or overlapping_maintenance(field.id, start, end).exists()
        ):
            raise HoldRefused("That slot was just booked. Please choose another.", code="slot_taken")
        mine = find_hold(token, ip, now)
        others = active_holds(field.id, start, end, now).exclude(ip_hash=ip)
        if others.exists():
            raise HoldRefused("Someone else is booking that slot right now. Please choose another.")

        # One hold per visitor: release anything else they were holding (switching is free).
        SlotHold.objects.filter(ip_hash=ip, status=SlotHold.Status.ACTIVE, expires_at__gt=now).exclude(
            pk=mine.pk if mine else None
        ).update(status=SlotHold.Status.RELEASED, updated_at=now)

        if mine:
            # Moving/extending keeps the original 10-minute clock.
            mine.field, mine.start, mine.end = field, start, end
            mine.save(update_fields=["field", "start", "end", "updated_at"])
            return mine

        window_start = now
        recent = (
            SlotHold.objects.filter(
                ip_hash=ip,
                field=field,
                status=SlotHold.Status.RELEASED,
                start__lt=end,
                end__gt=start,
                window_started_at__gt=now - timedelta(minutes=HOLD_MINUTES + COOLDOWN_MINUTES),
            )
            .order_by("window_started_at")
            .first()
        )
        if recent:
            window_start = recent.window_started_at  # re-taking the same slot: same clock
            if window_start + timedelta(minutes=HOLD_MINUTES) <= now:
                retry = window_start + timedelta(minutes=HOLD_MINUTES + COOLDOWN_MINUTES)
                raise HoldRefused(
                    "You already had this slot for 10 minutes without sending a request. "
                    f"You can select it again at {timezone.localtime(retry):%I:%M %p}.",
                    code="hold_cooldown",
                    retry_at=retry,
                )
        return SlotHold.objects.create(
            turf=turf,
            field=field,
            start=start,
            end=end,
            token=secrets.token_urlsafe(24),
            ip_hash=ip,
            window_started_at=window_start,
            expires_at=window_start + timedelta(minutes=HOLD_MINUTES),
        )


def release_hold(token: str, ip: str) -> bool:
    return bool(
        SlotHold.objects.filter(token=token, ip_hash=ip, status=SlotHold.Status.ACTIVE).update(
            status=SlotHold.Status.RELEASED, updated_at=timezone.now()
        )
    )
