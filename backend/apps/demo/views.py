"""Public demo booking APIs and demo-owner APIs, isolated from production records."""

import secrets
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

import segno
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.models import PlatformSettings
from apps.common.permissions import IsPlatformAdmin
from apps.legal import services as legal_services

from .models import DemoActivity, DemoBooking, DemoCustomer, DemoHold, DemoSlot, DemoSms, DemoWorkspace
from .services import (
    DEMO_FIELD_ID,
    DEMO_HOLD_MINUTES,
    DEMO_OWNER_COOKIE,
    DEMO_OWNER_TTL,
    demo_datetime,
    fingerprint_phone,
    get_public_workspace,
    issue_owner_session,
    mask_demo_phone,
    owner_session_valid,
    reset_public_workspace,
)

DEMO_PRICE = Decimal("1800.00")


def active_workspace(*, touch=True):
    workspace = get_public_workspace()
    if workspace.status != DemoWorkspace.Status.ACTIVE:
        raise Http404("The public demo is currently unavailable.")
    if touch and (
        workspace.last_access_at is None or timezone.now() - workspace.last_access_at > timedelta(minutes=1)
    ):
        workspace.last_access_at = timezone.now()
        workspace.save(update_fields=["last_access_at", "updated_at"])
    return workspace


def serialize_slot(slot, *, state="free"):
    return {
        "id": str(slot.pk),
        "label": slot.label,
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "category": slot.category,
        "price": str(slot.price),
        "enabled": slot.enabled,
        "booked": state in {"requested", "booked"},
        "state": state,
    }


def _booking_message(booking):
    return {
        "reference": booking.reference,
        "status": booking.status,
        "status_label": booking.get_status_display(),
        "turf": booking.workspace.name,
        "turf_slug": "turfbari-demo-arena",
        "turf_phone": None,
        "field": "Demo Field",
        "start": demo_datetime(booking.date, booking.start_time).isoformat(),
        "end": demo_datetime(booking.date, booking.end_time).isoformat(),
        "total": str(booking.price),
        "amount_paid": "0.00",
        "hold_expires_at": None,
        "payment": {
            "amount": str(booking.payment_amount),
            "trx_id": booking.transaction_reference,
            "status": booking.payment_status,
            "rejection_reason": booking.rejection_reason or None,
        },
        "message_bn": "ডেমো বুকিং অনুরোধ গ্রহণ করা হয়েছে। এটি বাস্তব বুকিং বা পেমেন্ট নয়।",
        "demo_mode": True,
    }


def serialize_booking(booking):
    return {
        "id": str(booking.pk),
        "reference": booking.reference,
        "customer_name": booking.customer.name,
        "customer_phone": booking.customer.phone,
        "date": booking.date.isoformat(),
        "slot_id": str(booking.slot_id),
        "start_time": booking.start_time.strftime("%H:%M"),
        "end_time": booking.end_time.strftime("%H:%M"),
        "price": str(booking.price),
        "payment_amount": str(booking.payment_amount),
        "sender_phone": booking.sender_phone,
        "transaction_reference": booking.transaction_reference,
        "payment_status": booking.payment_status,
        "rejection_reason": booking.rejection_reason,
        "note": "",
        "status": booking.status,
        "created_at": booking.created_at,
        "reviewed_at": booking.reviewed_at,
        "confirmed_at": booking.confirmed_at,
        "reviewed_by": booking.reviewed_by,
        "demo_mode": True,
    }


class DemoThrottleMixin:
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo_write"


class DemoOwnerPermission(BasePermission):
    """Short-lived signed cookie scoped to this demo workspace and reset generation."""

    def has_permission(self, request, view):
        workspace = DemoWorkspace.objects.filter(public_key="public", status="active").first()
        if workspace is None or not owner_session_valid(request.COOKIES.get(DEMO_OWNER_COOKIE), workspace):
            return False
        request.demo_workspace = workspace
        return True


class DemoOwnerMixin(APIView):
    authentication_classes = []
    permission_classes = [DemoOwnerPermission]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo_write"


class DemoQRCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        active_workspace(touch=False)
        qr = segno.make(f"{settings.FRONTEND_URL.rstrip('/')}/demo-booking", error="M")
        response = HttpResponse(content_type="image/svg+xml")
        qr.save(response, kind="svg", scale=5, border=2, dark="#064e3b", light="#ffffff")
        response["Cache-Control"] = "public, max-age=3600"
        return response


