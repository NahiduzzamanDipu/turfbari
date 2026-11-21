"""Demo APIs deliberately use demo-only tables and never call production booking services."""

import hashlib
import secrets
import uuid
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.bookings.phone import normalize_bd_phone
from apps.common.permissions import IsPlatformAdmin

from .models import DemoActivity, DemoBooking, DemoCustomer, DemoSlot, DemoWorkspace

DEMO_HOURS = 24


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token():
    return secrets.token_urlsafe(32)


def seed_workspace(workspace):
    for index, (label, start, end, category, price) in enumerate(
        [
            ("Morning · 08:00–09:00", time(8), time(9), DemoSlot.Category.MORNING, "1200.00"),
            ("Evening · 17:00–18:00", time(17), time(18), DemoSlot.Category.EVENING, "1800.00"),
            ("Evening · 18:00–19:00", time(18), time(19), DemoSlot.Category.EVENING, "1800.00"),
            ("Night · 20:00–21:00", time(20), time(21), DemoSlot.Category.NIGHT, "1500.00"),
            ("Midnight · 00:00–01:00", time(0), time(1), DemoSlot.Category.MIDNIGHT, "900.00"),
        ]
    ):
        DemoSlot.objects.create(
            workspace=workspace,
            label=label,
            start_time=start,
            end_time=end,
            category=category,
            price=Decimal(price),
            display_order=index,
        )
    sample_slot = workspace.slots.filter(start_time=time(18)).first()
    customer = DemoCustomer.objects.create(
        workspace=workspace, name="Rahim Uddin · Demo", phone="+8801800000001"
    )
    DemoBooking.objects.create(
        workspace=workspace,
        customer=customer,
        slot=sample_slot,
        date=timezone.localdate() + timedelta(days=1),
        start_time=sample_slot.start_time,
        end_time=sample_slot.end_time,
        price=sample_slot.price,
        reference=f"DEMO-{secrets.token_hex(4).upper()}",
        status=DemoBooking.Status.PENDING,
    )


@transaction.atomic
def create_workspace(*, actor=None, ttl_hours=DEMO_HOURS):
    token = new_token()
    workspace = DemoWorkspace.objects.create(
        access_token_hash=token_hash(token),
        expires_at=timezone.now() + timedelta(hours=ttl_hours),
        created_by=actor,
    )
    seed_workspace(workspace)
    return workspace, token


def get_workspace(request):
    return getattr(request, "demo_workspace", None)


