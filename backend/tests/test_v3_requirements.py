"""Version 3: prepaid SMS wallet, bKash recharge, single/bulk SMS, admin SMS controls, daily booking
limit, owner-booking SMS, faster slot selection, subscription approval. Numbers follow the spec list."""

import threading
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.bookings.models import Booking
from apps.common.models import PlatformSettings
from apps.notifications import wallet
from apps.notifications.models import SmsMessage, SmsRechargeRequest, SmsWallet, WalletTransaction
from apps.notifications.providers import MemoryProvider, segment_count
from apps.notifications.services import deliver, queue_sms
from apps.subscriptions.models import Invoice, PaymentTransaction, Subscription
from apps.subscriptions.services import standing
from apps.turfs.schedule import local_dt

from .test_core import bkash, client_for, make_turf, tomorrow_at
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db
DAILY_BN = "একজন গ্রাহক প্রতিদিন সর্বোচ্চ ২টি স্লট বুক করতে পারবেন।"


def balance(turf) -> Decimal:
    return SmsWallet.objects.get(turf=turf).balance


def empty_wallet(turf):
    w = wallet.wallet_for(turf)
    if w.balance:
        wallet.post(
            w.pk,
            kind=WalletTransaction.Kind.ADJUSTMENT,
            amount=-w.balance,
            key=f"empty:{turf.pk}:{uuid.uuid4()}",
            note="test",
        )


def settings_(**kw):
    from django.core.cache import cache

    PlatformSettings.objects.update_or_create(pk=1, defaults=kw)
    cache.delete("platform:settings")


def book(turf, start, end, phone="01912345678", **extra):
    return APIClient().post(
        f"/api/public/turfs/{turf.slug}/book/",
        {
            "field": str(turf.fields.first().id),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "name": "Rafi",
            "phone": phone,
            **bkash(),
            **extra,
        },
        format="json",
    )


def day_at(days: int, hhmm: str):
    h, m = map(int, hhmm.split(":"))
    return local_dt(timezone.localdate() + timedelta(days=days), time(h, m))


def open_all_day(turf):
    turf.hours.update(opens_at=time(0, 0), closes_at=time(0, 0), is_closed=False)


# ====================================================================== SMS wallet 1-8
def test_1_7_8_wallets_are_isolated_and_visible_to_the_right_people():
    a, owner_a = make_turf()
    b, owner_b = make_turf("Beta Turf", "beta@example.com")
    queue_sms(to="01712345678", body="hello", kind="custom", turf=a)
    wa = client_for(owner_a).get("/api/workspace/sms/wallet/").json()
    wb = client_for(owner_b).get("/api/workspace/sms/wallet/").json()
    assert Decimal(wa["balance"]) == Decimal("99.65") and Decimal(wb["balance"]) == Decimal("100")
    ledger_a = client_for(owner_a).get("/api/workspace/sms/wallet/ledger/").json()["results"]
    assert [t["kind"] for t in ledger_a] == ["sms_charge", "admin_credit"]
    assert all("Beta" not in str(t) for t in ledger_a)
    admin, _ = admin_client()
    rows = {r["turf"]["name"]: r for r in admin.get("/api/admin/sms/wallets/").json()}
    assert Decimal(rows["Alpha Turf"]["sms_spent"]) == Decimal("0.35") and Decimal(
        rows["Beta Turf"]["balance"]
    ) == Decimal("100")
    assert client_for(owner_a).get("/api/admin/sms/wallets/").status_code == 403


def test_2_insufficient_balance_blocks_without_sending_or_charging():
    turf, owner = make_turf()
    empty_wallet(turf)
    m = queue_sms(to="01712345678", body="hi", kind="booking_confirmed", turf=turf)
    assert m.status == "blocked" and m.block_reason == "insufficient_balance"
    assert MemoryProvider.outbox == [] and m.charged_amount == 0
    w = client_for(owner).get("/api/workspace/sms/wallet/").json()
    assert w["blocked"]["insufficient_balance"] == 1 and w["insufficient_message_bn"].startswith(
        "আপনার SMS Wallet-এ"
    )
    wallet.credit(turf, 5, key="topup")
    retried = client_for(owner).post(f"/api/workspace/sms/messages/{m.pk}/retry/").json()
    assert retried["sent"] == 1 and balance(turf) == Decimal("4.65")


