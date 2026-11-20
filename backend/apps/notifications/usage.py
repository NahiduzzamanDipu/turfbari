"""SMS usage reporting, counted by TurfBari itself (BulkSMSBD has no per-account usage report).

Usage counts *logical messages* (one row per notification, unique dedupe key) — retries are separate
SmsAttempt rows, so a message retried three times still counts once. "Parts" are billed SMS segments of
sent messages. Platform messages (plan notices, sign-in codes, admin tests) are never a turf's usage.
"""

import csv
import io
import statistics
from datetime import date, datetime, timedelta

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsPlatformAdmin
from apps.common.tenancy import IsTenantMember

from .models import SmsAttempt, SmsKind, SmsMessage

S = SmsMessage.Status
BOOKING_KINDS = [SmsKind.BOOKING_CONFIRMED, SmsKind.BOOKING_REMINDER]
REJECT_CANCEL_KINDS = [SmsKind.PAYMENT_REJECTED, SmsKind.BOOKING_CANCELLED]
PLAN_KINDS = [SmsKind.SUBSCRIPTION_REMINDER, SmsKind.SUBSCRIPTION_EXPIRED]


def summary(qs) -> dict:
    agg = qs.aggregate(
        total=Count("id"),
        sent=Count("id", filter=Q(status=S.SENT)),
        failed=Count("id", filter=Q(status__in=[S.FAILED, S.UNKNOWN])),
        pending=Count("id", filter=Q(status__in=[S.QUEUED, S.SENDING])),
        not_sent=Count("id", filter=Q(status=S.SKIPPED)),
        parts=Sum("segments", filter=Q(status=S.SENT)),
        booking_confirmations=Count("id", filter=Q(kind__in=BOOKING_KINDS, status=S.SENT)),
        rejections_cancellations=Count("id", filter=Q(kind__in=REJECT_CANCEL_KINDS, status=S.SENT)),
    )
    agg["parts"] = agg["parts"] or 0
    agg["attempts"] = SmsAttempt.objects.filter(message__in=qs).count()
    return agg


def parse_day(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({field: ["Use YYYY-MM-DD."]}) from None


def date_range(request) -> tuple[datetime | None, datetime | None]:
    tz = timezone.get_current_timezone()
    start = parse_day(request.query_params.get("from"), "from")
    end = parse_day(request.query_params.get("to"), "to")
    return (
        timezone.make_aware(datetime.combine(start, datetime.min.time()), tz) if start else None,
        timezone.make_aware(datetime.combine(end + timedelta(days=1), datetime.min.time()), tz)
        if end
        else None,
    )


def in_range(qs, start, end):
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lt=end)
    return qs


def monthly_history(qs, months: int = 6) -> list[dict]:
    since = (
        timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=31 * (months - 1))
    ).replace(day=1)
    # Grouped in Python: MariaDB without time-zone tables can't truncate aware datetimes in SQL.
    buckets: dict[str, dict] = {}
    for created, status, parts in qs.filter(created_at__gte=since).values_list(
        "created_at", "status", "segments"
    ):
        key = timezone.localtime(created).strftime("%Y-%m")
        row = buckets.setdefault(key, {"month": key, "sent": 0, "failed": 0, "parts": 0})
        if status == S.SENT:
            row["sent"] += 1
            row["parts"] += parts
        elif status in (S.FAILED, S.UNKNOWN):
            row["failed"] += 1
    return [buckets[k] for k in sorted(buckets)]


class WorkspaceSmsUsageView(APIView):
    """This turf's own SMS usage: all time, this month, by type and month by month."""

    permission_classes = [IsTenantMember]
    required_permission = "view_sms"

    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        mine = SmsMessage.objects.filter(turf=turf, scope=SmsMessage.Scope.TENANT)
        month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        plan_notices = SmsMessage.objects.filter(
            turf=turf, scope=SmsMessage.Scope.PLATFORM, kind__in=PLAN_KINDS
        )
        return Response(
            {
                "all_time": summary(mine),
                "this_month": {
                    **summary(mine.filter(created_at__gte=month_start)),
                    "since": month_start.date(),
                },
                "history": monthly_history(mine),
                "plan_notices_from_turfbari": plan_notices.filter(status=S.SENT).count(),
                "first_sms_at": mine.order_by("created_at").values_list("created_at", flat=True).first(),
                "source": "Counted by TurfBari for every SMS sent for your turf; retries count once.",
            }
        )


