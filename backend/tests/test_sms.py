"""SMS outbox: dedupe, retries, provider errors, templates, tick, admin + workspace screens."""

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import SmsConfig, SmsMessage
from apps.notifications.providers import BulkSMSBDProvider, MemoryProvider, bd_msisdn, segment_count
from apps.notifications.services import deliver, queue_sms, render, retry_due
from apps.notifications.tick import subscription_sms
from apps.subscriptions.models import Subscription
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def test_numbers_and_segments():
    assert bd_msisdn("01712-345678") == bd_msisdn("+8801712345678") == "8801712345678"
    assert bd_msisdn("12345") is None
    assert segment_count("a" * 160) == 1 and segment_count("a" * 161) == 2
    assert segment_count("ক" * 70) == 1 and segment_count("ক" * 71) == 2  # Bengali = Unicode


def test_same_notification_is_never_queued_or_sent_twice():
    turf, _ = make_turf()
    first = queue_sms(to="01712345678", body="hi", kind="test", turf=turf, dedupe_key="booking:1:confirmed")
    again = queue_sms(to="01712345678", body="hi", kind="test", turf=turf, dedupe_key="booking:1:confirmed")
    assert first.pk == again.pk and SmsMessage.objects.count() == 1
    assert first.status == "sent" and len(MemoryProvider.outbox) == 1
    assert deliver(first.pk) is None and len(MemoryProvider.outbox) == 1  # a second send is refused


def test_retryable_failure_backs_off_then_succeeds_on_the_tick():
    MemoryProvider.fail_with = "1005"  # provider internal error
    message = queue_sms(to="01712345678", body="hi", kind="test")
    message.refresh_from_db()
    assert message.status == "failed" and message.attempts == 1 and message.next_attempt_at > timezone.now()
    MemoryProvider.fail_with = None
    assert retry_due()["sms_due"] == 0  # not yet due
    SmsMessage.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    assert retry_due()["sms_sent"] == 1
    message.refresh_from_db()
    assert message.status == "sent" and message.attempts == 2


def test_permanent_failure_is_not_retried_and_attempts_are_capped():
    MemoryProvider.fail_with = "1002"  # bad sender id: retrying can't help
    message = queue_sms(to="01712345678", body="hi", kind="test")
    message.refresh_from_db()
    assert message.status == "failed" and message.next_attempt_at is None
    assert "Sender ID" in message.provider_message
    MemoryProvider.fail_with = "1005"
    capped = queue_sms(to="01812345678", body="hi", kind="test")
    for _ in range(5):
        SmsMessage.objects.filter(pk=capped.pk).update(next_attempt_at=timezone.now())
        retry_due()
    capped.refresh_from_db()
    assert capped.attempts == 3 and capped.status == "failed"


def test_skips_bad_numbers_switched_off_platform_and_monthly_limit():
    turf, _ = make_turf()
    assert queue_sms(to="12345", body="x", kind="test").status == "skipped"
    config = SmsConfig.load()
    config.per_turf_monthly_limit = 1
    config.save()
    queue_sms(to="01712345678", body="x", kind="booking_confirmed", turf=turf)
    over = queue_sms(to="01712345678", body="y", kind="booking_confirmed", turf=turf)
    assert over.status == "skipped" and "allowance" in over.provider_message
    config.enabled = False
    config.save()
    assert queue_sms(to="01712345678", body="z", kind="test").status == "skipped"
    assert len(MemoryProvider.outbox) == 1


def test_bulksmsbd_client_reads_codes_and_never_resends_after_a_timeout():
    provider = BulkSMSBDProvider("KEY", "https://bulksmsbd.net/api")

    def answer(payload):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = json.dumps(payload).encode()
        return response

    with mock.patch(
        "apps.notifications.providers.urlopen", return_value=answer({"response_code": 202})
    ) as call:
        assert provider.send("8801712345678", "hello", "8809617").ok
        sent = call.call_args.args[0]
        assert sent.full_url == "https://bulksmsbd.net/api/smsapi" and b"api_key=KEY" in sent.data
    with mock.patch(
        "apps.notifications.providers.urlopen",
        return_value=answer({"response_code": 1007, "error_message": "Insufficient Balance"}),
    ):
        result = provider.send("8801712345678", "hello", "8809617")
        assert not result.ok and result.code == "1007" and result.retryable
    with mock.patch("apps.notifications.providers.urlopen", side_effect=TimeoutError):
        result = provider.send("8801712345678", "hello", "8809617")
        assert result.code == "timeout" and not result.retryable
    with mock.patch("apps.notifications.providers.urlopen", return_value=answer({"balance": "152.75"})):
        assert str(provider.balance()) == "152.75"