class DemoOwnerAccessView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_write"

    def post(self, request):
        workspace = active_workspace()
        response = Response({"expires_in": DEMO_OWNER_TTL, "reset_count": workspace.reset_count})
        response.set_cookie(
            DEMO_OWNER_COOKIE,
            issue_owner_session(workspace),
            max_age=DEMO_OWNER_TTL,
            httponly=True,
            secure=request.is_secure(),
            samesite="Lax",
            path="/api/public/demo/",
        )
        return response


class DemoTurfView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_read"

    def get(self, request):
        workspace = active_workspace()
        slots = list(workspace.slots.filter(enabled=True))
        categories = []
        category_labels = {
            "morning": "Morning",
            "evening": "Evening",
            "night": "Night",
            "midnight": "Midnight",
        }
        for category in ("morning", "evening", "night", "midnight"):
            rows = [slot for slot in slots if slot.category == category]
            if rows:
                categories.append(
                    {
                        "key": category,
                        "label": category_labels[category],
                        "start": min(slot.start_time for slot in rows).strftime("%H"),
                        "end": max(slot.end_time for slot in rows).strftime("%H"),
                        "hourly_rate": str(min(slot.price for slot in rows)),
                    }
                )
        legal = legal_services.required("booking", "customer", legal_services.sector_id_of(None))
        legal = [
            {
                k: entry[k]
                for k in (
                    "version_id",
                    "version",
                    "category",
                    "scope",
                    "title_en",
                    "title_bn",
                    "url",
                    "sector_slug",
                )
            }
            for entry in legal
        ]
        settings_row = PlatformSettings.load()
        return Response(
            {
                "name": workspace.name,
                "slug": "turfbari-demo-arena",
                "short_description": (
                    "A sample 5-a-side football facility for exploring the TURFBARI booking experience."
                ),
                "district": {"id": "demo-district", "name": "Dhaka"},
                "area": {"id": "demo-area", "name": "Uttara"},
                "address": "Uttara, Dhaka, Bangladesh",
                "latitude": None,
                "longitude": None,
                "map_link": None,
                "distance_km": None,
                "profile_image_url": None,
                "cover_url": None,
                "turf_type": "outdoor",
                "surface": "artificial_turf",
                "amenities": ["Floodlights", "Changing room", "Parking"],
                "min_price": str(min((slot.price for slot in slots), default=DEMO_PRICE)),
                "fields_count": 1,
                "is_featured": False,
                "public_booking_enabled": True,
                "photos": [],
                "theme": {
                    "preset": "turfbari",
                    "color": None,
                    "surface": "plain",
                    "buttons": "rounded",
                    "font": "inter",
                },
                "youtube_video_id": settings_row.youtube_video_id
                if settings_row.booking_youtube_video_enabled
                else None,
                "legal": legal,
                "max_slots_per_customer": settings_row.max_slots_per_customer,
                "description": (
                    "Explore a sample turf profile, current slot prices, booking rules, and the complete "
                    "player booking flow. All records and payment details in this demo are simulated."
                ),
                "maps_url": "",
                "public_phone": "",
                "public_email": "",
                "booking_instructions": (
                    "Choose a date and one or more consecutive available slots. Enter sample customer "
                    "and payment details only. This demo never transfers money or sends SMS."
                ),
                "cancellation_policy": (
                    "The demo owner can approve, reject, or cancel a sample request. "
                    "No real booking or refund is created."
                ),
                "payment_methods_text": "Simulated bKash-style verification — no real payment",
                "fields_list": [
                    {
                        "id": DEMO_FIELD_ID,
                        "name": "Main Demo Field",
                        "size": "5-a-side",
                        "surface": "artificial_turf",
                        "is_indoor": False,
                        "has_lighting": True,
                        "slot_minutes": 60,
                    }
                ],
                "hours": [
                    {"weekday": day, "opens_at": "06:00", "closes_at": "23:00", "is_closed": False}
                    for day in range(7)
                ],
                "pricing": [],
                "base_rates": [],
                "payment": {
                    "accepts_online": True,
                    "bkash_number": None,
                    "advance_amount": "500.00",
                    "min_advance": "500.00",
                    "hold_minutes": DEMO_HOLD_MINUTES,
                },
                "price_categories": categories,
                "demo_mode": True,
                "demo_disclaimer": (
                    "DEMO MODE — sample data only. No real booking, payment, bKash transaction, "
                    "or SMS is created."
                ),
            }
        )


