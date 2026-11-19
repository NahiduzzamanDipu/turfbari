"""Live updates without WebSockets: GET /api/live/ returns a cheap "change version" for what the
signed-in user can see. The web app polls it every few seconds and refetches its data only when the
version changes, and shows a notification when new work arrives (online booking requests for a
turf; new turf applications and payments to verify for the Super Admin).

Polling suits the free single-process hosting (no long-lived connections to hold open). The version
is built from (row count, latest updated_at) per table, so creates, edits and deletes all change it.
"""

import hashlib

from django.db.models import Count, Max
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .tenancy import resolve_membership


def _fingerprint(querysets) -> str:
    parts = []
    for qs in querysets:
        agg = qs.aggregate(n=Count("pk"), latest=Max("updated_at"))
        parts.append(f"{agg['n']}:{agg['latest'].isoformat() if agg['latest'] else '-'}")
    return hashlib.sha1("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:16]


def _workspace_state(turf) -> dict:
    from apps.bookings.models import Booking, Customer, MaintenanceBlock, Payment
    from apps.expenses.models import Expense
    from apps.subscriptions.models import Invoice, PaymentTransaction, Subscription
    from apps.turfs.models import OperatingHours, PricingRule, TenantMembership, Turf, TurfField, TurfPhoto

    scoped = [
        model.objects.filter(turf=turf)
        for model in (
            Booking,
            Payment,
            Customer,
            MaintenanceBlock,
            Expense,
            Subscription,
            Invoice,
            TurfField,
            OperatingHours,
            PricingRule,
            TurfPhoto,
            TenantMembership,
        )
    ]
    scoped += [PaymentTransaction.objects.filter(invoice__turf=turf), Turf.objects.filter(pk=turf.pk)]
    pending = Booking.objects.awaiting_review().filter(turf=turf)
    newest = pending.select_related("customer", "field").order_by("-created_at").first()
    return {
        "version": _fingerprint(scoped),
        "scope": "workspace",
        "turf_id": str(turf.pk),
        "pending_requests": pending.count(),
        # Pending bookings with a bKash submission (Payment verification) vs. without (e.g. made by staff).
        "pending_payments_to_verify": pending.filter(payment_submission__isnull=False).count(),
        "pending_bookings": pending.filter(payment_submission__isnull=True).count(),
        "latest_request": (
            {
                "id": str(newest.pk),
                "reference": newest.reference,
                "name": newest.team_name or newest.customer.name,
                "field": newest.field.name,
                "start": newest.start.isoformat(),
                "created_at": newest.created_at.isoformat(),
            }
            if newest
            else None
        ),
    }


def _admin_state() -> dict:
    from apps.applications.models import TurfApplication
    from apps.subscriptions.models import Invoice, PaymentTransaction, Subscription
    from apps.turfs.models import Turf

    pending_apps = TurfApplication.objects.filter(status=TurfApplication.Status.PENDING)
    pending_payments = PaymentTransaction.objects.filter(
        status=PaymentTransaction.Status.PENDING_VERIFICATION
    )
    return {
        "version": _fingerprint(
            [
                TurfApplication.objects.all(),
                PaymentTransaction.objects.all(),
                Invoice.objects.all(),
                Subscription.objects.all(),
                Turf.objects.all(),
            ]
        ),
        "scope": "admin",
        "pending_applications": pending_apps.count(),
        "pending_payments": pending_payments.count(),
    }


class LiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["live"])
    def get(self, request):
        area = request.query_params.get("area")
        if area == "admin" and request.user.is_platform_admin:
            data = _admin_state()
        else:
            membership = resolve_membership(request)
            data = _workspace_state(membership.turf) if membership else {"version": "none", "scope": "none"}
        response = Response(data)
        response["Cache-Control"] = "no-store"
        return response
