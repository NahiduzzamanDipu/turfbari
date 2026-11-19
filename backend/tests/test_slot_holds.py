"""10-minute slot holds on the public booking page and the cooldown after a lapsed hold."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, SlotHold

from .test_core import make_turf, tomorrow_at

pytestmark = pytest.mark.django_db


@pytest.fixture
def turf():
    turf, _ = make_turf()
    return turf


def visitor(ip):
    return APIClient(REMOTE_ADDR=ip)


def slot(turf, hour, hours=1):
    return {
        "field": str(turf.fields.first().id),
        "start": tomorrow_at(hour).isoformat(),
        "end": tomorrow_at(hour + hours).isoformat(),
    }


def hold(client, turf, hour, token=None, hours=1):
    body = slot(turf, hour, hours) | ({"token": token} if token else {})
    return client.post(f"/api/public/turfs/{turf.slug}/hold/", body, format="json")


def states(client, turf, token=None):
    field = turf.fields.first().id
    headers = {"HTTP_X_HOLD_TOKEN": token} if token else {}
    data = client.get(
        f"/api/public/turfs/{turf.slug}/availability/?field={field}&date={tomorrow_at(0).date()}", **headers
    ).json()
    by_hour = {s["start"][11:13]: s["state"] for s in data["slots"]}
    return by_hour, data


def request_booking(client, turf, hour, token=None):
    body = slot(turf, hour) | {"name": "Player", "phone": "01912345678"}
    if token:
        body["hold_token"] = token
    return client.post(f"/api/public/turfs/{turf.slug}/book/", body, format="json")


def test_held_slot_shows_as_being_booked_to_others_and_converts_on_request(turf):
    a, b = visitor("10.0.0.1"), visitor("10.0.0.2")
    r = hold(a, turf, 18)
    assert r.status_code == 201, r.json()
    token = r.json()["token"]

    assert states(a, turf, token)[0]["18"] == "yours"
    others, data = states(b, turf)
    assert others["18"] == "held" and data["my_hold"] is None

    assert hold(b, turf, 18).status_code == 409
    assert request_booking(b, turf, 18).status_code == 400

    booked = request_booking(a, turf, 18, token)
    assert booked.status_code == 201, booked.json()
    assert SlotHold.objects.get(token=token).status == SlotHold.Status.CONVERTED
    assert states(b, turf)[0]["18"] == "requested"


def test_lapsed_hold_frees_the_slot_and_cools_down_that_ip(turf):
    a, b = visitor("10.0.0.1"), visitor("10.0.0.2")
    token = hold(a, turf, 18).json()["token"]
    SlotHold.objects.filter(token=token).update(expires_at=timezone.now() - timedelta(seconds=1))

    assert states(b, turf)[0]["18"] == "free"
    _, mine = states(a, turf)
    assert mine["cooldown_until"] is not None
    refused = hold(a, turf, 20)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "hold_cooldown"
    assert hold(b, turf, 18).status_code == 201  # others are not affected

    SlotHold.objects.filter(token=token).update(expires_at=timezone.now() - timedelta(minutes=11))
    assert hold(a, turf, 20).status_code == 201


def test_switching_and_releasing_are_free(turf):
    a, b = visitor("10.0.0.1"), visitor("10.0.0.2")
    first = hold(a, turf, 18).json()["token"]
    hold(a, turf, 20)  # picked another slot
    assert SlotHold.objects.get(token=first).status == SlotHold.Status.RELEASED
    assert states(b, turf)[0]["18"] == "free"

    second = SlotHold.objects.get(status=SlotHold.Status.ACTIVE).token
    assert (
        visitor("10.0.0.1")
        .delete(f"/api/public/turfs/{turf.slug}/hold/", HTTP_X_HOLD_TOKEN=second)
        .status_code
        == 204
    )
    assert states(b, turf)[0]["20"] == "free"
    assert hold(a, turf, 21).status_code == 201  # no cooldown after a release


def test_extending_keeps_the_same_clock(turf):
    a = visitor("10.0.0.1")
    first = hold(a, turf, 18).json()
    extended = hold(a, turf, 18, token=first["token"], hours=2).json()
    assert extended["token"] == first["token"]
    assert extended["expires_at"] == first["expires_at"]
    assert extended["end"].startswith(tomorrow_at(20).isoformat()[:16])


def test_release_and_retake_cannot_restart_the_ten_minutes(turf):
    a = visitor("10.0.0.1")
    first = hold(a, turf, 18).json()
    a.delete(f"/api/public/turfs/{turf.slug}/hold/", HTTP_X_HOLD_TOKEN=first["token"])
    again = hold(a, turf, 18).json()
    assert again["expires_at"] == first["expires_at"]

    SlotHold.objects.filter(token=again["token"]).update(status=SlotHold.Status.RELEASED)
    SlotHold.objects.update(window_started_at=timezone.now() - timedelta(minutes=10, seconds=5))
    refused = hold(a, turf, 18)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "hold_cooldown"


def test_booking_without_a_hold_still_works(turf):
    r = request_booking(visitor("10.0.0.3"), turf, 19)
    assert r.status_code == 201
    assert Booking.objects.get(reference=r.json()["reference"]).status == Booking.Status.PENDING


def test_client_ip_header_is_used_when_configured(settings):
    from django.test import RequestFactory

    from apps.audit.services import client_ip

    request = RequestFactory().get("/", REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="203.0.113.9")
    assert client_ip(request) == "127.0.0.1"
    settings.CLIENT_IP_HEADER = "HTTP_CF_CONNECTING_IP"
    assert client_ip(request) == "203.0.113.9"
