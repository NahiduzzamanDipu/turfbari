"""Super Admin: Legal & Compliance management (documents, versions, sectors, acceptance monitoring)."""

import csv
import difflib
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.common.permissions import IsPlatformAdmin

from . import catalog, content, services
from .models import Action, Audience, LegalAcceptance, LegalDocument, LegalDocumentVersion, Sector
from .standard_text import standard_text
from .views import acceptance_row, published_history, search_acceptances, sector_payload

PLATFORM = AuditEvent.Category.PLATFORM


def _audit(request, action: str, summary: str, data: dict | None = None):
    record(f"legal.{action}", summary, category=PLATFORM, request=request, data=data)


def version_state(v: LegalDocumentVersion, current_id) -> str:
    if v.status == LegalDocumentVersion.Status.DRAFT:
        return "draft"
    if v.status == LegalDocumentVersion.Status.ARCHIVED:
        return "withdrawn" if v.published_at else "archived"
    if v.pk == current_id:
        return "current"
    if v.effective_at and v.effective_at > timezone.now():
        return "scheduled"
    return "superseded"


def version_summary(v: LegalDocumentVersion, current_id) -> dict:
    return {
        "id": v.pk,
        "version": v.version,
        "status": v.status,
        "state": version_state(v, current_id),
        "title_en": v.title_en,
        "title_bn": v.title_bn,
        "change_summary": v.change_summary,
        "reacceptance": v.reacceptance,
        "reaccept_sector": str(v.reaccept_sector_id) if v.reaccept_sector_id else None,
        "effective_at": v.effective_at,
        "published_at": v.published_at,
        "published_by": (v.published_by.full_name or v.published_by.email) if v.published_by_id else None,
        "created_by": (v.created_by.full_name or v.created_by.email) if v.created_by_id else None,
        "created_at": v.created_at,
        "updated_at": v.updated_at,
        "has_en": not content.is_blank(v.body_en),
        "has_bn": not content.is_blank(v.body_bn),
    }


def document_summary(d: LegalDocument, *, acceptances: int | None = None) -> dict:
    versions = list(d.versions.select_related("published_by", "created_by").order_by("-version"))
    current = services.current_version(d)
    current_id = current.pk if current else None
    return {
        "id": str(d.pk),
        "category": d.category,
        "category_label": d.get_category_display(),
        "sector": sector_payload(d.sector) if d.sector_id else None,
        "scope": "sector" if d.sector_id else "platform",
        "slug": d.slug,
        "audiences": d.audiences,
        "actions": d.actions,
        "is_mandatory": d.is_mandatory,
        "is_archived": d.is_archived,
        "url": services.document_url(d.category, d.slug, d.sector.slug if d.sector_id else None),
        "current": version_summary(current, current_id) if current else None,
        "draft": next((version_summary(v, current_id) for v in versions if v.status == "draft"), None),
        "versions": [version_summary(v, current_id) for v in versions],
        "acceptances": acceptances if acceptances is not None else d.acceptances.count(),
        "updated_at": max((v.updated_at for v in versions), default=d.updated_at),
    }


# ------------------------------------------------------------------ overview
class AdminLegalOverviewView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        docs = LegalDocument.objects.filter(is_archived=False)
        entries = services.current_entries()
        published_ids = {e["document_id"] for e in entries}
        drafts = LegalDocumentVersion.objects.filter(status="draft", document__is_archived=False).count()
        scheduled = LegalDocumentVersion.objects.filter(
            status="published", effective_at__gt=timezone.now()
        ).count()
        since = timezone.now() - timedelta(days=30)
        recent = (
            LegalDocumentVersion.objects.filter(published_at__isnull=False)
            .select_related("document", "document__sector", "published_by")
            .order_by("-published_at")[:8]
        )
        return Response(
            {
                "documents": docs.count(),
                "published": len(published_ids),
                "drafts": drafts,
                "scheduled": scheduled,
                "sectors": Sector.objects.filter(is_active=True).count(),
                "acceptances": LegalAcceptance.objects.count(),
                "acceptances_30d": LegalAcceptance.objects.filter(accepted_at__gte=since).count(),
                "pending_accounts": len(pending_business_users(limit=500)),
                "unpublished_modules": [
                    {"id": str(d.pk), "label": str(d)}
                    for d in docs.select_related("sector")
                    if str(d.pk) not in published_ids
                ],
                "recent": [
                    {
                        "document": str(v.document),
                        "document_id": str(v.document_id),
                        "version": v.version,
                        "published_at": v.published_at,
                        "by": (v.published_by.full_name or v.published_by.email)
                        if v.published_by_id
                        else None,
                    }
                    for v in recent
                ],
            }
        )