def test_3_4_one_charge_per_message_even_if_delivered_twice():
    turf, _ = make_turf()
    m = queue_sms(to="01712345678", body="hi", kind="custom", turf=turf)
    assert m.status == "sent" and m.charged_amount == Decimal("0.35")
    assert deliver(m.pk) is None  # second run / duplicate callback: refused
    assert WalletTransaction.objects.filter(sms=m).count() == 1 and balance(turf) == Decimal("99.65")
    entry = WalletTransaction.objects.get(sms=m)
    assert (
        entry.segments == 1
        and entry.price_per_segment == Decimal("0.35")
        and entry.amount == Decimal("-0.35")
    )
    with pytest.raises(ValueError):
        entry.note = "edited"
        entry.save()  # ledger is immutable


def test_5_provider_refusal_is_refunded_and_timeout_waits_for_review():
    turf, _ = make_turf()
    MemoryProvider.fail_with = "1002"  # permanent refusal
    m = queue_sms(to="01712345678", body="hi", kind="custom", turf=turf)
    assert m.status == "failed" and m.charged_amount == 0 and balance(turf) == Decimal("100")
    assert [t.kind for t in WalletTransaction.objects.filter(sms=m).order_by("id")] == [
        "sms_charge",
        "sms_refund",
    ]
    MemoryProvider.fail_with = None
    from apps.notifications import providers

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            providers.MemoryProvider,
            "send",
            lambda self, *a: providers.SendResult(False, "timeout", "no answer", False),
        )
        t = queue_sms(to="01812345678", body="hi", kind="custom", turf=turf)
    t.refresh_from_db()
    assert t.status == "unknown" and t.charged_amount == Decimal("0.35")  # kept until checked
    admin, _ = admin_client()
    assert admin.post(f"/api/admin/sms/messages/{t.pk}/refund/").status_code == 200
    assert balance(turf) == Decimal("100")


def test_6_bengali_segments_and_cost():
    assert segment_count("ক" * 70) == 1 and segment_count("ক" * 71) == 2 and segment_count("a" * 161) == 2
    turf, owner = make_turf()
    quote = (
        client_for(owner)
        .post("/api/workspace/sms/send/", {"to": "01712345678", "body": "ক" * 140}, format="json")
        .json()
    )
    assert (
        quote["segments"] == 3
        and quote["unicode"] is True
        and Decimal(quote["estimated_cost"]) == Decimal("1.05")
    )


# ====================================================================== bKash recharge 9-13
def test_9_10_12_13_recharge_fee_approval_duplicates_and_sms():
    settings_(recharge_bkash_number="01999000111", recharge_fee_percent=Decimal("1.90"))
    turf, owner = make_turf()
    owner.phone = "01712345678"
    owner.save()
    client = client_for(owner)
    q = client.get("/api/workspace/sms/wallet/recharge/", {"amount": "1000"}).json()
    assert (q["fee"], q["total"]) == ("19.00", "1019.00")
    wrong = client.post(
        "/api/workspace/sms/wallet/recharge/",
        {
            "wallet_amount": "1000",
            "amount_sent": "1000",
            "sender_number": "01712345678",
            "trx_id": "RCH0000001",
        },
        format="json",
    )
    assert wrong.status_code == 400 and "1,019" in str(wrong.json())
    ok = client.post(
        "/api/workspace/sms/wallet/recharge/",
        {
            "wallet_amount": "1000",
            "amount_sent": "1019",
            "sender_number": "01712345678",
            "trx_id": "RCH0000001",
        },
        format="json",
    )
    assert ok.status_code == 201 and balance(turf) == Decimal("100")  # nothing credited yet
    dup = client.post(
        "/api/workspace/sms/wallet/recharge/",
        {
            "wallet_amount": "1000",
            "amount_sent": "1019",
            "sender_number": "01712345678",
            "trx_id": "rch 0000001",
        },
        format="json",
    )
    assert dup.status_code == 400
    admin, _ = admin_client()
    rid = ok.json()["id"]
    assert admin.post(f"/api/admin/sms/recharges/{rid}/approve/").status_code == 200
    assert balance(turf) == Decimal("1100")  # wallet amount only — the ৳19 bKash charge is not wallet money
    assert admin.post(f"/api/admin/sms/recharges/{rid}/approve/").status_code == 400  # never twice
    assert WalletTransaction.objects.filter(kind="recharge").count() == 1
    sms = SmsMessage.objects.get(kind="wallet_credited")
    assert sms.scope == "platform" and "৳1,000" in sms.body and "৳1,100" in sms.body
    fin = admin.get("/api/admin/finance/").json()
    assert (
        fin["recharges"]["approved_amount"] == "1000.00"
        and fin["recharges"]["bkash_charges_collected"] == "19.00"
    )


