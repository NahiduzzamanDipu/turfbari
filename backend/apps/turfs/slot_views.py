"""Owner tools for slot schedules and Morning/Evening/Night/Midnight pricing.

Writes need the owner role or the manager permission "manage_slots" (checked by IsTenantMember).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.tenancy import IsTenantMember, TenantViewSet

from .models import PriceCategory, SlotTemplate, TurfField
from .schedule import (
    DEFAULT_CATEGORY_STARTS,
    category_at,
    category_bands,
    crosses_boundary,
    local_dt,
    turf_categories,
)
from .serializers import TenantScopedPK

WEEK = 7 * 24 * 60
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def minutes_of(t: time) -> int:
    return t.hour * 60 + t.minute


def week_span(weekday: int, start: time, length: int) -> tuple[int, int]:
    begin = weekday * 24 * 60 + minutes_of(start)
    return begin, begin + length


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Interval overlap on a repeating week (Sunday night runs into Monday morning)."""
    return any(a[0] < b[1] + shift and b[0] + shift < a[1] for shift in (-WEEK, 0, WEEK))


def check_slot(field: TurfField, weekday: int, start: time, end: time, *, exclude_ids=()) -> int:
    if start.minute % 15 or end.minute % 15 or start.second or end.second:
        raise serializers.ValidationError(
            {"start_time": ["Use times on the quarter hour (:00, :15, :30, :45)."]}
        )
    length = (minutes_of(end) - minutes_of(start)) % (24 * 60)
    if length < 30 or length > 6 * 60:
        raise serializers.ValidationError(
            {"end_time": ["A slot must be between 30 minutes and 6 hours long."]}
        )
    mine = week_span(weekday, start, length)
    for other in SlotTemplate.objects.filter(field=field).exclude(pk__in=exclude_ids):
        if overlaps(mine, week_span(other.weekday, other.start_time, other.minutes)):
            raise serializers.ValidationError(
                {
                    "start_time": [
                        f"Overlaps the {WEEKDAYS[other.weekday]} slot "
                        f"{other.start_time:%I:%M %p}–{other.end_time:%I:%M %p} on {field.name}."
                    ]
                }
            )
    return length


class SlotTemplateSerializer(serializers.ModelSerializer):
    field = TenantScopedPK(queryset=TurfField.objects.all())
    minutes = serializers.IntegerField(read_only=True)
    category = serializers.SerializerMethodField()
    crosses_into = serializers.SerializerMethodField()

    class Meta:
        model = SlotTemplate
        fields = [
            "id",
            "field",
            "weekday",
            "start_time",
            "end_time",
            "is_active",
            "price",
            "minutes",
            "category",
            "crosses_into",
        ]

    def _window(self, obj):
        start = local_dt(
            date(2024, 1, 1) + timedelta(days=obj.weekday), obj.start_time
        )  # any real Monday-based week
        return start, start + timedelta(minutes=obj.minutes)

    def get_category(self, obj):
        categories = self.context.get("categories") or []
        c = category_at(categories, obj.start_time)
        return c.key if c else None

    def get_crosses_into(self, obj):
        categories = self.context.get("categories") or []
        c = crosses_boundary(categories, *self._window(obj))
        return c.key if c else None

    def validate_weekday(self, value):
        if not 0 <= value <= 6:
            raise serializers.ValidationError("Weekday must be 0 (Monday) – 6 (Sunday).")
        return value

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Price can't be negative.")
        return value

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        check_slot(
            get("field"),
            get("weekday"),
            get("start_time"),
            get("end_time"),
            exclude_ids=[self.instance.pk] if self.instance else [],
        )
        return attrs