class AdminSmsUsageView(APIView):
    """Usage per turf (and TurfBari's own platform messages) for a date range; ?export=csv exports."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        start, end = date_range(request)
        qs = in_range(SmsMessage.objects.all(), start, end)
        if status := request.query_params.get("status"):
            qs = qs.filter(status__in=[S.FAILED, S.UNKNOWN] if status == "failed" else [status])
        tenant = qs.filter(scope=SmsMessage.Scope.TENANT, turf__isnull=False)
        rows = list(
            tenant.values("turf_id", "turf__name", "turf__slug")
            .annotate(
                total=Count("id"),
                sent=Count("id", filter=Q(status=S.SENT)),
                failed=Count("id", filter=Q(status__in=[S.FAILED, S.UNKNOWN])),
                pending=Count("id", filter=Q(status__in=[S.QUEUED, S.SENDING])),
                not_sent=Count("id", filter=Q(status=S.SKIPPED)),
                parts=Sum("segments", filter=Q(status=S.SENT)),
            )
            .order_by("-sent", "turf__name")
        )
        if q := request.query_params.get("q", "").strip().lower():
            rows = [r for r in rows if q in (r["turf__name"] or "").lower() or q in (r["turf__slug"] or "")]
        # Attempts counted separately: joining them into the query above would multiply message counts.
        attempts = dict(
            SmsAttempt.objects.filter(message__in=tenant)
            .values_list("message__turf_id")
            .annotate(n=Count("id"))
            .values_list("message__turf_id", "n")
        )
        for r in rows:
            r["attempts"] = attempts.get(r["turf_id"], 0)
        sent_counts = [r["sent"] for r in rows if r["sent"]]
        median = statistics.median(sent_counts) if sent_counts else 0
        threshold = max(20, 3 * median)  # "unusually high": 3x the typical turf and at least 20
        out = [
            {
                "turf": {"id": str(r["turf_id"]), "name": r["turf__name"], "slug": r["turf__slug"]},
                "total": r["total"],
                "sent": r["sent"],
                "failed": r["failed"],
                "pending": r["pending"],
                "not_sent": r["not_sent"],
                "parts": r["parts"] or 0,
                "attempts": r["attempts"],
                "high_usage": r["sent"] >= threshold,
            }
            for r in rows
        ]
        platform = summary(qs.filter(scope=SmsMessage.Scope.PLATFORM))
        if request.query_params.get("export") == "csv":
            return self.csv(out, platform, start, end)
        return Response(
            {
                "from": start.date() if start else None,
                "to": (end - timedelta(days=1)).date() if end else None,
                "totals": summary(qs),
                "platform": platform,
                "turfs": out,
                "high_usage_threshold": threshold,
            }
        )

    @staticmethod
    def csv(rows, platform, start, end) -> HttpResponse:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "Account",
                "Sent",
                "Failed",
                "Pending",
                "Not sent",
                "SMS parts",
                "Provider attempts",
                "High usage",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["turf"]["name"],
                    r["sent"],
                    r["failed"],
                    r["pending"],
                    r["not_sent"],
                    r["parts"],
                    r["attempts"],
                    "yes" if r["high_usage"] else "",
                ]
            )
        writer.writerow(
            [
                "TurfBari platform messages",
                platform["sent"],
                platform["failed"],
                platform["pending"],
                platform["not_sent"],
                platform["parts"],
                platform["attempts"],
                "",
            ]
        )
        label = f"{start:%Y%m%d}-" if start else "all-"
        label += f"{end - timedelta(days=1):%Y%m%d}" if end else "now"
        response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="turfbari-sms-usage-{label}.csv"'
        return response