def test_11_rejection_credits_nothing():
    settings_(recharge_bkash_number="01999000111")
    turf, owner = make_turf()
    r = (
        client_for(owner)
        .post(
            "/api/workspace/sms/wallet/recharge/",
            {
                "wallet_amount": "500",
                "amount_sent": "509.50",
                "sender_number": "01712345678",
                "trx_id": "RCH0000002",
            },
            format="json",
        )
        .json()
    )
    admin, _ = admin_client()
    rejected = admin.post(
        f"/api/admin/sms/recharges/{r['id']}/reject/", {"reason": "TrxID not found"}, format="json"
    ).json()
    assert rejected["status"] == "rejected" and balance(turf) == Decimal("100")
    assert SmsRechargeRequest.objects.get(pk=r["id"]).rejection_reason == "TrxID not found"


# ====================================================================== SMS sending 14-21
def test_14_single_sms_needs_confirmation_and_logs():
    turf, owner = make_turf()
    client = client_for(owner)
    estimate = client.post(
        "/api/workspace/sms/send/", {"to": "01712345678", "body": "Hello from Alpha"}, format="json"
    ).json()
    assert "id" not in estimate and MemoryProvider.outbox == []
    sent = client.post(
        "/api/workspace/sms/send/",
        {"to": "01712345678", "body": "Hello from Alpha", "confirm": True},
        format="json",
    )
    assert (
        sent.status_code == 201
        and sent.json()["status"] == "sent"
        and MemoryProvider.outbox[0]["body"] == "Hello from Alpha"
    )
    assert (
        client.post(
            "/api/workspace/sms/send/", {"to": "123", "body": "x", "confirm": True}, format="json"
        ).status_code
        == 400
    )


def test_15_16_17_bulk_campaign_variables_cost_and_tenant_isolation():
    turf, owner = make_turf()
    other, _ = make_turf("Beta Turf", "beta@example.com")
    for t, phone, hour in ((turf, "01711111111", 18), (other, "01822222222", 18)):
        book(t, tomorrow_at(hour), tomorrow_at(hour + 1), phone=phone)
    client = client_for(owner)
    template = "প্রিয় {{customer_name}}, {{turf_name}}-এ {{booking_date}} {{booking_id}}"
    body = {"template": template, "from_bookings": True, "numbers": "01733333333, 01733333333, 12345"}
    preview = client.post("/api/workspace/sms/campaigns/preview/", body, format="json").json()
    assert (
        preview["valid"] == 2 and preview["duplicates"] == 1 and preview["invalid"] == 1
    )  # Beta's customer absent
    sample = preview["samples"][0]["text"]
    assert sample.startswith("প্রিয় Rafi, Alpha Turf-এ") and "TRF-" in sample
    assert Decimal(preview["estimated_cost"]) == Decimal("0.30") * preview["segments"]
    bad = client.post(
        "/api/workspace/sms/campaigns/preview/", {**body, "template": "{{password}}"}, format="json"
    )
    assert bad.status_code == 400
    key = str(uuid.uuid4())
    created = client.post(
        "/api/workspace/sms/campaigns/",
        {**body, "name": "Eid offer", "confirm": True, "idempotency_key": key},
        format="json",
    )
    assert created.status_code == 201, created.json()
    again = client.post(
        "/api/workspace/sms/campaigns/",
        {**body, "name": "Eid offer", "confirm": True, "idempotency_key": key},
        format="json",
    )
    assert again.json()["id"] == created.json()["id"]  # double click: one campaign
    row = client.get(f"/api/workspace/sms/campaigns/{created.json()['id']}/").json()
    assert row["sent"] == 2 and Decimal(row["cost"]) == Decimal(preview["estimated_cost"])
    assert {m["to"] for m in MemoryProvider.outbox} == {"8801711111111", "8801733333333"}
    foreign = client.post(
        "/api/workspace/sms/campaigns/preview/",
        {"template": "x", "customer_ids": [str(other.customers.first().id)]},
        format="json",
    )
    assert foreign.json()["valid"] == 0