class DemoAvailabilityView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_read"

    def get(self, request):
        workspace = active_workspace(touch=False)
        try:
            booking_date = date.fromisoformat(str(request.query_params.get("date", "")))
        except ValueError:
            return Response({"detail": "Choose a valid demo date."}, status=400)
        if request.query_params.get("field") != DEMO_FIELD_ID:
            return Response({"detail": "This demo field is unavailable."}, status=404)
        today = timezone.localdate()
        if booking_date < today or booking_date > today + timedelta(days=60):
            return Response({"detail": "Choose a date within the next 60 days."}, status=400)
        now = timezone.now()
        DemoHold.objects.filter(workspace=workspace, expires_at__lte=now).delete()
        slots = list(workspace.slots.all())
        bookings = list(
            workspace.bookings.filter(
                models.Q(status=DemoBooking.Status.CONFIRMED)
                | models.Q(status=DemoBooking.Status.PENDING, hold_expires_at__gt=timezone.now()),
                date=booking_date,
            )
        )
        visitor = str(request.headers.get("X-Visitor-Id", ""))[:64]
        own_holds = (
            list(
                workspace.holds.filter(date=booking_date, visitor_id=visitor, expires_at__gt=now).order_by(
                    "slot__start_time"
                )
            )
            if visitor
            else []
        )
        own_token = str(own_holds[0].token) if own_holds else None
        other_holds = {
            str(h.slot_id): h
            for h in workspace.holds.filter(date=booking_date, expires_at__gt=now).exclude(visitor_id=visitor)
        }
        own_ids = {h.slot_id for h in own_holds}
        serialized = []
        for slot in slots:
            overlaps = next(
                (b for b in bookings if slot.start_time < b.end_time and slot.end_time > b.start_time), None
            )
            state = (
                "booked"
                if overlaps and overlaps.status == DemoBooking.Status.CONFIRMED
                else "requested"
                if overlaps
                else "free"
            )
            held_by_other = other_holds.get(str(slot.pk))
            if held_by_other:
                state = "held"
            elif slot.pk in own_ids:
                state = "yours"
            elif not slot.enabled:
                state = "unavailable"
            elif booking_date == today and slot.end_time <= timezone.localtime(now).time():
                state = "past"
            serialized.append(
                {
                    "start": demo_datetime(booking_date, slot.start_time).isoformat(),
                    "end": demo_datetime(booking_date, slot.end_time).isoformat(),
                    "available": state in {"free", "yours"},
                    "price": str(slot.price),
                    "state": state,
                }
            )
        my_hold = None
        if own_holds:
            first, last = own_holds[0], own_holds[-1]
            my_hold = {
                "token": own_token,
                "field": DEMO_FIELD_ID,
                "start": demo_datetime(booking_date, first.slot.start_time).isoformat(),
                "end": demo_datetime(booking_date, last.slot.end_time).isoformat(),
                "expires_at": min(h.expires_at for h in own_holds).isoformat(),
            }
        return Response(
            {
                "date": booking_date.isoformat(),
                "field": DEMO_FIELD_ID,
                "slots": serialized,
                "my_hold": my_hold,
                "cooldown_until": None,
                "demo_mode": True,
            }
        )


