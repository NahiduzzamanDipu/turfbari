"""Public (no login) API: each turf's own booking page, availability, booking requests, applications.

There is no public turf directory: a turf page is reached only by its link or QR code.
"""

import io
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import segno
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.applications.models import TurfApplication
from apps.audit.services import Category, booking_label, record
from apps.bookings import holds, payments
from apps.bookings.models import Booking
from apps.bookings.phone import normalize_bd_phone
from apps.bookings.services import availability, get_or_create_customer, opening_window, reserve_slot
from apps.legal import services as legal_services
from apps.legal.models import Sector
from apps.locations.models import Area, District, Division

from . import schedule
from .models import Amenity, PricingRule, Turf, TurfField
from .serializers import AmenitySerializer, PublicTurfDetailSerializer

MAX_PENDING_PER_PHONE_PER_DAY = 3
BOOKING_HORIZON_DAYS = 60


log = logging.getLogger(__name__)


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
        context: dict = {}
        slots = availability(field, day, include_price=turf.show_pricing, context=context)
        ip = holds.visitor_key(request)
        mine = holds.find_hold(request.headers.get("X-Hold-Token"), ip) or holds.latest_hold(ip)
        _add_live_states(field, slots, mine, context)
        retry = holds.cooldown_until(ip)
        response = Response(
            {
                "date": day.isoformat(),
                "field": str(field.id),
                "slots": slots,
                "my_hold": _hold_payload(mine) if mine else None,
                "cooldown_until": retry.isoformat() if retry else None,
            }
        )
        response["Cache-Control"] = "no-store"
        return response


def _hold_payload(hold) -> dict:
    return {
        "token": hold.token,
        "field": str(hold.field_id),
        "start": timezone.localtime(hold.start).isoformat(),
        "end": timezone.localtime(hold.end).isoformat(),
        "expires_at": hold.expires_at.isoformat(),
    }


def _add_live_states(field, slots: list[dict], mine, context: dict) -> None:
    """state per slot: free | yours | held (someone is booking) | requested | booked | unavailable | past.
    Reuses the bookings/blocks availability() already read (same request, no second query)."""
    if not slots:
        return
    first, last = context["first"], context["last"]
    bookings, blocks = context["bookings"], context["blocks"]
    held = list(holds.active_holds(field.id, first, last).values_list("start", "end", "token"))
    now = timezone.now()
    for slot in slots:
        start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
        hit = [st for s, e, st in bookings if s < end and e > start]
        if start <= now:
            state = "past"
        elif hit:
            state = "requested" if all(st == Booking.Status.PENDING for st in hit) else "booked"
        elif any(s < end and e > start for s, e in blocks):
            state = "unavailable"
        elif any(s < end and e > start for s, e, _ in held):
            mine_here = mine and any(tok == mine.token and s < end and e > start for s, e, tok in held)
            state = "yours" if mine_here else "held"
        else:
            state = "free"
        slot["state"] = state
        slot["available"] = state in ("free", "yours")


class HoldSerializer(serializers.Serializer):
    field = serializers.UUIDField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    token = serializers.CharField(max_length=64, required=False, allow_blank=True)