def pending_business_users(limit: int = 200) -> list[dict]:
    """Owners/managers who still have to accept something before using their workspace."""
    from apps.turfs.models import TenantMembership

    users = {}
    for m in (
        TenantMembership.objects.filter(is_active=True, user__is_active=True)
        .select_related("user", "turf")
        .order_by("turf__name")
    ):
        users.setdefault(m.user_id, (m.user, []))[1].append(m)
    out = []
    for user, memberships in users.values():
        pending = services.pending_for_user(user, "account")
        if pending:
            out.append(
                {
                    "user_id": str(user.pk),
                    "name": user.full_name or user.email,
                    "email": user.email,
                    "roles": sorted({m.role for m in memberships}),
                    "turfs": [m.turf.name for m in memberships],
                    "pending": [f"{e['title_en']} v{e['version']}" for e in pending],
                }
            )
            if len(out) >= limit:
                break
    return out


# ------------------------------------------------------------------ sectors
class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ["id", "name_en", "name_bn", "slug", "is_active", "sort_order"]
        extra_kwargs = {"slug": {"required": False}}

    def validate(self, attrs):
        if not attrs.get("slug") and not (self.instance and self.instance.slug):
            attrs["slug"] = slugify(attrs.get("name_en", ""))[:80]
        if "slug" in attrs and not attrs["slug"]:
            raise ValidationError({"slug": ["Enter a URL name (letters, numbers and dashes)."]})
        return attrs


def _sector_rows():
    rows = Sector.objects.annotate(
        turf_count=Count("turfs", distinct=True), doc_count=Count("documents", distinct=True)
    )
    return [{**SectorSerializer(s).data, "turfs": s.turf_count, "documents": s.doc_count} for s in rows]


class AdminSectorsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        return Response({"sectors": _sector_rows()})

    @extend_schema(tags=["admin"], request=SectorSerializer)
    @transaction.atomic
    def post(self, request):
        data = SectorSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        sector = data.save()
        # Every sector gets its own (empty, unpublished) Terms and Rules modules.
        for category in ("sector_terms", "sector_rules"):
            slug, _, _, audiences, actions = catalog.DEFAULTS[category]
            LegalDocument.objects.get_or_create(
                category=category,
                sector=sector,
                defaults={
                    "slug": slug,
                    "audiences": audiences,
                    "actions": actions,
                    "sort_order": catalog.sort_key(category),
                },
            )
        services.bump_revision()
        _audit(request, "sector_created", f"Added sector {sector.name_en}")
        return Response({"sectors": _sector_rows()}, status=201)


class AdminSectorDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=SectorSerializer)
    def patch(self, request, pk):
        sector = Sector.objects.filter(pk=pk).first()
        if sector is None:
            raise NotFound()
        data = SectorSerializer(sector, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        services.bump_revision()
        _audit(
            request,
            "sector_updated",
            f"Updated sector {sector.name_en}",
            {"fields": sorted(data.validated_data)},
        )
        return Response({"sectors": _sector_rows()})


# ------------------------------------------------------------------ documents
class DocumentSerializer(serializers.Serializer):
    audiences = serializers.ListField(
        child=serializers.ChoiceField(choices=[a for a in Audience.values if a != "admin"]), required=False
    )
    actions = serializers.ListField(child=serializers.ChoiceField(choices=Action.values), required=False)
    is_mandatory = serializers.BooleanField(required=False)
    is_archived = serializers.BooleanField(required=False)
    slug = serializers.SlugField(max_length=80, required=False)


class CreateDocumentSerializer(DocumentSerializer):
    category = serializers.ChoiceField(choices=LegalDocument.Category.choices)
    sector = serializers.SlugRelatedField(
        slug_field="slug", queryset=Sector.objects.all(), required=False, allow_null=True
    )


def _check_mandatory_platform(document: LegalDocument, attrs: dict):
    """Platform Terms, Privacy and Prohibited Activities stay mandatory: a sector can add to them but
    nothing can switch them off."""
    if document.sector_id is None and document.category in ("terms", "privacy", "prohibited"):
        if attrs.get("is_mandatory") is False:
            raise ValidationError({"is_mandatory": ["The platform's core terms are always mandatory."]})


class AdminDocumentsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        counts = dict(LegalAcceptance.objects.values_list("document_id").annotate(n=Count("id")))
        docs = LegalDocument.objects.select_related("sector").all()
        rows = [document_summary(d, acceptances=counts.get(d.pk, 0)) for d in docs]
        rows.sort(
            key=lambda r: (
                r["scope"] == "sector",
                r["sector"]["name_en"] if r["sector"] else "",
                catalog.sort_key(r["category"]),
            )
        )
        return Response(
            {
                "documents": rows,
                "sectors": [sector_payload(s) for s in Sector.objects.all()],
                "categories": [{"value": v, "label": label} for v, label in LegalDocument.Category.choices],
                "audiences": [{"value": v, "label": label} for v, label in Audience.choices if v != "admin"],
                "actions": [{"value": v, "label": label} for v, label in Action.choices],
                "reacceptance": [
                    {"value": v, "label": label} for v, label in LegalDocumentVersion.Reaccept.choices
                ],
            }
        )

    @extend_schema(tags=["admin"], request=CreateDocumentSerializer)
    def post(self, request):
        data = CreateDocumentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        sector, category = v.get("sector"), v["category"]
        if category in catalog.SECTOR_CATEGORIES and sector is None:
            raise ValidationError({"sector": ["Choose the sector this document is for."]})
        if LegalDocument.objects.filter(category=category, sector=sector).exists():
            raise ValidationError(
                {"category": ["This document already exists — open it and add a new version."]}
            )
        slug, _, _, audiences, actions = catalog.DEFAULTS[category]
        doc = LegalDocument.objects.create(
            category=category,
            sector=sector,
            slug=v.get("slug") or slug,
            audiences=v.get("audiences", audiences),
            actions=v.get("actions", actions),
            is_mandatory=v.get("is_mandatory", True),
            sort_order=catalog.sort_key(category),
        )
        _audit(request, "document_created", f"Added legal document {doc}")
        return Response(document_summary(doc), status=201)


def _document(pk) -> LegalDocument:
    doc = LegalDocument.objects.select_related("sector").filter(pk=pk).first()
    if doc is None:
        raise NotFound()
    return doc


class AdminDocumentDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request, pk):
        return Response(document_summary(_document(pk)))

    @extend_schema(tags=["admin"], request=DocumentSerializer)
    def patch(self, request, pk):
        doc = _document(pk)
        data = DocumentSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        attrs = data.validated_data
        _check_mandatory_platform(doc, attrs)
        if (
            "slug" in attrs
            and LegalDocument.objects.filter(slug=attrs["slug"], sector=doc.sector)
            .exclude(pk=doc.pk)
            .exists()
        ):
            raise ValidationError({"slug": ["Another document already uses this URL."]})
        for field, value in attrs.items():
            setattr(doc, field, value)
        doc.save()
        services.bump_revision()
        _audit(request, "document_updated", f"Updated settings of {doc}", {"fields": sorted(attrs)})
        return Response(document_summary(doc))