class DemoHoldView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_booking"

    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=active_workspace(touch=False).pk)
        visitor = str(request.headers.get("X-Visitor-Id", ""))[:64]
        if len(visitor) < 16 or request.data.get("field") != DEMO_FIELD_ID:
            return Response({"detail": "Refresh the demo page and select a slot again."}, status=400)
        try:
            start, end = (
                datetime.fromisoformat(str(request.data.get("start"))),
                datetime.fromisoformat(str(request.data.get("end"))),
            )
            if timezone.is_naive(start) or timezone.is_naive(end) or start >= end:
                raise ValueError
            day = timezone.localtime(start).date()
            start_time, end_time = (
                timezone.localtime(start).time().replace(tzinfo=None),
                timezone.localtime(end).time().replace(tzinfo=None),
            )
            slots = list(
                workspace.slots.select_for_update()
                .filter(enabled=True, start_time__gte=start_time, end_time__lte=end_time)
                .order_by("start_time")
            )
            if (
                not slots
                or slots[0].start_time != start_time
                or slots[-1].end_time != end_time
                or any(a.end_time != b.start_time for a, b in zip(slots, slots[1:], strict=False))
            ):
                raise ValueError
        except (ValueError, TypeError):
            return Response({"detail": "Choose one or more consecutive available demo slots."}, status=400)
        if day < timezone.localdate() or day > timezone.localdate() + timedelta(days=60):
            return Response({"detail": "Choose a date within the next 60 days."}, status=400)
        now = timezone.now()
        workspace.holds.filter(expires_at__lte=now).delete()
        if (
            workspace.bookings.filter(date=day, start_time__lt=end_time, end_time__gt=start_time)
            .filter(
                models.Q(status=DemoBooking.Status.CONFIRMED)
                | models.Q(status=DemoBooking.Status.PENDING, hold_expires_at__gt=now)
            )
            .exists()
        ):
            return Response({"detail": "That demo time was just booked. Choose another slot."}, status=409)
        conflict = (
            workspace.holds.filter(date=day, slot__in=slots, expires_at__gt=now)
            .exclude(visitor_id=visitor)
            .exists()
        )
        if conflict:
            return Response(
                {"detail": "Someone else is selecting that demo time. Choose another slot."}, status=409
            )
        token = request.data.get("token")
        try:
            old_token = uuid.UUID(str(token)) if token else None
        except ValueError:
            old_token = None
        if old_token:
            workspace.holds.filter(token=old_token, visitor_id=visitor).delete()
        hold_token = uuid.uuid4()
        expiry = now + timedelta(minutes=DEMO_HOLD_MINUTES)
        for slot in slots:
            DemoHold.objects.update_or_create(
                workspace=workspace,
                date=day,
                slot=slot,
                defaults={"visitor_id": visitor, "token": hold_token, "expires_at": expiry},
            )
        return Response(
            {
                "token": str(hold_token),
                "field": DEMO_FIELD_ID,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "expires_at": expiry.isoformat(),
                "demo_mode": True,
            }
        )

    @transaction.atomic
    def delete(self, request):
        workspace = active_workspace(touch=False)
        token = request.headers.get("X-Hold-Token")
        visitor = str(request.headers.get("X-Visitor-Id", ""))[:64]
        if token and visitor:
            DemoHold.objects.filter(workspace=workspace, token=token, visitor_id=visitor).delete()
        return Response(status=204)


