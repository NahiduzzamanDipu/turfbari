"""Temporary passwords, forced password change, forgot password, admin account tools, manager access."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import PasswordResetCode
from apps.audit.models import AuditEvent
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db
NEW_PASSWORD = "Bright-Goal-2026!"


def sign_in(identifier, password):
    client = APIClient()
    r = client.post("/api/auth/login/", {"identifier": identifier, "password": password}, format="json")
    return client, r


def sms_password() -> str:
    """The temporary password from the last credential SMS (it is never in an API response)."""
    from apps.notifications.providers import MemoryProvider

    body = MemoryProvider.outbox[-1]["body"]
    return re.search(r"(?:password|পাসওয়ার্ড): (\S{12})", body).group(1)


def add_manager(owner_client, email="mgr@example.com"):
    r = owner_client.post(
        "/api/workspace/managers/",
        {"email": email, "full_name": "Manager Mia", "phone": "01812345678"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    assert r.json()["temporary_password"] is None and r.json()["credential"]["status"] == "submitted"
    return {**r.json(), "temporary_password": sms_password()}


# ------------------------------------------------------------------ first sign-in
def test_new_manager_must_replace_temporary_password_before_anything_else():
    _, owner = make_turf()
    temp = add_manager(client_for(owner))["temporary_password"]
    assert len(temp) == 12
    manager = get_user_model().objects.get(email="mgr@example.com")
    assert manager.must_change_password and manager.temp_password_expires_at > timezone.now()
    assert not manager.check_password("") and temp not in str(manager.password)  # only a hash is stored

    client, r = sign_in("mgr@example.com", temp)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    blocked = client.get("/api/workspace/bookings/")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert client.get("/api/auth/me/").status_code == 200  # allowed

    same = client.post(
        "/api/auth/change-password/",
        {"current_password": temp, "new_password": temp, "new_password_confirm": temp},
        format="json",
    )
    assert same.status_code == 400
    weak = client.post(
        "/api/auth/change-password/",
        {"current_password": temp, "new_password": "1234567890", "new_password_confirm": "1234567890"},
        format="json",
    )
    assert weak.status_code == 400
    ok = client.post(
        "/api/auth/change-password/",
        {"current_password": temp, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 204
    assert client.get("/api/workspace/bookings/").status_code == 200  # same session keeps working
    manager.refresh_from_db()
    assert not manager.must_change_password and manager.temp_password_expires_at is None
    assert sign_in("mgr@example.com", temp)[1].status_code == 400  # the temporary password is gone


def test_expired_temporary_password_is_refused():
    _, owner = make_turf()
    temp = add_manager(client_for(owner))["temporary_password"]
    get_user_model().objects.filter(email="mgr@example.com").update(
        temp_password_expires_at=timezone.now() - timedelta(minutes=1)
    )
    _, r = sign_in("mgr@example.com", temp)
    assert r.status_code == 400 and r.json()["error"]["code"] == "temporary_password_expired"


# ------------------------------------------------------------------ forgot password
def _code_from_mail() -> str:
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


def _code_from_sms() -> str:
    from apps.notifications.providers import MemoryProvider

    return re.search(r"\b(\d{6})\b", MemoryProvider.outbox[-1]["body"]).group(1)


def _owner_without_phone():
    _, owner = make_turf()
    owner.phone = ""
    owner.save()
    return owner


def test_reset_code_goes_by_sms_when_the_account_has_a_phone_and_is_not_logged():
    from apps.notifications.models import SmsMessage
    from apps.notifications.providers import MemoryProvider

    owner = _owner_without_phone()
    owner.phone = "01712345678"
    owner.save()
    APIClient().post("/api/auth/password-reset/", {"identifier": "01712-345678"}, format="json")
    assert mail.outbox == [] and MemoryProvider.outbox[0]["to"] == "8801712345678"
    code = _code_from_sms()
    log = SmsMessage.objects.get(kind="password_reset")
    assert log.status == "sent" and code not in log.body  # the code is blanked in the stored log
    assert PasswordResetCode.objects.get(user=owner).channel == "sms"


def test_reset_falls_back_to_email_when_sms_fails():
    from apps.notifications.providers import MemoryProvider

    owner = _owner_without_phone()
    owner.phone = "01712345678"
    owner.save()
    MemoryProvider.fail_with = "1007"  # out of SMS balance
    APIClient().post("/api/auth/password-reset/", {"identifier": owner.email}, format="json")
    assert len(mail.outbox) == 1 and PasswordResetCode.objects.get(user=owner).channel == "email"


def test_forgot_password_by_email_is_single_use_and_signs_out_everywhere():
    owner = _owner_without_phone()
    other_device, _ = sign_in(owner.email, PASSWORD)
    unknown = APIClient().post(
        "/api/auth/password-reset/", {"identifier": "nobody@example.com"}, format="json"
    )
    known = APIClient().post("/api/auth/password-reset/", {"identifier": owner.email.upper()}, format="json")
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()  # no account enumeration
    assert len(mail.outbox) == 1 and mail.outbox[0].to == [owner.email]
    code = _code_from_mail()
    stored = PasswordResetCode.objects.get(user=owner)
    assert code not in stored.code_hash

    wrong = APIClient().post(
        "/api/auth/password-reset/confirm/",
        {
            "identifier": owner.email,
            "code": "000000" if code != "000000" else "111111",
            "new_password": NEW_PASSWORD,
        },
        format="json",
    )
    assert wrong.status_code == 400
    ok = APIClient().post(
        "/api/auth/password-reset/confirm/",
        {"identifier": owner.email, "code": code, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 200, ok.json()
    again = APIClient().post(
        "/api/auth/password-reset/confirm/",
        {"identifier": owner.email, "code": code, "new_password": "Another-Pass-2026"},
        format="json",
    )
    assert again.status_code == 400  # single use
    assert other_device.get("/api/workspace/bookings/").status_code == 403  # old session ended
    assert sign_in(owner.email, NEW_PASSWORD)[1].status_code == 200
    assert AuditEvent.objects.filter(action="account.password_reset", actor=owner).exists()


def test_reset_code_dies_after_five_wrong_guesses():
    from apps.accounts.passwords import confirm_reset

    owner = _owner_without_phone()
    APIClient().post("/api/auth/password-reset/", {"identifier": owner.email}, format="json")
    code = _code_from_mail()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert confirm_reset(owner.email, wrong) is None
    assert confirm_reset(owner.email, code) is None  # locked out even with the right code


def test_platform_admins_cannot_use_forgot_password():
    _, admin = admin_client()
    APIClient().post("/api/auth/password-reset/", {"identifier": admin.email}, format="json")
    assert mail.outbox == []


# ------------------------------------------------------------------ admin tools
def test_admin_creates_searches_resets_and_deactivates_accounts():
    turf, owner = make_turf()
    admin, me = admin_client()
    created = admin.post(
        "/api/admin/users/",
        {
            "email": "New.Mgr@Example.com",
            "full_name": "New Manager",
            "phone": "01812345678",
            "turf": str(turf.id),
            "role": "manager",
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["email"] == "new.mgr@example.com" and body["must_change_password"] is True
    assert body["temporary_password"] is None and body["memberships"][0]["role"] == "manager"
    assert body["credential"]["status"] == "submitted" and body["credential"]["masked_phone"] == "018•••••678"
    assert "temporary_password" not in admin.get(f"/api/admin/users/{body['id']}/").json()

    found = admin.get("/api/admin/users/", {"q": "01812345678"}).json()["results"]
    assert [u["email"] for u in found] == ["new.mgr@example.com"]
    by_turf = {u["email"] for u in admin.get("/api/admin/users/", {"q": "Alpha"}).json()["results"]}
    assert {owner.email, "new.mgr@example.com"} <= by_turf

    reset = admin.post(f"/api/admin/users/{owner.id}/reset-password/").json()
    assert reset["temporary_password"] is None and "credential" in reset
    reset["temporary_password"] = sms_password()
    owner.refresh_from_db()
    assert owner.must_change_password and owner.check_password(reset["temporary_password"])
    off = admin.post(f"/api/admin/users/{owner.id}/deactivate/")
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert sign_in(owner.email, reset["temporary_password"])[1].status_code == 400
    assert AuditEvent.objects.filter(action="platform.user_reset_password").exists()

    assert admin.post(f"/api/admin/users/{me.id}/deactivate/").status_code == 400  # not yourself
    other_admin = get_user_model().objects.create_superuser("ops@example.com", PASSWORD)
    assert admin.post(f"/api/admin/users/{other_admin.id}/reset-password/").status_code == 400


@override_settings(AXES_ENABLED=True)
def test_admin_unlocks_a_locked_account():
    _, owner = make_turf()
    for _ in range(5):
        sign_in(owner.email, "wrong-password-x")
    locked = sign_in(owner.email, PASSWORD)[1]
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "account_locked"
    admin, _ = admin_client()
    assert admin.get(f"/api/admin/users/{owner.id}/").json()["locked"] is True
    admin.post(f"/api/admin/users/{owner.id}/unlock/")
    assert sign_in(owner.email, PASSWORD)[1].status_code == 200


def test_turf_always_keeps_an_owner_and_owners_only_tools_need_admin():
    turf, owner = make_turf()
    admin, _ = admin_client()
    membership = TenantMembership.objects.get(user=owner, turf=turf)
    demote = admin.patch(f"/api/admin/memberships/{membership.id}/", {"role": "manager"}, format="json")
    assert demote.status_code == 400
    assert client_for(owner).get("/api/admin/users/").status_code == 403


# ------------------------------------------------------------------ manager access
def test_manager_permissions_are_enforced_on_the_server():
    _, owner = make_turf()
    owner_client = client_for(owner)
    row = add_manager(owner_client)
    assert row["permissions"] == {"approve_payments": True, "manage_slots": False, "view_sms": False}
    manager = get_user_model().objects.get(email="mgr@example.com")
    mgr = client_for(manager)
    assert (
        mgr.post(
            "/api/workspace/fields/", {"name": "Field X", "default_hourly_rate": "900"}, format="json"
        ).status_code
        == 403
    )

    granted = owner_client.patch(
        f"/api/workspace/managers/{row['id']}/", {"permissions": {"manage_slots": True}}, format="json"
    )
    assert granted.status_code == 200 and granted.json()["permissions"]["manage_slots"] is True
    assert (
        mgr.post(
            "/api/workspace/fields/", {"name": "Field X", "default_hourly_rate": "900"}, format="json"
        ).status_code
        == 201
    )
    assert (
        mgr.patch(
            f"/api/workspace/managers/{row['id']}/", {"permissions": {"view_sms": True}}, format="json"
        ).status_code
        == 403
    )
    bad = owner_client.patch(
        f"/api/workspace/managers/{row['id']}/", {"permissions": {"root": True}}, format="json"
    )
    assert bad.status_code == 400