class PublicHoldView(PublicAPIView):
    """Select slots: keep them for this visitor for 10 minutes (see apps.bookings.holds)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_hold"

    @extend_schema(tags=["public"], request=HoldSerializer)
    def post(self, request, slug):
        turf = listed_turf(slug)
        if not turf.public_booking_enabled:
            raise PermissionDenied("This turf is not taking online booking requests.")
        data = HoldSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        field = turf.fields.filter(is_active=True, pk=v["field"]).first()
        if field is None:
            raise NotFound("Field not found.")
        start, end = v["start"], v["end"]
        _check_public_window(turf, start, end, field)
        try:
            hold = holds.place_hold(
                turf=turf,
                field=field,
                start=start,
                end=end,
                ip=holds.visitor_key(request),
                token=v.get("token"),
            )
        except holds.HoldRefused as exc:
            return Response(
                {
                    "error": {
                        "code": exc.get_codes(),
                        "message": str(exc.detail),
                        "fields": None,
                        "retry_at": exc.retry_at.isoformat() if exc.retry_at else None,
                    }
                },
                status=exc.status_code,
            )
        return Response(_hold_payload(hold), status=201)

    @extend_schema(tags=["public"], request=None)
    def delete(self, request, slug):
        token = request.headers.get("X-Hold-Token") or request.data.get("token", "")
        holds.release_hold(token, holds.visitor_key(request))
        return Response(status=204)


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
    hold_token = serializers.CharField(max_length=64, required=False, allow_blank=True)
    # The bKash advance the customer already sent (verified by a person before anything is confirmed).
    payment_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))
    bkash_sender = serializers.CharField(max_length=20)
    trx_id = serializers.CharField(max_length=30)
    # Consent to the platform Terms & Booking Rules: the box must be ticked for the *current* version.
    agree_terms = serializers.BooleanField(default=False)
    # Ids of the exact legal document versions shown next to the checkbox (see turf detail "legal").
    accepted_versions = serializers.ListField(child=serializers.IntegerField(), required=False)
    terms_version = serializers.IntegerField(required=False, allow_null=True)  # old clients; ignored


IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9-]{16,64}$")


class PublicBookingRequestView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_booking"

    @extend_schema(tags=["public"], request=BookingRequestSerializer)
    def post(self, request, slug):
        turf = listed_turf(slug)
        if not turf.public_booking_enabled or not turf.payment_bkash_number:
            raise PermissionDenied("This turf is not taking online bookings. Call the turf to book.")
        data = BookingRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("website"):
            raise ValidationError({"non_field_errors": ["Request rejected."]})
        # A retried submit (double click, flaky network) with the same key returns the same booking.
        key = (request.headers.get("Idempotency-Key") or "").strip()
        key = key if IDEMPOTENCY_KEY.match(key) else None
        if key and (done := Booking.objects.filter(idempotency_key=key, turf=turf).first()):
            return Response(_public_booking(done), status=200)
        legal_needed = legal_services.required("booking", "customer", legal_services.sector_id_of(turf))
        legal_services.require_accepted(legal_needed, v["agree_terms"], set(v.get("accepted_versions") or []))
        phone = normalize_bd_phone(v["phone"])
        start, end = v["start"], v["end"]
        field = turf.fields.filter(is_active=True, pk=v["field"]).first()
        if field is None:
            raise NotFound("Field not found.")
        _check_public_window(turf, start, end, field)
        today_start = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time()))
        recent = (
            Booking.objects.awaiting_review()  # lapsed holds no longer count
            .filter(turf=turf, customer__phone=phone, created_at__gte=today_start)
            .count()
        )
        if recent >= MAX_PENDING_PER_PHONE_PER_DAY:
            raise ValidationError({"phone": ["Too many pending requests for this number today."]})

        ip = holds.visitor_key(request)
        with transaction.atomic():
            # Lock the field first (as reserve_slot does) so holds and requests can't interleave.
            TurfField.objects.select_for_update().filter(pk=v["field"], turf=turf).first()
            mine = holds.find_hold(v.get("hold_token"), ip)
            others = holds.active_holds(v["field"], start, end)
            if mine:
                others = others.exclude(pk=mine.pk)
            if others.exclude(ip_hash=ip).exists():
                raise ValidationError(
                    {"start": ["Someone else is booking this slot right now. Please choose another."]}
                )
            slots = payments.slot_count_for(field, start, end)
            payments.enforce_customer_limit(phone, slots, start)
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
            payment = payments.validate_payment(
                turf,
                total=booking.total,
                amount=v["payment_amount"],
                sender_number=v["bkash_sender"],
                trx_id=v["trx_id"],
            )
            payments.attach_submission(booking, payment)
            booking.slot_count, booking.idempotency_key = slots, key
            booking.terms_agreed_at = timezone.now() if legal_needed else None
            booking.save(update_fields=["slot_count", "idempotency_key", "terms_agreed_at", "updated_at"])
            legal_services.record_acceptances(
                legal_needed,
                action="booking",
                turf=turf,
                booking=booking,
                related_ref=f"booking:{booking.reference}",
                request=request,
            )
            # Every hold of this visitor is done with: the request went through.
            holds.SlotHold.objects.filter(ip_hash=ip, status=holds.SlotHold.Status.ACTIVE).update(
                status=holds.SlotHold.Status.CONVERTED, updated_at=timezone.now()
            )
        record(
            "booking.requested",
            f"Online request {booking_label(booking)} — bKash ৳{payment['amount']:,.0f} "
            f"(TrxID {payment['trx_id']}) waiting for verification",
            category=Category.BOOKING,
            request=request,
            turf=turf,
            target=booking,
        )
        return Response(_public_booking(booking), status=201)


def _check_public_window(turf: Turf, start: datetime, end: datetime, field: TurfField) -> None:
    now = timezone.now()
    if start <= now:
        raise ValidationError({"start": ["Choose a time in the future."]})
    if start > now + timedelta(days=BOOKING_HORIZON_DAYS):
        raise ValidationError({"start": [f"Bookings open {BOOKING_HORIZON_DAYS} days ahead."]})
    if end <= start:
        raise ValidationError({"end": ["End must be after start."]})
    if schedule.uses_templates(field, timezone.localtime(start).date()) or schedule.uses_templates(
        field, timezone.localtime(start).date() - timedelta(days=1)
    ):
        # Custom slots: only whole, back-to-back offered slots can be held or booked.
        if not schedule.is_offered_range(field, start, end):
            msg = "Choose one of the turf's listed slots (or back-to-back ones)."
            raise ValidationError({"start": [msg]})
        return
    _ensure_within_hours(turf, start, end)


def _ensure_within_hours(turf: Turf, start: datetime, end: datetime) -> None:
    local_start = timezone.localtime(start)
    for day in (local_start.date(), local_start.date() - timedelta(days=1)):  # overnight windows
        window = opening_window(turf, day)
        if window and window[0] <= start and end <= window[1]:
            return
    raise ValidationError({"start": ["The turf is closed at that time."]})


def _public_booking(booking: Booking) -> dict:
    status = booking.status
    if (
        status == Booking.Status.PENDING
        and booking.hold_expires_at
        and booking.hold_expires_at <= timezone.now()
    ):
        status = Booking.Status.EXPIRED  # the tick hasn't caught up yet; tell the truth anyway
    submission = getattr(booking, "payment_submission", None)
    return {
        "reference": booking.reference,
        "status": status,
        "status_label": Booking.Status(status).label,
        "turf": booking.turf.name,
        "turf_slug": booking.turf.slug,
        "turf_phone": booking.turf.public_phone or None,
        "field": booking.field.name,
        "start": timezone.localtime(booking.start).isoformat(),
        "end": timezone.localtime(booking.end).isoformat(),
        "total": str(booking.total),
        "amount_paid": str(booking.amount_paid),
        "hold_expires_at": timezone.localtime(booking.hold_expires_at).isoformat()
        if status == Booking.Status.PENDING and booking.hold_expires_at
        else None,
        "payment": {
            "amount": str(submission.amount),
            "trx_id": submission.trx_id,
            "status": submission.status,
            "rejection_reason": submission.rejection_reason or None,
        }
        if submission
        else None,
        "message_bn": payments.ACCEPTED_MESSAGE_BN
        if status == Booking.Status.PENDING and submission
        else None,
    }


class PublicBookingLookupView(PublicAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_booking"

    @extend_schema(tags=["public"])
    def get(self, request):
        reference = request.query_params.get("reference", "").strip().upper()
        phone = normalize_bd_phone(request.query_params.get("phone", ""))
        booking = (
            Booking.objects.select_related("turf", "field", "payment_submission")
            .filter(reference=reference, customer__phone=phone)
            .first()
        )
        if booking is None:
            raise NotFound("No booking matches that reference and phone number.")
        return Response(_public_booking(booking))


def booking_page_url(turf: Turf) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/turfs/{turf.slug}"


def qr_response(
    turf: Turf, kind: str = "svg", *, download: bool = False, scale: int | None = None
) -> HttpResponse:
    """The turf's booking-page QR code as SVG or PNG."""
    qr = segno.make(booking_page_url(turf), error="m")
    buffer = io.BytesIO()
    if kind == "png":
        qr.save(buffer, kind="png", scale=scale or 16, dark="#064e3b", light="#ffffff", border=4)
        content_type = "image/png"
    else:
        # A standalone SVG document (with xmlns) so it renders in <img> tags and as a downloaded file.
        qr.save(
            buffer,
            kind="svg",
            scale=scale or 8,
            dark="#064e3b",
            light="#ffffff",
            border=4,
            xmldecl=False,
            title=f"{turf.name} booking page",
        )
        content_type = "image/svg+xml"
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    if download:
        response["Content-Disposition"] = f'attachment; filename="{turf.slug}-booking-qr.{kind}"'
        response["Cache-Control"] = "private, no-store"
    else:
        response["Cache-Control"] = "public, max-age=3600"
    return response


