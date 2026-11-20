"""Temporary passwords sent by SMS for new accounts and admin resets (requirements 1-15)."""

import logging
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.credentials import expire_due
from apps.accounts.models import TemporaryCredential
from apps.audit.models import AuditEvent
from apps.common.models import PlatformSettings
from apps.notifications.models import SmsMessage, WalletTransaction
from apps.notifications.providers import MemoryProvider

from .test_account_security import sign_in
from .test_core import PASSWORD, client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db
User = get_user_model()
NEW_PASSWORD = "Bright-Goal-2026!"
PW = re.compile(r"(?:password|পাসওয়ার্ড): (\S{12})")


def settings_(**kw):
    PlatformSettings.objects.update_or_create(pk=1, defaults=kw)
    cache.delete("platform:settings")


def last_password(to=None) -> str:
    msgs = [m for m in MemoryProvider.outbox if to is None or m["to"].endswith(to[-10:])]
    return PW.search(msgs[-1]["body"]).group(1)


def create(admin, turf, phone="01812345678", email="mia@example.com"):
    r = admin.post(
        "/api/admin/users/",
        {"email": email, "full_name": "Mia Rahman", "phone": phone, "turf": str(turf.id), "role": "manager"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    return r.json()


def reset(admin, user, key=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return admin.post(f"/api/admin/users/{user.pk}/reset-password/", **headers)


def wallet_rows():
    return WalletTransaction.objects.count()


# 1, 2 ----------------------------------------------------------------- new account
def test_1_2_new_account_sends_login_details_to_the_registered_number():
    turf, _ = make_turf()
    admin, me = admin_client()
    body = create(admin, turf)
    assert body["temporary_password"] is None and body["must_change_password"] is True
    assert body["credential"]["status"] == "submitted" and body["credential"]["masked_phone"] == "018•••••678"
    sms = MemoryProvider.outbox[-1]
    assert sms["to"] == "8801812345678"
    text = sms["body"]
    assert "/login" in text and "mia@example.com" in text and "পাসওয়ার্ড" in text  # default language: Bengali
    password = last_password()
    user = User.objects.get(email="mia@example.com")
    assert user.check_password(password) and len(password) == 12
    # Stored SMS text and the credential never contain the password.
    stored = SmsMessage.objects.get(kind="account_credentials")
    assert password not in stored.body and "*" * 12 in stored.body and stored.scope == "platform"
    cred = TemporaryCredential.objects.get(user=user)
    assert (
        cred.secret == "" and cred.status == "submitted" and cred.created_by == me
    )  # copy wiped after hand-off
    assert user.temp_password_expires_at > timezone.now() + timedelta(hours=71)


# 3, 4 ----------------------------------------------------------------- reset
def test_3_4_reset_issues_a_new_password_and_the_old_one_stops_working():
    turf, owner = make_turf()
    admin, _ = admin_client()
    first = reset(admin, owner).json()
    assert first["temporary_password"] is None and first["credential"]["purpose"] == "admin_reset"
    p1 = last_password()
    owner.refresh_from_db()
    assert owner.check_password(p1) and owner.must_change_password
    TemporaryCredential.objects.filter(user=owner).update(created_at=timezone.now() - timedelta(minutes=5))
    reset(admin, owner)
    p2 = last_password()
    owner.refresh_from_db()
    assert p1 != p2 and owner.check_password(p2) and not owner.check_password(p1)
    assert sign_in(owner.email, p1)[1].status_code == 400
    statuses = list(
        TemporaryCredential.objects.filter(user=owner).order_by("created_at").values_list("status", flat=True)
    )
    assert statuses == ["superseded", "submitted"]


# 5 -------------------------------------------------------------------- expiry
def test_5_temporary_passwords_expire():
    settings_(temp_password_hours=2)
    turf, owner = make_turf()
    admin, _ = admin_client()
    reset(admin, owner)
    password = last_password()
    owner.refresh_from_db()
    assert owner.temp_password_expires_at < timezone.now() + timedelta(hours=2, minutes=1)
    assert "২ ঘণ্টা" in MemoryProvider.outbox[-1]["body"]
    User.objects.filter(pk=owner.pk).update(temp_password_expires_at=timezone.now() - timedelta(minutes=1))
    TemporaryCredential.objects.filter(user=owner).update(expires_at=timezone.now() - timedelta(minutes=1))
    _, r = sign_in(owner.email, password)
    assert r.status_code == 400 and r.json()["error"]["code"] == "temporary_password_expired"
    assert expire_due() == 1
    assert TemporaryCredential.objects.get(user=owner).status == "expired"
    assert AuditEvent.objects.filter(action="account.temporary_password_expired").exists()


# 6, 7, 8 -------------------------------------------------------------- forced change
def test_6_7_8_first_login_forces_a_password_change_enforced_by_the_api():
    turf, _ = make_turf()
    admin, _ = admin_client()
    create(admin, turf)
    client, r = sign_in("mia@example.com", last_password())
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    for url in (
        "/api/workspace/bookings/",
        "/api/workspace/settings/",
        "/api/workspace/subscription/",
        "/api/legal/status/",
    ):
        blocked = client.get(url)
        assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required", (
            url
        )
    temp = last_password()
    no_confirm = client.post(
        "/api/auth/change-password/", {"current_password": temp, "new_password": NEW_PASSWORD}, format="json"
    )
    assert no_confirm.status_code == 400 and "new_password_confirm" in no_confirm.json()["error"]["fields"]
    mismatch = client.post(
        "/api/auth/change-password/",
        {"current_password": temp, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD + "x"},
        format="json",
    )
    assert mismatch.status_code == 400
    ok = client.post(
        "/api/auth/change-password/",
        {"current_password": temp, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 204
    assert client.get("/api/workspace/bookings/").status_code == 200
    user = User.objects.get(email="mia@example.com")
    assert not user.must_change_password and user.temp_password_expires_at is None
    assert TemporaryCredential.objects.get(user=user).status == "used"
    assert AuditEvent.objects.filter(action="account.temporary_password_replaced").exists()
    assert sign_in("mia@example.com", temp)[1].status_code == 400


# 9, 10 ---------------------------------------------------------------- failures and resend
def test_9_10_failed_sms_never_exposes_the_password_and_resend_reuses_it(caplog):
    turf, owner = make_turf()
    admin, _ = admin_client()
    MemoryProvider.fail_with = "1007"  # permanent provider error
    with caplog.at_level(logging.DEBUG):
        r = reset(admin, owner).json()
    assert r["temporary_password"] is None and r["credential"]["status"] in ("failed", "retrying")
    cred = TemporaryCredential.objects.get(user=owner)
    assert cred.secret  # kept (encrypted) so the same password can be resent
    assert MemoryProvider.outbox == []
    detail = admin.get(f"/api/admin/users/{owner.pk}/").json()
    secrets_seen = (
        str(r) + str(detail) + caplog.text + str(list(AuditEvent.objects.values("summary", "data")))
    )
    owner.refresh_from_db()
    assert "*" * 12 in SmsMessage.objects.get(kind="credential_reset").body
    # The password itself appears nowhere (we only know it from what the provider would have received).
    MemoryProvider.fail_with = None
    again = admin.post(f"/api/admin/users/{owner.pk}/credential/resend/").json()
    assert again["credential"]["status"] == "submitted" and again["credential"]["id"] == str(cred.pk)
    first_sms = SmsMessage.objects.filter(kind="credential_reset").order_by("created_at").first()
    assert first_sms.next_attempt_at is None  # its automatic retry was cancelled: no second copy later
    password = last_password()
    assert password not in secrets_seen
    owner.refresh_from_db()
    assert owner.check_password(password)  # same password as the failed attempt, not a new one
    assert TemporaryCredential.objects.filter(user=owner).count() == 1
    assert TemporaryCredential.objects.get(user=owner).secret == ""
    # Resending after it was handed over makes a new password and kills the old one.
    after = admin.post(f"/api/admin/users/{owner.pk}/credential/resend/").json()
    assert after["credential"]["id"] != str(cred.pk)
    owner.refresh_from_db()
    assert not owner.check_password(password)
    # Expired: resend also issues a new one.
    TemporaryCredential.objects.filter(user=owner, status="submitted").update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    newest = admin.post(f"/api/admin/users/{owner.pk}/credential/resend/").json()
    assert newest["credential"]["status"] == "submitted"
    assert TemporaryCredential.objects.filter(user=owner, status="superseded").count() == 2


# 11, 12 --------------------------------------------------------------- duplicates and wallets
def test_11_12_duplicate_requests_send_once_and_no_turf_wallet_is_charged():
    turf, owner = make_turf()
    admin, _ = admin_client()
    before = wallet_rows()
    from apps.notifications import wallet

    balance = wallet.wallet_for(turf).balance
    a = reset(admin, owner, key="11111111-2222-3333-4444-555555555555").json()
    b = reset(admin, owner, key="11111111-2222-3333-4444-555555555555").json()  # same click retried
    c = reset(admin, owner).json()  # double click without a key, within seconds
    assert a["credential"]["id"] == b["credential"]["id"] == c["credential"]["id"]
    assert len(MemoryProvider.outbox) == 1 and TemporaryCredential.objects.filter(user=owner).count() == 1
    assert wallet_rows() == before and wallet.wallet_for(turf).balance == balance == Decimal("100")
    msg = SmsMessage.objects.get(kind="credential_reset")
    assert msg.turf_id is None and msg.scope == "platform"
    # Managers added by an owner: also TurfBari's cost, not the turf's.
    client_for(owner).post(
        "/api/workspace/managers/",
        {"email": "m2@example.com", "full_name": "M2", "phone": "01912345670"},
        format="json",
    )
    assert wallet_rows() == before and len(MemoryProvider.outbox) == 2


# 13, 14 --------------------------------------------------------------- authorisation and rate limits
def test_13_14_only_platform_admins_reset_and_resets_are_rate_limited():
    turf, owner = make_turf()
    other, other_owner = make_turf("Beta Turf", "beta@example.com")
    admin, _ = admin_client()
    for client in (client_for(owner), APIClient()):
        assert reset(client, other_owner).status_code in (401, 403)
        assert client.post(f"/api/admin/users/{other_owner.pk}/credential/resend/").status_code in (401, 403)
        assert client.get(f"/api/admin/users/{other_owner.pk}/credential/").status_code in (401, 403)
    assert MemoryProvider.outbox == []
    for _ in range(5):
        TemporaryCredential.objects.filter(user=owner).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        assert reset(admin, owner).status_code == 200
    TemporaryCredential.objects.filter(user=owner).update(created_at=timezone.now() - timedelta(minutes=10))
    assert reset(admin, owner).status_code == 429
    # The public "forgot password" flow still never reveals whether an account exists.
    a = APIClient().post("/api/auth/password-reset/", {"identifier": "01799999999"}, format="json")
    b = APIClient().post("/api/auth/password-reset/", {"identifier": owner.email}, format="json")
    assert a.status_code == b.status_code and a.json() == b.json()


# 15 ------------------------------------------------------------------- templates
def test_15_bengali_and_english_templates_and_placeholder_validation():
    turf, owner = make_turf()
    admin, _ = admin_client()
    cfg = admin.get("/api/admin/api-config/credentials/").json()
    assert cfg["language"] == "bn" and cfg["sms_available"] and "*" * 12 in cfg["previews"]["created_en"]
    bad = admin.put(
        "/api/admin/api-config/credentials/",
        {
            **{
                k: cfg[k]
                for k in (
                    "enabled",
                    "language",
                    "temp_password_hours",
                    "created_en",
                    "created_bn",
                    "reset_bn",
                )
            },
            "reset_en": "Hi {name} {pin}",
        },
        format="json",
    )
    assert bad.status_code == 400 and "reset_en" in bad.json()["error"]["fields"]
    missing = admin.put(
        "/api/admin/api-config/credentials/",
        {
            **{k: cfg[k] for k in ("enabled", "temp_password_hours", "created_en", "created_bn", "reset_bn")},
            "language": "en",
            "reset_en": "Hi {name}, go to {login_url}",
        },
        format="json",
    )
    assert missing.status_code == 400 and "{password}" in str(missing.json())
    ok = admin.put(
        "/api/admin/api-config/credentials/",
        {
            **{k: cfg[k] for k in ("enabled", "temp_password_hours", "created_en", "created_bn", "reset_bn")},
            "language": "en",
            "reset_en": "Hello {name}. {login_url} user {username} pass {password} ({expires})",
        },
        format="json",
    )
    assert ok.status_code == 200
    reset(admin, owner)
    text = MemoryProvider.outbox[-1]["body"]
    assert text.startswith("Hello Owner.") and "72 hours" in text and owner.email in text
    # Turning it off: the creator sees the password once instead (never an unreachable account).
    admin.put("/api/admin/api-config/credentials/", {**ok.json(), "enabled": False}, format="json")
    body = create(admin, turf, email="nosms@example.com")
    assert body["temporary_password"] and body["credential"]["channel"] == "shown_once"
    assert User.objects.get(email="nosms@example.com").check_password(body["temporary_password"])
    assert len(MemoryProvider.outbox) == 1
    # And with SMS on, an account without a valid mobile number is refused.
    admin.put("/api/admin/api-config/credentials/", {**ok.json(), "enabled": True}, format="json")
    r = admin.post(
        "/api/admin/users/",
        {"email": "x@example.com", "full_name": "X", "phone": "", "turf": str(turf.id), "role": "manager"},
        format="json",
    )
    assert r.status_code == 400 and "phone" in r.json()["error"]["fields"]
    assert PASSWORD  # (shared fixture constant kept imported for parity with other suites)
