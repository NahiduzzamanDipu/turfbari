from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.models import PlatformSettings
from apps.common.permissions import IsPlatformAdmin
from apps.notifications.models import SmsPricing
from apps.subscriptions.models import Plan, Subscription
from apps.turfs.models import Turf

from .models import HomepageFAQ, TurfOnboarding, TurfOnboardingEvent


class PublicPlansView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True, is_public=True).order_by("display_order", "months")
        return Response(
            [
                {
                    "id": p.pk,
                    "period": p.period,
                    "name": p.name,
                    "months": p.months,
                    "price": str(p.price),
                    "description": p.description,
                    "featured": p.featured,
                    "features": p.features,
                    "limits": p.limits,
                    "sms_enabled": p.sms_enabled,
                }
                for p in plans
            ]
        )


class PublicSmsPricingView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        price = (
            SmsPricing.objects.filter(effective_from__lte=timezone.now())
            .order_by("-effective_from", "-id")
            .first()
        )
        if not price:
            return Response({"configured": False, "price_per_segment": None, "examples": []})
        rate = Decimal(price.price_per_segment)
        counts = (1, 2, 3, 5, 10)
        return Response(
            {
                "configured": True,
                "price_per_segment": str(rate),
                "effective_from": price.effective_from,
                "examples": [
                    {"segments": n, "cost": str((rate * n).quantize(Decimal("0.01")))} for n in counts
                ],
            }
        )


class PublicYoutubeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        settings = PlatformSettings.load()
        return Response({"video_id": settings.youtube_video_id or None})


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomepageFAQ
        fields = [
            "id",
            "question_en",
            "question_bn",
            "answer_en",
            "answer_bn",
            "display_order",
            "is_published",
        ]
        read_only_fields = ["id"]

    def validate_question_en(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("English question is required.")
        return value


class PublicFAQsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        qs = HomepageFAQ.objects.filter(is_published=True).only(
            "id", "question_en", "question_bn", "answer_en", "answer_bn", "display_order"
        )
        return Response(FAQSerializer(qs, many=True).data)


class AdminFAQsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(FAQSerializer(HomepageFAQ.objects.all(), many=True).data)

    def post(self, request):
        serializer = FAQSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        faq = serializer.save(created_by=request.user, updated_by=request.user)
        record(
            "platform.homepage_faq_created",
            "Created homepage FAQ",
            category=Category.PLATFORM,
            request=request,
            target=faq,
        )
        return Response(FAQSerializer(faq).data, status=201)

    def put(self, request, pk=None):
        faq = get_object_or_404(HomepageFAQ, pk=pk)
        serializer = FAQSerializer(faq, data=request.data)
        serializer.is_valid(raise_exception=True)
        faq = serializer.save(updated_by=request.user)
        record(
            "platform.homepage_faq_updated",
            "Updated homepage FAQ",
            category=Category.PLATFORM,
            request=request,
            target=faq,
        )
        return Response(FAQSerializer(faq).data)

    patch = put

    def delete(self, request, pk=None):
        faq = get_object_or_404(HomepageFAQ, pk=pk)
        record(
            "platform.homepage_faq_deleted",
            "Deleted homepage FAQ",
            category=Category.PLATFORM,
            request=request,
            target=faq,
        )
        faq.delete()
        return Response(status=204)


TOPICS = [
    "Account setup",
    "Turf profile",
    "Slots and pricing",
    "Booking management",
    "Payment verification",
    "Booking page and QR",
    "SMS wallet and messaging",
    "Staff management",
    "Reports and dashboard",
]


class OnboardingSerializer(serializers.ModelSerializer):
    turf_name = serializers.CharField(source="turf.name", read_only=True)
    owner_name = serializers.CharField(source="turf.owner_name", read_only=True)
    owner_phone = serializers.CharField(source="turf.owner_phone", read_only=True)
    plan_name = serializers.SerializerMethodField()
    activation_date = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    class Meta:
        model = TurfOnboarding
        fields = [
            "id",
            "turf",
            "turf_name",
            "owner_name",
            "owner_phone",
            "plan_name",
            "activation_date",
            "status",
            "assigned_to",
            "assigned_to_name",
            "training_at",
            "notes",
            "topics",
            "events",
            "updated_at",
        ]
        read_only_fields = ["id", "turf"]

    def get_plan_name(self, obj):
        subscriptions = getattr(obj.turf, "onboarding_subscriptions", None)
        if subscriptions is None:
            subscriptions = list(
                obj.turf.subscriptions.filter(status=Subscription.Status.ACTIVE)
                .select_related("plan")
                .order_by("-ends_on")
            )
        sub = subscriptions[0] if subscriptions else None
        return (sub.plan_snapshot or {}).get("name") or sub.plan.name if sub else None

    def get_activation_date(self, obj):
        return getattr(obj, "first_activated_on", None)

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.full_name or obj.assigned_to.email if obj.assigned_to else None

    def get_events(self, obj):
        events = getattr(obj, "recent_events", None)
        if events is None:
            events = obj.events.select_related("actor").order_by("-created_at")[:20]
        return [
            {
                "action": e.action,
                "summary": e.summary,
                "created_at": e.created_at,
                "actor": (e.actor.full_name or e.actor.email) if e.actor else "System",
            }
            for e in events
        ]

    def validate_topics(self, value):
        if not isinstance(value, list) or any(topic not in TOPICS for topic in value):
            raise serializers.ValidationError("Select only supported onboarding topics.")
        return list(dict.fromkeys(value))


class AdminOnboardingView(APIView):
    permission_classes = [IsPlatformAdmin]

    @staticmethod
    def _queryset():
        today = timezone.localdate()
        first_activation = (
            Subscription.objects.filter(turf_id=OuterRef("turf_id"), status=Subscription.Status.ACTIVE)
            .exclude(starts_on__isnull=True)
            .order_by("starts_on")
            .values("starts_on")[:1]
        )
        current_periods = (
            Subscription.objects.filter(
                status=Subscription.Status.ACTIVE, starts_on__lte=today, ends_on__gte=today
            )
            .select_related("plan")
            .order_by("-ends_on")
        )
        return (
            TurfOnboarding.objects.select_related("turf", "assigned_to")
            .annotate(first_activated_on=Subquery(first_activation))
            .prefetch_related(
                Prefetch(
                    "events",
                    queryset=TurfOnboardingEvent.objects.select_related("actor").order_by("-created_at")[:20],
                    to_attr="recent_events",
                ),
                Prefetch("turf__subscriptions", queryset=current_periods, to_attr="onboarding_subscriptions"),
            )
        )

    def get(self, request, pk=None):
        if pk:
            item = get_object_or_404(self._queryset(), pk=pk)
            return Response(OnboardingSerializer(item).data)
        today = timezone.localdate()
        active_ids = list(
            Subscription.objects.filter(
                status=Subscription.Status.ACTIVE, starts_on__lte=today, ends_on__gte=today
            )
            .values_list("turf_id", flat=True)
            .distinct()
        )
        known = set(TurfOnboarding.objects.filter(turf_id__in=active_ids).values_list("turf_id", flat=True))
        TurfOnboarding.objects.bulk_create(
            [TurfOnboarding(turf_id=turf_id) for turf_id in active_ids if turf_id not in known],
            ignore_conflicts=True,
        )
        qs = self._queryset().filter(turf__status=Turf.Status.ACTIVE)
        status = request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        plan = request.query_params.get("plan")
        if plan:
            qs = qs.filter(
                turf__subscriptions__status=Subscription.Status.ACTIVE,
                turf__subscriptions__starts_on__lte=today,
                turf__subscriptions__ends_on__gte=today,
                turf__subscriptions__plan__period=plan,
            )
        search = request.query_params.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(turf__name__icontains=search)
                | Q(turf__owner_name__icontains=search)
                | Q(turf__owner_phone__icontains=search)
            )
        start, end = request.query_params.get("from"), request.query_params.get("to")
        if start:
            qs = qs.filter(first_activated_on__gte=start)
        if end:
            qs = qs.filter(first_activated_on__lte=end)
        qs = qs.distinct()
        users = get_user_model().objects.filter(is_platform_admin=True, is_active=True).order_by("email")
        return Response(
            {
                "results": OnboardingSerializer(qs, many=True).data,
                "support_users": [{"id": str(u.pk), "name": u.full_name or u.email} for u in users],
                "plans": [{"period": p.period, "name": p.name} for p in Plan.objects.all()],
            }
        )

    @transaction.atomic
    def patch(self, request, pk=None):
        item = get_object_or_404(TurfOnboarding.objects.select_for_update(), pk=pk)
        before = {"status": item.status, "assigned_to": str(item.assigned_to_id or ""), "topics": item.topics}
        serializer = OnboardingSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "assigned_to" in request.data and request.data["assigned_to"]:
            if (
                not get_user_model()
                .objects.filter(pk=request.data["assigned_to"], is_platform_admin=True, is_active=True)
                .exists()
            ):
                raise serializers.ValidationError({"assigned_to": "Choose an active platform support user."})
        item = serializer.save(updated_by=request.user)
        after = {"status": item.status, "assigned_to": str(item.assigned_to_id or ""), "topics": item.topics}
        if before != after or "notes" in request.data or "training_at" in request.data:
            TurfOnboardingEvent.objects.create(
                onboarding=item,
                actor=request.user,
                action="updated",
                summary="Updated onboarding record",
                data={"before": before, "after": after},
            )
        record(
            "platform.onboarding_updated",
            f"Updated onboarding for {item.turf.name}",
            category=Category.PLATFORM,
            request=request,
            turf=item.turf,
            target=item,
        )
        return Response(OnboardingSerializer(item).data)
