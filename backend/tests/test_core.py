"""Core behaviour: pricing, booking overlap safety, tenant isolation, roles, public API, onboarding."""

import itertools
import threading
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import TurfApplication
from apps.applications.services import create_turf_with_owner
from apps.bookings.models import Booking
from apps.bookings.services import SlotUnavailable, get_or_create_customer, reserve_slot
from apps.locations.models import District
from apps.turfs.models import PricingRule, TenantMembership, Turf
from apps.turfs.pricing import local_dt, quote

pytestmark = pytest.mark.django_db
PASSWORD = "a-strong-pass-123"
_trx = itertools.count(1)


def bkash(amount="500", sender="01712345678") -> dict:
    """The bKash advance fields every public booking request now carries (unique TrxID each call)."""
    return {"payment_amount": amount, "bkash_sender": sender, "trx_id": f"TEST{next(_trx):06d}"}


def make_turf(name="Alpha Turf", email="alpha@example.com", listed=True):
    turf, owner, _ = create_turf_with_owner(
        name=name,
        district=District.objects.get(slug="dhaka"),
        area=None,
        address="Road 1",
        turf_type="outdoor",
        owner_email=email,
        owner_name="Owner",
        owner_phone="+8801711000000",
        number_of_fields=2,
        hourly_rate=Decimal("1000.00"),
    )
    owner.set_password(PASSWORD)
    owner.must_change_password = False  # tests sign in as an owner who already chose a password
    owner.save()
    turf.is_listed = listed
    turf.bkash_number = "01711000000"
    turf.save()
    return turf, owner


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def tomorrow_at(hour, minute=0):
    return local_dt(timezone.localdate() + timedelta(days=1), time(hour, minute))


@pytest.fixture
def alpha():
    return make_turf()


@pytest.fixture
def beta():
    return make_turf("Beta Turf", "beta@example.com")


# ------------------------------------------------------------------ pricing
def test_quote_splits_across_peak_boundary(alpha):
    turf, _ = alpha
    field = turf.fields.first()
    PricingRule.objects.create(
        turf=turf, label="Peak", start_time=time(18), end_time=time(23), hourly_rate=Decimal("2000.00")
    )
    q = quote(field, tomorrow_at(17), tomorrow_at(19))
    assert q.subtotal == Decimal("3000.00")  # 1h standard 1000 + 1h peak 2000
    assert [s["label"] for s in q.segments] == ["Standard", "Peak"]


def test_special_date_rule_beats_priority(alpha):
    turf, _ = alpha
    field = turf.fields.first()
    day = timezone.localdate() + timedelta(days=1)
    PricingRule.objects.create(
        turf=turf,
        label="Peak",
        start_time=time(0),
        end_time=time(0),
        hourly_rate=Decimal("2000"),
        priority=99,
    )
    PricingRule.objects.create(
        turf=turf, label="Eid", date=day, start_time=time(0), end_time=time(0), hourly_rate=Decimal("500")
    )
    assert quote(field, tomorrow_at(10), tomorrow_at(11)).subtotal == Decimal("500.00")


# ------------------------------------------------------------------ booking safety
def test_overlapping_booking_rejected_adjacent_allowed(alpha):
    turf, _ = alpha
    field = turf.fields.first()
    customer = get_or_create_customer(turf, name="A", phone="01712345678")
    reserve_slot(turf=turf, field_id=field.id, start=tomorrow_at(18), end=tomorrow_at(19), customer=customer)
    with pytest.raises(SlotUnavailable):
        reserve_slot(
            turf=turf,
            field_id=field.id,
            start=tomorrow_at(18, 30),
            end=tomorrow_at(19, 30),
            customer=customer,
        )
    reserve_slot(turf=turf, field_id=field.id, start=tomorrow_at(19), end=tomorrow_at(20), customer=customer)


def test_cancelled_booking_frees_slot(alpha):
    turf, owner = alpha
    field = turf.fields.first()
    customer = get_or_create_customer(turf, name="A", phone="01712345678")
    b = reserve_slot(
        turf=turf, field_id=field.id, start=tomorrow_at(18), end=tomorrow_at(19), customer=customer
    )
    client_for(owner).post(f"/api/workspace/bookings/{b.id}/status/", {"status": "cancelled"}, format="json")
    reserve_slot(turf=turf, field_id=field.id, start=tomorrow_at(18), end=tomorrow_at(19), customer=customer)


