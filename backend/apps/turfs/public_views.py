"""Public (no login) API: discovery, turf pages, availability, booking requests, applications."""

import io
import math
import uuid
from datetime import date, datetime, timedelta

import segno
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, F, FloatField, Prefetch, Q
from django.db.models.functions import Cast, Power, Sqrt
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.applications.models import TurfApplication
from apps.audit.services import Category, booking_label, record
from apps.bookings.models import Booking
from apps.bookings.phone import normalize_bd_phone
from apps.bookings.services import availability, get_or_create_customer, opening_window, reserve_slot
from apps.locations.models import Area, District, Division

from .models import Amenity, PricingRule, Turf, TurfField
from .serializers import AmenitySerializer, PublicTurfCardSerializer, PublicTurfDetailSerializer

MAX_PENDING_PER_PHONE_PER_DAY = 3
BOOKING_HORIZON_DAYS = 60


class PublicAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


def parse_day(value: str | None) -> date:
    if not value:
        return timezone.localdate()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({"date": ["Use YYYY-MM-DD."]}) from None


def listed_turf(slug: str) -> Turf:
    return get_object_or_404(Turf.objects.publicly_listed(), slug=slug)


class LocationsView(PublicAPIView):
    @extend_schema(tags=["public"])
    def get(self, request):
        data = cache.get("public:locations")
        if data is None:
            divisions = Division.objects.prefetch_related(
                Prefetch("districts", queryset=District.objects.prefetch_related("areas"))
            )
            data = [
                {
                    "name": d.name,
                    "slug": d.slug,
                    "districts": [
                        {
                            "name": x.name,
                            "slug": x.slug,
                            "areas": [{"name": a.name, "slug": a.slug} for a in x.areas.all()],
                        }
                        for x in d.districts.all()
                    ],
                }
                for d in divisions
            ]
            cache.set("public:locations", data, 600)
        return Response(data)


class AmenitiesView(PublicAPIView):
    @extend_schema(tags=["public"])
    def get(self, request):
        return Response(AmenitySerializer(Amenity.objects.all(), many=True).data)


class StatsView(PublicAPIView):
    """Real counts only — no invented marketing numbers."""

    @extend_schema(tags=["public"])
    def get(self, request):
        listed = Turf.objects.publicly_listed()
        return Response(
            {
                "turfs": listed.count(),
                "districts": listed.values("district").distinct().count(),
                "fields": TurfField.objects.filter(turf__in=listed, is_active=True).count(),
            }
        )


class PublicTurfListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicTurfCardSerializer
    filter_backends = []

    SORTS = {
        "featured": ["-is_featured", "name"],
        "price_asc": ["min_public_price", "name"],
        "price_desc": ["-min_public_price", "name"],
        "newest": ["-created_at"],
        "name": ["name"],
    }

    def get_queryset(self):
        params = self.request.query_params
        qs = (
            Turf.objects.publicly_listed()
            .select_related("district", "area")
            .prefetch_related("amenities", "photos")
            .annotate(fields_count=Count("fields", filter=Q(fields__is_active=True)))
        )
        if q := params.get("q", "").strip()[:80]:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(address__icontains=q)
                | Q(area__name__icontains=q)
                | Q(district__name__icontains=q)
                | Q(short_description__icontains=q)
            )
        if division := params.get("division"):
            qs = qs.filter(district__division__slug=division)
        if district := params.get("district"):
            qs = qs.filter(district__slug=district)
        if area := params.get("area"):
            qs = qs.filter(area__slug=area)
        if turf_type := params.get("type"):
            qs = qs.filter(turf_type=turf_type)
        if surface := params.get("surface"):
            qs = qs.filter(surface=surface)
        for amenity in params.getlist("amenity"):
            qs = qs.filter(amenities__slug=amenity)
        if max_price := params.get("max_price"):
            try:
                qs = qs.filter(show_pricing=True, min_public_price__lte=max_price)
            except (ValueError, TypeError):
                pass
        if params.get("bookable") == "1":
            qs = qs.filter(public_booking_enabled=True)

        origin = self.origin()
        sort = params.get("sort") or ("nearest" if origin else "featured")
        if origin:
            qs = qs.annotate(distance_km=self.distance_expr(*origin))
            if radius := self.number("radius_km", 1, 500):
                qs = qs.filter(distance_km__lte=radius)
            if sort == "nearest":
                return qs.order_by(F("distance_km").asc(nulls_last=True), "name").distinct()
        order = self.SORTS.get(sort, self.SORTS["featured"])
        return qs.order_by(*order).distinct()

    def number(self, name, low, high) -> float | None:
        try:
            value = float(self.request.query_params.get(name, ""))
        except ValueError:
            return None
        return value if low <= value <= high and math.isfinite(value) else None

    def origin(self) -> tuple[float, float] | None:
        """The player's position, sent by the browser only after they allow location access."""
        lat, lng = self.number("lat", -90, 90), self.number("lng", -180, 180)
        return (lat, lng) if lat is not None and lng is not None else None

    @staticmethod
    def distance_expr(lat: float, lng: float):
        # Equirectangular approximation: well under 1% error at city/country scale, and plain SQL.
        km_per_degree = 111.32
        dlat = (Cast("latitude", FloatField()) - lat) * km_per_degree
        dlng = (Cast("longitude", FloatField()) - lng) * (km_per_degree * math.cos(math.radians(lat)))
        return Sqrt(Power(dlat, 2) + Power(dlng, 2))


