"""Registration payment API: public quote / status / resubmit, and Super Admin verification."""

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination
from apps.common.permissions import IsPlatformAdmin

from . import registration
from .models import RegistrationPayment


class PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]


class RegistrationOptionsView(PublicView):
    throttle_scope = "registration_quote"

    @extend_schema(tags=["public"])
    def get(self, request):
        return Response(
            {
                "plans": registration.plans(),
                "receiving": registration.receiving(),
                "payments_open": registration.payments_open(),
            }
        )


class RegistrationQuoteView(PublicView):
    """Server-calculated price for a plan and (optional) promo code. Nothing is reserved here."""

    throttle_scope = "registration_quote"

    @extend_schema(tags=["public"], request=None)
    def post(self, request):
        return Response(registration.public_quote(request.data))


class RegistrationStatusView(PublicView):
    """Applicants check progress with their registration reference + the mobile number they used."""

    throttle_scope = "registration_status"

    @extend_schema(tags=["public"], request=None)
    def post(self, request):
        return Response(registration.lookup(request.data.get("reference", ""), request.data.get("phone", "")))


class RegistrationResubmitView(PublicView):
    throttle_scope = "public_application"

    @extend_schema(tags=["public"], request=None)
    def post(self, request):
        return Response(registration.resubmit(request.data, request=request))


# ------------------------------------------------------------------ admin
class AdminRegistrationPaymentsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        qs = RegistrationPayment.objects.select_related("application", "plan", "reviewed_by")
        params = request.query_params
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if promo := params.get("promo"):
            qs = qs.filter(promo_snapshot__code=promo.upper())
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(application__reference__icontains=q)
                | Q(application__turf_name__icontains=q)
                | Q(application__owner_name__icontains=q)
                | Q(application__phone__icontains=q)
                | Q(application__email__icontains=q)
                | Q(trx_id__icontains=q)
                | Q(sender_number__icontains=q)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response([registration.admin_row(p) for p in page])
        response.data["report"] = registration.report()
        return response


def _payment(pk) -> RegistrationPayment:
    p = RegistrationPayment.objects.filter(pk=pk).first()
    if p is None:
        raise NotFound()
    return p


class ApproveSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AdminRegistrationApproveView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=ApproveSerializer)
    def post(self, request, pk):
        data = ApproveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = registration.approve(
            _payment(pk), admin=request.user, note=data.validated_data.get("note", ""), request=request
        )
        payment = RegistrationPayment.objects.select_related("application", "plan", "reviewed_by").get(pk=pk)
        delivery = result["delivery"] or {"credential": None, "temporary_password": None}
        return Response(registration.admin_row(payment) | {"duplicate": result["duplicate"], **delivery})


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    allow_resubmit = serializers.BooleanField(default=True)


class AdminRegistrationRejectView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=RejectSerializer)
    def post(self, request, pk):
        data = RejectSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        registration.reject(
            _payment(pk),
            admin=request.user,
            reason=data.validated_data["reason"],
            allow_resubmit=data.validated_data["allow_resubmit"],
            request=request,
        )
        payment = RegistrationPayment.objects.select_related("application", "plan", "reviewed_by").get(pk=pk)
        return Response(registration.admin_row(payment))