def test_18_19_admin_switches_block_sms_without_charging():
    turf, owner = make_turf()
    admin, _ = admin_client()
    admin.put(f"/api/admin/turfs/{turf.id}/sms/", {"bulk": False}, format="json")
    assert queue_sms(to="01712345678", body="x", kind="custom", turf=turf).status == "sent"  # single still on
    off = client_for(owner).post(
        "/api/workspace/sms/campaigns/preview/", {"template": "x", "numbers": "01712345678"}, format="json"
    )
    assert off.status_code == 200
    blocked_bulk = client_for(owner).post(
        "/api/workspace/sms/campaigns/",
        {
            "template": "x",
            "numbers": "01712345678",
            "name": "n",
            "confirm": True,
            "idempotency_key": str(uuid.uuid4()),
        },
        format="json",
    )
    assert blocked_bulk.status_code == 400
    admin.put(f"/api/admin/turfs/{turf.id}/sms/", {"all_enabled": False}, format="json")
    m = queue_sms(to="01712345678", body="x", kind="booking_confirmed", turf=turf)
    assert m.status == "blocked" and m.block_reason == "account_disabled" and m.charged_amount == 0
    w = client_for(owner).get("/api/workspace/sms/wallet/").json()
    assert w["sms_disabled"] is True and "প্রশাসক" in w["disabled_message_bn"]
    assert AuditEvent.objects.filter(action="platform.sms_controls", turf=turf).count() == 2
    assert (
        queue_sms(to="01712345678", body="code", kind="password_reset", turf=turf).status == "sent"
    )  # platform SMS separate


def test_20_21_owner_booking_sms_and_empty_wallet_never_blocks_booking():
    turf, owner = make_turf()
    client = client_for(owner)
    field = str(turf.fields.first().id)
    payload = {
        "field": field,
        "start": tomorrow_at(18).isoformat(),
        "end": tomorrow_at(19).isoformat(),
        "customer_name": "Walk In",
        "customer_phone": "01712345678",
        "status": "confirmed",
    }
    r = client.post("/api/workspace/bookings/", payload, format="json")
    assert r.status_code == 201 and r.json()["sms"]["status"] == "sent"
    sms = SmsMessage.objects.get(kind="owner_booking_confirmed")
    assert "কনফার্ম" in sms.body and r.json()["reference"] in sms.body
    empty_wallet(turf)
    r2 = client.post(
        "/api/workspace/bookings/",
        {**payload, "start": tomorrow_at(20).isoformat(), "end": tomorrow_at(21).isoformat()},
        format="json",
    )
    assert r2.status_code == 201 and r2.json()["status"] == "confirmed"
    assert (
        r2.json()["sms"]["status"] == "blocked" and r2.json()["sms"]["block_reason"] == "insufficient_balance"
    )


