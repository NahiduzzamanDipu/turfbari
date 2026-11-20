"""Super Admin API: platform dashboard, applications pipeline, turf management, users."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import credentials
from apps.audit.services import Category, record
from apps.bookings.models import Booking, Payment
from apps.bookings.phone import normalize_bd_phone
from apps.common.permissions import IsPlatformAdmin
from apps.locations.models import Area, District
from apps.subscriptions.models import Invoice, PaymentTransaction, Plan, Subscription
from apps.subscriptions.serializers import standing_payload
from apps.turfs.models import Turf

from .models import TurfApplication
from .services import approve_application, create_turf_with_owner


def _deliver(owner, password, request) -> dict:
    """New owner account: send the temporary password by SMS (or show it once if SMS is unavailable)."""
    if not password:  # the owner already had an account
        return {"temporary_password": None, "credential": None}
    from apps.accounts.models import TemporaryCredential

    return credentials.start_delivery(
        owner, password, purpose=TemporaryCredential.Purpose.ACCOUNT_CREATED, by=request.user, request=request
    )


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
                "plans": plan_breakdown(),
                "payments_to_verify": PaymentTransaction.objects.filter(
                    status=PaymentTransaction.Status.PENDING_VERIFICATION
                ).count(),
            }
        )


def plan_breakdown() -> list[dict]:
    """How many turfs are on each plan today (current paid period)."""
    today = timezone.localdate()
    counts = dict(
        Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, starts_on__lte=today, ends_on__gte=today
        )
        .values_list("plan__period")
        .annotate(n=Count("turf", distinct=True))
    )
    return [
        {"period": p.period, "name": p.name, "turfs": counts.get(p.period, 0)} for p in Plan.objects.all()
    ]


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
    plan = serializers.SlugRelatedField(
        slug_field="period", queryset=Plan.objects.all(), required=False, allow_null=True
    )
    payment_received = serializers.BooleanField(default=True)


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
        app = serializer.instance
        record(
            "platform.application_updated",
            f"Marked application “{app.turf_name}” as {app.get_status_display().lower()}",
            category=Category.PLATFORM,
            request=self.request,
            target=app,
        )

    @extend_schema(request=ApproveSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        data = ApproveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = approve_application(self.get_object(), reviewer=request.user, **data.validated_data)
        delivery = _deliver(result["owner"], result["temporary_password"], request)
        record(
            "platform.application_approved",
            f"Approved application and created turf “{result['turf'].name}” for {result['owner'].email}",
            category=Category.PLATFORM,
            request=request,
            turf=result["turf"],
            target=result["turf"],
        )
        return Response(
            {
                "application": ApplicationAdminSerializer(TurfApplication.objects.get(pk=pk)).data,
                "turf": {
                    "id": str(result["turf"].id),
                    "name": result["turf"].name,
                    "slug": result["turf"].slug,
                },
                "owner_email": result["owner"].email,
                **delivery,
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
    subscription = serializers.SerializerMethodField()

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
            "subscription",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "min_public_price", "created_at"]

    def get_subscription(self, obj):
        payload = standing_payload(obj)
        open_invoice = (
            obj.invoices.filter(status__in=Invoice.OPEN).select_related("subscription__plan").first()
        )
        payload["open_order"] = (
            {
                "plan": open_invoice.subscription.plan.name,
                "status": open_invoice.status,
                "amount": str(open_invoice.amount),
            }
            if open_invoice
            else None
        )
        return payload

    def get_owner_email(self, obj):
        m = next((m for m in obj.memberships.all() if m.role == "owner" and m.is_active), None)
        return m.user.email if m else None


class TurfCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    district = serializers.SlugRelatedField(slug_field="slug", queryset=District.objects.all())
    area = serializers.SlugRelatedField(
        slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False, default=None
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
    plan = serializers.SlugRelatedField(
        slug_field="period", queryset=Plan.objects.all(), required=False, allow_null=True
    )
    payment_received = serializers.BooleanField(default=True)

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
        if plan := params.get("plan"):
            today = timezone.localdate()
            current = Subscription.objects.filter(
                status=Subscription.Status.ACTIVE, starts_on__lte=today, ends_on__gte=today
            )
            if plan == "none":
                qs = qs.exclude(id__in=current.values("turf_id"))
            else:
                qs = qs.filter(id__in=current.filter(plan__period=plan).values("turf_id"))
        return qs

    def perform_update(self, serializer):
        turf = serializer.instance
        changes = {
            k: (str(getattr(turf, k)), str(v))
            for k, v in serializer.validated_data.items()
            if getattr(turf, k) != v
        }
        serializer.save()
        if changes:
            readable = ", ".join(f"{k.replace('_', ' ')}: {old} → {new}" for k, (old, new) in changes.items())
            record(
                "platform.turf_updated",
                f"Changed {readable}"[:255],
                category=Category.PLATFORM,
                request=self.request,
                turf=turf,
                target=turf,
                data={"changes": changes},
            )

    @extend_schema(request=TurfCreateSerializer)
    def create(self, request, *args, **kwargs):
        data = TurfCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["owner_email"].strip().lower()
        if not get_user_model().objects.filter(email=email).exists():
            credentials.require_phone(data.validated_data.get("owner_phone", ""))
        with transaction.atomic():
            turf, owner, password = create_turf_with_owner(**data.validated_data, assigned_by=request.user)
            delivery = _deliver(owner, password, request)
        record(
            "platform.turf_created",
            f"Created turf “{turf.name}” for {owner.email}",
            category=Category.PLATFORM,
            request=request,
            turf=turf,
            target=turf,
        )
        return Response(
            {
                "turf": TurfAdminSerializer(self.get_queryset().get(pk=turf.pk)).data,
                "owner_email": owner.email,
                **delivery,
            },
            status=201,
        )