class DemoBookingCreateView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_booking"

    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=active_workspace(touch=False).pk)
        visitor = str(request.headers.get("X-Visitor-Id", ""))[:64]
        key = str(request.headers.get("Idempotency-Key", ""))[:64]
        if len(visitor) < 16 or not key:
            return Response({"detail": "Refresh the demo and submit the request once more."}, status=400)
        prior = (
            DemoBooking.objects.filter(workspace=workspace, idempotency_key=key)
            .select_related("workspace", "slot")
            .first()
        )
        if prior:
            return Response(_booking_message(prior), status=200)
        try:
            booking_date = date.fromisoformat(str(request.data.get("start", ""))[:10])
            start_dt = datetime.fromisoformat(str(request.data.get("start", "")))
            end_dt = datetime.fromisoformat(str(request.data.get("end", "")))
            start_time = timezone.localtime(start_dt).time().replace(tzinfo=None)
            end_time = timezone.localtime(end_dt).time().replace(tzinfo=None)
            slots = list(
                workspace.slots.select_for_update()
                .filter(enabled=True, start_time__gte=start_time, end_time__lte=end_time)
                .order_by("start_time")
            )
            name = str(request.data.get("name", "")).strip()[:96]
            phone_raw = str(request.data.get("phone", ""))
            masked_phone = mask_demo_phone(phone_raw)
            phone_fingerprint = fingerprint_phone(phone_raw)
            amount = Decimal(str(request.data.get("payment_amount", "0"))).quantize(Decimal("0.01"))
            hold_token = uuid.UUID(str(request.data.get("hold_token", "")))
            if (
                timezone.is_naive(start_dt)
                or timezone.is_naive(end_dt)
                or not slots
                or slots[0].start_time != start_time
                or slots[-1].end_time != end_time
                or any(a.end_time != b.start_time for a, b in zip(slots, slots[1:], strict=False))
            ):
                raise ValueError
            if booking_date < timezone.localdate() or booking_date > timezone.localdate() + timedelta(
                days=60
            ):
                return Response({"detail": "Choose a date within the next 60 days."}, status=400)
            if request.data.get("field") != DEMO_FIELD_ID or not name or name.casefold() == "your name":
                return Response(
                    {"detail": "Choose the demo field and enter a sample customer name."}, status=400
                )
            active_holds = list(
                DemoHold.objects.select_for_update().filter(
                    workspace=workspace,
                    date=booking_date,
                    visitor_id=visitor,
                    token=hold_token,
                    expires_at__gt=timezone.now(),
                    slot__in=slots,
                )
            )
            if len(active_holds) != len(slots):
                return Response(
                    {"detail": "The demo slot hold expired. Select an available time again."}, status=409
                )
            if (
                workspace.bookings.filter(date=booking_date, start_time__lt=end_time, end_time__gt=start_time)
                .filter(
                    models.Q(status=DemoBooking.Status.CONFIRMED)
                    | models.Q(status=DemoBooking.Status.PENDING, hold_expires_at__gt=timezone.now())
                )
                .exists()
            ):
                return Response(
                    {"detail": "That demo time was just booked. Select another slot."}, status=409
                )
            current = (
                workspace.bookings.filter(customer__phone_fingerprint=phone_fingerprint, date=booking_date)
                .filter(
                    models.Q(status=DemoBooking.Status.CONFIRMED)
                    | models.Q(status=DemoBooking.Status.PENDING, hold_expires_at__gt=timezone.now())
                )
                .aggregate(total=models.Sum("slot_count"))["total"]
                or 0
            )
            try:
                max_daily = max(1, int(PlatformSettings.load().max_slots_per_customer))
            except (TypeError, ValueError):
                max_daily = 2
            if current + len(slots) > max_daily:
                return Response(
                    {
                        "detail": (
                            f"A demo customer may request at most {max_daily} slots on one Bangladesh "
                            "calendar day."
                        )
                    },
                    status=400,
                )
            total = sum((slot.price for slot in slots), Decimal("0.00"))
            if amount < min(total, Decimal("500.00")) or amount > total:
                return Response(
                    {
                        "detail": "Enter the simulated advance shown above.",
                        "fields": {
                            "payment_amount": [
                                "Amount must match the demo advance and stay within the slot total."
                            ]
                        },
                    },
                    status=400,
                )
            required = legal_services.required("booking", "customer", legal_services.sector_id_of(None))
            required_ids = sorted(int(item["version_id"]) for item in required)
            accepted = sorted({int(item) for item in (request.data.get("accepted_versions") or [])})
            if required_ids and (not request.data.get("agree_terms") or accepted != required_ids):
                return Response(
                    {"detail": "Accept the current required terms before submitting the demo request."},
                    status=400,
                )
            customer, _ = DemoCustomer.objects.get_or_create(
                workspace=workspace,
                phone_fingerprint=phone_fingerprint,
                defaults={"name": f"{name} (Demo)", "phone": masked_phone},
            )
            customer.name = f"{name} (Demo)"
            customer.phone = masked_phone
            customer.save(update_fields=["name", "phone", "updated_at"])
            entered_reference = str(request.data.get("trx_id", "")).strip().upper()
            if (
                not entered_reference.startswith("SIM-")
                or not entered_reference[4:].isalnum()
                or not 6 <= len(entered_reference[4:]) <= 20
            ):
                return Response(
                    {
                        "detail": (
                            "Use a sample reference such as SIM-9C7A6B5D. "
                            "Do not enter a real payment transaction ID."
                        )
                    },
                    status=400,
                )
            transaction_reference = entered_reference
            if DemoBooking.objects.filter(
                workspace=workspace, transaction_reference=transaction_reference
            ).exists():
                return Response(
                    {
                        "detail": (
                            "That simulated transaction reference was already used. "
                            "Enter a different sample reference."
                        )
                    },
                    status=400,
                )
            booking = DemoBooking.objects.create(
                workspace=workspace,
                customer=customer,
                slot=slots[0],
                date=booking_date,
                start_time=start_time,
                end_time=end_time,
                price=total,
                slot_count=len(slots),
                payment_amount=amount,
                sender_phone=mask_demo_phone(str(request.data.get("bkash_sender") or phone_raw)),
                transaction_reference=transaction_reference,
                terms_version_ids=accepted,
                terms_agreed_at=timezone.now() if required_ids else None,
                reference=f"DEMO-{secrets.token_hex(5).upper()}",
                idempotency_key=key,
                hold_expires_at=timezone.now() + timedelta(minutes=DEMO_HOLD_MINUTES),
            )
            DemoHold.objects.filter(workspace=workspace, token=hold_token, visitor_id=visitor).delete()
            DemoActivity.objects.create(
                workspace=workspace,
                action="booking_created",
                actor_type="visitor",
                actor_id=visitor[:16],
                summary=f"Demo booking {booking.reference} was submitted with simulated payment.",
            )
            DemoSms.objects.create(
                workspace=workspace,
                booking=booking,
                kind=DemoSms.Kind.BOOKING_REQUEST,
                recipient=customer.phone,
                body=(
                    f"DEMO ONLY: Booking request {booking.reference} was submitted for owner review. "
                    "No SMS was sent."
                ),
            )
        except (ValueError, TypeError, InvalidOperation, DjangoValidationError):
            return Response(
                {"detail": "Check the selected demo date, slot, sample phone number, and payment amount."},
                status=400,
            )
        except IntegrityError:
            prior = (
                DemoBooking.objects.filter(workspace=workspace, idempotency_key=key)
                .select_related("workspace", "slot")
                .first()
            )
            if prior:
                return Response(_booking_message(prior), status=200)
            return Response({"detail": "That demo time was just booked. Select another slot."}, status=409)
        return Response(_booking_message(booking), status=status.HTTP_201_CREATED)


