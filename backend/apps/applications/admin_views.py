"""Super Admin API: platform dashboard, applications pipeline, turf management, users."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking, Payment
from apps.bookings.phone import normalize_bd_phone
from apps.common.permissions import IsPlatformAdmin
from apps.locations.models import Area, District
from apps.turfs.models import Turf

from .models import TurfApplication
from .services import approve_application, create_turf_with_owner


class AdminDashboardView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        now = timezone.now()
        month_start = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        turfs = Turf.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status=Turf.Status.ACTIVE)),
            suspended=Count("id", filter=Q(status=Turf.Status.SUSPENDED)),
            listed=Count("id", filter=Q(status=Turf.Status.ACTIVE, is_listed=True)),
        )
        bookings_month = Booking.objects.filter(start__gte=month_start).exclude(
            status__in=[Booking.Status.CANCELLED, Booking.Status.REJECTED]
        )
        gmv = Payment.objects.filter(paid_at__gte=month_start, kind=Payment.Kind.PAYMENT).aggregate(
            s=Sum("amount")
        )["s"] or Decimal("0")
        recent = TurfApplication.objects.select_related("district")[:5]
        return Response(
            {
                "turfs": turfs,
                "applications_pending": TurfApplication.objects.filter(
                    status__in=[TurfApplication.Status.PENDING, TurfApplication.Status.CONTACTED]
                ).count(),
                "bookings_this_month": bookings_month.count(),
                "payments_this_month": str(gmv),
                "users": get_user_model().objects.filter(is_active=True).count(),
                "recent_applications": ApplicationAdminSerializer(recent, many=True).data,
                "new_turfs_30d": Turf.objects.filter(created_at__gte=now - timedelta(days=30)).count(),
            }
        )


class ApplicationAdminSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source="district.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    turf_slug = serializers.CharField(source="turf.slug", read_only=True, default=None)
    reviewed_by_email = serializers.CharField(source="reviewed_by.email", read_only=True, default=None)

    class Meta:
        model = TurfApplication
        fields = [
            "id",
            "turf_name",
            "owner_name",
            "phone",
            "email",
            "district_name",
            "area_name",
            "address",
            "turf_type",
            "number_of_fields",
            "message",
            "status",
            "admin_note",
            "reviewed_by_email",
            "reviewed_at",
            "turf_slug",
            "created_at",
        ]
        read_only_fields = [f for f in fields if f not in ("status", "admin_note")]

    def validate_status(self, value):
        if value == TurfApplication.Status.APPROVED:
            raise serializers.ValidationError("Use the approve action to approve an application.")
        if self.instance and self.instance.status == TurfApplication.Status.APPROVED:
            raise serializers.ValidationError("Approved applications cannot change status.")
        return value


class ApproveSerializer(serializers.Serializer):
    hourly_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("1500.00")
    )


class ApplicationAdminViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsPlatformAdmin]
    serializer_class = ApplicationAdminSerializer
    filter_backends = []

    def get_queryset(self):
        qs = TurfApplication.objects.select_related("district", "area", "turf", "reviewed_by")
        params = self.request.query_params
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(turf_name__icontains=q)
                | Q(owner_name__icontains=q)
                | Q(email__icontains=q)
                | Q(phone__icontains=q)
            )
        return qs

    def perform_update(self, serializer):
        serializer.save(reviewed_by=self.request.user, reviewed_at=timezone.now())

    @extend_schema(request=ApproveSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        data = ApproveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = approve_application(self.get_object(), reviewer=request.user, **data.validated_data)
        return Response(
            {
                "application": ApplicationAdminSerializer(TurfApplication.objects.get(pk=pk)).data,
                "turf": {
                    "id": str(result["turf"].id),
                    "name": result["turf"].name,
                    "slug": result["turf"].slug,
                },
                "owner_email": result["owner"].email,
                "temporary_password": result["temporary_password"],
            }
        )


class TurfAdminSerializer(serializers.ModelSerializer):
    district = serializers.SlugRelatedField(slug_field="slug", queryset=District.objects.all())
    area = serializers.SlugRelatedField(
        slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False
    )
    district_name = serializers.CharField(source="district.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    owner_email = serializers.SerializerMethodField()
    fields_count = serializers.IntegerField(read_only=True)
    bookings_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Turf
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "district",
            "area",
            "district_name",
            "area_name",
            "address",
            "turf_type",
            "surface",
            "owner_name",
            "owner_phone",
            "owner_email",
            "contract_notes",
            "is_listed",
            "is_featured",
            "public_booking_enabled",
            "min_public_price",
            "fields_count",
            "bookings_count",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "min_public_price", "created_at"]

    def get_owner_email(self, obj):
        m = next((m for m in obj.memberships.all() if m.role == "owner" and m.is_active), None)
        return m.user.email if m else None


class TurfCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    district = serializers.SlugRelatedField(slug_field="slug", queryset=District.objects.all())
    area = serializers.SlugRelatedField(
        slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False
    )
    address = serializers.CharField(max_length=255)
    turf_type = serializers.ChoiceField(choices=Turf.TurfType.choices, default=Turf.TurfType.OUTDOOR)
    owner_email = serializers.EmailField()
    owner_name = serializers.CharField(max_length=120)
    owner_phone = serializers.CharField(max_length=20)
    number_of_fields = serializers.IntegerField(min_value=1, max_value=20, default=1)
    hourly_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("1500.00")
    )

    def validate_owner_phone(self, value):
        return normalize_bd_phone(value)


class TurfAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsPlatformAdmin]
    serializer_class = TurfAdminSerializer
    filter_backends = []

    def get_queryset(self):
        qs = (
            Turf.objects.select_related("district", "area")
            .prefetch_related("memberships__user")
            .annotate(
                fields_count=Count("fields", distinct=True), bookings_count=Count("bookings", distinct=True)
            )
            .order_by("-created_at")
        )
        params = self.request.query_params
        if status := params.get("status"):
            qs = qs.filter(status=status)
        if q := params.get("q", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(address__icontains=q) | Q(owner_name__icontains=q))
        return qs

    @extend_schema(request=TurfCreateSerializer)
    def create(self, request, *args, **kwargs):
        data = TurfCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        turf, owner, password = create_turf_with_owner(**data.validated_data)
        return Response(
            {
                "turf": TurfAdminSerializer(self.get_queryset().get(pk=turf.pk)).data,
                "owner_email": owner.email,
                "temporary_password": password,
            },
            status=201,
        )
