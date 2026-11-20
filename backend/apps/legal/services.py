"""Which legal documents apply to whom, what still needs accepting, and recording acceptances.

"Current" version of a document = its newest published version whose effective time has passed.
A version is only ever required if it is published, current and the document is mandatory, so
unpublished drafts or empty modules never block anyone.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from django.core.cache import cache
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import catalog
from .models import LegalAcceptance, LegalDocument, LegalDocumentVersion, Sector

REV_KEY = "legal:rev"
CURRENT_TTL = 60  # scheduled versions become current within a minute
PENDING_TTL = 300

ACCEPT_MESSAGE = "Please read and accept the required terms and policies to continue."
CHANGED_MESSAGE = "The terms and policies were just updated. Please read them again and accept."


# ------------------------------------------------------------------ cache revision
def _rev() -> str:
    rev = cache.get(REV_KEY)
    if rev is None:
        rev = uuid.uuid4().hex
        cache.set(REV_KEY, rev, None)
    return rev


def bump_revision() -> None:
    """Call after anything that changes which versions are current (publish, unpublish, settings)."""
    cache.set(REV_KEY, uuid.uuid4().hex, None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def document_url(category: str, slug: str, sector_slug: str | None) -> str:
    if sector_slug:
        return f"/legal/sector/{sector_slug}#{category}"
    return f"/legal/{slug}"


def entry_for(v: LegalDocumentVersion) -> dict:
    d = v.document
    sector_slug = d.sector.slug if d.sector_id else None
    return {
        "version_id": v.pk,
        "version": v.version,
        "document_id": str(d.pk),
        "category": d.category,
        "category_label": d.get_category_display(),
        "sector_id": str(d.sector_id) if d.sector_id else None,
        "sector_slug": sector_slug,
        "sector_name_en": d.sector.name_en if d.sector_id else None,
        "sector_name_bn": d.sector.name_bn if d.sector_id else None,
        "scope": "sector" if d.sector_id else "platform",
        "slug": d.slug,
        "audiences": list(d.audiences or []),
        "actions": list(d.actions or []),
        "mandatory": d.is_mandatory,
        "title_en": v.title_en,
        "title_bn": v.title_bn,
        "effective_at": _iso(v.effective_at or v.published_at),
        "published_at": _iso(v.published_at),
        "url": document_url(d.category, d.slug, sector_slug),
    }


def _sort(entries: list[dict]) -> list[dict]:
    """Inheritance order: platform terms → platform rules → sector terms → sector rules → policies."""
    return sorted(entries, key=lambda e: (catalog.sort_key(e["category"]), e["scope"] == "sector"))


def current_versions_qs(now=None):
    now = now or timezone.now()
    return (
        LegalDocumentVersion.objects.filter(
            status=LegalDocumentVersion.Status.PUBLISHED, document__is_archived=False
        )
        .filter(Q(effective_at__isnull=True) | Q(effective_at__lte=now))
        .filter(Q(document__sector__isnull=True) | Q(document__sector__is_active=True))
        .select_related("document", "document__sector")
        .order_by("document_id", "-version")
    )


def current_entries() -> list[dict]:
    """Every document's current version (cached briefly; cleared on publish/unpublish)."""
    key = f"legal:current:{_rev()}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    seen, entries = set(), []
    for v in current_versions_qs():
        if v.document_id in seen:
            continue
        seen.add(v.document_id)
        entries.append(entry_for(v))
    entries = _sort(entries)
    cache.set(key, entries, CURRENT_TTL)
    return entries


def current_version(document: LegalDocument) -> LegalDocumentVersion | None:
    return current_versions_qs().filter(document=document).first()


# ------------------------------------------------------------------ sectors
def default_sector() -> Sector | None:
    return Sector.objects.filter(is_active=True).order_by("sort_order", "name_en").first()


def sector_id_of(turf) -> str | None:
    if turf is None:
        return None
    if turf.sector_id:
        return str(turf.sector_id)
    s = default_sector()
    return str(s.pk) if s else None


# ------------------------------------------------------------------ requirements
def required(action: str, audience: str, sector_id: str | None) -> list[dict]:
    """Mandatory current documents for one action by one kind of user in one sector."""
    sector_id = str(sector_id) if sector_id else None
    return [
        e
        for e in current_entries()
        if e["mandatory"]
        and action in e["actions"]
        and audience in e["audiences"]
        and (e["sector_id"] is None or e["sector_id"] == sector_id)
    ]


def _business_context(user, turf=None) -> tuple[set[str], set[str]]:
    from apps.common.tenancy import memberships_for

    memberships = list(memberships_for(user))
    if turf is not None:
        memberships = [m for m in memberships if m.turf_id == turf.pk]
    audiences = {m.role for m in memberships}
    sectors = {sector_id_of(m.turf) for m in memberships} - {None}
    return audiences, sectors


def _reaccept_needed(document_id: str, after_version: int, upto_version: int, action: str, sectors) -> bool:
    """Has any version published since the one this user accepted asked people to accept again?"""
    newer = LegalDocumentVersion.objects.filter(
        document_id=document_id,
        status=LegalDocumentVersion.Status.PUBLISHED,
        version__gt=after_version,
        version__lte=upto_version,
    ).values_list("reacceptance", "reaccept_sector_id")
    R = LegalDocumentVersion.Reaccept
    for scope, sector in newer:
        if scope in (R.ALL, R.BUSINESS):
            return True
        if scope == R.SECTOR and (sector is None or str(sector) in sectors):
            return True
        if scope == R.NEXT_ACTION and action != "account":
            return True
    return False