@pytest.mark.django_db(transaction=True)
def test_concurrent_requests_cannot_double_book():
    turf, _ = make_turf("Race Turf", "race@example.com")
    field = turf.fields.first()
    customer = get_or_create_customer(turf, name="A", phone="01712345678")
    barrier = threading.Barrier(4)
    results = []

    def attempt():
        try:
            barrier.wait()
            reserve_slot(
                turf=turf, field_id=field.id, start=tomorrow_at(20), end=tomorrow_at(21), customer=customer
            )
            results.append("ok")
        except SlotUnavailable:
            results.append("clash")
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1
    assert Booking.objects.filter(field=field).count() == 1


# ------------------------------------------------------------------ workspace
def booking_payload(field_id, start_hour=18):
    return {
        "field": str(field_id),
        "start": tomorrow_at(start_hour).isoformat(),
        "end": tomorrow_at(start_hour + 1).isoformat(),
        "customer_name": "Walk In",
        "customer_phone": "01812345678",
        "advance_amount": "300.00",
        "advance_method": "bkash",
    }


def test_owner_creates_booking_with_advance(alpha):
    turf, owner = alpha
    response = client_for(owner).post(
        "/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json"
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (
        body["total"] == "1000.00" and body["amount_paid"] == "300.00" and body["payment_status"] == "partial"
    )
    assert body["customer"]["phone"] == "+8801812345678"


def test_cross_tenant_ids_are_invisible(alpha, beta):
    turf_a, owner_a = alpha
    turf_b, owner_b = beta
    client_b = client_for(owner_b)
    created = client_for(owner_a).post(
        "/api/workspace/bookings/", booking_payload(turf_a.fields.first().id), format="json"
    )
    booking_id = created.json()["id"]
    assert client_b.get(f"/api/workspace/bookings/{booking_id}/").status_code == 404
    assert (
        client_b.post(f"/api/workspace/bookings/{booking_id}/status/", {"status": "cancelled"}).status_code
        == 404
    )
    # Using another tenant's field id is rejected as unknown.
    response = client_b.post(
        "/api/workspace/bookings/", booking_payload(turf_a.fields.first().id), format="json"
    )
    assert response.status_code == 400 and "field" in response.json()["error"]["fields"]
    assert client_b.get("/api/workspace/bookings/").json()["count"] == 0
    field_a = turf_a.fields.first()
    assert (
        client_b.patch(f"/api/workspace/fields/{field_a.id}/", {"name": "X"}, format="json").status_code
        == 404
    )


def test_manager_permissions(alpha):
    turf, _ = alpha
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=turf, role="manager")
    client = client_for(manager)
    assert client.get("/api/workspace/dashboard/").status_code == 200
    assert (
        client.post(
            "/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json"
        ).status_code
        == 201
    )
    assert client.get("/api/workspace/expenses/").status_code == 403
    assert client.get("/api/workspace/reports/summary/").status_code == 403
    assert client.get("/api/workspace/fields/").status_code == 200
    assert client.post("/api/workspace/fields/", {"name": "New"}, format="json").status_code == 403
    assert client.get("/api/workspace/managers/").status_code == 403


def test_non_member_and_anonymous_blocked(alpha):
    stranger = get_user_model().objects.create_user("x@example.com", PASSWORD)
    assert client_for(stranger).get("/api/workspace/dashboard/").status_code == 403
    assert APIClient().get("/api/workspace/dashboard/").status_code in (401, 403)


def test_suspended_turf_is_read_only(alpha):
    turf, owner = alpha
    turf.status = Turf.Status.SUSPENDED
    turf.save()
    client = client_for(owner)
    assert client.get("/api/workspace/bookings/").status_code == 200
    response = client.post("/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json")
    assert response.status_code == 403 and response.json()["error"]["code"] == "turf_suspended"


def test_reports_and_export(alpha):
    turf, owner = alpha
    client = client_for(owner)
    client.post("/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json")
    summary = client.get("/api/workspace/reports/summary/")
    assert summary.status_code == 200 and summary.json()["revenue"] == "300.00"
    assert summary.json()["daily"][-1]["revenue"] == "300.00"  # per-day grouping in Asia/Dhaka
    assert client.get("/api/workspace/dashboard/").json()["revenue_series"][-1]["revenue"] == "300.00"
    export = client.get("/api/workspace/reports/bookings.xlsx")
    assert export.status_code == 200 and export["Content-Type"].startswith("application/vnd.openxmlformats")


# ------------------------------------------------------------------ public
def test_no_public_directory_only_published_active_turf_pages(alpha, beta):
    make_turf("Hidden Turf", "hidden@example.com", listed=False)
    turf_b, _ = beta
    turf_b.status = Turf.Status.SUSPENDED
    turf_b.save()
    assert APIClient().get("/api/public/turfs/").status_code == 404  # the marketplace list is gone
    assert APIClient().get("/api/public/stats/").status_code == 404
    assert APIClient().get("/api/public/turfs/alpha-turf/").status_code == 200
    assert APIClient().get(f"/api/public/turfs/{turf_b.slug}/").status_code == 404
    assert APIClient().get("/api/public/turfs/hidden-turf/").status_code == 404