def test_templates_render_with_defaults_and_ignore_unknown_values():
    text = render("booking_confirmed", turf="Green Arena", date="21 Nov", time="7:00 PM", reference="TRF-1")
    assert text.startswith("আপনার Green Arena-এ 21 Nov তারিখ 7:00 PM") and "TRF-1" in text


# ------------------------------------------------------------------ tick
def test_tick_endpoint_needs_the_token():
    assert APIClient().post("/api/system/tick/").status_code == 403
    assert APIClient().post("/api/system/tick/", HTTP_X_TICK_TOKEN="wrong").status_code == 403
    ok = APIClient().post("/api/system/tick/?force=1", HTTP_X_TICK_TOKEN="test-tick-token")
    assert ok.status_code == 200 and "sms" in ok.json() and "demo_cleanup" in ok.json()
    with override_settings(TICK_TOKEN=""):
        assert APIClient().post("/api/system/tick/", HTTP_X_TICK_TOKEN="").status_code == 404


def test_subscription_reminders_and_expiry_sms_go_once():
    turf, owner = make_turf()
    owner.phone = "01712345678"
    owner.save()
    sub = Subscription.objects.get(turf=turf, status="active")
    today = timezone.localdate()
    sub.ends_on = today + timedelta(days=3)
    sub.save()
    assert subscription_sms()["subscription_sms"] == 1
    assert subscription_sms()["subscription_sms"] == 0  # same threshold: nothing new
    message = SmsMessage.objects.get(kind="subscription_reminder")
    assert message.to == "8801712345678" and "3 দিন" in message.body
    sub.ends_on = today - timedelta(days=1)
    sub.save()
    assert subscription_sms()["subscription_sms"] == 1
    assert SmsMessage.objects.filter(kind="subscription_expired").count() == 1
    assert subscription_sms()["subscription_sms"] == 0


# ------------------------------------------------------------------ admin + workspace
def test_admin_overview_templates_test_send_and_retry():
    admin, _ = admin_client()
    overview = admin.get("/api/admin/sms/").json()
    assert overview["provider"] == "memory" and "api_key" not in json.dumps(overview).replace(
        "api_key_set", ""
    )
    bad = admin.put(
        "/api/admin/sms/templates/booking_confirmed/", {"body": "Hi {name} {password}"}, format="json"
    )
    assert bad.status_code == 400 and "{password}" in str(bad.json())
    good = admin.put(
        "/api/admin/sms/templates/booking_confirmed/", {"body": "{turf}: OK {reference}"}, format="json"
    )
    assert good.status_code == 200
    assert render("booking_confirmed", turf="T", reference="R") == "T: OK R"
    sent = admin.post("/api/admin/sms/test/", {"to": "01712345678"}, format="json")
    assert sent.status_code == 201 and sent.json()["status"] == "sent"
    MemoryProvider.fail_with = "1002"
    failed = admin.post("/api/admin/sms/test/", {"to": "01812345678"}, format="json").json()
    assert failed["status"] == "failed"
    MemoryProvider.fail_with = None
    retried = admin.post(f"/api/admin/sms/messages/{failed['id']}/retry/").json()
    assert retried["status"] == "sent"
    days = admin.patch("/api/admin/sms/", {"subscription_reminder_days": [1, 7, 3]}, format="json")
    assert days.json()["subscription_reminder_days"] == [7, 3, 1]


def test_workspace_sms_is_tenant_scoped_masked_and_permissioned():
    turf, owner = make_turf()
    other, _ = make_turf("Beta Turf", "beta@example.com")
    queue_sms(to="01712345678", body="mine", kind="test", turf=turf)
    queue_sms(to="01812345678", body="theirs", kind="test", turf=other)
    body = client_for(owner).get("/api/workspace/sms/").json()
    assert [m["body"] for m in body["results"]] == ["mine"]
    assert body["results"][0]["to"] == "8801712***678" and body["usage"]["sent"] == 1

    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    membership = TenantMembership.objects.create(user=manager, turf=turf, role="manager")
    assert client_for(manager).get("/api/workspace/sms/").status_code == 403
    membership.permissions = {**membership.permissions, "view_sms": True}
    membership.save()
    assert client_for(manager).get("/api/workspace/sms/").status_code == 200
    assert (
        client_for(manager)
        .patch("/api/workspace/sms/settings/", {"booking_reminder": True}, format="json")
        .status_code
        == 403
    )
    on = client_for(owner).patch(
        "/api/workspace/sms/settings/", {"booking_reminder": True, "reminder_hours": 2}, format="json"
    )
    assert on.json()["booking_reminder"] is True and on.json()["reminder_hours"] == 2
