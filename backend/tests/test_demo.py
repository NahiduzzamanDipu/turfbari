"""End-to-end tests for the isolated public customer-to-owner demo."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, Payment, PaymentSubmission
from apps.common.models import PlatformSettings
from apps.demo.models import DemoActivity, DemoBooking, DemoHold, DemoSms
from apps.demo.services import get_public_workspace, reset_demo_if_due
from apps.notifications.models import SmsMessage, WalletTransaction

pytestmark = pytest.mark.django_db


def visitor():
    return APIClient()


def owner_client():
    client = APIClient()
    response = client.post("/api/public/demo/owner-access/", {}, format="json")
    assert response.status_code == 200
    return client


def turf_and_slot(client, *, day_offset=2, slot_start="17:00"):
    turf = client.get("/api/public/demo/turf/")
    assert turf.status_code == 200
    availability = client.get(
        "/api/public/demo/availability/",
        {"field": "demo-field", "date": (timezone.localdate() + timedelta(days=day_offset)).isoformat()},
    )
    assert availability.status_code == 200
    return turf.json(), next(
        item for item in availability.json()["slots"] if item["start"].endswith(f"T{slot_start}:00+06:00")
    )


def create_request(client, *, phone="01712345678", day_offset=2, start_hour="17:00", key="demo-request-1"):
    turf = client.get("/api/public/demo/turf/").json()
    day = (timezone.localdate() + timedelta(days=day_offset)).isoformat()
    availability = client.get("/api/public/demo/availability/", {"field": "demo-field", "date": day}).json()
    selected = next(
        item for item in availability["slots"] if item["start"].endswith(f"T{start_hour}:00+06:00")
    )
    hold = client.post(
        "/api/public/demo/hold/",
        {"field": "demo-field", "start": selected["start"], "end": selected["end"]},
        format="json",
        HTTP_X_VISITOR_ID="demo-browser-visitor-001",
    )
    assert hold.status_code == 200, hold.json()
    legal = turf.get("legal", [])
    response = client.post(
        "/api/public/demo/book/",
        {
            "field": "demo-field",
            "start": selected["start"],
            "end": selected["end"],
            "hold_token": hold.json()["token"],
            "name": "Demo Player",
            "phone": phone,
            "payment_amount": selected["price"],
            "bkash_sender": phone,
            "trx_id": f"SIM-{''.join(c for c in key.upper() if c.isalnum())[:15]}",
            "agree_terms": True,
            "accepted_versions": [item["version_id"] for item in legal],
        },
        format="json",
        HTTP_X_VISITOR_ID="demo-browser-visitor-001",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    return response


def test_full_customer_to_demo_owner_flow_is_isolated_and_trackable():
    customer = visitor()
    workspace = get_public_workspace()
    real_counts = (
        Booking.objects.count(),
        Payment.objects.count(),
        PaymentSubmission.objects.count(),
        SmsMessage.objects.count(),
        WalletTransaction.objects.count(),
    )

    submitted = create_request(customer)
    assert submitted.status_code == 201, submitted.json()
    result = submitted.json()
    assert result["status"] == DemoBooking.Status.PENDING
    assert result["payment"]["status"] == DemoBooking.PaymentStatus.PENDING
    assert result["demo_mode"] is True
    assert result["turf_phone"] is None

    # Public workspace configuration is safe; booking/customer details require the demo owner session.
    public = customer.get("/api/public/demo/workspace/").json()
    assert "bookings" not in public and "customers" not in public
    assert customer.get("/api/public/demo/owner/workspace/").status_code == 403

    owner = owner_client()
    dashboard = owner.get("/api/public/demo/owner/workspace/")
    assert dashboard.status_code == 200
    booking = next(row for row in dashboard.json()["bookings"] if row["reference"] == result["reference"])
    assert booking["customer_name"] == "Demo Player (Demo)"
    assert booking["customer_phone"] == "+8801*****5678"
    assert booking["payment_amount"] == result["payment"]["amount"]
    assert booking["sender_phone"] == "+8801*****5678"
    assert booking["transaction_reference"] == "SIM-DEMOREQUEST1"
    assert dashboard.json()["sms_messages"]

    approved = owner.patch(
        f"/api/public/demo/owner/bookings/{booking['id']}/", {"action": "approve"}, format="json"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == DemoBooking.Status.CONFIRMED
    assert approved.json()["payment_status"] == DemoBooking.PaymentStatus.APPROVED
    assert (
        customer.get(f"/api/public/demo/bookings/status/{result['reference']}/").json()["status"]
        == "confirmed"
    )
    assert DemoSms.objects.filter(workspace=workspace, booking_id=booking["id"]).count() == 2
    assert (
        Booking.objects.count(),
        Payment.objects.count(),
        PaymentSubmission.objects.count(),
        SmsMessage.objects.count(),
        WalletTransaction.objects.count(),
    ) == real_counts


def test_demo_booking_requires_a_hold_and_idempotency_prevents_duplicate_records():
    client = visitor()
    first = create_request(client, key="same-demo-key")
    assert first.status_code == 201, first.json()
    repeated = client.post(
        "/api/public/demo/book/",
        {},
        format="json",
        HTTP_X_VISITOR_ID="demo-browser-visitor-001",
        HTTP_IDEMPOTENCY_KEY="same-demo-key",
    )
    assert repeated.status_code == 200
    assert repeated.json()["reference"] == first.json()["reference"]
    assert DemoBooking.objects.filter(reference=first.json()["reference"]).count() == 1
    assert DemoHold.objects.count() == 0


def test_reject_releases_slot_and_status_change_is_visible_to_customer():
    client = visitor()
    created = create_request(client, key="rejectable-demo")
    assert created.status_code == 201
    owner = owner_client()
    booking = DemoBooking.objects.get(reference=created.json()["reference"])
    rejected = owner.patch(
        f"/api/public/demo/owner/bookings/{booking.pk}/",
        {"action": "reject", "reason": "Simulated details do not match."},
        format="json",
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Simulated details do not match."
    assert client.get(f"/api/public/demo/bookings/status/{booking.reference}/").json()["status"] == "rejected"


def test_other_visitors_cannot_take_an_active_demo_hold_and_owner_actions_require_cookie():
    first, second = visitor(), visitor()
    day = (timezone.localdate() + timedelta(days=7)).isoformat()
    availability = first.get("/api/public/demo/availability/", {"field": "demo-field", "date": day}).json()
    slot = next(row for row in availability["slots"] if row["start"].endswith("T17:00:00+06:00"))
    held = first.post(
        "/api/public/demo/hold/",
        {"field": "demo-field", "start": slot["start"], "end": slot["end"]},
        format="json",
        HTTP_X_VISITOR_ID="first-demo-browser-visitor",
    )
    assert held.status_code == 200
    other = second.get("/api/public/demo/availability/", {"field": "demo-field", "date": day}).json()
    other_slot = next(row for row in other["slots"] if row["start"] == slot["start"])
    assert other_slot["state"] == "held" and other_slot["available"] is False
    assert (
        second.patch(
            "/api/public/demo/owner/bookings/00000000-0000-0000-0000-000000000000/",
            {"action": "approve"},
            format="json",
        ).status_code
        == 403
    )


def test_expired_demo_payment_hold_releases_slot_and_updates_owner_status():
    client = visitor()
    created = create_request(client, key="expiring-demo")
    assert created.status_code == 201
    booking = DemoBooking.objects.get(reference=created.json()["reference"])
    booking.hold_expires_at = timezone.now() - timedelta(seconds=1)
    booking.save(update_fields=["hold_expires_at", "updated_at"])
    availability = client.get(
        "/api/public/demo/availability/",
        {"field": "demo-field", "date": booking.date.isoformat()},
    ).json()
    slot = next(row for row in availability["slots"] if row["start"].endswith("T17:00:00+06:00"))
    assert slot["available"] is True
    owner_data = owner_client().get("/api/public/demo/owner/workspace/").json()
    row = next(item for item in owner_data["bookings"] if item["id"] == str(booking.pk))
    assert row["status"] == DemoBooking.Status.EXPIRED


def test_customer_daily_limit_counts_active_slots_for_normalized_phone():
    settings = PlatformSettings.load()
    settings.max_slots_per_customer = 2
    settings.save(update_fields=["max_slots_per_customer", "updated_at"])
    day_offset = 11
    phone = "01612345678"
    one = create_request(visitor(), phone=phone, day_offset=day_offset, start_hour="17:00", key="limit-one")
    two = create_request(visitor(), phone=phone, day_offset=day_offset, start_hour="18:00", key="limit-two")
    three = create_request(
        visitor(), phone=phone, day_offset=day_offset, start_hour="20:00", key="limit-three"
    )
    assert one.status_code == 201
    assert two.status_code == 201
    assert three.status_code == 400
    assert (
        DemoBooking.objects.filter(
            customer__phone_fingerprint__gt="",
            date=timezone.localdate() + timedelta(days=day_offset),
        ).count()
        == 2
    )


def test_demo_owner_cookie_is_invalidated_by_reset_and_reset_only_touches_demo_tables():
    owner = owner_client()
    workspace = get_public_workspace()
    prior_count = workspace.bookings.count()
    real_before = Booking.objects.count()
    old_reset = workspace.reset_count
    from apps.demo.services import reset_public_workspace

    reset_public_workspace(workspace)
    assert owner.get("/api/public/demo/owner/workspace/").status_code == 403
    workspace.refresh_from_db()
    assert workspace.reset_count == old_reset + 1
    assert workspace.bookings.count() == prior_count
    assert Booking.objects.count() == real_before
    assert DemoActivity.objects.filter(workspace=workspace, action="workspace_reset").exists()


def test_scheduler_resets_only_when_ten_minutes_have_elapsed():
    workspace = get_public_workspace()
    workspace.last_reset_at = timezone.now() - timedelta(minutes=9, seconds=59)
    workspace.save(update_fields=["last_reset_at", "updated_at"])
    assert reset_demo_if_due()["status"] == "not_due"
    workspace.refresh_from_db()
    workspace.last_reset_at = timezone.now() - timedelta(minutes=10, seconds=1)
    workspace.save(update_fields=["last_reset_at", "updated_at"])
    result = reset_demo_if_due()
    workspace.refresh_from_db()
    assert result["status"] == "reset"
    assert workspace.reset_count == 1


def test_admin_only_can_disable_and_reset_the_demo():
    workspace = get_public_workspace()
    guest = visitor()
    assert guest.get("/api/admin/demo/workspaces/").status_code == 403
    assert guest.post(f"/api/admin/demo/workspaces/{workspace.pk}/reset/").status_code == 403
    from .test_subscriptions import admin_client

    admin, _ = admin_client()
    disabled = admin.patch(
        f"/api/admin/demo/workspaces/{workspace.pk}/", {"status": "disabled"}, format="json"
    )
    assert disabled.status_code == 200
    assert guest.get("/api/public/demo/turf/").status_code == 404
    admin.patch(f"/api/admin/demo/workspaces/{workspace.pk}/", {"status": "active"}, format="json")
    assert guest.get("/api/public/demo/turf/").status_code == 200


def test_demo_qr_points_only_to_the_customer_demo_page():
    class FakeQr:
        def save(self, output, **kwargs):
            output.write(b"<svg>simulated-demo-qr</svg>")

    with patch("apps.demo.views.segno.make", return_value=FakeQr()) as make_qr:
        response = visitor().get("/api/public/demo/qr.svg")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    make_qr.assert_called_once()
    assert make_qr.call_args.args[0].endswith("/demo-booking")