class TurfQRCodeView(PublicAPIView):
    @extend_schema(tags=["public"], responses={200: bytes})
    def get(self, request, slug):
        return qr_response(listed_turf(slug))


class ApplicationSerializer(serializers.ModelSerializer):
    district = serializers.SlugRelatedField(slug_field="slug", queryset=District.objects.all())
    area = serializers.SlugRelatedField(
        slug_field="slug", queryset=Area.objects.all(), allow_null=True, required=False
    )
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)
    sector = serializers.SlugRelatedField(
        slug_field="slug", queryset=Sector.objects.filter(is_active=True), required=False, allow_null=True
    )

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
            "sector",
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
        sector = data.validated_data.get("sector") or legal_services.default_sector()
        needed = legal_services.required("registration", "owner", sector.pk if sector else None)
        legal_services.require_accepted(
            needed,
            bool(request.data.get("agree_legal")),
            legal_services.parse_version_ids(request.data.get("accepted_versions")),
            field="agree_legal",
        )
        from apps.applications import registration

        with_payment = bool(request.data.get("plan")) and registration.payments_open()
        with transaction.atomic():
            application = data.save(sector=sector)
            legal_services.record_acceptances(
                needed, action="registration", related_ref=f"application:{application.pk}", request=request
            )
            if with_payment:  # plan + promo + bKash payment, verified by TurfBari before anything activates
                registration.start(application, request.data, request=request)
        if with_payment:
            return Response(registration.status_payload(application), status=201)
        return Response({"detail": "Thanks! Our team will contact you within 2 working days."}, status=201)