def test_owner_and_manager_download_their_own_qr(alpha):
    turf, owner = alpha
    client = client_for(owner)
    png = client.get("/api/workspace/booking-page/qr.png?download=1")
    assert png.status_code == 200 and png["Content-Type"] == "image/png"
    assert png.content[1:4] == b"PNG"
    assert "attachment" in png["Content-Disposition"]
    svg = client.get("/api/workspace/booking-page/qr.svg")
    assert svg.status_code == 200 and b"<svg" in svg.content
    assert client.get("/api/workspace/booking-page/qr.gif").status_code == 404
    assert APIClient().get("/api/workspace/booking-page/qr.png").status_code in (401, 403)


def test_public_detail_never_leaks_private_fields(alpha):
    body = APIClient().get("/api/public/turfs/alpha-turf/").json()
    for private in ("owner_name", "owner_phone", "contract_notes", "id", "status", "memberships"):
        assert private not in body
    assert len(body["fields_list"]) == 2


def test_public_booking_request_flow(alpha):
    turf, _ = alpha
    field = turf.fields.first()
    payload = {
        "field": str(field.id),
        "start": tomorrow_at(18).isoformat(),
        "end": tomorrow_at(19).isoformat(),
        "name": "Online Player",
        "phone": "+880 1912-345678",
        **bkash(),
    }
    client = APIClient()
    created = client.post("/api/public/turfs/alpha-turf/book/", payload, format="json")
    assert created.status_code == 201, created.json()
    assert created.json()["status"] == "pending"
    # Slot is now held.
    again = {**payload, **bkash()}
    assert client.post("/api/public/turfs/alpha-turf/book/", again, format="json").status_code == 400
    slots = client.get(
        f"/api/public/turfs/alpha-turf/availability/?field={field.id}&date={tomorrow_at(0).date()}"
    ).json()["slots"]
    held = next(s for s in slots if s["start"].startswith(tomorrow_at(18).isoformat()[:16]))
    assert held["available"] is False
    lookup = client.get(
        f"/api/public/bookings/lookup/?reference={created.json()['reference']}&phone=01912345678"
    )
    assert lookup.status_code == 200


def test_public_booking_honeypot_and_closed_hours(alpha):
    turf, _ = alpha
    field = turf.fields.first()
    base = {"field": str(field.id), "name": "Bot", "phone": "01912345678", **bkash()}
    bot = {**base, "start": tomorrow_at(18).isoformat(), "end": tomorrow_at(19).isoformat(), "website": "x"}
    assert APIClient().post("/api/public/turfs/alpha-turf/book/", bot, format="json").status_code == 400
    closed = {**base, "start": tomorrow_at(3).isoformat(), "end": tomorrow_at(4).isoformat()}
    assert APIClient().post("/api/public/turfs/alpha-turf/book/", closed, format="json").status_code == 400


# ------------------------------------------------------------------ onboarding & auth
def test_application_to_live_turf():
    response = APIClient().post(
        "/api/public/applications/",
        {
            "turf_name": "New Ground",
            "owner_name": "Sadia",
            "phone": "01755000010",
            "email": "sadia@example.com",
            "district": "dhaka",
            "address": "Road 5",
            "turf_type": "outdoor",
            "number_of_fields": 2,
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    application = TurfApplication.objects.get()
    owner_like = get_user_model().objects.create_user("notadmin@example.com", PASSWORD)
    assert (
        client_for(owner_like).post(f"/api/admin/applications/{application.id}/approve/").status_code == 403
    )

    admin = get_user_model().objects.create_superuser("root@example.com", PASSWORD)
    approved = client_for(admin).post(f"/api/admin/applications/{application.id}/approve/", {}, format="json")
    assert approved.status_code == 200, approved.json()
    password = approved.json()["temporary_password"]
    turf = Turf.objects.get(slug="new-ground")
    assert turf.fields.count() == 2 and turf.hours.count() == 7

    login = APIClient().post(
        "/api/auth/login/", {"identifier": "sadia@example.com", "password": password}, format="json"
    )
    assert login.status_code == 200 and login.json()["home"] == "/workspace"


def test_admin_login_goes_to_admin():
    get_user_model().objects.create_superuser("boss@example.com", PASSWORD)
    response = APIClient().post(
        "/api/auth/login/", {"identifier": "boss@example.com", "password": PASSWORD}, format="json"
    )
    assert response.json()["home"] == "/admin"
    bad = APIClient().post(
        "/api/auth/login/", {"identifier": "boss@example.com", "password": "nope"}, format="json"
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_credentials"
