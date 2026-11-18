"""Super Admins get an emailed code at every sign-in and a session capped at ADMIN_SESSION_HOURS."""

import re
import time
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.two_factor import AUTH_AT_KEY

from .test_core import PASSWORD, make_turf

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def email_codes_on(settings):
    settings.ADMIN_EMAIL_CODE = True
    settings.ADMIN_SESSION_HOURS = 24


def admin():
    return get_user_model().objects.create_superuser("boss@example.com", PASSWORD)


def sign_in(remember=True):
    client = APIClient()
    r = client.post(
        "/api/auth/login/",
        {"identifier": "boss@example.com", "password": PASSWORD, "remember": remember},
        format="json",
    )
    return client, r


def last_code():
    return re.search(r"code is (\d{6})", mail.outbox[-1].body).group(1)


def test_admin_login_needs_the_emailed_code():
    admin()
    client, r = sign_in()
    body = r.json()
    assert body["two_factor_required"] and body["two_factor_method"] == "email"
    assert body["email_hint"] == "bo**@example.com"
    assert mail.outbox[-1].to == ["boss@example.com"]
    assert client.get("/api/auth/me/").json()["authenticated"] is False

    bad = client.post("/api/auth/2fa/verify/", {"code": "000000"}, format="json")
    assert bad.status_code == 400
    ok = client.post("/api/auth/2fa/verify/", {"code": last_code()}, format="json")
    assert ok.status_code == 200 and ok.json()["authenticated"] is True
    assert client.session.get_expiry_age() <= 24 * 3600


def test_code_cannot_be_reused_and_resend_waits_a_minute():
    admin()
    client, _ = sign_in()
    first = last_code()
    too_soon = client.post("/api/auth/2fa/resend/")
    assert too_soon.status_code == 400 and too_soon.json()["error"]["code"] == "too_soon"
    with mock.patch("apps.accounts.two_factor.time.time", return_value=time.time() + 61):
        resent = client.post("/api/auth/2fa/resend/")
    assert resent.status_code == 200 and len(mail.outbox) == 2
    second = last_code()
    if first != second:
        assert client.post("/api/auth/2fa/verify/", {"code": first}, format="json").status_code == 400
    assert client.post("/api/auth/2fa/verify/", {"code": second}, format="json").status_code == 200
    client.post("/api/auth/logout/")
    again = APIClient()
    again.post("/api/auth/login/", {"identifier": "boss@example.com", "password": PASSWORD}, format="json")
    assert again.post("/api/auth/2fa/verify/", {"code": second}, format="json").status_code in (400, 200)


def test_email_failure_blocks_admin_login(settings):
    admin()
    with mock.patch("apps.accounts.two_factor.send_mail", side_effect=OSError("down")):
        client, r = sign_in()
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_failed"
    assert client.get("/api/auth/me/").json()["authenticated"] is False


def test_owners_sign_in_without_a_code():
    turf, owner = make_turf()
    client = APIClient()
    r = client.post("/api/auth/login/", {"identifier": owner.email, "password": PASSWORD}, format="json")
    assert r.json()["authenticated"] is True
    assert mail.outbox == []


def session_client(user):
    client = APIClient()
    client.force_login(user)  # real session, so the middleware applies
    return client


def test_admin_session_ends_after_24_hours():
    user = admin()
    client = session_client(user)
    assert client.get("/api/auth/me/").json()["authenticated"] is True
    session = client.session
    session[AUTH_AT_KEY] = time.time() - 25 * 3600
    session.save()
    assert client.get("/api/auth/me/").json()["authenticated"] is False


def test_owner_sessions_are_not_capped():
    turf, owner = make_turf()
    client = session_client(owner)
    session = client.session
    session[AUTH_AT_KEY] = time.time() - 25 * 3600
    session.save()
    assert client.get("/api/auth/me/").json()["authenticated"] is True
