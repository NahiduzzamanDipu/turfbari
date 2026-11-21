"""The public demo persists in one demo-only workspace shared by all visitors."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.demo.models import DemoActivity, DemoBooking, DemoWorkspace
from apps.demo.services import get_public_workspace

from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def visitor():
    return APIClient()


def test_booking_persists_and_is_shared_across_independent_visitors_without_production_effects():
    customer = visitor()
    owner = visitor()
    data = customer.get("/api/public/demo/workspace/").json()
    slot = next(item for item in data["slots"] if item["start_time"] == "17:00")
    day = (timezone.localdate() + timedelta(days=3)).isoformat()
    before = Booking.objects.count()
    submitted = customer.post(
        "/api/public/demo/bookings/",
        {
            "date": day,
            "slot_id": slot["id"],
            "name": "Demo Player",
            "phone": "01712345678",
            "note": "Do not retain my private details",
        },
        format="json",
    )
    assert submitted.status_code == 201, submitted.json()
    assert submitted.json()["status"] == DemoBooking.Status.PENDING
    assert submitted.json()["customer_phone"] == "+8801*****5678"
    assert submitted.json()["note"] == ""
    dashboard = owner.get("/api/public/demo/workspace/").json()
    assert dashboard["id"] == data["id"]
    assert any(row["id"] == submitted.json()["id"] for row in dashboard["bookings"])
    assert Booking.objects.count() == before
    assert not data.get("expires_at")

    approved = owner.patch(
        f"/api/public/demo/bookings/{submitted.json()['id']}/", {"action": "approve"}, format="json"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == DemoBooking.Status.CONFIRMED
    assert customer.get("/api/public/demo/workspace/").json()["bookings"][-1]["status"] == "confirmed"


def test_demo_data_is_permanent_and_there_is_no_session_or_cleanup_endpoint():
    client = visitor()
    first = client.get("/api/public/demo/workspace/").json()
    assert first["id"] == visitor().get("/api/public/demo/workspace/").json()["id"]
    assert client.post("/api/public/demo/session/", {}, format="json").status_code == 404
    assert not hasattr(DemoWorkspace, "expires_at")
    assert not hasattr(DemoWorkspace, "access_token_hash")


def test_demo_qr_only_links_to_the_simulated_public_demo():
    response = visitor().get("/api/public/demo/qr.svg")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert len(response.content) > 100


def test_disabled_public_demo_is_unavailable_and_admin_can_reenable_it():
    workspace = get_public_workspace()
    admin, _ = admin_client()
    response = admin.patch(
        f"/api/admin/demo/workspaces/{workspace.pk}/", {"status": "disabled"}, format="json"
    )
    assert response.status_code == 200
    assert visitor().get("/api/public/demo/workspace/").status_code == 404
    enabled = admin.patch(f"/api/admin/demo/workspaces/{workspace.pk}/", {"status": "active"}, format="json")
    assert enabled.status_code == 200
    assert visitor().get("/api/public/demo/workspace/").status_code == 200


def test_booking_conflict_then_rejection_releases_slot_without_side_effects():
    client = visitor()
    data = client.get("/api/public/demo/workspace/").json()
    slot = next(item for item in data["slots"] if item["start_time"] == "17:00")
    day = (timezone.localdate() + timedelta(days=4)).isoformat()
    payload = {"date": day, "slot_id": slot["id"], "name": "A Player", "phone": "01812345678"}
    one = client.post("/api/public/demo/bookings/", payload, format="json")
    assert one.status_code == 201
    assert client.post("/api/public/demo/bookings/", payload, format="json").status_code == 409
    assert (
        client.patch(
            f"/api/public/demo/bookings/{one.json()['id']}/", {"action": "reject"}, format="json"
        ).status_code
        == 200
    )
    payload["phone"] = "01912345678"
    assert client.post("/api/public/demo/bookings/", payload, format="json").status_code == 201


def test_demo_slot_edits_are_shared_and_validate_overlaps():
    one, two = visitor(), visitor()
    slots = one.get("/api/public/demo/workspace/").json()["slots"]
    other_slots = two.get("/api/public/demo/workspace/").json()["slots"]
    response = one.patch(f"/api/public/demo/slots/{slots[0]['id']}/", {"price": "1499"}, format="json")
    assert response.status_code == 200 and response.json()["price"] == "1499.00"
    assert two.get("/api/public/demo/workspace/").json()["slots"][0]["price"] == "1499.00"
    overlap = one.post(
        "/api/public/demo/slots/",
        {
            "label": "Overlap",
            "start_time": "08:30",
            "end_time": "09:30",
            "category": "morning",
            "price": "500",
        },
        format="json",
    )
    assert overlap.status_code == 400
    assert len(other_slots) == len(slots)


def test_only_platform_admin_can_manage_or_reset_shared_demo_and_reset_is_audited():
    workspace = get_public_workspace()
    guest = visitor()
    assert guest.get("/api/admin/demo/workspaces/").status_code == 403
    assert guest.post(f"/api/admin/demo/workspaces/{workspace.pk}/reset/").status_code == 403
    admin, _ = admin_client()
    assert guest.post("/api/admin/demo/workspaces/", {}, format="json").status_code == 403
    booking_count = workspace.bookings.count()
    reset = admin.post(f"/api/admin/demo/workspaces/{workspace.pk}/reset/", {}, format="json")
    assert reset.status_code == 200
    workspace.refresh_from_db()
    assert workspace.bookings.count() == booking_count
    assert workspace.reset_count == 1
    assert DemoActivity.objects.filter(
        workspace=workspace, action="workspace_reset", actor_type="admin"
    ).exists()


def test_public_customer_number_is_never_stored_in_full():
    client = visitor()
    data = client.get("/api/public/demo/workspace/").json()
    slot = next(item for item in data["slots"] if item["start_time"] == "17:00")
    posted = client.post(
        "/api/public/demo/bookings/",
        {
            "date": (timezone.localdate() + timedelta(days=5)).isoformat(),
            "slot_id": slot["id"],
            "name": "Shared Visitor",
            "phone": "01987654321",
        },
        format="json",
    )
    assert posted.status_code == 201
    assert posted.json()["customer_phone"] == "+8801*****4321"
    assert "01987654321" not in str(client.get("/api/public/demo/workspace/").json())