class DemoBookingStatusView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_read"

    def get(self, request, reference):
        workspace = active_workspace(touch=False)
        booking = get_object_or_404(
            DemoBooking.objects.select_related("workspace", "slot"), workspace=workspace, reference=reference
        )
        return Response(_booking_message(booking))


class DemoWorkspaceView(DemoThrottleMixin, APIView):
    """Retained public endpoint for legacy links; contains no visitor or booking data."""

    throttle_scope = "demo_read"

    def get(self, request):
        workspace = active_workspace()
        return Response(
            {
                "id": str(workspace.pk),
                "name": workspace.name,
                "owner_name": workspace.owner_name,
                "location": "Uttara, Dhaka",
                "slots": [serialize_slot(slot) for slot in workspace.slots.all()],
                "demo_mode": True,
            }
        )


class DemoOwnerWorkspaceView(DemoOwnerMixin):
    @transaction.atomic
    def get(self, request):
        workspace = request.demo_workspace
        expired = workspace.bookings.filter(
            status=DemoBooking.Status.PENDING,
            hold_expires_at__lte=timezone.now(),
        )
        expired_refs = list(expired.values_list("reference", flat=True))
        expired.update(status=DemoBooking.Status.EXPIRED)
        if expired_refs:
            DemoActivity.objects.bulk_create(
                [
                    DemoActivity(
                        workspace=workspace,
                        actor_type="system",
                        action="booking_expired",
                        summary=f"{reference} expired before demo payment review.",
                    )
                    for reference in expired_refs
                ]
            )
        today = timezone.localdate()
        bookings = list(workspace.bookings.select_related("customer", "slot").order_by("date", "start_time"))
        customers = list(workspace.customers.order_by("name"))
        slots = list(workspace.slots.all())
        return Response(
            {
                "id": str(workspace.pk),
                "name": workspace.name,
                "owner_name": workspace.owner_name,
                "location": "Uttara, Dhaka, Bangladesh",
                "reset_count": workspace.reset_count,
                "last_reset_at": workspace.last_reset_at,
                "demo_mode": True,
                "slots": [serialize_slot(slot) for slot in slots],
                "bookings": [serialize_booking(booking) for booking in bookings],
                "customers": [{"id": str(c.pk), "name": c.name, "phone": c.phone} for c in customers],
                "activity": [
                    {"action": a.action, "summary": a.summary, "created_at": a.created_at}
                    for a in workspace.activity.all()[:30]
                ],
                "sms_messages": [
                    {
                        "kind": item.kind,
                        "recipient": item.recipient,
                        "body": item.body,
                        "status": item.status,
                        "created_at": item.created_at,
                        "reference": item.booking.reference if item.booking_id else "",
                    }
                    for item in workspace.sms_messages.select_related("booking")[:50]
                ],
                "summary": {
                    "today": sum(b.date == today for b in bookings),
                    "pending": sum(b.status == DemoBooking.Status.PENDING for b in bookings),
                    "confirmed": sum(b.status == DemoBooking.Status.CONFIRMED for b in bookings),
                    "customers": len(customers),
                    "enabled_slots": sum(s.enabled for s in slots),
                },
            }
        )


