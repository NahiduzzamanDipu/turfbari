"""SMS management: platform-wide for the Super Admin, per-turf for owners (and managers allowed to see
SMS), plus the token-protected tick endpoint. The BulkSMSBD API key is never returned by any view."""

import hmac
import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsPlatformAdmin
from apps.common.tenancy import IsTenantMember

from .models import SmsConfig, SmsKind, SmsMessage, SmsTemplate
from .providers import bd_msisdn, get_provider
from .services import (
    DEFAULT_TEMPLATES,
    PLACEHOLDERS,
    TURF_SMS_DEFAULTS,
    manual_retry,
    month_usage,
    queue_sms,
    sender_id,
    template_placeholders,
    turf_sms_settings,
)
from .tick import run_tick


def message_row(m: SmsMessage, *, admin: bool) -> dict:
    row = {
        "id": str(m.id),
        "created_at": m.created_at,
        "sent_at": m.sent_at,
        "kind": m.kind,
        "kind_label": m.get_kind_display(),
        "to": m.to if admin else m.masked_to,
        "body": m.body,
        "status": m.status,
        "segments": m.segments,
        "attempts": m.attempts,
        "provider_code": m.provider_code,
        "provider_message": m.provider_message,
        "booking_reference": m.booking.reference if m.booking_id else None,
    }
    if admin:
        row["turf"] = {"id": str(m.turf_id), "name": m.turf.name} if m.turf_id else None
    return row


def filtered_messages(request, qs):
    params = request.query_params
    if s := params.get("status"):
        qs = qs.filter(status=s)
    if k := params.get("kind"):
        qs = qs.filter(kind=k)
    if q := params.get("q", "").strip()[:60]:
        digits = "".join(ch for ch in q if ch.isdigit())
        cond = Q(body__icontains=q) | Q(booking__reference__icontains=q)
        if len(digits) >= 4:
            cond |= Q(to__contains=digits[-10:])
        qs = qs.filter(cond)
    return qs


def counts(qs) -> dict:
    agg = qs.aggregate(
        total=Count("id"),
        sent=Count("id", filter=Q(status=SmsMessage.Status.SENT)),
        failed=Count("id", filter=Q(status__in=[SmsMessage.Status.FAILED, SmsMessage.Status.UNKNOWN])),
        pending=Count("id", filter=Q(status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.SENDING])),
        skipped=Count("id", filter=Q(status=SmsMessage.Status.SKIPPED)),
        segments=Sum("segments", filter=Q(status=SmsMessage.Status.SENT)),
    )
    agg["segments"] = agg["segments"] or 0
    return agg


def month_start():
    return timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ------------------------------------------------------------------ admin
class SmsConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsConfig
        fields = ["enabled", "sender_id", "per_turf_monthly_limit", "subscription_reminder_days"]

    def validate_sender_id(self, value):
        value = value.strip()
        if value and not re.fullmatch(r"[A-Za-z0-9 ._-]{1,20}", value):
            raise serializers.ValidationError("Use the sender ID exactly as approved in BulkSMSBD.")
        return value

    def validate_subscription_reminder_days(self, value):
        try:
            days = sorted({int(d) for d in value}, reverse=True)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Use whole numbers of days, e.g. 7, 3, 1.") from None
        if any(d < 1 or d > 60 for d in days) or len(days) > 6:
            raise serializers.ValidationError("Up to 6 reminders, each 1–60 days before the plan ends.")
        return days


