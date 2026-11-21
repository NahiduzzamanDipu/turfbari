"""Public shared demo APIs. They only read and write the isolated demo tables."""

import secrets
import uuid
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.permissions import IsPlatformAdmin

from .models import DemoActivity, DemoBooking, DemoCustomer, DemoSlot, DemoWorkspace
from .services import get_public_workspace, mask_demo_phone, reset_public_workspace


def active_workspace():
    workspace = get_public_workspace()
    if workspace.status != DemoWorkspace.Status.ACTIVE:
        raise Http404("The public demo is currently unavailable.")
    workspace.last_access_at = timezone.now()
    workspace.save(update_fields=["last_access_at", "updated_at"])
    return workspace


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
        "note": "",
        "status": booking.status,
        "created_at": booking.created_at,
    }


class DemoThrottleMixin:
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo_write"


class DemoQRCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        active_workspace()
        import segno

        qr = segno.make(request.build_absolute_uri("/demo-booking"), error="M")
        response = HttpResponse(content_type="image/svg+xml")
        qr.save(response, kind="svg", scale=5, border=2, dark="#064e3b", light="#ffffff")
        response["Cache-Control"] = "public, max-age=3600"
        return response


class DemoWorkspaceView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        workspace = active_workspace()
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
        workspace = active_workspace()
        workspace.name = str(request.data.get("name", workspace.name)).strip()[:100] or workspace.name
        workspace.save(update_fields=["name", "updated_at"])
        return Response({"name": workspace.name})


class DemoBookingCreateView(DemoThrottleMixin, APIView):
    throttle_scope = "demo_booking"

    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=active_workspace().pk)
        try:
            booking_date = date.fromisoformat(str(request.data.get("date", "")))
            slot_id = uuid.UUID(str(request.data.get("slot_id", "")))
            slot = DemoSlot.objects.select_for_update().get(pk=slot_id, workspace=workspace)
            name = str(request.data.get("name", "")).strip()[:100]
            phone = mask_demo_phone(str(request.data.get("phone", "")))
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
            customer = DemoCustomer.objects.create(workspace=workspace, name=f"{name} (Demo)", phone=phone)
            booking = DemoBooking.objects.create(
                workspace=workspace,
                customer=customer,
                slot=slot,
                date=booking_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                price=slot.price,
                reference=f"DEMO-{secrets.token_hex(4).upper()}",
                note="",
            )
            DemoActivity.objects.create(
                workspace=workspace,
                action="booking_created",
                summary=f"Demo booking {booking.reference} was submitted.",
            )
        except (ValueError, TypeError, DjangoValidationError, DemoSlot.DoesNotExist):
            return Response(
                {"detail": "The selected demo date, slot, or Bangladesh mobile number is invalid."},
                status=400,
            )
        except IntegrityError:
            return Response({"detail": "That demo slot was just booked. Choose another time."}, status=409)
        return Response(serialize_booking(booking), status=status.HTTP_201_CREATED)


class DemoBookingActionView(DemoThrottleMixin, APIView):
    @transaction.atomic
    def patch(self, request, pk):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=active_workspace().pk)
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
        past = {"approve": "approved", "reject": "rejected", "cancel": "cancelled"}[action]
        DemoActivity.objects.create(
            workspace=workspace,
            action=f"booking_{action}",
            summary=f"{booking.reference} was {past} in demo.",
        )
        return Response(serialize_booking(booking))


class DemoSlotDetailView(DemoThrottleMixin, APIView):
    @transaction.atomic
    def patch(self, request, pk):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=active_workspace().pk)
        slot = get_object_or_404(DemoSlot, pk=pk, workspace=workspace)
        if "enabled" in request.data:
            slot.enabled = bool(request.data["enabled"])
        if "price" in request.data:
            try:
                slot.price = Decimal(str(request.data["price"])).quantize(Decimal("0.01"))
                if slot.price < 0 or slot.price > Decimal("1000000"):
                    raise ValueError
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


class DemoSlotsView(DemoThrottleMixin, APIView):
    @transaction.atomic
    def post(self, request):
        workspace = DemoWorkspace.objects.select_for_update().get(pk=active_workspace().pk)
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


def serialize_admin_workspace(workspace):
    return {
        "id": str(workspace.pk),
        "name": workspace.name,
        "owner_name": workspace.owner_name,
        "status": workspace.status,
        "created_at": workspace.created_at,
        "last_access_at": workspace.last_access_at,
        "booking_count": workspace.bookings.count(),
        "customer_count": workspace.customers.count(),
        "slot_count": workspace.slots.count(),
        "reset_count": workspace.reset_count,
    }


class AdminDemoWorkspacesView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response([serialize_admin_workspace(get_public_workspace())])


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