# ====================================================================== daily limit 22-27
def test_22_23_24_two_per_bangladesh_day_and_more_next_day():
    a, _ = make_turf()
    b, _ = make_turf("Beta Turf", "beta@example.com")
    open_all_day(a)
    open_all_day(b)
    assert book(a, day_at(1, "22:00"), day_at(1, "23:00")).status_code == 201
    assert book(b, day_at(1, "23:00"), day_at(2, "00:00")).status_code == 201  # starts 11 PM: still day 1
    third = book(a, day_at(1, "21:00"), day_at(1, "22:00"))
    assert third.status_code == 400 and DAILY_BN in str(third.json())
    from django.core.cache import cache

    cache.clear()  # the public booking rate limit is not what this test is about
    assert book(a, day_at(2, "00:00"), day_at(2, "01:00")).status_code == 201  # 12:00 AM next day: new day
    assert book(b, day_at(2, "06:00"), day_at(2, "07:00")).status_code == 201
    assert book(b, day_at(2, "08:00"), day_at(2, "09:00")).status_code == 400


def test_25_26_pending_counts_cancelled_rejected_expired_do_not():
    turf, owner = make_turf()
    first = book(turf, tomorrow_at(10), tomorrow_at(11)).json()
    second = book(turf, tomorrow_at(12), tomorrow_at(13)).json()  # both pending: limit reached
    assert book(turf, tomorrow_at(14), tomorrow_at(15)).status_code == 400
    sub = Booking.objects.get(reference=first["reference"]).payment_submission
    client_for(owner).post(f"/api/workspace/payment-verifications/{sub.pk}/reject/")
    assert book(turf, tomorrow_at(14), tomorrow_at(15)).status_code == 201
    Booking.objects.filter(reference=second["reference"]).update(
        hold_expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert book(turf, tomorrow_at(16), tomorrow_at(17)).status_code == 201


@pytest.mark.django_db(transaction=True)
def test_27_parallel_requests_cannot_beat_the_limit():
    from .conftest import reseed_reference_data

    reseed_reference_data()  # an earlier transactional test may have flushed districts and plans
    turf, _ = make_turf()
    settings_(max_slots_per_customer=1)
    results = []

    def go(hour):
        try:
            results.append(book(turf, tomorrow_at(hour), tomorrow_at(hour + 1)).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=go, args=(h,)) for h in (10, 12, 14)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 400, 400]


# ====================================================================== slot selection 28-30
def test_28_29_hold_is_fast_and_taken_slots_are_refused(django_assert_max_num_queries):
    turf, _ = make_turf()
    field = turf.fields.first()
    body = {"field": str(field.id), "start": tomorrow_at(18).isoformat(), "end": tomorrow_at(19).isoformat()}
    APIClient().post(
        f"/api/public/turfs/{turf.slug}/hold/",
        {**body, "start": tomorrow_at(6).isoformat(), "end": tomorrow_at(7).isoformat()},
        format="json",
        HTTP_X_VISITOR_ID=str(uuid.uuid4()),
    )
    with django_assert_max_num_queries(16):
        held = APIClient().post(
            f"/api/public/turfs/{turf.slug}/hold/", body, format="json", HTTP_X_VISITOR_ID=str(uuid.uuid4())
        )
    assert held.status_code in (200, 201)
    assert book(turf, tomorrow_at(20), tomorrow_at(21), phone="01812345678").status_code == 201
    taken = APIClient().post(
        f"/api/public/turfs/{turf.slug}/hold/",
        {**body, "start": tomorrow_at(20).isoformat(), "end": tomorrow_at(21).isoformat()},
        format="json",
        HTTP_X_VISITOR_ID=str(uuid.uuid4()),
    )
    assert taken.status_code == 409  # the optimistic tick in the browser is reverted