class AdminSmsOverviewView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        provider = get_provider()
        balance = None
        if provider.name != "disabled":
            balance = cache.get("sms:balance")
            if balance is None or request.query_params.get("refresh") == "1":
                value = provider.balance()
                balance = str(value) if value is not None else "unavailable"
                cache.set("sms:balance", balance, 60)
        config = SmsConfig.load()
        start = month_start()
        month = SmsMessage.objects.filter(created_at__gte=start)
        by_turf = (
            month.filter(turf__isnull=False)
            .values("turf_id", "turf__name")
            .annotate(
                sent=Count("id", filter=Q(status=SmsMessage.Status.SENT)),
                segments=Sum("segments", filter=Q(status=SmsMessage.Status.SENT)),
                failed=Count(
                    "id", filter=Q(status__in=[SmsMessage.Status.FAILED, SmsMessage.Status.UNKNOWN])
                ),
            )
            .order_by("-sent")[:20]
        )
        return Response(
            {
                "provider": provider.name,
                "configured": provider.name not in ("disabled",),
                "api_key_set": bool(settings.BULKSMSBD_API_KEY),
                "sender_id": sender_id(),
                "balance": balance,
                "config": SmsConfigSerializer(config).data,
                "today": counts(
                    SmsMessage.objects.filter(
                        created_at__gte=timezone.localtime().replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                    )
                ),
                "month": counts(month),
                "by_turf": [
                    {
                        "turf_id": str(r["turf_id"]),
                        "turf": r["turf__name"],
                        "sent": r["sent"],
                        "segments": r["segments"] or 0,
                        "failed": r["failed"],
                    }
                    for r in by_turf
                ],
                "last_tick": cache.get("tick:last"),
                "panel_url": "https://bulksmsbd.net/",
            }
        )

    @extend_schema(tags=["admin"], request=SmsConfigSerializer)
    def patch(self, request):
        config = SmsConfig.load()
        data = SmsConfigSerializer(config, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        record(
            "platform.sms_settings",
            "Changed SMS settings: " + ", ".join(sorted(data.validated_data)),
            category=Category.PLATFORM,
            request=request,
            data={k: v for k, v in data.validated_data.items()},
        )
        return Response(SmsConfigSerializer(config).data)


class AdminSmsMessagesView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        qs = filtered_messages(request, SmsMessage.objects.select_related("turf", "booking"))
        if turf := request.query_params.get("turf"):
            qs = qs.filter(turf_id=turf)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([message_row(m, admin=True) for m in page])


class AdminSmsRetryView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=None)
    def post(self, request, pk):
        message = get_object_or_404(SmsMessage, pk=pk)
        if message.status not in (SmsMessage.Status.FAILED, SmsMessage.Status.UNKNOWN):
            return Response(
                {
                    "error": {
                        "code": "not_retryable",
                        "message": "Only failed messages can be retried.",
                        "fields": None,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        message = manual_retry(message, user=request.user)
        record(
            "platform.sms_retried",
            f"Retried SMS to {message.masked_to} ({message.get_kind_display()}): "
            f"{message.get_status_display()}",
            category=Category.PLATFORM,
            request=request,
            target=message,
        )
        message.refresh_from_db()
        return Response(message_row(message, admin=True))


class SmsTestSerializer(serializers.Serializer):
    to = serializers.CharField(max_length=20)
    body = serializers.CharField(max_length=320, required=False, allow_blank=True)

    def validate_to(self, value):
        if not bd_msisdn(value):
            raise serializers.ValidationError("Enter a Bangladeshi mobile number, e.g. 01712345678.")
        return value


class AdminSmsTestView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=SmsTestSerializer)
    def post(self, request):
        data = SmsTestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = data.validated_data.get("body") or "TURFBARI test SMS — the BulkSMSBD connection works. ধন্যবাদ!"
        message = queue_sms(
            to=data.validated_data["to"],
            body=body,
            kind=SmsKind.TEST,
            created_by=request.user,
            auto_dispatch=False,
        )
        from .services import deliver

        if message.status == SmsMessage.Status.QUEUED:
            deliver(message.pk)
        message.refresh_from_db()
        record(
            "platform.sms_test",
            f"Sent a test SMS to {message.masked_to}: {message.get_status_display()}",
            category=Category.PLATFORM,
            request=request,
        )
        return Response(message_row(message, admin=True), status=status.HTTP_201_CREATED)


class SmsTemplateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=480)


class AdminSmsTemplatesView(APIView):
    permission_classes = [IsPlatformAdmin]

    @staticmethod
    def rows():
        saved = {t.kind: t for t in SmsTemplate.objects.all()}
        return [
            {
                "kind": kind,
                "label": SmsKind(kind).label,
                "body": saved[kind].body if kind in saved else default,
                "default": default,
                "customised": kind in saved,
                "placeholders": sorted(PLACEHOLDERS[kind]),
            }
            for kind, default in DEFAULT_TEMPLATES.items()
        ]

    @extend_schema(tags=["admin"])
    def get(self, request):
        return Response(self.rows())

    @extend_schema(tags=["admin"], request=SmsTemplateSerializer)
    def put(self, request, kind):
        if kind not in DEFAULT_TEMPLATES:
            raise Http404
        data = SmsTemplateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = data.validated_data["body"].strip()
        try:
            used = template_placeholders(body)
        except ValueError:
            raise serializers.ValidationError({"body": ["Check the { } brackets."]}) from None
        unknown = used - PLACEHOLDERS[kind]
        if unknown:
            raise serializers.ValidationError(
                {"body": [f"Unknown placeholder: {', '.join('{' + u + '}' for u in sorted(unknown))}"]}
            )
        if body == DEFAULT_TEMPLATES[kind]:
            SmsTemplate.objects.filter(kind=kind).delete()
        else:
            SmsTemplate.objects.update_or_create(
                kind=kind, defaults={"body": body, "updated_by": request.user}
            )
        record(
            "platform.sms_template",
            f"Edited the “{SmsKind(kind).label}” SMS",
            category=Category.PLATFORM,
            request=request,
        )
        return Response(self.rows())


# ------------------------------------------------------------------ workspace
class TurfSmsSettingsSerializer(serializers.Serializer):
    booking_confirmed = serializers.BooleanField(required=False)
    payment_rejected = serializers.BooleanField(required=False)
    booking_cancelled = serializers.BooleanField(required=False)
    booking_reminder = serializers.BooleanField(required=False)
    reminder_hours = serializers.IntegerField(min_value=1, max_value=24, required=False)


class WorkspaceSmsView(APIView):
    """This turf's SMS log and usage (owner, or managers with "See SMS messages")."""

    permission_classes = [IsTenantMember]
    required_permission = "view_sms"

    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        qs = filtered_messages(request, SmsMessage.objects.filter(turf=turf).select_related("booking"))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response([message_row(m, admin=False) for m in page])
        config = SmsConfig.load()
        response.data["usage"] = {
            **counts(SmsMessage.objects.filter(turf=turf, created_at__gte=month_start())),
            "limit": config.per_turf_monthly_limit,
            "used": month_usage(turf),
        }
        response.data["platform_sms_on"] = config.enabled and get_provider().name != "disabled"
        response.data["settings"] = turf_sms_settings(turf)
        return response


class WorkspaceSmsSettingsView(APIView):
    permission_classes = [IsTenantMember]
    owner_only_writes = True

    @extend_schema(tags=["workspace"])
    def get(self, request):
        return Response(turf_sms_settings(request.tenant))

    @extend_schema(tags=["workspace"], request=TurfSmsSettingsSerializer)
    def patch(self, request):
        data = TurfSmsSettingsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        turf = request.tenant
        turf.sms_settings = {**TURF_SMS_DEFAULTS, **(turf.sms_settings or {}), **data.validated_data}
        turf.save(update_fields=["sms_settings", "updated_at"])
        record(
            "settings.sms",
            "Changed SMS notification settings",
            category=Category.SETTINGS,
            request=request,
            data=data.validated_data,
        )
        return Response(turf_sms_settings(turf))


# ------------------------------------------------------------------ tick
class TickView(APIView):
    """POST with header X-Tick-Token: <TICK_TOKEN>. 404 when no token is configured."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["system"], request=None)
    def post(self, request):
        token = settings.TICK_TOKEN
        given = request.headers.get("X-Tick-Token", "")
        if not token:
            raise Http404
        if not hmac.compare_digest(given.encode(), token.encode()):
            return Response(status=status.HTTP_403_FORBIDDEN)
        last = cache.get("tick:last")
        if last and request.query_params.get("force") != "1":
            try:
                ran_at = timezone.datetime.fromisoformat(last["at"])
                if timezone.now() - ran_at < timedelta(seconds=50):
                    return Response({"skipped": "ran less than a minute ago"})
            except (KeyError, ValueError):
                pass
        return Response(run_tick())