class AdminStandardTextView(APIView):
    """TurfBari's standard wording for a module (for "Rewrite with standard text"); nothing is saved."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request, pk):
        doc = _document(pk)
        text = standard_text(
            doc.category,
            doc.sector.name_en if doc.sector_id else None,
            doc.sector.name_bn if doc.sector_id else None,
        )
        if text is None:
            raise NotFound("There is no standard text for this document.")
        return Response({k: content.sanitize(v) if k.startswith("body") else v for k, v in text.items()})


# ------------------------------------------------------------------ versions
class VersionEditSerializer(serializers.Serializer):
    title_en = serializers.CharField(max_length=200)
    title_bn = serializers.CharField(max_length=200, required=False, allow_blank=True)
    body_en = serializers.CharField(
        required=False, allow_blank=True, max_length=content.MAX_BODY, trim_whitespace=False
    )
    body_bn = serializers.CharField(
        required=False, allow_blank=True, max_length=content.MAX_BODY, trim_whitespace=False
    )
    change_summary = serializers.CharField(max_length=300, required=False, allow_blank=True)


def version_detail(v: LegalDocumentVersion) -> dict:
    current = services.current_version(v.document)
    return {
        **version_summary(v, current.pk if current else None),
        "document": document_summary(v.document),
        "body_en": v.body_en,
        "body_bn": v.body_bn,
        "acceptances": v.acceptances.count(),
    }


def _version(pk) -> LegalDocumentVersion:
    v = (
        LegalDocumentVersion.objects.select_related(
            "document", "document__sector", "published_by", "created_by"
        )
        .filter(pk=pk)
        .first()
    )
    if v is None:
        raise NotFound()
    return v


class AdminDocumentVersionsView(APIView):
    """POST: start a new draft (copying the newest version's text), or return the existing draft."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=None)
    @transaction.atomic
    def post(self, request, pk):
        doc = LegalDocument.objects.select_for_update().filter(pk=pk).first()
        if doc is None:
            raise NotFound()
        draft = doc.versions.filter(status="draft").first()
        if draft is None:
            latest = doc.versions.order_by("-version").first()
            _, title_en, title_bn, _, _ = catalog.DEFAULTS.get(doc.category, ("", str(doc), "", [], []))
            if doc.sector_id and latest is None:
                title_en = f"{doc.sector.name_en} — {title_en}"
                title_bn = f"{doc.sector.name_bn} — {title_bn}" if doc.sector.name_bn else title_bn
            draft = LegalDocumentVersion.objects.create(
                document=doc,
                version=(latest.version + 1) if latest else 1,
                title_en=latest.title_en if latest else title_en,
                title_bn=latest.title_bn if latest else title_bn,
                body_en=latest.body_en if latest else "",
                body_bn=latest.body_bn if latest else "",
                created_by=request.user,
            )
            _audit(request, "draft_created", f"Started draft v{draft.version} of {doc}")
        return Response(version_detail(_version(draft.pk)), status=201)


class AdminVersionView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request, pk):
        return Response(version_detail(_version(pk)))

    @extend_schema(tags=["admin"], request=VersionEditSerializer)
    def put(self, request, pk):
        v = _version(pk)
        if v.status != LegalDocumentVersion.Status.DRAFT:
            raise ValidationError(
                {"status": ["Published versions can't be edited. Start a new draft instead."]}
            )
        data = VersionEditSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        attrs = data.validated_data
        v.title_en = attrs["title_en"].strip()
        v.title_bn = attrs.get("title_bn", v.title_bn).strip()
        v.body_en = content.sanitize(attrs.get("body_en", v.body_en))
        v.body_bn = content.sanitize(attrs.get("body_bn", v.body_bn))
        v.change_summary = attrs.get("change_summary", v.change_summary).strip()
        v.save()
        return Response(version_detail(v))

    @extend_schema(tags=["admin"])
    def delete(self, request, pk):
        v = _version(pk)
        if v.status != LegalDocumentVersion.Status.DRAFT:
            raise ValidationError(
                {"status": ["Only drafts can be discarded; published versions are kept forever."]}
            )
        doc, number = v.document, v.version
        v.delete()
        _audit(request, "draft_discarded", f"Discarded draft v{number} of {doc}")
        return Response(status=204)


class PublishSerializer(serializers.Serializer):
    effective_at = serializers.DateTimeField(required=False, allow_null=True)
    reacceptance = serializers.ChoiceField(choices=LegalDocumentVersion.Reaccept.choices)
    reaccept_sector = serializers.SlugRelatedField(
        slug_field="slug", queryset=Sector.objects.all(), required=False, allow_null=True
    )
    change_summary = serializers.CharField(max_length=300, required=False, allow_blank=True)


class AdminVersionPublishView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=PublishSerializer)
    @transaction.atomic
    def post(self, request, pk):
        v = LegalDocumentVersion.objects.select_for_update().filter(pk=pk).first()
        if v is None:
            raise NotFound()
        if v.status != LegalDocumentVersion.Status.DRAFT:
            raise ValidationError({"status": ["This version is already published."]})
        data = PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        attrs = data.validated_data
        if not v.title_en.strip():
            raise ValidationError({"title_en": ["Give the document a title."]})
        if content.is_blank(v.body_en) and content.is_blank(v.body_bn):
            raise ValidationError(
                {"body": ["Write the document text before publishing — empty documents can't be published."]}
            )
        now = timezone.now()
        effective = attrs.get("effective_at") or now
        if effective < now - timedelta(minutes=5):
            raise ValidationError({"effective_at": ["The effective date can't be in the past."]})
        newer = v.document.versions.filter(published_at__isnull=False, version__gt=v.version).exists()
        if newer:
            raise ValidationError({"status": ["A newer version is already published."]})
        v.status = LegalDocumentVersion.Status.PUBLISHED
        v.published_at = now
        v.published_by = request.user
        v.effective_at = effective
        v.reacceptance = attrs["reacceptance"]
        v.reaccept_sector = attrs.get("reaccept_sector") if attrs["reacceptance"] == "sector" else None
        if "change_summary" in attrs:
            v.change_summary = attrs["change_summary"].strip()
        v.save()
        services.bump_revision()
        when = "now" if effective <= now else f"from {timezone.localtime(effective):%d %b %Y %H:%M}"
        _audit(
            request,
            "published",
            f"Published {v.document} v{v.version} "
            f"(effective {when}; re-acceptance: {v.get_reacceptance_display()})",
            {"version_id": v.pk},
        )
        return Response(version_detail(_version(v.pk)))


