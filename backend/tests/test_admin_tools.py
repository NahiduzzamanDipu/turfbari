"""Super Admin subscription tools (overview, extend, end now, history) and the health page."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.subscriptions.models import Subscription
from apps.subscriptions.services import standing

from .test_core import client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def set_end(turf, days_from_today):
    sub = Subscription.objects.get(turf=turf, status="active")
    sub.ends_on = timezone.localdate() + timedelta(days=days_from_today)
    sub.save()
    return sub


def test_overview_filters_expiring_and_counts_states():
    soon, _ = make_turf("Soon Turf", "soon@example.com")
    later, _ = make_turf("Later Turf", "later@example.com")
    set_end(soon, 5)
    set_end(later, 60)
    admin, _ = admin_client()
    body = admin.get("/api/admin/subscriptions/", {"ending_within": 7}).json()
    assert [r["turf"]["name"] for r in body["results"]] == ["Soon Turf"]
    assert body["results"][0]["owner"]["email"] == "soon@example.com"
    assert body["counts"]["expiring"] == 1 and body["counts"]["active"] == 1


def test_extend_needs_a_reason_and_is_audited():
    turf, _ = make_turf()
    sub = set_end(turf, 2)
    admin, _ = admin_client()
    assert (
        admin.post(
            f"/api/admin/turfs/{turf.id}/extend-subscription/", {"days": 10}, format="json"
        ).status_code
        == 400
    )
    r = admin.post(
        f"/api/admin/turfs/{turf.id}/extend-subscription/",
        {"days": 10, "reason": "Rain damage week"},
        format="json",
    )
    assert r.status_code == 200 and r.json()["days_left"] == 12
    sub.refresh_from_db()
    assert "Rain damage week" in sub.note
    assert AuditEvent.objects.filter(action="subscription.extended", turf=turf).exists()


def test_extend_after_expiry_gives_complimentary_days():
    turf, _ = make_turf()
    set_end(turf, -30)
    admin, _ = admin_client()
    r = admin.post(
        f"/api/admin/turfs/{turf.id}/extend-subscription/",
        {"days": 7, "reason": "Launch promotion"},
        format="json",
    )
    assert r.json()["state"] in ("active", "expiring") and standing(turf).can_operate


def test_end_now_stops_the_turf_and_history_shows_it():
    turf, _ = make_turf()
    set_end(turf, 40)
    admin, _ = admin_client()
    r = admin.post(
        f"/api/admin/turfs/{turf.id}/end-subscription/", {"reason": "Chargeback on payment"}, format="json"
    )
    assert r.status_code == 200 and r.json()["state"] in ("expired", "none")
    assert not standing(turf).can_operate
    assert APIClient().get(f"/api/public/turfs/{turf.slug}/").status_code == 404  # booking page closed
    history = admin.get(f"/api/admin/turfs/{turf.id}/subscription-history/").json()
    assert history["periods"] and any("Chargeback" in e["summary"] for e in history["events"])


def test_health_reports_without_secrets_and_is_admin_only():
    turf, owner = make_turf()
    admin, _ = admin_client()
    body = admin.get("/api/admin/health/").json()
    assert body["database"] is True and body["cache"] is True
    assert body["config"]["sms_provider"] == "memory" and body["config"]["tick_endpoint"] is True
    assert any("never run" in p for p in body["problems"])  # no tick yet in this test
    APIClient().post("/api/system/tick/?force=1", HTTP_X_TICK_TOKEN="test-tick-token")
    after = admin.get("/api/admin/health/").json()
    assert after["tick"]["minutes_ago"] == 0
    text = str(after)
    assert "test-tick-token" not in text and "SECRET" not in text
    assert client_for(owner).get("/api/admin/health/").status_code == 403
