"""Two-factor sign-in for Super Admins (TOTP + recovery codes)."""

import base64
import time
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts import totp
from apps.accounts.models import TwoFactorDevice
from apps.audit.models import AuditEvent

from .test_core import PASSWORD, client_for, make_turf

pytestmark = pytest.mark.django_db


def test_rfc6238_reference_vector():
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59 // 30) == "287082"  # RFC 6238 SHA1 vector, last 6 digits
    assert totp.code_at(secret, 1111111109 // 30) == "081804"
    assert totp.match(secret, "287 082", now=59) == 1
    assert totp.match(secret, "287082", now=59, after_counter=1) is None  # replay blocked
    assert totp.match(secret, "000000", now=59) is None


def now_code(secret):
    return totp.code_at(secret, totp.current_counter())


def admin():
    return get_user_model().objects.create_superuser("boss@example.com", PASSWORD)


def enrol(user) -> tuple[str, list[str]]:
    client = client_for(user)
    setup = client.post("/api/auth/2fa/setup/").json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/TurfBari%3Aboss%40example.com?secret=")
    assert setup["qr_svg"].startswith("data:image/svg+xml")
    assert client.get("/api/auth/2fa/").json() == {"enabled": False, "recovery_codes_left": 0}
    bad = client.post("/api/auth/2fa/confirm/", {"code": "000000"}, format="json")
    assert bad.status_code == 400
    ok = client.post("/api/auth/2fa/confirm/", {"code": now_code(setup["secret"])}, format="json")
    assert ok.status_code == 200
    codes = ok.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    return setup["secret"], codes


def password_step(email=None):
    client = APIClient()
    r = client.post(
        "/api/auth/login/", {"identifier": email or "boss@example.com", "password": PASSWORD}, format="json"
    )
    return client, r


def test_login_requires_code_once_enabled_and_codes_cannot_be_replayed():
    user = admin()
    secret, _ = enrol(user)
    device = TwoFactorDevice.objects.get(user=user)
    device.last_counter = -1  # pretend the enrol code was in an earlier window
    device.save()

    client, r = password_step()
    assert r.status_code == 200 and r.json()["two_factor_required"] is True
    assert client.get("/api/auth/me/").json()["authenticated"] is False  # not signed in yet

    wrong = client.post("/api/auth/2fa/verify/", {"code": "000000"}, format="json")
    assert wrong.status_code == 400
    code = now_code(secret)
    ok = client.post("/api/auth/2fa/verify/", {"code": code}, format="json")
    assert ok.status_code == 200 and ok.json()["home"] == "/admin"
    assert client.get("/api/auth/me/").json()["authenticated"] is True

    other, _ = password_step()
    replay = other.post("/api/auth/2fa/verify/", {"code": code}, format="json")
    assert replay.status_code == 400  # same code can't be used twice
    assert AuditEvent.objects.filter(action="account.login", summary__contains="two-factor").count() == 1


def test_recovery_code_works_once():
    user = admin()
    _, codes = enrol(user)
    client, _ = password_step()
    assert client.post("/api/auth/2fa/verify/", {"code": codes[0].upper()}, format="json").status_code == 200
    assert client_for(user).get("/api/auth/2fa/").json()["recovery_codes_left"] == 9
    again, _ = password_step()
    assert again.post("/api/auth/2fa/verify/", {"code": codes[0]}, format="json").status_code == 400


def test_pending_sign_in_expires_and_locks_after_wrong_codes():
    user = admin()
    secret, _ = enrol(user)
    client, _ = password_step()
    for _ in range(4):
        assert client.post("/api/auth/2fa/verify/", {"code": "111111"}, format="json").status_code == 400
    locked = client.post("/api/auth/2fa/verify/", {"code": "111111"}, format="json")
    assert locked.status_code == 401 and locked.json()["error"]["code"] == "two_factor_expired"
    assert client.post("/api/auth/2fa/verify/", {"code": now_code(secret)}, format="json").status_code == 401

    cache.clear()  # reset the 10/min two-factor throttle this test deliberately exhausts
    late, _ = password_step()
    with mock.patch("apps.accounts.two_factor.time.time", return_value=time.time() + 301):
        expired = late.post("/api/auth/2fa/verify/", {"code": now_code(secret)}, format="json")
    assert expired.status_code == 401
    assert APIClient().post("/api/auth/2fa/verify/", {"code": "123456"}, format="json").status_code == 401


def test_disable_needs_password_and_code_and_regenerate_codes():
    user = admin()
    secret, codes = enrol(user)
    client = client_for(user)
    device = TwoFactorDevice.objects.get(user=user)
    device.last_counter = -1
    device.save()
    new = client.post("/api/auth/2fa/recovery-codes/", {"code": now_code(secret)}, format="json").json()
    assert set(new["recovery_codes"]).isdisjoint(codes)

    assert (
        client.post(
            "/api/auth/2fa/disable/", {"password": "nope", "code": new["recovery_codes"][0]}, format="json"
        ).status_code
        == 400
    )
    off = client.post(
        "/api/auth/2fa/disable/", {"password": PASSWORD, "code": new["recovery_codes"][0]}, format="json"
    )
    assert off.json() == {"enabled": False}
    _, r = password_step()
    assert "two_factor_required" not in r.json() and r.json()["authenticated"] is True


def test_only_platform_admins_can_enrol_and_owners_log_in_normally():
    _, owner = make_turf()
    assert client_for(owner).post("/api/auth/2fa/setup/").status_code == 403
    _, r = password_step(owner.email)
    assert r.json()["authenticated"] is True and r.json()["home"] == "/workspace"


def test_cannot_restart_setup_while_enabled():
    user = admin()
    enrol(user)
    assert client_for(user).post("/api/auth/2fa/setup/").status_code == 400