class AdminVersionUnpublishView(APIView):
    """Withdraw a published version: the previous published version (if any) becomes current again.
    The text and every acceptance of it stay on record."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=None)
    @transaction.atomic
    def post(self, request, pk):
        v = LegalDocumentVersion.objects.select_for_update().filter(pk=pk).first()
        if v is None:
            raise NotFound()
        if v.status != LegalDocumentVersion.Status.PUBLISHED:
            raise ValidationError({"status": ["Only a published version can be withdrawn."]})
        v.status = LegalDocumentVersion.Status.ARCHIVED
        v.save()
        services.bump_revision()
        _audit(request, "unpublished", f"Withdrew {v.document} v{v.version}", {"version_id": v.pk})
        return Response(version_detail(_version(v.pk)))


class AdminVersionCompareView(APIView):
    """Line-by-line comparison of two versions of the same document (text only)."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request, pk, other):
        a, b = _version(pk), _version(other)
        if a.document_id != b.document_id:
            raise ValidationError({"other": ["Compare versions of the same document."]})
        if a.version > b.version:
            a, b = b, a
        lang = "bn" if request.query_params.get("lang") == "bn" else "en"
        left = content.to_text(getattr(a, f"body_{lang}")).splitlines()
        right = content.to_text(getattr(b, f"body_{lang}")).splitlines()
        rows = []
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes():
            if op == "equal":
                rows += [{"type": "same", "text": t} for t in left[i1:i2]]
            else:
                rows += [{"type": "removed", "text": t} for t in left[i1:i2]]
                rows += [{"type": "added", "text": t} for t in right[j1:j2]]
        return Response(
            {
                "from": {
                    "id": a.pk,
                    "version": a.version,
                    "title": getattr(a, f"title_{lang}") or a.title_en,
                },
                "to": {"id": b.pk, "version": b.version, "title": getattr(b, f"title_{lang}") or b.title_en},
                "lang": lang,
                "rows": rows,
                "changes": sum(1 for r in rows if r["type"] != "same"),
            }
        )


# ------------------------------------------------------------------ acceptance monitoring
class AdminAcceptancesView(APIView):
    """Search acceptance records; ?export=csv downloads them. Only what's needed is shown: who (name),
    which business/booking, which version, when — no phone numbers or IP addresses."""

    permission_classes = [IsPlatformAdmin]
    PAGE = 50

    @extend_schema(tags=["admin"])
    def get(self, request):
        qs = search_acceptances(request.query_params)
        if request.query_params.get("export") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="legal-acceptances.csv"'
            response.write("﻿")
            writer = csv.writer(response)
            writer.writerow(
                [
                    "Accepted at (Dhaka)",
                    "Person",
                    "Business",
                    "Booking",
                    "Document",
                    "Sector",
                    "Version",
                    "Action",
                    "Reference",
                ]
            )
            for a in qs[:20000]:
                r = acceptance_row(a, with_person=True)
                writer.writerow(
                    [
                        timezone.localtime(a.accepted_at).strftime("%Y-%m-%d %H:%M"),
                        r["person"] or "Customer (booking)",
                        r["turf"] or "",
                        r["booking"] or "",
                        r["document"],
                        r["sector"] or "Platform",
                        r["version"],
                        r["action_label"],
                        r["related_ref"],
                    ]
                )
            _audit(request, "acceptances_exported", "Exported legal acceptance records")
            return response
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        total = qs.count()
        rows = qs[(page - 1) * self.PAGE : page * self.PAGE]
        return Response(
            {
                "count": total,
                "page": page,
                "pages": max(1, -(-total // self.PAGE)),
                "results": [acceptance_row(a, with_person=True) for a in rows],
            }
        )


class AdminPendingView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        return Response({"results": pending_business_users()})


__all__ = [
    "AdminAcceptancesView",
    "AdminDocumentDetailView",
    "AdminDocumentVersionsView",
    "AdminDocumentsView",
    "AdminLegalOverviewView",
    "AdminPendingView",
    "AdminSectorDetailView",
    "AdminSectorsView",
    "AdminVersionCompareView",
    "AdminVersionPublishView",
    "AdminVersionUnpublishView",
    "AdminVersionView",
    "published_history",
]
