"""Super Admin subscription tools and the platform health page.

- Subscriptions overview: every turf's plan standing, filterable (expiring soon, in grace, expired).
- Per-turf history: paid periods and invoices.
- Extend (adds days, with a required reason) and End now (expires paid time, with a reason). Both are
  audited. Assigning/renewing a plan stays on the existing "assign plan" endpoint.
- Health: database/cache, background tick freshness, SMS and email failures, sign-in problems, recent
  platform events. No secrets, stack traces or customer data.
"""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.services import Category, record
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsPlatformAdmin
from apps.turfs.models import TenantMembership, Turf

from .models import Invoice, PaymentTransaction, Plan, ReminderLog, Subscription
from .services import GRACE_DAYS, paid_until, standing


def turf_row(turf: Turf, today) -> dict:
    s = standing(turf, today)
    owner = next(
        (m.user for m in turf.memberships.all() if m.role == TenantMembership.Role.OWNER and m.is_active),
        None,
    )
    return {
        "turf": {"id": str(turf.id), "name": turf.name, "slug": turf.slug, "status": turf.status},
        "owner": {"name": owner.full_name, "email": owner.email, "phone": owner.phone} if owner else None,
        "state": s.state,
        "plan": s.current.plan.name if s.current else None,
        "paid_until": s.paid_until,
        "days_left": s.days_left,
        "grace_until": s.grace_until,
    }


class AdminSubscriptionsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        today = timezone.localdate()
        params = request.query_params
        turfs = (
            Turf.objects.exclude(status=Turf.Status.ARCHIVED)
            .prefetch_related("memberships__user")
            .annotate(
                last_paid=Max(
                    "subscriptions__ends_on", filter=Q(subscriptions__status=Subscription.Status.ACTIVE)
                )
            )
            .order_by("last_paid", "name")
        )
        if q := params.get("q", "").strip()[:80]:
            turfs = turfs.filter(
                Q(name__icontains=q) | Q(owner_name__icontains=q) | Q(memberships__user__email__icontains=q)
            ).distinct()
        all_rows = [turf_row(t, today) for t in turfs]
        counts: dict[str, int] = {}
        for r in all_rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        rows = all_rows
        if state := params.get("state"):
            rows = [r for r in rows if r["state"] == state]
        if within := params.get("ending_within"):
            try:
                days = max(1, min(int(within), 365))
            except ValueError:
                days = 30
            rows = [r for r in rows if r["paid_until"] and 0 <= (r["paid_until"] - today).days <= days]
        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response(page)
        response.data["counts"] = counts
        response.data["grace_days"] = GRACE_DAYS
        return response


class AdminTurfSubscriptionHistoryView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request, pk):
        turf = get_object_or_404(Turf, pk=pk)
        periods = (
            Subscription.objects.filter(turf=turf)
            .select_related("plan", "created_by")
            .order_by("-created_at")[:50]
        )
        invoices = Invoice.objects.filter(turf=turf).select_related("promo_code").order_by("-created_at")[:50]
        events = AuditEvent.objects.filter(turf=turf, category=Category.SUBSCRIPTION).order_by("-created_at")[
            :30
        ]
        return Response(
            {
                **turf_row(
                    Turf.objects.prefetch_related("memberships__user").get(pk=turf.pk), timezone.localdate()
                ),
                "periods": [
                    {
                        "id": str(p.id),
                        "plan": p.plan.name,
                        "status": p.status,
                        "status_label": p.get_status_display(),
                        "starts_on": p.starts_on,
                        "ends_on": p.ends_on,
                        "price": str(p.price),
                        "note": p.note,
                        "by": (p.created_by.full_name or p.created_by.email) if p.created_by_id else None,
                    }
                    for p in periods
                ],
                "invoices": [
                    {
                        "id": str(i.id),
                        "number": getattr(i, "number", "") or str(i.id)[:8],
                        "status": i.status,
                        "amount": str(i.amount),
                        "discount": str(i.discount),
                        "promo_code": i.promo_code.code if i.promo_code_id else None,
                        "created_at": i.created_at,
                    }
                    for i in invoices
                ],
                "events": [{"at": e.created_at, "summary": e.summary, "by": e.actor_label} for e in events],
            }
        )


class ExtendSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=366)
    reason = serializers.CharField(min_length=5, max_length=200)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=200)


class AdminExtendSubscriptionView(APIView):
    """Add free days: lengthens the latest paid period, or starts a complimentary one from today."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=ExtendSerializer)
    @transaction.atomic
    def post(self, request, pk):
        turf = get_object_or_404(Turf.objects.select_for_update(), pk=pk)
        data = ExtendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        days, reason = data.validated_data["days"], data.validated_data["reason"].strip()
        today = timezone.localdate()
        latest = (
            Subscription.objects.select_for_update()
            .filter(turf=turf, status=Subscription.Status.ACTIVE)
            .order_by("-ends_on")
            .first()
        )
        if latest and latest.ends_on and latest.ends_on >= today - timedelta(days=GRACE_DAYS):
            before = latest.ends_on
            latest.ends_on = latest.ends_on + timedelta(days=days)
            latest.note = f"{latest.note} · +{days}d: {reason}".strip(" ·")[:200]
            latest.save(update_fields=["ends_on", "note", "updated_at"])
            summary = (
                f"Extended the plan by {days} days ({before:%d %b %Y} → {latest.ends_on:%d %b %Y}): {reason}"
            )
        else:
            plan = latest.plan if latest else Plan.objects.order_by("months").first()
            latest = Subscription.objects.create(
                turf=turf,
                plan=plan,
                status=Subscription.Status.ACTIVE,
                starts_on=today,
                ends_on=today + timedelta(days=days - 1),
                price=0,
                note=f"Complimentary {days} days: {reason}"[:200],
                created_by=request.user,
            )
            summary = f"Gave {days} complimentary days (until {latest.ends_on:%d %b %Y}): {reason}"
        record(
            "subscription.extended",
            summary[:255],
            category=Category.SUBSCRIPTION,
            request=request,
            turf=turf,
            target=latest,
        )
        return Response(turf_row(Turf.objects.prefetch_related("memberships__user").get(pk=turf.pk), today))


class AdminEndSubscriptionView(APIView):
    """Expire now: paid time ends yesterday (no grace), future periods are cancelled."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=ReasonSerializer)
    @transaction.atomic
    def post(self, request, pk):
        turf = get_object_or_404(Turf.objects.select_for_update(), pk=pk)
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reason = data.validated_data["reason"].strip()
        today = timezone.localdate()
        cutoff = today - timedelta(days=GRACE_DAYS + 1)  # before the grace window: stops at once
        active = Subscription.objects.select_for_update().filter(turf=turf, status=Subscription.Status.ACTIVE)
        cancelled = active.filter(starts_on__gt=cutoff).update(
            status=Subscription.Status.CANCELLED, updated_at=timezone.now()
        )
        ended = active.filter(ends_on__gt=cutoff).update(ends_on=cutoff, updated_at=timezone.now())
        from apps.homepage.models import clear_client_showcase_cache

        clear_client_showcase_cache()
        before = paid_until(turf)
        record(
            "subscription.ended",
            f"Ended the plan now ({ended} period(s) cut, {cancelled} future cancelled): {reason}"[:255],
            category=Category.SUBSCRIPTION,
            request=request,
            turf=turf,
            data={"paid_until_after": str(before)},
        )
        return Response(turf_row(Turf.objects.prefetch_related("memberships__user").get(pk=turf.pk), today))


def email_backend_name() -> str:
    """'smtp', 'console', 'Resend'… — the backend's short name (never its settings)."""
    module, _, cls = settings.EMAIL_BACKEND.rpartition(".")
    return module.rsplit(".", 1)[-1] if cls == "EmailBackend" else cls.replace("EmailBackend", "") or cls