class SlotTemplateViewSet(TenantViewSet):
    queryset = SlotTemplate.objects.select_related("field")
    serializer_class = SlotTemplateSerializer
    owner_only_writes = True
    manager_permission = "manage_slots"
    filter_backends = []
    pagination_class = None
    audit_noun = "slot"

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "categories": turf_categories(self.request.tenant.pk)}

    def get_queryset(self):
        qs = super().get_queryset()
        if field := self.request.query_params.get("field"):
            qs = qs.filter(field_id=field)
        return qs.order_by("weekday", "start_time")

    def _field(self, request) -> TurfField:
        field = TurfField.objects.filter(turf=request.tenant, pk=request.data.get("field")).first()
        if field is None:
            raise serializers.ValidationError({"field": ["Choose a field."]})
        return field

    @staticmethod
    def _weekdays(value) -> list[int]:
        try:
            days = sorted({int(d) for d in value or []})
        except (TypeError, ValueError):
            raise serializers.ValidationError({"weekdays": ["Choose days of the week."]}) from None
        if not days or any(d < 0 or d > 6 for d in days):
            raise serializers.ValidationError({"weekdays": ["Choose days of the week."]})
        return days

    def _list(self, field):
        rows = SlotTemplate.objects.filter(field=field).order_by("weekday", "start_time")
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(request=None)
    @action(detail=False, methods=["post"])
    @transaction.atomic
    def generate(self, request):
        """Replace the chosen days' slots with back-to-back slots of one length between two times."""
        field = self._field(request)
        days = self._weekdays(request.data.get("weekdays"))
        try:
            first = time.fromisoformat(request.data.get("start", ""))
            last = time.fromisoformat(request.data.get("end", ""))
            length = int(request.data.get("minutes", 0))
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                {"start": ["Enter a start time, end time and slot length."]}
            ) from None
        if length < 30 or length > 360 or length % 15:
            raise serializers.ValidationError(
                {"minutes": ["Slot length must be 30 minutes to 6 hours, in 15-minute steps."]}
            )
        span = (minutes_of(last) - minutes_of(first)) % (24 * 60) or 24 * 60
        count = span // length
        if count < 1:
            raise serializers.ValidationError(
                {"end": ["The time between start and end is shorter than one slot."]}
            )
        price = request.data.get("price")
        price = Decimal(str(price)) if price not in (None, "") else None
        SlotTemplate.objects.filter(field=field, weekday__in=days).delete()
        for day in days:
            for i in range(count):
                begin = (datetime.combine(date.today(), first) + timedelta(minutes=i * length)).time()
                finish = (datetime.combine(date.today(), first) + timedelta(minutes=(i + 1) * length)).time()
                check_slot(field, day, begin, finish)
                SlotTemplate.objects.create(
                    turf=request.tenant,
                    field=field,
                    weekday=day,
                    start_time=begin,
                    end_time=finish,
                    price=price,
                )
        record(
            "slot.generated",
            f"Set {count} slots of {length} min ({first:%I:%M %p}–{last:%I:%M %p}) on "
            f"{', '.join(WEEKDAYS[d] for d in days)} for {field.name}",
            category=Category.SETUP,
            request=request,
        )
        return self._list(field)

    @extend_schema(request=None)
    @action(detail=False, methods=["post"])
    @transaction.atomic
    def copy(self, request):
        """Copy one day's slots to other days (replacing what those days had)."""
        field = self._field(request)
        source = self._weekdays([request.data.get("from_weekday")])[0]
        targets = [d for d in self._weekdays(request.data.get("to_weekdays")) if d != source]
        rows = list(SlotTemplate.objects.filter(field=field, weekday=source))
        if not rows:
            raise serializers.ValidationError(
                {"from_weekday": [f"{WEEKDAYS[source]} has no custom slots to copy."]}
            )
        SlotTemplate.objects.filter(field=field, weekday__in=targets).delete()
        for day in targets:
            for r in rows:
                check_slot(field, day, r.start_time, r.end_time)
                SlotTemplate.objects.create(
                    turf=request.tenant,
                    field=field,
                    weekday=day,
                    start_time=r.start_time,
                    end_time=r.end_time,
                    is_active=r.is_active,
                    price=r.price,
                )
        record(
            "slot.copied",
            f"Copied {WEEKDAYS[source]}'s slots to "
            f"{', '.join(WEEKDAYS[d] for d in targets)} for {field.name}",
            category=Category.SETUP,
            request=request,
        )
        return self._list(field)

    @extend_schema(request=None)
    @action(detail=False, methods=["post"])
    @transaction.atomic
    def clear(self, request):
        """Go back to automatic slots (opening hours + slot length) on the chosen days."""
        field = self._field(request)
        days = self._weekdays(request.data.get("weekdays"))
        SlotTemplate.objects.filter(field=field, weekday__in=days).delete()
        record(
            "slot.cleared",
            f"Back to automatic slots on {', '.join(WEEKDAYS[d] for d in days)} for {field.name}",
            category=Category.SETUP,
            request=request,
        )
        return self._list(field)