class DemoBookingActionView(DemoOwnerMixin):
    @transaction.atomic
    def patch(self, request, pk):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=request.demo_workspace.pk)
        booking = get_object_or_404(
            DemoBooking.objects.select_for_update().select_related("customer", "slot"),
            pk=pk,
            workspace=workspace,
        )
        action = str(request.data.get("action", ""))
        reason = str(request.data.get("reason", "")).strip()[:300]
        transitions = {
            "approve": DemoBooking.Status.CONFIRMED,
            "reject": DemoBooking.Status.REJECTED,
            "cancel": DemoBooking.Status.CANCELLED,
        }
        allowed = {
            DemoBooking.Status.PENDING: {"approve", "reject", "cancel"},
            DemoBooking.Status.CONFIRMED: {"cancel"},
        }
        if action not in allowed.get(booking.status, set()):
            return Response({"detail": "This demo booking cannot be changed that way."}, status=400)
        if (
            booking.status == DemoBooking.Status.PENDING
            and booking.hold_expires_at
            and booking.hold_expires_at <= timezone.now()
        ):
            booking.status = DemoBooking.Status.EXPIRED
            booking.save(update_fields=["status", "updated_at"])
            DemoActivity.objects.create(
                workspace=workspace,
                actor_type="system",
                action="booking_expired",
                summary=f"{booking.reference} expired before demo payment review.",
            )
            return Response(
                {"detail": "This demo payment hold expired. The slot is available again."}, status=409
            )
        if action == "reject" and not reason:
            reason = "Payment details were not approved in this simulation."
        booking.status = transitions[action]
        booking.payment_status = (
            DemoBooking.PaymentStatus.APPROVED
            if action == "approve"
            else DemoBooking.PaymentStatus.REJECTED
            if action == "reject"
            else booking.payment_status
        )
        booking.rejection_reason = reason if action == "reject" else ""
        booking.reviewed_at = timezone.now()
        booking.reviewed_by = "Demo Owner"
        if action == "approve":
            booking.confirmed_at = timezone.now()
            booking.hold_expires_at = None
        booking.save(
            update_fields=[
                "status",
                "payment_status",
                "rejection_reason",
                "reviewed_at",
                "reviewed_by",
                "confirmed_at",
                "hold_expires_at",
                "updated_at",
            ]
        )
        past = {"approve": "approved in demo", "reject": "rejected in demo", "cancel": "cancelled in demo"}[
            action
        ]
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="demo_owner",
            action=f"booking_{action}",
            summary=f"{booking.reference} was {past}.",
        )
        kind = {
            "approve": DemoSms.Kind.BOOKING_APPROVED,
            "reject": DemoSms.Kind.BOOKING_REJECTED,
            "cancel": DemoSms.Kind.BOOKING_CANCELLED,
        }[action]
        DemoSms.objects.create(
            workspace=workspace,
            booking=booking,
            kind=kind,
            recipient=booking.customer.phone,
            body=f"DEMO ONLY: Booking {booking.reference} was {booking.status}. No SMS was sent.",
        )
        return Response(serialize_booking(booking))


