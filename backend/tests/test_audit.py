"""Audit log: key actions are recorded, owners see only their turf, admins see everything."""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.subscriptions.models import Plan
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, bkash, booking_payload, client_for, make_turf, tomorrow_at

pytestmark = pytest.mark.django_db


def actions(turf=None):
    qs = AuditEvent.objects.all() if turf is None else AuditEvent.objects.filter(turf=turf)
    return list(qs.order_by("created_at").values_list("action", flat=True))


def test_booking_lifecycle_is_recorded_with_who_and_what():
    turf, owner = make_turf()
    client = client_for(owner)
    payload = {**booking_payload(turf.fields.first().id), "team_name": "Banani FC", "discount": "100.00"}
    booking = client.post("/api/workspace/bookings/", payload, format="json").json()
    client.post(f"/api/workspace/bookings/{booking['id']}/payments/", {"amount": "200.00"}, format="json")
    client.post(f"/api/workspace/bookings/{booking['id']}/status/", {"status": "cancelled"}, format="json")

    assert actions(turf) == ["booking.created", "payment.recorded", "booking.status"]
    created, paid, status = AuditEvent.objects.filter(turf=turf).order_by("created_at")
    assert created.actor == owner and created.actor_label == owner.full_name
    assert "Banani FC" in created.summary and "discount ৳100.00" in created.summary
    assert "advance ৳300.00" in created.summary
    assert paid.summary.startswith("Received ৳200.00") and paid.category == "payment"
    assert status.summary.startswith("Confirmed → Cancelled")
    assert created.ip == "127.0.0.1"


def test_public_request_has_no_actor():
    turf, _ = make_turf()
    field = turf.fields.first()
    APIClient().post(
        f"/api/public/turfs/{turf.slug}/book/",
        {
            "field": str(field.id),
            "start": tomorrow_at(18).isoformat(),
            "end": tomorrow_at(19).isoformat(),
            "name": "Rafi",
            "phone": "01812345678",
            **bkash(),
        },
        format="json",
    )
    event = AuditEvent.objects.get(action="booking.requested")
    assert event.actor is None and event.turf == turf and "waiting for verification" in event.summary


def test_setup_settings_team_and_auto_crud_events():
    turf, owner = make_turf()
    client = client_for(owner)
    field = client.post(
        "/api/workspace/fields/",
        {"name": "Field 9", "slot_minutes": 60, "default_hourly_rate": "900"},
        format="json",
    ).json()
    client.patch(f"/api/workspace/fields/{field['id']}/", {"default_hourly_rate": "950"}, format="json")
    client.delete(f"/api/workspace/fields/{field['id']}/")
    client.patch(
        "/api/workspace/settings/", {"short_description": "New text", "name": turf.name}, format="json"
    )
    client.patch("/api/workspace/settings/", {"short_description": "New text"}, format="json")  # no change
    manager = client.post(
        "/api/workspace/managers/",
        {"email": "mgr@example.com", "full_name": "Mina", "phone": "01812345678"},
        format="json",
    ).json()
    client.delete(f"/api/workspace/managers/{manager['id']}/")

    assert actions(turf) == [
        "field.added",
        "field.updated",
        "field.deleted",
        "settings.updated",
        "team.manager_added",
        "account.temporary_password_issued",  # the new manager's login details went out by SMS
        "team.manager_removed",
    ]
    settings_event = AuditEvent.objects.get(action="settings.updated")
    assert settings_event.data["fields"] == ["short_description"]  # unchanged name not listed
    assert AuditEvent.objects.get(action="field.deleted").summary == "Deleted field “Field 9”"


def test_owner_reads_own_activity_managers_cannot_and_tenants_are_isolated():
    turf, owner = make_turf()
    other, other_owner = make_turf("Other", "other@example.com")
    record("x.one", "Alpha event", category="booking", turf=turf)
    record("x.two", "Beta event", category="booking", turf=other)
    record("platform.x", "Admin-only", category="platform", turf=turf)

    rows = client_for(owner).get("/api/workspace/activity/").json()["results"]
    assert [r["summary"] for r in rows] == ["Alpha event"]  # no other turf, no platform rows

    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=turf, role=TenantMembership.Role.MANAGER)
    assert client_for(manager).get("/api/workspace/activity/").status_code == 403

    filtered = client_for(owner).get("/api/workspace/activity/?category=payment").json()["results"]
    assert filtered == []
    assert client_for(owner).get("/api/workspace/activity/?from=bad").status_code == 400


def test_admin_sees_all_with_filters_and_platform_actions_logged():
    turf, _ = make_turf()
    admin = get_user_model().objects.create_superuser("boss@example.com", PASSWORD)
    client = client_for(admin)
    client.patch(f"/api/admin/turfs/{turf.id}/", {"status": "suspended"}, format="json")
    client.post(f"/api/admin/turfs/{turf.id}/assign-plan/", {"plan": "yearly", "paid": True}, format="json")
    monthly = Plan.objects.get(period="monthly")
    client.patch(f"/api/admin/plans/{monthly.id}/", {"price": "1600.00"}, format="json")

    rows = client.get("/api/admin/audit/").json()["results"]
    by_action = {r["action"]: r for r in rows}
    assert "status: active → suspended" in by_action["platform.turf_updated"]["summary"]
    assert by_action["subscription.plan_assigned"]["turf_name"] == turf.name
    assert "৳1600.00" in by_action["platform.plan_updated"]["summary"]
    only_turf = client.get(f"/api/admin/audit/?turf={turf.id}").json()["results"]
    assert {r["action"] for r in only_turf} == {"platform.turf_updated", "subscription.plan_assigned"}
    assert client_for(make_turf("X", "x@example.com")[1]).get("/api/admin/audit/").status_code == 403


def test_sign_in_events():
    turf, owner = make_turf()
    APIClient().post("/api/auth/login/", {"identifier": owner.email, "password": "wrong"}, format="json")
    APIClient().post("/api/auth/login/", {"identifier": owner.email, "password": PASSWORD}, format="json")
    failed = AuditEvent.objects.get(action="account.login_failed")
    assert failed.turf is None and owner.email in failed.summary
    ok = AuditEvent.objects.get(action="account.login")
    assert ok.actor == owner and ok.turf == turf


def test_audit_failure_never_breaks_the_action():
    turf, owner = make_turf()
    with mock.patch("apps.audit.services.AuditEvent.objects.create", side_effect=RuntimeError("db down")):
        response = client_for(owner).post(
            "/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json"
        )
    assert response.status_code == 201


def test_client_ip_only_trusts_x_real_ip_when_configured(settings):
    from django.test import RequestFactory

    from apps.audit.services import client_ip

    request = RequestFactory().get("/", HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR="6.6.6.6")
    settings.TRUST_X_REAL_IP = False
    assert client_ip(request) == "127.0.0.1"  # spoofable headers ignored by default
    settings.TRUST_X_REAL_IP = True
    assert client_ip(request) == "203.0.113.7"
