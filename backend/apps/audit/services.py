"""`record()` writes one audit event. It must never break the action being audited."""

import logging

from .models import AuditEvent

log = logging.getLogger(__name__)
Category = AuditEvent.Category


_ip_headers_logged = False


def _log_ip_headers_once(meta) -> None:
    """Help choose CLIENT_IP_HEADER on a new host: logs header NAMES (never values) once per process."""
    global _ip_headers_logged
    if _ip_headers_logged:
        return
    _ip_headers_logged = True
    names = sorted(k for k in meta if k.startswith("HTTP_") and ("IP" in k or "FORWARDED" in k))
    log.info("CLIENT_IP_HEADER is not set; client-IP headers on this request: %s", names)


def client_ip(request) -> str | None:
    """REMOTE_ADDR, or X-Real-IP when settings.TRUST_X_REAL_IP says our own proxy sets it.
    X-Forwarded-For is never trusted: clients can put anything in it."""
    from django.conf import settings

    meta = getattr(request, "META", {}) or {}
    # Hosts behind a CDN/proxy that sets a trusted client-IP header (e.g. Render via Cloudflare:
    # CLIENT_IP_HEADER=HTTP_CF_CONNECTING_IP). Only set it when that proxy overwrites the header.
    headers = [h.strip() for h in getattr(settings, "CLIENT_IP_HEADER", "").split(",") if h.strip()]
    for header in headers:
        if meta.get(header):
            return meta[header].split(",")[0].strip()[:45] or None
    if not headers and not settings.DEBUG:
        _log_ip_headers_once(meta)
    if getattr(settings, "TRUST_X_REAL_IP", False) and meta.get("HTTP_X_REAL_IP"):
        return meta["HTTP_X_REAL_IP"].strip()[:45] or None
    return meta.get("REMOTE_ADDR") or None


def record(
    action: str,
    summary: str,
    *,
    category: str,
    request=None,
    actor=None,
    turf=None,
    target=None,
    data: dict | None = None,
) -> AuditEvent | None:
    try:
        if actor is None and request is not None:
            user = getattr(request, "user", None)
            actor = user if user is not None and user.is_authenticated else None
        if turf is None and request is not None:
            turf = getattr(request, "tenant", None)
        return AuditEvent.objects.create(
            actor=actor,
            actor_label=(getattr(actor, "full_name", "") or getattr(actor, "email", "")) if actor else "",
            turf=turf,
            turf_name=turf.name if turf else "",
            category=category,
            action=action[:60],
            target_type=type(target).__name__.lower()[:40] if target is not None else "",
            target_id=str(getattr(target, "pk", "") or "")[:64] if target is not None else "",
            summary=summary[:255],
            ip=client_ip(request) if request is not None else None,
            data=data or {},
        )
    except Exception:  # noqa: BLE001
        log.exception("Could not write audit event %s", action)
        return None


def label(obj) -> str:
    for attr in ("name", "label", "title", "reference", "category", "reason"):
        value = getattr(obj, attr, None)
        if value:
            return str(value)
    return str(obj)


class AuditedViewSetMixin:
    """Helpers the tenant base viewset calls after create / update / delete. Set `audit_noun` and
    `audit_category`; views that write richer events themselves set `audit_auto = False`."""

    audit_noun = ""
    audit_category = Category.SETUP
    audit_auto = True

    def _audit(self, verb: str, obj, data=None):
        if not self.audit_auto or not self.audit_noun:
            return
        record(
            f"{self.audit_noun.replace(' ', '_')}.{verb}",
            f"{verb.capitalize()} {self.audit_noun} “{label(obj)}”",
            category=self.audit_category,
            request=self.request,
            target=obj,
            data=data,
        )

    def _audit_deleted(self, name: str, pk, kind: str):
        if not self.audit_auto or not self.audit_noun:
            return
        record(
            f"{self.audit_noun.replace(' ', '_')}.deleted",
            f"Deleted {self.audit_noun} “{name}”",
            category=self.audit_category,
            request=self.request,
            data={"id": str(pk), "type": kind},
        )


def booking_label(booking) -> str:
    """ "Field 1, 18 Nov 9:00 PM–10:00 PM · Demo Tigers (TRF-2611-ABCDE)" — for summaries."""
    from django.utils import timezone

    start, end = timezone.localtime(booking.start), timezone.localtime(booking.end)
    who = booking.team_name or booking.customer.name
    when = f"{start:%d %b} {start:%I:%M %p}–{end:%I:%M %p}".replace(" 0", " ")
    return f"{booking.field.name}, {when} · {who} ({booking.reference})"
