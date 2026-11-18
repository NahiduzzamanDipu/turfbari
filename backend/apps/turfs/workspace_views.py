"""Workspace configuration: fields, hours, pricing, turf settings, managers."""

import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.tenancy import IsTenantMember, TenantViewSet

from .models import OperatingHours, PricingRule, TenantMembership, TurfField
from .pricing import recompute_min_price
from .serializers import FieldSerializer, HoursSerializer, PricingRuleSerializer, TurfSettingsSerializer


class FieldViewSet(TenantViewSet):
    queryset = TurfField.objects.all()
    serializer_class = FieldSerializer
    owner_only_writes = True
    filter_backends = []
    pagination_class = None

    def perform_create(self, serializer):
        super().perform_create(serializer)
        recompute_min_price(self.request.tenant)

    def perform_update(self, serializer):
        serializer.save()
        recompute_min_price(self.request.tenant)

    def destroy(self, request, *args, **kwargs):
        field = self.get_object()
        if field.bookings.exists():
            raise ValidationError(
                {"field": ["This field has bookings, so it can't be deleted. Mark it inactive instead."]}
            )
        field.delete()
        recompute_min_price(request.tenant)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PricingRuleViewSet(TenantViewSet):
    queryset = PricingRule.objects.select_related("field")
    serializer_class = PricingRuleSerializer
    owner_only_writes = True
    filter_backends = []
    pagination_class = None

    def perform_create(self, serializer):
        super().perform_create(serializer)
        recompute_min_price(self.request.tenant)

    def perform_update(self, serializer):
        serializer.save()
        recompute_min_price(self.request.tenant)

    def perform_destroy(self, instance):
        instance.delete()
        recompute_min_price(self.request.tenant)


class HoursView(APIView):
    permission_classes = [IsTenantMember]
    owner_only_writes = True

    @extend_schema(tags=["workspace"], responses=HoursSerializer(many=True))
    def get(self, request):
        return Response(HoursSerializer(OperatingHours.objects.filter(turf=request.tenant), many=True).data)

    @extend_schema(
        tags=["workspace"], request=HoursSerializer(many=True), responses=HoursSerializer(many=True)
    )
    @transaction.atomic
    def put(self, request):
        data = HoursSerializer(data=request.data, many=True)
        data.is_valid(raise_exception=True)
        days = [row["weekday"] for row in data.validated_data]
        if sorted(days) != list(range(7)):
            raise ValidationError({"non_field_errors": ["Send exactly one row for each weekday 0–6."]})
        for row in data.validated_data:
            if not row["is_closed"] and row["opens_at"] == row["closes_at"]:
                raise ValidationError({"non_field_errors": ["Opening and closing time can't be the same."]})
            OperatingHours.objects.update_or_create(
                turf=request.tenant,
                weekday=row["weekday"],
                defaults={k: row[k] for k in ("opens_at", "closes_at", "is_closed")},
            )
        return self.get(request)


class SettingsView(APIView):
    permission_classes = [IsTenantMember]
    owner_only_writes = True

    @extend_schema(tags=["workspace"], responses=TurfSettingsSerializer)
    def get(self, request):
        return Response(TurfSettingsSerializer(request.tenant).data)

    @extend_schema(tags=["workspace"], request=TurfSettingsSerializer, responses=TurfSettingsSerializer)
    def patch(self, request):
        data = TurfSettingsSerializer(request.tenant, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(data.data)


class ManagerSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


def manager_row(m: TenantMembership) -> dict:
    return {
        "id": str(m.id),
        "email": m.user.email,
        "full_name": m.user.full_name,
        "phone": m.user.phone,
        "role": m.role,
        "is_active": m.is_active,
    }


class ManagersView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], responses=ManagerSerializer(many=True))
    def get(self, request):
        rows = TenantMembership.objects.filter(turf=request.tenant, is_active=True).select_related("user")
        return Response([manager_row(m) for m in rows.order_by("role", "user__full_name")])

    @extend_schema(tags=["workspace"], request=ManagerSerializer)
    @transaction.atomic
    def post(self, request):
        data = ManagerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        User = get_user_model()
        email = v["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        password = None
        if user is None:
            password = secrets.token_urlsafe(9)
            user = User.objects.create_user(
                email, password, full_name=v["full_name"], phone=v.get("phone", "")
            )
        elif user.is_platform_admin:
            raise ValidationError({"email": ["This email can't be added as a manager."]})
        membership, created = TenantMembership.objects.get_or_create(
            user=user, turf=request.tenant, defaults={"role": TenantMembership.Role.MANAGER}
        )
        if not created:
            if membership.is_active:
                raise ValidationError({"email": ["This person already has access to your turf."]})
            membership.is_active = True
            membership.role = TenantMembership.Role.MANAGER
            membership.save(update_fields=["is_active", "role", "updated_at"])
        return Response({**manager_row(membership), "temporary_password": password}, status=201)


class ManagerDetailView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], responses={204: None})
    def delete(self, request, pk):
        membership = TenantMembership.objects.filter(turf=request.tenant, pk=pk, is_active=True).first()
        if membership is None:
            return Response(
                {"error": {"code": "not_found", "message": "Not found.", "fields": None}}, status=404
            )
        if membership.role == TenantMembership.Role.OWNER:
            raise ValidationError({"role": ["The owner can't be removed."]})
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
