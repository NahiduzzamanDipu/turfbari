"""Workspace API for advance & recurring bookings (owners, and managers with "advance_bookings")."""

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination
from apps.common.tenancy import IsTenantMember

from . import recurring
from .models import BookingSeries, Payment
from .workspace_views import sms_outcome


class SeriesAPIView(APIView):
    permission_classes = [IsTenantMember]
    required_permission = "advance_bookings"

    def series(self, pk) -> BookingSeries:
        s = (
            BookingSeries.objects.filter(turf=self.request.tenant, pk=pk)
            .select_related("customer", "field", "turf", "created_by")
            .first()
        )
        if s is None:
            raise NotFound("Series not found.")
        return s


class SeriesListView(SeriesAPIView):
    @extend_schema(tags=["workspace"])
    def get(self, request):
        qs = BookingSeries.objects.filter(turf=request.tenant).select_related(
            "customer", "field", "created_by"
        )
        params = request.query_params
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(reference__icontains=q) | Q(customer__name__icontains=q) | Q(customer__phone__icontains=q)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            [recurring.series_payload(s, occurrences=False) for s in page]
        )

    @extend_schema(tags=["workspace"], request=None)
    def post(self, request):
        key = (request.headers.get("Idempotency-Key") or "").strip()[:40] or None
        series, sms = recurring.create_series(
            request.tenant, request.data, user=request.user, request=request, idempotency_key=key
        )
        return Response(recurring.series_payload(series) | {"sms": sms_outcome(sms)}, status=201)


class SeriesPreviewView(SeriesAPIView):
    @extend_schema(tags=["workspace"], request=None)
    def post(self, request):
        return Response(recurring.preview(request.tenant, request.data))


class SeriesDetailView(SeriesAPIView):
    @extend_schema(tags=["workspace"])
    def get(self, request, pk):
        return Response(recurring.series_payload(self.series(pk)))


class ConfirmSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True)


class SeriesConfirmView(SeriesAPIView):
    @extend_schema(tags=["workspace"], request=ConfirmSerializer)
    def post(self, request, pk):
        data = ConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        sms = recurring.confirm_series(
            self.series(pk),
            amount=v["amount"],
            method=v["method"],
            reference=v.get("reference", ""),
            user=request.user,
            request=request,
        )
        return Response(recurring.series_payload(self.series(pk)) | {"sms": sms_outcome(sms)})


class CancelSerializer(serializers.Serializer):
    booking_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    all_future = serializers.BooleanField(default=False)


class SeriesCancelView(SeriesAPIView):
    @extend_schema(tags=["workspace"], request=CancelSerializer)
    def post(self, request, pk):
        data = CancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        result = recurring.cancel(
            self.series(pk),
            booking_ids=v.get("booking_ids"),
            all_future=v["all_future"],
            user=request.user,
            request=request,
        )
        result["sms"] = sms_outcome(result["sms"])
        return Response(recurring.series_payload(self.series(pk)) | {"result": result})


class AddDateSerializer(serializers.Serializer):
    date = serializers.DateField()
    dry_run = serializers.BooleanField(default=False)


class SeriesAddDateView(SeriesAPIView):
    @extend_schema(tags=["workspace"], request=AddDateSerializer)
    def post(self, request, pk):
        data = AddDateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = recurring.add_date(
            self.series(pk),
            data.validated_data["date"],
            user=request.user,
            request=request,
            dry_run=data.validated_data["dry_run"],
        )
        result["sms"] = sms_outcome(result.get("sms"))
        return Response(recurring.series_payload(self.series(pk)) | {"result": result})


class RescheduleSerializer(serializers.Serializer):
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    from_date = serializers.DateField(required=False, allow_null=True)
    keep_dates = serializers.ListField(child=serializers.DateField(), required=False)
    dry_run = serializers.BooleanField(default=True)


class SeriesRescheduleView(SeriesAPIView):
    @extend_schema(tags=["workspace"], request=RescheduleSerializer)
    def post(self, request, pk):
        data = RescheduleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        result = recurring.reschedule(
            self.series(pk),
            start_time=v["start_time"],
            end_time=v["end_time"],
            from_date=v.get("from_date"),
            keep_dates=v.get("keep_dates") or [],
            user=request.user,
            request=request,
            dry_run=v["dry_run"],
        )
        result["sms"] = sms_outcome(result.get("sms"))
        return Response(recurring.series_payload(self.series(pk)) | {"result": result})
