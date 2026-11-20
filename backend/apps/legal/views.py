"""Public legal pages and the signed-in user's legal status / acceptance."""

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.services import record

from . import catalog, services
from .models import Action, LegalAcceptance, LegalDocument, LegalDocumentVersion, Sector


def version_body(v: LegalDocumentVersion) -> dict:
    data = services.entry_for(v)
    data.update(
        {
            "body_en": v.body_en,
            "body_bn": v.body_bn,
            "change_summary": v.change_summary,
            "status": v.status,
        }
    )
    return data


def published_history(document: LegalDocument) -> list[dict]:
    """Every version that was ever published (newest first) — never drafts."""
    return [
        {
            "version": v.version,
            "published_at": v.published_at,
            "effective_at": v.effective_at or v.published_at,
            "change_summary": v.change_summary,
            "withdrawn": v.status == LegalDocumentVersion.Status.ARCHIVED,
        }
        for v in document.versions.filter(published_at__isnull=False).order_by("-version")
    ]


def sector_payload(s: Sector) -> dict:
    return {"id": str(s.pk), "slug": s.slug, "name_en": s.name_en, "name_bn": s.name_bn}


class PublicAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class PublicLegalIndexView(PublicAPIView):
    """Navigation for the public legal centre: published documents only."""

    @extend_schema(tags=["public"])
    def get(self, request):
        entries = services.current_entries()
        platform = [e for e in entries if e["scope"] == "platform"]
        sectors = []
        for s in Sector.objects.filter(is_active=True):
            docs = [e for e in entries if e["sector_id"] == str(s.pk)]
            sectors.append({**sector_payload(s), "documents": docs})
        return Response({"documents": platform, "sectors": sectors})


def _published_version(document: LegalDocument, number) -> LegalDocumentVersion:
    if number in (None, ""):
        v = services.current_version(document)
    else:
        try:
            n = int(number)
        except ValueError:
            raise NotFound() from None
        v = document.versions.filter(version=n, published_at__isnull=False).first()
    if v is None:
        raise NotFound("This document hasn't been published yet.")
    return v


class PublicLegalDocumentView(PublicAPIView):
    """/legal/<slug>: a platform document's current version, or ?version=N for an earlier one."""

    @extend_schema(tags=["public"])
    def get(self, request, slug):
        document = (
            LegalDocument.objects.filter(slug=slug, sector__isnull=True, is_archived=False)
            .select_related("sector")
            .first()
        )
        if document is None:
            raise NotFound()
        v = _published_version(document, request.query_params.get("version"))
        current = services.current_version(document)
        return Response(
            {
                **version_body(v),
                "is_current": current is not None and current.pk == v.pk,
                "history": published_history(document),
            }
        )


class PublicSectorLegalView(PublicAPIView):
    """/legal/sector/<slug>: the sector's own documents plus the platform documents it builds on."""

    @extend_schema(tags=["public"])
    def get(self, request, slug):
        sector = Sector.objects.filter(slug=slug, is_active=True).first()
        if sector is None:
            raise NotFound()
        docs = []
        for document in sector.documents.filter(is_archived=False).select_related("sector"):
            v = services.current_version(document)
            if v is not None:
                docs.append({**version_body(v), "history": published_history(document)})
        docs.sort(key=lambda d: catalog.sort_key(d["category"]))
        inherited = [e for e in services.current_entries() if e["scope"] == "platform"]
        return Response({"sector": sector_payload(sector), "documents": docs, "inherited": inherited})


class PublicRequiredView(PublicAPIView):
    """What a visitor must accept for an action: ?action=registration&sector=<slug>."""

    @extend_schema(tags=["public"])
    def get(self, request):
        action = request.query_params.get("action", "registration")
        if action not in ("registration", "booking"):
            raise ValidationError({"action": ["Unknown action."]})
        audience = "owner" if action == "registration" else "customer"
        slug = request.query_params.get("sector")
        sector = (
            Sector.objects.filter(slug=slug, is_active=True).first() if slug else services.default_sector()
        )
        sectors = [sector_payload(s) for s in Sector.objects.filter(is_active=True)]
        return Response(
            {
                "sector": sector_payload(sector) if sector else None,
                "sectors": sectors,
                "documents": services.required(action, audience, sector.pk if sector else None),
            }
        )


class PublicVersionView(PublicAPIView):
    """One published version by id (opened from a booking/registration checkbox link)."""

    @extend_schema(tags=["public"])
    def get(self, request, pk):
        v = (
            LegalDocumentVersion.objects.filter(pk=pk, published_at__isnull=False)
            .select_related("document", "document__sector")
            .first()
        )
        if v is None:
            raise NotFound()
        return Response(version_body(v))


