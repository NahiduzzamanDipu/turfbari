"""Read-only audit views: owners see their own turf, the Super Admin sees everything."""

from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import ValidationError

from apps.common.permissions import IsPlatformAdmin
from apps.common.tenancy import IsTenantMember

from .models import AuditEvent
from .serializers import AdminAuditEventSerializer, AuditEventSerializer

OWNER_CATEGORIES = [c for c in AuditEvent.Category.values if c != AuditEvent.Category.PLATFORM]


def _day(value: str, end: bool):
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError({"date": ["Use YYYY-MM-DD."]}) from None
    return timezone.make_aware(datetime.combine(day, time.max if end else time.min))


def filtered(qs, params):
    if category := params.get("category"):
        qs = qs.filter(category=category)
    if q := params.get("q", "").strip()[:80]:
        qs = qs.filter(Q(summary__icontains=q) | Q(actor_label__icontains=q) | Q(turf_name__icontains=q))
    if params.get("from"):
        qs = qs.filter(created_at__gte=_day(params["from"], end=False))
    if params.get("to"):
        qs = qs.filter(created_at__lte=_day(params["to"], end=True))
    return qs


class WorkspaceActivityView(generics.ListAPIView):
    """The owner's activity log for the active turf (managers cannot read it)."""

    permission_classes = [IsTenantMember]
    owner_only = True
    serializer_class = AuditEventSerializer
    filter_backends = []

    def get_queryset(self):
        qs = AuditEvent.objects.filter(turf=self.request.tenant, category__in=OWNER_CATEGORIES)
        return filtered(qs, self.request.query_params)


class AdminAuditView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminAuditEventSerializer
    filter_backends = []

    def get_queryset(self):
        qs = filtered(AuditEvent.objects.all(), self.request.query_params)
        if turf := self.request.query_params.get("turf"):
            qs = qs.filter(turf_id=turf)
        return qs