class PublicTurfDetailView(PublicAPIView):
    @extend_schema(tags=["public"], responses=PublicTurfDetailSerializer)
    def get(self, request, slug):
        turf = get_object_or_404(
            Turf.objects.publicly_listed()
            .select_related("district", "area")
            .prefetch_related(
                "amenities",
                "photos",
                "hours",
                "fields",
                Prefetch("pricing_rules", queryset=PricingRule.objects.select_related("field")),
            )
            .annotate(fields_count=Count("fields", filter=Q(fields__is_active=True))),
            slug=slug,
        )
        return Response(PublicTurfDetailSerializer(turf).data)


class PublicAvailabilityView(PublicAPIView):
    @extend_schema(tags=["public"])
    def get(self, request, slug):
        turf = listed_turf(slug)
        day = parse_day(request.query_params.get("date"))
        if day < timezone.localdate() or day > timezone.localdate() + timedelta(days=BOOKING_HORIZON_DAYS):
            raise ValidationError({"date": [f"Choose a date within the next {BOOKING_HORIZON_DAYS} days."]})
        try:
            field = turf.fields.filter(
                is_active=True, pk=uuid.UUID(request.query_params.get("field", ""))
            ).first()
        except ValueError:
            field = None
        if field is None:
            raise NotFound("Field not found.")
        slots = availability(field, day, include_price=turf.show_pricing)
        return Response({"date": day.isoformat(), "field": str(field.id), "slots": slots})


class BookingRequestSerializer(serializers.Serializer):
    field = serializers.UUIDField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    team_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True)  # honeypot: humans leave it empty


class PublicBookingRequestView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_booking"

    @extend_schema(tags=["public"], request=BookingRequestSerializer)
    def post(self, request, slug):
        turf = listed_turf(slug)
        if not turf.public_booking_enabled:
            raise PermissionDenied("This turf is not taking online booking requests.")
        data = BookingRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("website"):
            raise ValidationError({"non_field_errors": ["Request rejected."]})
        phone = normalize_bd_phone(v["phone"])
        start, end = v["start"], v["end"]
        now = timezone.now()
        if start <= now:
            raise ValidationError({"start": ["Choose a time in the future."]})
        if start > now + timedelta(days=BOOKING_HORIZON_DAYS):
            raise ValidationError({"start": [f"Bookings open {BOOKING_HORIZON_DAYS} days ahead."]})
        _ensure_within_hours(turf, start, end)
        today_start = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time()))
        recent = Booking.objects.filter(
            turf=turf, customer__phone=phone, status=Booking.Status.PENDING, created_at__gte=today_start
        ).count()
        if recent >= MAX_PENDING_PER_PHONE_PER_DAY:
            raise ValidationError({"phone": ["Too many pending requests for this number today."]})

        customer = get_or_create_customer(turf, name=v["name"], phone=phone, email=v.get("email", ""))
        booking = reserve_slot(
            turf=turf,
            field_id=v["field"],
            start=start,
            end=end,
            customer=customer,
            status=Booking.Status.PENDING,
            source=Booking.Source.ONLINE,
            team_name=v.get("team_name", ""),
            notes=v.get("notes", ""),
        )
        record(
            "booking.requested",
            f"Online request {booking_label(booking)} — waiting for confirmation",
            category=Category.BOOKING,
            request=request,
            turf=turf,
            target=booking,
        )
        return Response(_public_booking(booking), status=201)


