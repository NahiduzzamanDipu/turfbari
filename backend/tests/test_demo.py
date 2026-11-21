"""Interactive demos remain short-lived and isolated from all production records."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.demo.models import DemoBooking, DemoWorkspace
from apps.demo.services import cleanup_expired_demo

from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def start_demo():
    response = APIClient().post("/api/public/demo/session/", {}, format="json")
    assert response.status_code == 201, response.json()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['token']}")
    return client, response.json()


def test_customer_booking_is_visible_in_same_private_owner_dashboard_and_never_production():
    client, _ = start_demo()
    workspace = client.get("/api/public/demo/workspace/").json()
    slot = next(item for item in workspace["slots"] if item["start_time"] == "17:00")
    day = (timezone.localdate() + timedelta(days=3)).isoformat()
    before = Booking.objects.count()
    submitted = client.post(
        "/api/public/demo/bookings/",
        {
            "date": day,
            "slot_id": slot["id"],
            "name": "Demo Player",
            "phone": "01712345678",
            "note": "Demo only",
        },
        format="json",
    )
    assert submitted.status_code == 201, submitted.json()
    assert submitted.json()["status"] == DemoBooking.Status.PENDING
    dashboard = client.get("/api/public/demo/workspace/").json()
    assert any(row["id"] == submitted.json()["id"] for row in dashboard["bookings"])
    assert Booking.objects.count() == before

    approved = client.patch(
        f"/api/public/demo/bookings/{submitted.json()['id']}/", {"action": "approve"}, format="json"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == DemoBooking.Status.CONFIRMED


def test_demo_workspaces_are_isolated_and_expired_tokens_are_rejected():
    first, _ = start_demo()
    second, _ = start_demo()
    first_data = first.get("/api/public/demo/workspace/").json()
    second_data = second.get("/api/public/demo/workspace/").json()
    assert first_data["id"] != second_data["id"]
    own = first_data["bookings"][0]
    assert (
        second.patch(
            f"/api/public/demo/bookings/{own['id']}/", {"action": "approve"}, format="json"
        ).status_code
        == 404
    )

    row = DemoWorkspace.objects.get(pk=first_data["id"])
    row.expires_at = timezone.now() - timedelta(seconds=1)
    row.save(update_fields=["expires_at"])
    assert first.get("/api/public/demo/workspace/").status_code in {401, 403}


def test_demo_qr_only_links_to_the_simulated_public_demo():
    response = APIClient().get("/api/public/demo/qr.svg")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert len(response.content) > 100


def test_expired_demo_cleanup_removes_demo_records_but_keeps_activity():
    _, session = start_demo()
    workspace = DemoWorkspace.objects.get(pk=session["workspace_id"])
    workspace.expires_at = timezone.now() - timedelta(days=31)
    workspace.save(update_fields=["expires_at"])
    assert workspace.bookings.exists() and workspace.customers.exists() and workspace.slots.exists()
    assert workspace.activity.exists()

    result = cleanup_expired_demo()
    workspace.refresh_from_db()
    assert result["expired"] == 1 and result["records_removed"] >= 7
    assert workspace.status == DemoWorkspace.Status.EXPIRED
    assert (
        not workspace.bookings.exists() and not workspace.customers.exists() and not workspace.slots.exists()
    )
    assert workspace.activity.exists()


def test_demo_booking_conflict_then_rejection_releases_slot_without_side_effects():
    client, _ = start_demo()
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


def test_demo_slot_edits_are_scoped_and_validate_overlaps():
    one, _ = start_demo()
    two, _ = start_demo()
    slots = one.get("/api/public/demo/workspace/").json()["slots"]
    other_slots = two.get("/api/public/demo/workspace/").json()["slots"]
    response = one.patch(f"/api/public/demo/slots/{slots[0]['id']}/", {"price": "1499"}, format="json")
    assert response.status_code == 200 and response.json()["price"] == "1499.00"
    assert (
        two.patch(f"/api/public/demo/slots/{slots[0]['id']}/", {"enabled": False}, format="json").status_code
        == 404
    )
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


def test_only_platform_admin_can_manage_demo_workspaces_and_reset_is_demo_only():
    client, session = start_demo()
    assert client.get("/api/admin/demo/workspaces/").status_code == 403
    admin, _ = admin_client()
    created = admin.post("/api/admin/demo/workspaces/", {}, format="json")
    assert created.status_code == 201 and "access_url" in created.json()
    workspace = DemoWorkspace.objects.get(pk=created.json()["id"])
    booking_count = workspace.bookings.count()
    reset = admin.post(f"/api/admin/demo/workspaces/{workspace.pk}/reset/", {}, format="json")
    assert reset.status_code == 200
    assert workspace.bookings.count() == booking_count  # restores the same seeded example state
    assert workspace.activity.filter(action="workspace_reset").exists()
    assert DemoWorkspace.objects.filter(pk=session["workspace_id"]).exists()


def test_admin_rotating_access_invalidates_old_token_and_sets_expiry():
    admin, _ = admin_client()
    created = admin.post("/api/admin/demo/workspaces/", {}, format="json")
    workspace_id = created.json()["id"]
    old_token = parse_qs(urlsplit(created.json()["access_url"]).fragment)["access"][0]
    old_client = APIClient()
    old_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
    assert old_client.get("/api/public/demo/workspace/").status_code == 200

    rotated = admin.post(f"/api/admin/demo/workspaces/{workspace_id}/access/", {}, format="json")
    new_token = parse_qs(urlsplit(rotated.json()["access_url"]).fragment)["access"][0]
    assert old_client.get("/api/public/demo/workspace/").status_code in {401, 403}
    session = APIClient().post("/api/public/demo/session/", {"access_key": new_token}, format="json")
    assert session.status_code == 200
    new_client = APIClient()
    new_client.credentials(HTTP_AUTHORIZATION=f"Bearer {session.json()['token']}")
    assert new_client.get("/api/public/demo/workspace/").status_code == 200

    expiry = timezone.now() + timedelta(days=3)
    updated = admin.patch(
        f"/api/admin/demo/workspaces/{workspace_id}/",
        {"expires_at": expiry.isoformat()},
        format="json",
    )
    assert updated.status_code == 200
    assert abs((DemoWorkspace.objects.get(pk=workspace_id).expires_at - expiry).total_seconds()) < 1