class DemoSlotDetailView(DemoOwnerMixin):
    @transaction.atomic
    def patch(self, request, pk):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=request.demo_workspace.pk)
        slot = get_object_or_404(DemoSlot.objects.select_for_update(), pk=pk, workspace=workspace)
        if "enabled" in request.data:
            slot.enabled = bool(request.data["enabled"])
        if "price" in request.data:
            try:
                slot.price = Decimal(str(request.data["price"])).quantize(Decimal("0.01"))
                if slot.price < 0 or slot.price > Decimal("1000000"):
                    raise ValueError
            except (ValueError, InvalidOperation):
                return Response({"detail": "Enter a valid demo price."}, status=400)
        for field in ("start_time", "end_time"):
            if field in request.data:
                try:
                    setattr(slot, field, time.fromisoformat(str(request.data[field])))
                except ValueError:
                    return Response({"detail": "Enter a valid slot time."}, status=400)
        if slot.start_time >= slot.end_time:
            return Response({"detail": "Demo slots must end after they start."}, status=400)
        if (
            workspace.slots.exclude(pk=slot.pk)
            .filter(start_time__lt=slot.end_time, end_time__gt=slot.start_time)
            .exists()
        ):
            return Response({"detail": "This time overlaps another demo slot."}, status=400)
        if workspace.bookings.filter(slot=slot, status__in=["pending", "confirmed"]).exists():
            return Response(
                {"detail": "A slot with active demo bookings cannot be rescheduled or disabled."}, status=400
            )
        slot.save(update_fields=["enabled", "price", "start_time", "end_time", "updated_at"])
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="demo_owner",
            action="slot_updated",
            summary=f"Demo slot {slot.label} was changed.",
        )
        return Response(serialize_slot(slot))


class DemoSlotsView(DemoOwnerMixin):
    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=request.demo_workspace.pk)
        try:
            start, end = (
                time.fromisoformat(str(request.data.get("start_time", ""))),
                time.fromisoformat(str(request.data.get("end_time", ""))),
            )
            price = Decimal(str(request.data.get("price", "0"))).quantize(Decimal("0.01"))
            category = str(request.data.get("category", DemoSlot.Category.EVENING))
            label = str(request.data.get("label", "Custom demo slot")).strip()[:80]
            if start >= end or price < 0 or category not in DemoSlot.Category.values or not label:
                raise ValueError
        except (ValueError, InvalidOperation):
            return Response(
                {"detail": "Enter a valid label, time range, category, and non-negative price."}, status=400
            )
        if workspace.slots.filter(start_time__lt=end, end_time__gt=start).exists():
            return Response({"detail": "This time overlaps another demo slot."}, status=400)
        slot = DemoSlot.objects.create(
            workspace=workspace,
            label=label,
            start_time=start,
            end_time=end,
            category=category,
            price=price,
            display_order=workspace.slots.count(),
        )
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="demo_owner",
            action="slot_created",
            summary=f"Demo slot {label} was added.",
        )
        return Response(serialize_slot(slot), status=201)


class AdminDemoWorkspacesView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response([serialize_admin_workspace(get_public_workspace())])


def serialize_admin_workspace(workspace):
    return {
        "id": str(workspace.pk),
        "name": workspace.name,
        "owner_name": workspace.owner_name,
        "status": workspace.status,
        "created_at": workspace.created_at,
        "last_access_at": workspace.last_access_at,
        "last_reset_at": workspace.last_reset_at,
        "booking_count": workspace.bookings.count(),
        "customer_count": workspace.customers.count(),
        "slot_count": workspace.slots.count(),
        "reset_count": workspace.reset_count,
    }


class AdminDemoWorkspaceDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk, public_key="public")
        if "status" in request.data:
            if request.data["status"] not in DemoWorkspace.Status.values:
                return Response({"detail": "Invalid demo status."}, status=400)
            workspace.status = request.data["status"]
        if "name" in request.data:
            workspace.name = str(request.data["name"]).strip()[:100] or workspace.name
        if "owner_name" in request.data:
            workspace.owner_name = str(request.data["owner_name"]).strip()[:100] or workspace.owner_name
        workspace.save(update_fields=["status", "name", "owner_name", "updated_at"])
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="admin",
            action="workspace_updated",
            summary=f"Admin updated shared demo status to {workspace.status}.",
        )
        return Response(serialize_admin_workspace(workspace))


class AdminDemoWorkspaceResetView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk, public_key="public")
        count = reset_public_workspace(workspace)
        workspace.refresh_from_db()
        return Response({"reset_count": count, "workspace": serialize_admin_workspace(workspace)})


class AdminDemoWorkspaceActivityView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk, public_key="public")
        return Response(
            [
                {
                    "actor_type": a.actor_type,
                    "action": a.action,
                    "summary": a.summary,
                    "created_at": a.created_at,
                }
                for a in workspace.activity.all()[:100]
            ]
        )