def _ensure_within_hours(turf: Turf, start: datetime, end: datetime) -> None:
    local_start = timezone.localtime(start)
    for day in (local_start.date(), local_start.date() - timedelta(days=1)):  # overnight windows
        window = opening_window(turf, day)
        if window and window[0] <= start and end <= window[1]:
            return
    raise ValidationError({"start": ["The turf is closed at that time."]})


def _public_booking(booking: Booking) -> dict:
    return {
        "reference": booking.reference,
        "status": booking.status,
        "status_label": booking.get_status_display(),
        "turf": booking.turf.name,
        "field": booking.field.name,
        "start": timezone.localtime(booking.start).isoformat(),
        "end": timezone.localtime(booking.end).isoformat(),
        "total": str(booking.total) if booking.turf.show_pricing else None,
    }


class PublicBookingLookupView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_booking"

    @extend_schema(tags=["public"])
    def get(self, request):
        reference = request.query_params.get("reference", "").strip().upper()
        phone = normalize_bd_phone(request.query_params.get("phone", ""))
        booking = (
            Booking.objects.select_related("turf", "field")
            .filter(reference=reference, customer__phone=phone)
            .first()
        )
        if booking is None:
            raise NotFound("No booking matches that reference and phone number.")
        return Response(_public_booking(booking))


class TurfQRCodeView(PublicAPIView):
    @extend_schema(tags=["public"], responses={200: bytes})
    def get(self, request, slug):
        turf = listed_turf(slug)
        url = f"{settings.FRONTEND_URL.rstrip('/')}/turfs/{turf.slug}"
        qr = segno.make(url, error="m")
        # A standalone SVG document (with xmlns) so it renders in <img> tags and as a downloaded file.
        buffer = io.BytesIO()
        qr.save(
            buffer,
            kind="svg",
            scale=8,
            dark="#064e3b",
            light="#ffffff",
            border=2,
            xmldecl=False,
            title=f"{turf.name} booking page",
        )
        response = HttpResponse(buffer.getvalue(), content_type="image/svg+xml")
        response["Cache-Control"] = "public, max-age=3600"
        return response


class ApplicationSerializer(serializers.ModelSerializer):
    district = serializers.SlugRelatedField(slug_field="slug", queryset=District.objects.all())
    area = serializers.SlugRelatedField(
        slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False
    )
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = TurfApplication
        fields = [
            "turf_name",
            "owner_name",
            "phone",
            "email",
            "district",
            "area",
            "address",
            "turf_type",
            "number_of_fields",
            "message",
            "website",
        ]

    def validate_phone(self, value):
        return normalize_bd_phone(value)

    def validate_turf_type(self, value):
        if value not in Turf.TurfType.values:
            raise serializers.ValidationError("Choose outdoor, indoor or rooftop.")
        return value

    def validate_number_of_fields(self, value):
        if not 1 <= value <= 20:
            raise serializers.ValidationError("Between 1 and 20 fields.")
        return value

    def validate(self, attrs):
        if attrs.pop("website", ""):
            raise serializers.ValidationError({"non_field_errors": ["Request rejected."]})
        area = attrs.get("area")
        if area and area.district_id != attrs["district"].id:
            raise serializers.ValidationError({"area": ["This area is not in the selected district."]})
        return attrs


class PublicApplicationView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_application"

    @extend_schema(tags=["public"], request=ApplicationSerializer)
    def post(self, request):
        data = ApplicationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.save()
        return Response({"detail": "Thanks! Our team will contact you within 2 working days."}, status=201)