def pending_for_user(user, action: str = "account", turf=None) -> list[dict]:
    """Documents a business user (owner/manager) must accept before doing `action`."""
    if not (user and user.is_authenticated) or user.is_platform_admin:
        return []
    audiences, sectors = _business_context(user, turf)
    if not audiences:
        return []
    candidates = [
        e
        for e in current_entries()
        if e["mandatory"]
        and action in e["actions"]
        and audiences & set(e["audiences"])
        and (e["sector_id"] is None or e["sector_id"] in sectors)
    ]
    if not candidates:
        return []
    rows = (
        LegalAcceptance.objects.filter(user=user, document_id__in=[e["document_id"] for e in candidates])
        .values("document_id")
        .annotate(last=Max("version__version"))
    )
    last_accepted = {str(r["document_id"]): r["last"] for r in rows}
    accepted_ids = set(
        LegalAcceptance.objects.filter(
            user=user, version_id__in=[e["version_id"] for e in candidates]
        ).values_list("version_id", flat=True)
    )
    pending = []
    for e in candidates:
        if e["version_id"] in accepted_ids:
            continue
        last = last_accepted.get(e["document_id"])
        if last is None or _reaccept_needed(e["document_id"], last, e["version"], action, sectors):
            pending.append(e)
    return pending


def _pending_key(user_id) -> str:
    return f"legal:pending:{user_id}:{_rev()}"


def account_gate_pending(user) -> bool:
    """Cached yes/no for the sign-in gate (checked on every workspace request)."""
    key = _pending_key(user.pk)
    value = cache.get(key)
    if value is None:
        value = bool(pending_for_user(user, "account"))
        cache.set(key, value, PENDING_TTL)
    return value


def forget_pending(user) -> None:
    cache.delete(_pending_key(user.pk))


# ------------------------------------------------------------------ recording
def _ip_hash(request) -> str:
    if request is None:
        return ""
    ip = (request.META.get("REMOTE_ADDR") or "").strip()
    return hashlib.sha256(f"turfbari-legal:{ip}".encode()).hexdigest()[:32] if ip else ""


def record_acceptances(
    entries: list[dict],
    *,
    action: str,
    user=None,
    turf=None,
    booking=None,
    related_ref: str = "",
    request=None,
    accepted_at=None,
) -> list[LegalAcceptance]:
    ip = _ip_hash(request)
    context_sector = sector_id_of(turf)  # the business's sector, also for platform-wide documents
    rows = []
    for e in entries:
        row = LegalAcceptance(
            version_id=e["version_id"],
            document_id=e["document_id"],
            category=e["category"],
            sector_id=e["sector_id"] or context_sector,
            user=user,
            turf=turf,
            booking=booking,
            action=action,
            related_ref=related_ref[:80],
            ip_hash=ip,
        )
        row.save()
        if accepted_at is not None:
            LegalAcceptance.objects.filter(pk=row.pk).update(accepted_at=accepted_at)
        rows.append(row)
    if user is not None:
        forget_pending(user)
    return rows


def parse_version_ids(raw) -> set[int]:
    if raw in (None, ""):
        return set()
    if isinstance(raw, str):
        raw = [p for p in raw.split(",") if p.strip()]
    if not isinstance(raw, list | tuple):
        raise ValidationError({"accepted_versions": ["Send the accepted version ids as a list."]})
    ids = set()
    for item in raw:
        try:
            ids.add(int(item))
        except (TypeError, ValueError):
            raise ValidationError({"accepted_versions": ["Invalid version id."]}) from None
    return ids


def require_accepted(needed: list[dict], agreed: bool, accepted_ids: set[int], field: str = "agree_terms"):
    """Raises unless the user ticked the box AND the ids they saw are exactly the current versions."""
    if not needed:
        return
    if not agreed:
        raise ValidationError({field: [ACCEPT_MESSAGE], "code": ["legal_acceptance_required"]})
    missing = [e for e in needed if e["version_id"] not in accepted_ids]
    if missing:
        raise ValidationError(
            {
                field: [CHANGED_MESSAGE],
                "code": ["legal_versions_changed"],
                "legal_versions": [str(e["version_id"]) for e in needed],
            }
        )


def require_for_user(user, action: str, turf, request) -> None:
    """For workspace transactions (plan orders, SMS recharges): asks only for what is still pending,
    so people aren't asked again for documents they already accepted."""
    needed = pending_for_user(user, action, turf)
    if not needed:
        return
    agreed = bool(request.data.get("agree_legal"))
    ids = parse_version_ids(request.data.get("accepted_versions"))
    require_accepted(needed, agreed, ids, field="agree_legal")
    record_acceptances(needed, action=action, user=user, turf=turf, request=request)


def copy_application_acceptances(application, owner, turf) -> None:
    """The owner accepted the documents when applying; attach those acceptances to their new account
    (original time kept, application id as the reference) so they aren't asked again at first sign-in."""
    ref = f"application:{application.pk}"
    for a in LegalAcceptance.objects.filter(related_ref=ref, user__isnull=True).select_related("version"):
        if LegalAcceptance.objects.filter(user=owner, version_id=a.version_id).exists():
            continue
        row = LegalAcceptance(
            version_id=a.version_id,
            document_id=a.document_id,
            category=a.category,
            sector_id=a.sector_id,
            user=owner,
            turf=turf,
            action=a.action,
            related_ref=ref,
            ip_hash=a.ip_hash,
        )
        row.save()
        LegalAcceptance.objects.filter(pk=row.pk).update(accepted_at=a.accepted_at)
    forget_pending(owner)