# ------------------------------------------------------------------ signed-in users
def acceptance_row(a: LegalAcceptance, *, with_person: bool = False) -> dict:
    row = {
        "id": a.pk,
        "accepted_at": a.accepted_at,
        "document": a.document.get_category_display(),
        "category": a.category,
        "sector": a.sector.name_en if a.sector_id else None,
        "version": a.version.version,
        "version_id": a.version_id,
        "action": a.action,
        "action_label": Action(a.action).label if a.action in Action.values else a.action,
        "turf": a.turf.name if a.turf_id else None,
        "booking": a.booking.reference if a.booking_id else None,
        "related_ref": a.related_ref,
    }
    if with_person:
        row["person"] = (a.user.full_name or a.user.email) if a.user_id else None
    return row


class LegalStatusView(APIView):
    """Owner/manager "Legal & Policies": what applies, what's pending, and their acceptance history."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["legal"])
    def get(self, request):
        from apps.common.tenancy import resolve_membership

        user = request.user
        membership = resolve_membership(request)
        turf = membership.turf if membership else None
        sector_id = services.sector_id_of(turf)
        applicable = []
        if membership:
            role = membership.role
            applicable = [
                e
                for e in services.current_entries()
                if role in e["audiences"] and (e["sector_id"] is None or e["sector_id"] == sector_id)
            ]
        pending = services.pending_for_user(user, "account")
        history = LegalAcceptance.objects.filter(user=user).select_related(
            "document", "version", "sector", "turf", "booking"
        )[:100]
        sector = Sector.objects.filter(pk=sector_id).first() if sector_id else None
        return Response(
            {
                "pending": [{**e, **_bodies(e["version_id"])} for e in pending],
                "documents": applicable,
                "history": [acceptance_row(a) for a in history],
                "sector": sector_payload(sector) if sector else None,
                "business": {
                    "name": turf.name if turf else None,
                    "cancellation_policy": turf.cancellation_policy if turf else "",
                }
                if turf
                else None,
            }
        )


def _bodies(version_id: int) -> dict:
    v = LegalDocumentVersion.objects.only("body_en", "body_bn").get(pk=version_id)
    return {"body_en": v.body_en, "body_bn": v.body_bn}


class LegalPendingView(APIView):
    """Pending documents for one workspace action (?action=subscription|sms_recharge|account)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["legal"])
    def get(self, request):
        from apps.common.tenancy import resolve_membership

        action = request.query_params.get("action", "account")
        if action not in ("account", "subscription", "sms_recharge"):
            raise ValidationError({"action": ["Unknown action."]})
        membership = resolve_membership(request)
        pending = services.pending_for_user(request.user, action, membership.turf if membership else None)
        return Response({"documents": pending})


class AcceptSerializer(serializers.Serializer):
    accepted_versions = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    agree = serializers.BooleanField()


class LegalAcceptView(APIView):
    """Accept the documents the sign-in gate is asking for."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["legal"], request=AcceptSerializer)
    def post(self, request):
        from apps.common.tenancy import resolve_membership

        data = AcceptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        pending = services.pending_for_user(request.user, "account")
        services.require_accepted(
            pending, data.validated_data["agree"], set(data.validated_data["accepted_versions"])
        )
        membership = resolve_membership(request)
        services.record_acceptances(
            pending,
            action="account",
            user=request.user,
            turf=membership.turf if membership else None,
            request=request,
        )
        if pending:
            record(
                "legal.accepted",
                "Accepted " + ", ".join(f"{e['title_en']} v{e['version']}" for e in pending),
                category=AuditEvent.Category.ACCOUNT,
                request=request,
                turf=membership.turf if membership else None,
            )
        return Response({"pending": [], "accepted": len(pending)})


def search_acceptances(params, base=None):
    qs = base if base is not None else LegalAcceptance.objects.all()
    qs = qs.select_related("document", "version", "sector", "turf", "booking", "user")
    if q := (params.get("q") or "").strip():
        qs = qs.filter(
            Q(user__email__icontains=q)
            | Q(user__full_name__icontains=q)
            | Q(turf__name__icontains=q)
            | Q(booking__reference__icontains=q)
            | Q(related_ref__icontains=q)
        )
    for field in ("category", "action"):
        if value := params.get(field):
            qs = qs.filter(**{field: value})
    if value := params.get("sector"):
        qs = qs.filter(sector__slug=value)
    if value := params.get("document"):
        qs = qs.filter(document_id=value)
    if value := params.get("version"):
        qs = qs.filter(version_id=value)
    return qs