class DemoBearerMixin:
    """Resolve a short-lived bearer token to exactly one isolated workspace."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        authorization = request.headers.get("Authorization", "")
        scheme, _, raw = authorization.partition(" ")
        workspace = None
        if scheme.lower() == "bearer" and raw:
            workspace = DemoWorkspace.objects.filter(
                access_token_hash=token_hash(raw),
                status=DemoWorkspace.Status.ACTIVE,
                expires_at__gt=timezone.now(),
            ).first()
        if not workspace:
            from rest_framework.exceptions import AuthenticationFailed

            raise AuthenticationFailed("Demo session is missing, expired, or disabled.")
        workspace.last_access_at = timezone.now()
        workspace.save(update_fields=["last_access_at", "updated_at"])
        request.demo_workspace = workspace


def serialize_slot(slot, *, booked=False):
    return {
        "id": str(slot.pk),
        "label": slot.label,
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "category": slot.category,
        "price": str(slot.price),
        "enabled": slot.enabled,
        "booked": booked,
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
        "note": booking.note,
        "status": booking.status,
        "created_at": booking.created_at,
    }


class DemoSessionView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo_session"

    def post(self, request):
        invite = str(request.data.get("access_key", ""))
        if invite:
            workspace = DemoWorkspace.objects.filter(
                access_token_hash=token_hash(invite),
                status=DemoWorkspace.Status.ACTIVE,
                expires_at__gt=timezone.now(),
            ).first()
            if workspace:
                return Response(
                    {"token": invite, "workspace_id": str(workspace.pk), "expires_at": workspace.expires_at}
                )
            return Response({"detail": "This demo access link has expired or was disabled."}, status=400)
        workspace, token = create_workspace()
        DemoActivity.objects.create(
            workspace=workspace, action="session_created", summary="A visitor started a demo."
        )
        return Response(
            {"token": token, "workspace_id": str(workspace.pk), "expires_at": workspace.expires_at},
            status=status.HTTP_201_CREATED,
        )


class DemoQRCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        import segno

        target = request.build_absolute_uri("/demo-booking")
        qr = segno.make(target, error="M")
        response = HttpResponse(content_type="image/svg+xml")
        qr.save(response, kind="svg", scale=5, border=2, dark="#064e3b", light="#ffffff")
        response["Cache-Control"] = "public, max-age=3600"
        return response


class DemoWorkspaceView(DemoBearerMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        workspace = get_workspace(request)
        slots = list(workspace.slots.all())
        bookings = list(workspace.bookings.select_related("customer", "slot"))
        customers = list(workspace.customers.all())
        today = timezone.localdate()
        return Response(
            {
                "id": str(workspace.pk),
                "name": workspace.name,
                "owner_name": workspace.owner_name,
                "location": "Demo Location, Bangladesh",
                "expires_at": workspace.expires_at,
                "slots": [serialize_slot(slot) for slot in slots],
                "bookings": [serialize_booking(booking) for booking in bookings],
                "customers": [{"id": str(c.pk), "name": c.name, "phone": c.phone} for c in customers],
                "activity": [
                    {"action": a.action, "summary": a.summary, "created_at": a.created_at}
                    for a in workspace.activity.all()[:10]
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

    def patch(self, request):
        workspace = get_workspace(request)
        workspace.name = str(request.data.get("name", workspace.name)).strip()[:100] or workspace.name
        workspace.save(update_fields=["name", "updated_at"])
        return Response({"name": workspace.name})


class DemoBookingCreateView(DemoBearerMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=get_workspace(request).pk)
        try:
            booking_date = date.fromisoformat(str(request.data.get("date", "")))
            slot_id = uuid.UUID(str(request.data.get("slot_id", "")))
            slot = DemoSlot.objects.select_for_update().get(pk=slot_id, workspace=workspace)
            name = str(request.data.get("name", "")).strip()[:100]
            phone = normalize_bd_phone(str(request.data.get("phone", "")))
            note = str(request.data.get("note", "")).strip()[:500]
            if booking_date < timezone.localdate() or booking_date > timezone.localdate() + timedelta(
                days=60
            ):
                return Response({"detail": "Choose a date within the next 60 days."}, status=400)
            if not slot.enabled or not name:
                return Response({"detail": "Choose an available demo slot and enter your name."}, status=400)
            if DemoBooking.objects.filter(
                workspace=workspace,
                date=booking_date,
                slot=slot,
                status__in=[DemoBooking.Status.PENDING, DemoBooking.Status.CONFIRMED],
            ).exists():
                return Response(
                    {"detail": "That demo slot was just booked. Choose another time."}, status=409
                )
            customer, _ = DemoCustomer.objects.get_or_create(
                workspace=workspace, phone=phone, defaults={"name": name}
            )
            if customer.name != name:
                customer.name = name
                customer.save(update_fields=["name", "updated_at"])
            reference = f"DEMO-{secrets.token_hex(4).upper()}"
            with transaction.atomic():
                booking = DemoBooking.objects.create(
                    workspace=workspace,
                    customer=customer,
                    slot=slot,
                    date=booking_date,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    price=slot.price,
                    reference=reference,
                    note=note,
                )
            DemoActivity.objects.create(
                workspace=workspace,
                action="booking_created",
                summary=f"Demo booking {reference} was submitted.",
            )
        except (ValueError, TypeError, DjangoValidationError, DemoSlot.DoesNotExist):
            return Response({"detail": "The selected demo date or slot is invalid."}, status=400)
        except IntegrityError:
            return Response({"detail": "That demo slot was just booked. Choose another time."}, status=409)
        return Response(serialize_booking(booking), status=201)


class DemoBookingActionView(DemoBearerMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def patch(self, request, pk):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=get_workspace(request).pk)
        booking = get_object_or_404(
            DemoBooking.objects.select_for_update().select_related("customer", "slot"),
            pk=pk,
            workspace=workspace,
        )
        action = str(request.data.get("action", ""))
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
        booking.status = transitions[action]
        booking.reviewed_at = timezone.now()
        booking.save(update_fields=["status", "reviewed_at", "updated_at"])
        past_tense = {"approve": "approved", "reject": "rejected", "cancel": "cancelled"}[action]
        DemoActivity.objects.create(
            workspace=workspace,
            action=f"booking_{action}",
            summary=f"{booking.reference} was {past_tense} in demo.",
        )
        return Response(serialize_booking(booking))


class DemoSlotDetailView(DemoBearerMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def patch(self, request, pk):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=get_workspace(request).pk)
        slot = get_object_or_404(DemoSlot, pk=pk, workspace=workspace)
        if "enabled" in request.data:
            slot.enabled = bool(request.data["enabled"])
        if "price" in request.data:
            try:
                price = Decimal(str(request.data["price"]))
                if price < 0 or price > Decimal("1000000"):
                    raise ValueError
                slot.price = price.quantize(Decimal("0.01"))
            except Exception:
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
        if "label" in request.data:
            slot.label = str(request.data["label"]).strip()[:80] or slot.label
        slot.save(update_fields=["enabled", "price", "start_time", "end_time", "label", "updated_at"])
        DemoActivity.objects.create(
            workspace=workspace, action="slot_updated", summary=f"Demo slot {slot.label} was changed."
        )
        return Response(serialize_slot(slot))


class DemoSlotsView(DemoBearerMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=get_workspace(request).pk)
        try:
            start = time.fromisoformat(str(request.data.get("start_time", "")))
            end = time.fromisoformat(str(request.data.get("end_time", "")))
            price = Decimal(str(request.data.get("price", "0"))).quantize(Decimal("0.01"))
            category = str(request.data.get("category", DemoSlot.Category.EVENING))
            label = str(request.data.get("label", "Custom demo slot")).strip()[:80]
            if start >= end or price < 0 or category not in DemoSlot.Category.values or not label:
                raise ValueError
        except Exception:
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
            workspace=workspace, action="slot_created", summary=f"Demo slot {label} was added."
        )
        return Response(serialize_slot(slot), status=201)


class AdminDemoWorkspacesView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        qs = DemoWorkspace.objects.annotate(booking_count=models.Count("bookings")).order_by("-created_at")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(models.Q(name__icontains=search) | models.Q(owner_name__icontains=search))
        return Response(
            [
                {
                    "id": str(w.pk),
                    "name": w.name,
                    "owner_name": w.owner_name,
                    "status": w.status,
                    "created_at": w.created_at,
                    "expires_at": w.expires_at,
                    "last_access_at": w.last_access_at,
                    "booking_count": w.booking_count,
                }
                for w in qs[:200]
            ]
        )

    def post(self, request):
        workspace, token = create_workspace(actor=request.user)
        workspace.name = str(request.data.get("name", workspace.name)).strip()[:100] or workspace.name
        workspace.owner_name = (
            str(request.data.get("owner_name", workspace.owner_name)).strip()[:100] or workspace.owner_name
        )
        workspace.save(update_fields=["name", "owner_name", "updated_at"])
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="admin",
            action="workspace_created",
            summary="Admin created a demo workspace.",
        )
        return Response(
            {
                "id": str(workspace.pk),
                "name": workspace.name,
                "access_url": f"/demo-account#access={token}",
                "expires_at": workspace.expires_at,
            },
            status=201,
        )


class AdminDemoWorkspaceDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk)
        if "name" in request.data:
            workspace.name = str(request.data["name"]).strip()[:100] or workspace.name
        if "owner_name" in request.data:
            workspace.owner_name = str(request.data["owner_name"]).strip()[:100] or workspace.owner_name
        if "status" in request.data:
            if request.data["status"] not in DemoWorkspace.Status.values:
                return Response({"detail": "Invalid demo status."}, status=400)
            workspace.status = request.data["status"]
        if "hours" in request.data:
            try:
                hours = int(request.data["hours"])
                if not 1 <= hours <= 24 * 90:
                    raise ValueError
                workspace.expires_at = timezone.now() + timedelta(hours=hours)
                if workspace.status == DemoWorkspace.Status.EXPIRED:
                    workspace.status = DemoWorkspace.Status.ACTIVE
            except ValueError:
                return Response({"detail": "Expiry must be between 1 hour and 90 days."}, status=400)
        if "expires_at" in request.data:
            from django.utils.dateparse import parse_datetime

            expiry = parse_datetime(str(request.data["expires_at"]))
            if (
                not expiry
                or timezone.is_naive(expiry)
                or not timezone.now() < expiry <= timezone.now() + timedelta(days=90)
            ):
                return Response(
                    {"detail": "Choose a future expiry date within the next 90 days."}, status=400
                )
            workspace.expires_at = expiry
            if workspace.status == DemoWorkspace.Status.EXPIRED:
                workspace.status = DemoWorkspace.Status.ACTIVE
        workspace.save()
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="admin",
            action="workspace_updated",
            summary="Admin updated demo access.",
        )
        return Response(
            {"id": str(workspace.pk), "status": workspace.status, "expires_at": workspace.expires_at}
        )

    def delete(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk)
        workspace.status = DemoWorkspace.Status.DISABLED
        workspace.save(update_fields=["status", "updated_at"])
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="admin",
            action="workspace_disabled",
            summary="Admin disabled demo access.",
        )
        return Response(status=204)


class AdminDemoWorkspaceResetView(APIView):
    permission_classes = [IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace.objects.select_for_update(), pk=pk)
        workspace.bookings.all().delete()
        workspace.customers.all().delete()
        workspace.slots.all().delete()
        workspace.reset_count += 1
        workspace.save(update_fields=["reset_count", "updated_at"])
        seed_workspace(workspace)
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="admin",
            action="workspace_reset",
            summary="Admin reset demo bookings, customers, and slots.",
        )
        return Response({"reset": True, "reset_count": workspace.reset_count})


class AdminDemoWorkspaceAccessView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk)
        token = new_token()
        workspace.access_token_hash = token_hash(token)
        workspace.status = DemoWorkspace.Status.ACTIVE
        workspace.expires_at = timezone.now() + timedelta(hours=DEMO_HOURS)
        workspace.save(update_fields=["access_token_hash", "status", "expires_at", "updated_at"])
        DemoActivity.objects.create(
            workspace=workspace,
            actor_type="admin",
            action="access_rotated",
            summary="Admin rotated demo access link.",
        )
        return Response({"access_url": f"/demo-account#access={token}", "expires_at": workspace.expires_at})


class AdminDemoWorkspaceActivityView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        workspace = get_object_or_404(DemoWorkspace, pk=pk)
        return Response(
            [
                {
                    "actor_type": item.actor_type,
                    "action": item.action,
                    "summary": item.summary,
                    "created_at": item.created_at,
                }
                for item in workspace.activity.all()[:100]
            ]
        )