class AdminHealthView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        from apps.bookings.models import Booking, PaymentSubmission
        from apps.notifications.models import SmsMessage
        from apps.notifications.providers import get_provider

        now = timezone.now()
        day_ago = now - timedelta(days=1)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        try:
            cache.set("health:admin", "1", 5)
            cache_ok = cache.get("health:admin") == "1"
        except Exception:  # noqa: BLE001
            cache_ok = False
        last_tick = cache.get("tick:last")
        tick_age = None
        if last_tick:
            try:
                tick_age = int((now - timezone.datetime.fromisoformat(last_tick["at"])).total_seconds() // 60)
            except (KeyError, ValueError):
                tick_age = None
        step_errors = {
            k: v
            for k, v in (last_tick or {}).get("results", {}).items()
            if isinstance(v, dict) and "error" in v
        }
        sms = SmsMessage.objects.filter(created_at__gte=day_ago).aggregate(
            failed=Count("id", filter=Q(status=SmsMessage.Status.FAILED)),
            unknown=Count("id", filter=Q(status=SmsMessage.Status.UNKNOWN)),
            waiting=Count("id", filter=Q(status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.SENDING])),
            sent=Count("id", filter=Q(status=SmsMessage.Status.SENT)),
        )
        recent_sms_errors = list(
            SmsMessage.objects.filter(
                status__in=[SmsMessage.Status.FAILED, SmsMessage.Status.UNKNOWN], created_at__gte=day_ago
            )
            .values("provider_code", "provider_message")
            .annotate(n=Count("id"))
            .order_by("-n")[:5]
        )
        accounts = AuditEvent.objects.filter(category=Category.ACCOUNT, created_at__gte=day_ago).aggregate(
            failed_logins=Count("id", filter=Q(action="account.login_failed")),
            resets=Count("id", filter=Q(action="account.password_reset")),
        )
        from axes.models import AccessAttempt

        locked = AccessAttempt.objects.filter(
            failures_since_start__gte=settings.AXES_FAILURE_LIMIT,
            attempt_time__gte=now - settings.AXES_COOLOFF_TIME,
        ).count()
        bookings = {
            "awaiting_verification": Booking.objects.awaiting_review(now)
            .filter(payment_submission__isnull=False)
            .count(),
            "expired_unverified_24h": PaymentSubmission.objects.filter(
                status=PaymentSubmission.Status.EXPIRED, updated_at__gte=day_ago
            ).count(),
            "requests_24h": PaymentSubmission.objects.filter(created_at__gte=day_ago).count(),
        }
        subscriptions = {
            "email_reminders_failed_7d": ReminderLog.objects.filter(
                status=ReminderLog.Status.FAILED, created_at__gte=now - timedelta(days=7)
            ).count(),
            "payments_awaiting_check": PaymentTransaction.objects.filter(
                status=PaymentTransaction.Status.PENDING_VERIFICATION
            ).count(),
        }
        events = AuditEvent.objects.filter(category__in=[Category.PLATFORM, Category.ACCOUNT]).order_by(
            "-created_at"
        )[:20]
        config = {
            "sms_provider": get_provider().name,
            "tick_endpoint": bool(settings.TICK_TOKEN),
            "email_backend": email_backend_name(),
            "online_payments": bool(getattr(settings, "SSLCOMMERZ_STORE_ID", "")),
        }
        problems = []
        if not db_ok:
            problems.append("Database is not answering.")
        if not cache_ok:
            problems.append("Cache is not working (sessions, rate limits and locks depend on it).")
        if tick_age is None:
            problems.append(
                "Background tasks have never run — set TICK_TOKEN and schedule the tick (see docs)."
            )
        elif tick_age > 30:
            problems.append(f"Background tasks last ran {tick_age} minutes ago (expected every 5–10).")
        if step_errors:
            problems.append("A background step failed: " + ", ".join(step_errors))
        if config["sms_provider"] == "disabled":
            problems.append("SMS is not connected (BULKSMSBD_API_KEY missing).")
        if sms["failed"] or sms["unknown"]:
            problems.append(f"{sms['failed'] + sms['unknown']} SMS failed or need checking in the last 24 h.")
        return Response(
            {
                "ok": not problems,
                "problems": problems,
                "database": db_ok,
                "cache": cache_ok,
                "tick": {
                    "last_run": last_tick["at"] if last_tick else None,
                    "minutes_ago": tick_age,
                    "errors": list(step_errors),
                },
                "sms_24h": sms,
                "sms_errors": recent_sms_errors,
                "accounts_24h": {**accounts, "locked_now": locked},
                "bookings": bookings,
                "subscriptions": subscriptions,
                "config": config,
                "events": [
                    {
                        "at": e.created_at,
                        "category": e.category,
                        "summary": e.summary,
                        "by": e.actor_label,
                        "turf": e.turf_name,
                    }
                    for e in events
                ],
            }
        )
