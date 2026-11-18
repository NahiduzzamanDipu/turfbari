"""GET /api/live/ — the change version the web app polls for live updates."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .test_core import PASSWORD, client_for, make_turf, tomorrow_at

pytestmark = pytest.mark.django_db


def request_slot(turf, hour):
    payload = {
        "field": str(turf.fields.first().id),
        "start": tomorrow_at(hour).isoformat(),
        "end": tomorrow_at(hour + 1).isoformat(),
        "name": "Online Player",
        "phone": "+880 1912-345678",
    }
    r = APIClient().post(f"/api/public/turfs/{turf.slug}/book/", payload, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def test_workspace_version_changes_when_a_request_arrives():
    turf, owner = make_turf()
    client = client_for(owner)
    before = client.get("/api/live/").json()
    assert before["scope"] == "workspace" and before["pending_requests"] == 0
    assert before["latest_request"] is None
    assert client.get("/api/live/").json()["version"] == before["version"]  # stable when idle

    booking = request_slot(turf, 18)
    after = client.get("/api/live/").json()
    assert after["version"] != before["version"]
    assert after["pending_requests"] == 1
    assert after["latest_request"]["reference"] == booking["reference"]


def test_other_turfs_do_not_change_my_version():
    turf, owner = make_turf()
    other, _ = make_turf(name="Beta Turf", email="beta@example.com")
    client = client_for(owner)
    before = client.get("/api/live/").json()["version"]
    request_slot(other, 18)
    assert client.get("/api/live/").json()["version"] == before


def test_admin_scope_counts_pending_work():
    get_user_model().objects.create_superuser("boss@example.com", PASSWORD)
    admin = get_user_model().objects.get(email="boss@example.com")
    client = client_for(admin)
    data = client.get("/api/live/?area=admin").json()
    assert data["scope"] == "admin"
    assert {"pending_applications", "pending_payments", "version"} <= data.keys()


def test_owner_cannot_read_admin_scope_and_anonymous_is_refused():
    turf, owner = make_turf()
    assert client_for(owner).get("/api/live/?area=admin").json()["scope"] == "workspace"
    assert APIClient().get("/api/live/").status_code in (401, 403)
