"""Payment Verification (পেমেন্ট যাচাই): bKash submissions waiting for an owner or manager.

Everyone in the workspace can see the queue; approving or rejecting needs the owner role or the
manager permission "approve_payments" (enforced here, not just hidden in the UI).
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, booking_label, record
from apps.common.pagination import StandardPagination
from apps.common.tenancy import IsTenantMember

from . import payments
from .models import Booking, PaymentSubmission
from .services import overlapping_bookings


def submission_row(s: PaymentSubmission) -> dict:
    b = s.booking
    now = timezone.now()
    status = s.status
    if status == PaymentSubmission.Status.PENDING and b.hold_expires_at and b.hold_expires_at <= now:
        status = PaymentSubmission.Status.EXPIRED
    conflict = False
    if status in (PaymentSubmission.Status.PENDING, PaymentSubmission.Status.EXPIRED):
        conflict = overlapping_bookings(b.field_id, b.start, b.end, exclude_id=b.pk).exists()
    return {
        "id": str(s.id),
        "status": status,
        "status_label": PaymentSubmission.Status(status).label,
        "submitted_at": s.created_at,
        "amount": str(s.amount),
        "sender_number": s.sender_number,
        "trx_id": s.trx_id,
        "reviewed_by": (s.reviewed_by.full_name or s.reviewed_by.email) if s.reviewed_by_id else None,
        "reviewed_at": s.reviewed_at,
        "rejection_reason": s.rejection_reason or None,
        "slot_conflict": conflict,
        "booking": {
            "id": str(b.id),
            "reference": b.reference,
            "status": b.status,
            "customer_name": b.customer.name,
            "customer_phone": b.customer.phone,
            "team_name": b.team_name,
            "field": b.field.name,
            "start": timezone.localtime(b.start).isoformat(),
            "end": timezone.localtime(b.end).isoformat(),
            "total": str(b.total),
            "amount_paid": str(b.amount_paid),
            "hold_expires_at": timezone.localtime(b.hold_expires_at).isoformat()
            if b.hold_expires_at
            else None,
            "notes": b.notes,
        },
    }


def base_qs(turf):
    return PaymentSubmission.objects.filter(turf=turf).select_related(
        "booking__customer", "booking__field", "reviewed_by"
    )


class PaymentVerificationListView(APIView):
    permission_classes = [IsTenantMember]

    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        now = timezone.now()
        params = request.query_params
        status = params.get("status", "pending")
        qs = base_qs(turf)
        live_pending = Q(status=PaymentSubmission.Status.PENDING, booking__hold_expires_at__gt=now)
        expired = Q(status=PaymentSubmission.Status.EXPIRED) | Q(
            status=PaymentSubmission.Status.PENDING, booking__hold_expires_at__lte=now
        )
        if status == "pending":
            qs = qs.filter(live_pending).order_by("booking__hold_expires_at")
        elif status == "expired":
            qs = qs.filter(expired)
        elif status in (PaymentSubmission.Status.APPROVED, PaymentSubmission.Status.REJECTED):
            qs = qs.filter(status=status).order_by("-reviewed_at")
        if q := params.get("q", "").strip()[:60]:
            digits = "".join(ch for ch in q if ch.isdigit())
            cond = (
                Q(trx_id__icontains=q)
                | Q(booking__reference__icontains=q)
                | Q(booking__customer__name__icontains=q)
                | Q(booking__team_name__icontains=q)
            )
            if len(digits) >= 4:
                cond |= Q(sender_number__contains=digits[-10:]) | Q(
                    booking__customer__phone__contains=digits[-10:]
                )
            qs = qs.filter(cond)
        counts = base_qs(turf).aggregate(
            pending=Count("id", filter=live_pending),
            expired=Count("id", filter=expired),
            approved=Count("id", filter=Q(status=PaymentSubmission.Status.APPROVED)),
            rejected=Count("id", filter=Q(status=PaymentSubmission.Status.REJECTED)),
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response([submission_row(s) for s in page])
        response.data["counts"] = counts
        response.data["can_review"] = request.membership.can("approve_payments")
        return response


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


class PaymentApproveView(APIView):
    permission_classes = [IsTenantMember]
    required_permission = "approve_payments"

    @extend_schema(tags=["workspace"], request=None)
    def post(self, request, pk):
        submission = get_object_or_404(base_qs(request.tenant), pk=pk)
        booking = payments.approve(submission, user=request.user)
        record(
            "booking.payment_approved",
            f"Approved bKash ৳{submission.amount:,.0f} (TrxID {submission.trx_id}) and confirmed "
            f"{booking_label(booking)}",
            category=Category.PAYMENT,
            request=request,
            target=booking,
            data={"trx_id": submission.trx_id, "amount": str(submission.amount)},
        )
        return Response(submission_row(base_qs(request.tenant).get(pk=pk)))


class PaymentRejectView(APIView):
    permission_classes = [IsTenantMember]
    required_permission = "approve_payments"

    @extend_schema(tags=["workspace"], request=RejectSerializer)
    def post(self, request, pk):
        submission = get_object_or_404(base_qs(request.tenant), pk=pk)
        data = RejectSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reason = data.validated_data.get("reason", "")
        booking = payments.reject(submission, user=request.user, reason=reason)
        record(
            "booking.payment_rejected",
            f"Rejected bKash ৳{submission.amount:,.0f} (TrxID {submission.trx_id}) for "
            f"{booking_label(booking)}" + (f": {reason}" if reason else ""),
            category=Category.PAYMENT,
            request=request,
            target=booking,
            data={"trx_id": submission.trx_id, "reason": reason},
        )
        return Response(submission_row(base_qs(request.tenant).get(pk=pk)))


def pending_verifications(turf) -> int:
    return Booking.objects.awaiting_review().filter(turf=turf, payment_submission__isnull=False).count()
