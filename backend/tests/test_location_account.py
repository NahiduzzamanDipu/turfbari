"""Map links, "near me" search and self-service password change."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.turfs.geo import coords_from_maps_url, haversine_km, is_google_maps_url
from apps.turfs.models import TenantMembership, Turf

from .test_core import PASSWORD, client_for, make_turf

pytestmark = pytest.mark.django_db

MIRPUR = (Decimal("23.806900"), Decimal("90.368700"))
GULSHAN = (Decimal("23.794600"), Decimal("90.414300"))
CHATTOGRAM = (Decimal("22.325700"), Decimal("91.811300"))


def place(turf, coords):
    turf.latitude, turf.longitude = coords
    turf.save(update_fields=["latitude", "longitude"])
    return turf


# ------------------------------------------------------------------ geo helpers
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://www.google.com/maps/place/X/@23.80,90.36,17z/data=!3d23.8069!4d90.3687",
            ("23.806900", "90.368700"),
        ),
        ("https://www.google.com/maps/@23.7946,90.4143,15z", ("23.794600", "90.414300")),
        ("https://maps.google.com/?q=22.3257,91.8113", ("22.325700", "91.811300")),
        ("https://www.google.com/maps/search/?api=1&query=23.81%2C90.41", ("23.810000", "90.410000")),
        ("https://maps.app.goo.gl/AbCdEf123", None),
    ],
)
def test_coords_from_maps_url(url, expected):
    result = coords_from_maps_url(url)
    assert (tuple(str(v) for v in result) if result else None) == expected


def test_only_google_maps_links_accepted():
    assert is_google_maps_url("https://maps.app.goo.gl/AbC")
    assert is_google_maps_url("https://www.google.com/maps/place/x")
    assert not is_google_maps_url("https://www.google.com/search?q=turf")
    assert not is_google_maps_url("https://evil.example/maps")
    assert not is_google_maps_url("https://google.com.evil.example/maps")


def test_haversine_dhaka_to_chattogram():
    assert 210 < haversine_km(*MIRPUR, *CHATTOGRAM) < 235


# ------------------------------------------------------------------ owner settings
def test_owner_sets_map_link_and_pin_fills_from_link():
    turf, owner = make_turf()
    client = client_for(owner)
    link = "https://www.google.com/maps/place/Turf/@23.80,90.36,17z/data=!3d23.8069!4d90.3687"
    response = client.patch("/api/workspace/settings/", {"maps_url": link}, format="json")
    assert response.status_code == 200, response.json()
    turf.refresh_from_db()
    assert (turf.latitude, turf.longitude) == MIRPUR

    # Explicit coordinates win over the link.
    response = client.patch(
        "/api/workspace/settings/",
        {"maps_url": "https://maps.app.goo.gl/xyz", "latitude": "23.7946", "longitude": "90.4143"},
        format="json",
    )
    assert response.status_code == 200, response.json()
    turf.refresh_from_db()
    assert (turf.latitude, turf.longitude) == GULSHAN


def test_settings_reject_bad_map_input():
    _, owner = make_turf()
    client = client_for(owner)
    bad_link = client.patch("/api/workspace/settings/", {"maps_url": "https://evil.example/x"}, format="json")
    assert bad_link.status_code == 400
    half_pin = client.patch("/api/workspace/settings/", {"latitude": "23.8"}, format="json")
    assert half_pin.status_code == 400
    off_map = client.patch("/api/workspace/settings/", {"latitude": "95", "longitude": "90"}, format="json")
    assert off_map.status_code == 400


def test_manager_cannot_move_the_pin():
    turf, _ = make_turf()
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=turf, role=TenantMembership.Role.MANAGER)
    response = client_for(manager).patch(
        "/api/workspace/settings/", {"latitude": "1", "longitude": "1"}, format="json"
    )
    assert response.status_code == 403


# ------------------------------------------------------------------ near me
def test_owner_map_link_is_public():
    turf, _ = make_turf()
    turf.maps_url = "https://maps.app.goo.gl/AbC"
    turf.save()
    detail = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()
    assert detail["map_link"] == "https://maps.app.goo.gl/AbC"
    assert Turf.objects.filter(pk=turf.pk, latitude__isnull=True).exists()


# ------------------------------------------------------------------ password change
def _login(email, password):
    client = APIClient()
    response = client.post("/api/auth/login/", {"identifier": email, "password": password}, format="json")
    assert response.status_code == 200, response.json()
    return client


@pytest.mark.parametrize("who", ["admin", "owner", "manager"])
def test_everyone_can_change_their_password(who):
    users = get_user_model().objects
    if who == "admin":
        user = users.create_superuser("boss@example.com", PASSWORD)
    elif who == "owner":
        _, user = make_turf()
    else:
        turf, _ = make_turf()
        user = users.create_user("mgr@example.com", PASSWORD)
        TenantMembership.objects.create(user=user, turf=turf, role=TenantMembership.Role.MANAGER)

    client = _login(user.email, PASSWORD)
    new_password = "brand-new-Pass-456"
    wrong = client.post(
        "/api/auth/change-password/",
        {"current_password": "not-it", "new_password": new_password},
        format="json",
    )
    assert wrong.status_code == 400
    weak = client.post(
        "/api/auth/change-password/",
        {"current_password": PASSWORD, "new_password": "1234567890"},
        format="json",
    )
    assert weak.status_code == 400

    ok = client.post(
        "/api/auth/change-password/",
        {"current_password": PASSWORD, "new_password": new_password},
        format="json",
    )
    assert ok.status_code == 204
    assert client.get("/api/auth/me/").json()["authenticated"] is True  # session survives
    user.refresh_from_db()
    assert user.check_password(new_password) and not user.check_password(PASSWORD)
    _login(user.email, new_password)


def test_anonymous_cannot_change_password():
    response = APIClient().post(
        "/api/auth/change-password/", {"current_password": "x", "new_password": "y" * 12}, format="json"
    )
    assert response.status_code in (401, 403)


def test_turf_qr_code_is_a_standalone_svg():
    turf, _ = make_turf()
    response = APIClient().get(f"/api/public/turfs/{turf.slug}/qr.svg")
    assert response.status_code == 200 and response["Content-Type"] == "image/svg+xml"
    body = response.content.decode()
    # Without the namespace browsers refuse to draw the SVG inside an <img> tag.
    assert body.startswith("<svg") and 'xmlns="http://www.w3.org/2000/svg"' in body
    assert "booking page</title>" in body