class CategoryInput(serializers.Serializer):
    key = serializers.ChoiceField(choices=PriceCategory.Key.choices)
    starts_at = serializers.TimeField()
    hourly_rate = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class PriceCategoriesSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    categories = CategoryInput(many=True, required=False)

    def validate(self, attrs):
        if not attrs["enabled"]:
            return attrs
        cats = attrs.get("categories") or []
        keys = [c["key"] for c in cats]
        if sorted(keys) != sorted(PriceCategory.ORDER):
            raise serializers.ValidationError(
                {"categories": ["Set all four: Morning, Evening, Night and Midnight."]}
            )
        starts = [c["starts_at"] for c in cats]
        if len(set(starts)) != 4:
            raise serializers.ValidationError({"categories": ["Each category needs a different start time."]})
        if any(t.minute % 15 or t.second for t in starts):
            raise serializers.ValidationError({"categories": ["Use start times on the quarter hour."]})
        by_time = [c["key"] for c in sorted(cats, key=lambda c: c["starts_at"])]
        rotate = by_time.index(PriceCategory.Key.MORNING)
        if by_time[rotate:] + by_time[:rotate] != list(PriceCategory.ORDER):
            raise serializers.ValidationError(
                {"categories": ["Keep the order through the day: Morning → Evening → Night → Midnight."]}
            )
        return attrs


class PriceCategoriesView(APIView):
    permission_classes = [IsTenantMember]
    owner_only_writes = True
    manager_permission = "manage_slots"

    @staticmethod
    def payload(turf) -> dict:
        categories = turf_categories(turf.pk)
        if categories:
            return {"enabled": True, "categories": category_bands(categories)}
        rate = (
            turf.fields.filter(is_active=True)
            .order_by("default_hourly_rate")
            .values_list("default_hourly_rate", flat=True)
            .first()
        )
        suggestion = [
            {"key": key, "start": start.strftime("%H:%M"), "hourly_rate": str(rate or Decimal("0"))}
            for key, start in DEFAULT_CATEGORY_STARTS.items()
        ]
        return {"enabled": False, "categories": [], "suggested": suggestion}

    @extend_schema(tags=["workspace"])
    def get(self, request):
        return Response(self.payload(request.tenant))

    @extend_schema(tags=["workspace"], request=PriceCategoriesSerializer)
    @transaction.atomic
    def put(self, request):
        from .pricing import recompute_min_price

        data = PriceCategoriesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        turf = request.tenant
        PriceCategory.objects.filter(turf=turf).delete()
        if data.validated_data["enabled"]:
            for c in data.validated_data["categories"]:
                PriceCategory.objects.create(
                    turf=turf, key=c["key"], starts_at=c["starts_at"], hourly_rate=c["hourly_rate"]
                )
            summary = ", ".join(
                f"{b['label']} {b['start']}–{b['end']} ৳{Decimal(b['hourly_rate']):,.0f}/h"
                for b in category_bands(turf_categories(turf.pk))
            )
        else:
            summary = "turned off (back to standard rates and price rules)"
        recompute_min_price(turf)
        record(
            "pricing.categories",
            f"Time-of-day pricing: {summary}"[:255],
            category=Category.SETUP,
            request=request,
        )
        return Response(self.payload(turf))