def test_30_resubmitting_a_restored_draft_does_not_duplicate():
    turf, _ = make_turf()
    key = str(uuid.uuid4())
    first = book(turf, tomorrow_at(18), tomorrow_at(19), HTTP_IDEMPOTENCY_KEY=key) if False else None  # noqa: F841
    c = APIClient()
    payload = {
        "field": str(turf.fields.first().id),
        "start": tomorrow_at(18).isoformat(),
        "end": tomorrow_at(19).isoformat(),
        "name": "R",
        "phone": "01912345678",
        **bkash(),
    }
    a = c.post(f"/api/public/turfs/{turf.slug}/book/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    b = c.post(f"/api/public/turfs/{turf.slug}/book/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert a.status_code == 201 and b.status_code == 200 and Booking.objects.count() == 1


# ====================================================================== subscriptions 31-38
def _pay(client, invoice, trx, amount):
    return client.post(
        f"/api/workspace/subscription/invoices/{invoice['id']}/manual-payment/",
        {"method": "bkash", "reference": trx, "sender_number": "01712345678", "amount_sent": amount},
        format="json",
    )


@override_settings(
    SUBSCRIPTION_PAYMENT_ACCOUNTS={"bkash": "01700000000", "nagad": "", "rocket": "", "bank": ""}
)
def test_31_to_38_renewal_and_plan_change_only_with_admin_approval():
    settings_(subscription_fee_percent=Decimal("1.50"))
    turf, owner = make_turf()
    owner.phone = "01712345678"
    owner.save()
    client = client_for(owner)
    before = standing(turf)
    renew = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json").json()
    assert Subscription.objects.get(invoice__id=renew["id"]).change_type == "renewal"
    low = _pay(client, renew, "SUBTRX0001", "100")
    assert low.status_code == 400  # monthly price + 1.5% charge expected
    price = Decimal(renew["amount"])
    total = price + (price * Decimal("0.015")).quantize(Decimal("0.01"))
    tx = _pay(client, renew, "SUBTRX0001", str(total))
    assert tx.status_code == 201
    assert standing(turf).paid_until == before.paid_until  # 33: nothing changes before approval
    admin, _ = admin_client()
    row = admin.get("/api/admin/payments/", {"status": "pending_verification"}).json()
    item = (row["results"] if isinstance(row, dict) else row)[0]
    assert item["change_type"] == "renewal" and item["payable"] == str(total) and item["current"]["plan"]
    assert admin.post(f"/api/admin/payments/{item['id']}/verify/").status_code == 200
    after = standing(turf)
    assert after.paid_until > before.paid_until  # 34: extends from the old expiry
    new_period = Subscription.objects.get(invoice__id=renew["id"])
    assert new_period.starts_on == before.paid_until + timedelta(days=1)
    approved_sms = SmsMessage.objects.get(kind="subscription_approved")
    assert (
        approved_sms.scope == "platform" and "রিনিউ" in approved_sms.body and balance(turf) == Decimal("100")
    )

    upgrade = client.post("/api/workspace/subscription/order/", {"plan": "yearly"}, format="json").json()
    assert Subscription.objects.get(invoice__id=upgrade["id"]).change_type == "upgrade"
    reused = _pay(client, upgrade, "SUBTRX0001", "999999")
    assert reused.status_code == 400  # 36: same TrxID can't pay twice
    _pay(client, upgrade, "SUBTRX0002", "999999")
    pending = PaymentTransaction.objects.get(reference="SUBTRX0002")
    admin.post(f"/api/admin/payments/{pending.pk}/reject/", {"note": "Not received"}, format="json")
    assert standing(turf).paid_until == after.paid_until  # 35: rejection leaves the plan alone
    assert Invoice.objects.get(pk=upgrade["id"]).status == "unpaid"
    assert SmsMessage.objects.filter(kind="subscription_rejected").exists()
    assert (
        AuditEvent.objects.filter(
            action__in=["subscription.payment_verified", "subscription.payment_rejected"], turf=turf
        ).count()
        == 2
    )
    assert Subscription.objects.filter(turf=turf).count() >= 3  # 38: history kept


def test_dates_use_bangladesh_calendar_not_utc():
    from apps.bookings.payments import day_bounds

    start, end = day_bounds(date(2026, 11, 20))
    assert start.utcoffset() == timedelta(hours=6) and (end - start) == timedelta(days=1)
    assert (
        start == datetime(2026, 11, 19, 18, 0, tzinfo=start.tzinfo).astimezone(start.tzinfo)
        or start.hour == 0
    )
