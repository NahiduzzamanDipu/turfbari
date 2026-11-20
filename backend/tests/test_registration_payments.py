"""Registration with plan, promo code and bKash payment verified by TurfBari (spec section 13)."""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import RegistrationPayment, TurfApplication
from apps.applications.registration import expire_reservations
from apps.common.models import PlatformSettings
from apps.subscriptions.models import Invoice, Plan, PromoCode, PromoRedemption, Subscription
from apps.subscriptions.promos import discount_for
from apps.turfs.models import Turf

from .test_core import client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db
_n = iter(range(10_000, 99_999))


def bkash_on():
    PlatformSettings.objects.update_or_create(pk=1, defaults={"subscription_bkash_number": "01999000111"})
    cache.delete("platform:settings")


def monthly() -> Plan:
    return Plan.objects.get(period="monthly")


def promo(code="TURFSTART20", **kw) -> PromoCode:
    defaults = {"discount_type": "percent", "percent_off": 20}
    defaults.update(kw)
    plans = defaults.pop("plans", None)
    p = PromoCode.objects.create(code=code, **defaults)
    if plans:
        p.plans.set(plans)
    return p


def quote(code="", plan="monthly", **extra):
    return APIClient().post(
        "/api/public/registration/quote/", {"plan": plan, "promo_code": code, **extra}, format="json"
    )


def register(code="", amount=None, trx=None, phone="01755000010", email="sadia@example.com", **extra):
    payable = (
        Decimal(quote(code, phone=phone, email=email).json().get("payable", "0"))
        if amount is None
        else amount
    )
    body = {
        "turf_name": "New Ground",
        "owner_name": "Sadia",
        "phone": phone,
        "email": email,
        "district": "dhaka",
        "address": "Road 5",
        "turf_type": "outdoor",
        "number_of_fields": 2,
        "plan": "monthly",
        "promo_code": code,
        "sender_number": "01811000000",
        "amount_sent": str(payable),
        "trx_id": trx or f"REG{next(_n)}X",
        **extra,
    }
    # Each submission from its own address: the real per-IP limit (3/hour) is tested separately.
    ip = f"10.0.{next(_n) % 250}.{next(_n) % 250}"
    return APIClient().post("/api/public/applications/", body, format="json", REMOTE_ADDR=ip)


@pytest.fixture(autouse=True)
def _payments_open():
    bkash_on()


# ------------------------------------------------------------------ promo validation
def test_promo_rules_percent_fixed_caps_and_messages():
    plan = monthly()
    price = plan.price
    p = promo("PCT", percent_off=50, max_discount=Decimal("300"))
    assert discount_for(p, price) == Decimal("300.00")  # capped
    f = promo("FIX", discount_type="fixed", percent_off=0, amount_off=Decimal("500"))
    assert discount_for(f, Decimal("400")) == Decimal("400.00")  # never more than the price
    q = quote("fix").json()
    assert q["original"] == str(price) and q["discount"] == "500.00" and q["payable"] == str(price - 500)
    assert q["promo"]["code"] == "FIX" and q["receiving"]["number"] == "01999000111"
    today = timezone.localdate()
    promo("OLD", valid_until=today - timedelta(days=1))
    promo("OFF", is_active=False)
    promo("SOON", valid_from=today + timedelta(days=2))
    promo("YEARLY", plans=[Plan.objects.get(period="yearly")])
    promo("BIG", min_amount=price + 1)
    promo("ONE", max_uses=1)
    expected = {
        "NOPE": "Invalid promo code.",
        "OLD": "This promo code has expired.",
        "OFF": "This promo code is not active.",
        "SOON": "This promo code is not active yet.",
        "YEARLY": "This promo code isn't valid for the selected plan.",
        "BIG": "This promo code needs a larger plan.",
    }
    for code, message in expected.items():
        r = quote(code)
        assert r.status_code == 400 and r.json()["error"]["fields"]["promo_code"] == [message], code
    assert quote("YEARLY", plan="yearly").status_code == 200
    assert register("ONE").status_code == 201
    used = quote("ONE", phone="01755000099", email="x@example.com")
    assert used.json()["error"]["fields"]["promo_error"] == ["used_up"]


# ------------------------------------------------------------------ submission
def test_submission_reserves_the_code_and_awaits_verification_without_any_account():
    p = promo()
    r = register("turfstart20")
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["status"] == "payment_review" and body["reference"].startswith("REG-")
    assert body["promo_code"] == "TURFSTART20" and Decimal(body["discount"]) == monthly().price * Decimal(
        "0.2"
    )
    assert "•••" in body["trx"]
    app = TurfApplication.objects.get()
    pay = app.payments.get()
    assert pay.status == "pending_verification" and pay.receiving_number == "01999000111"
    assert pay.promo_snapshot["code"] == "TURFSTART20" and pay.promo_snapshot["final"] == str(pay.amount_due)
    assert PromoRedemption.objects.get().status == "reserved"
    assert not get_user_model().objects.filter(email="sadia@example.com").exists()  # nothing activated
    assert not Turf.objects.filter(name="New Ground").exists()
    # Status page: reference + the same mobile number; anything else finds nothing.
    ok = APIClient().post(
        "/api/public/registration/status/",
        {"reference": body["reference"], "phone": "01755000010"},
        format="json",
    )
    assert ok.status_code == 200 and ok.json()["status_label"] == "Payment under review"
    bad = APIClient().post(
        "/api/public/registration/status/",
        {"reference": body["reference"], "phone": "01711111111"},
        format="json",
    )
    assert bad.status_code == 404
    # A second registration for the same person while one is under review is refused.
    again = register(phone="01755000010", email="other@example.com")
    assert again.status_code == 400
    assert p.redemptions.count() == 1


def test_wrong_amount_tampered_price_and_duplicate_trx_are_refused():
    promo()
    payable = Decimal(quote("TURFSTART20").json()["payable"])
    full = register("TURFSTART20", amount=monthly().price)  # sent the undiscounted price
    assert full.status_code == 400 and "amount_sent" in full.json()["error"]["fields"]
    tampered = register("TURFSTART20", amount=Decimal("1"))
    assert tampered.status_code == 400
    changed = register("TURFSTART20", amount=payable, expected_payable="10")
    assert changed.status_code == 400 and changed.json()["error"]["fields"]["code"] == ["price_changed"]
    assert register("TURFSTART20", trx="ABC12345XY").status_code == 201
    dup = register(trx="ABC12345XY", phone="01755000011", email="b@example.com")
    assert dup.status_code == 400 and "already submitted" in str(dup.json())
    bad_phone = register(phone="01755000012", email="c@example.com", sender_number="12345")
    assert bad_phone.status_code == 400 and "sender_number" in bad_phone.json()["error"]["fields"]
    assert RegistrationPayment.objects.count() == 1 and PromoRedemption.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_claims_cannot_exceed_the_limit():
    from .conftest import reseed_reference_data

    reseed_reference_data()
    bkash_on()
    promo("LAST1", max_uses=1)
    codes = []

    def go(i):
        try:
            codes.append(register("LAST1", phone=f"0175500002{i}", email=f"p{i}@example.com").status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=go, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [201, 400, 400]
    assert PromoRedemption.objects.filter(status="reserved").count() == 1


# ------------------------------------------------------------------ admin approval
def test_approval_activates_account_plan_and_redeems_the_promo_once():
    promo()
    body = register("TURFSTART20").json()
    pay = RegistrationPayment.objects.get()
    admin, me = admin_client()
    _, owner = make_turf()
    assert client_for(owner).post(f"/api/admin/registration-payments/{pay.pk}/approve/").status_code == 403
    assert APIClient().post(f"/api/admin/registration-payments/{pay.pk}/approve/").status_code in (401, 403)
    listed = admin.get("/api/admin/registration-payments/", {"q": body["reference"]}).json()
    assert listed["count"] == 1 and listed["results"][0]["trx_id"] == pay.trx_id
    assert listed["report"]["pending"] == 1 and listed["report"]["revenue"] == "0.00"  # pending isn't revenue
    r = admin.post(
        f"/api/admin/registration-payments/{pay.pk}/approve/", {"note": "Seen in bKash app"}, format="json"
    )
    assert r.status_code == 200, r.json()
    assert r.json()["status"] == "approved" and r.json()["temporary_password"] is None
    assert r.json()["credential"]["status"] == "submitted"  # login details SMS
    turf = Turf.objects.get(name="New Ground")
    sub = Subscription.objects.get(turf=turf)
    inv = Invoice.objects.get(turf=turf)
    assert sub.status == "active" and sub.starts_on == timezone.localdate()
    assert inv.status == "paid" and inv.amount == pay.amount_due and inv.discount == pay.discount
    assert inv.promo_code.code == "TURFSTART20"
    assert PromoRedemption.objects.get().status == "redeemed"
    assert TurfApplication.objects.get().status == "approved"
    pay.refresh_from_db()
    assert pay.reviewed_by == me and pay.review_note == "Seen in bKash app"
    again = admin.post(f"/api/admin/registration-payments/{pay.pk}/approve/")
    assert again.json()["duplicate"] is True and Subscription.objects.filter(turf=turf).count() == 1
    report = admin.get("/api/admin/registration-payments/").json()["report"]
    assert (
        report["approved"] == 1
        and report["revenue"] == str(pay.amount_sent)
        and report["discounts"] == str(pay.discount)
    )
    assert report["by_promo"][0]["code"] == "TURFSTART20"
    # The promo counts one use (the paid invoice), not two.
    stats = admin.get("/api/admin/promo-codes/").json()[0]["stats"]
    assert stats["times_used"] == 1 and stats["redeemed"] == 1 and stats["reserved"] == 0
    # Old "approve application" can't bypass the payment check.
    app2 = register(phone="01755000030", email="z@example.com").json()
    app = TurfApplication.objects.get(reference=app2["reference"])
    assert admin.post(f"/api/admin/applications/{app.pk}/approve/", {}, format="json").status_code == 400


# ------------------------------------------------------------------ rejection & resubmission
def test_rejection_shows_reason_allows_correction_and_keeps_history():
    promo()
    body = register("TURFSTART20").json()
    pay = RegistrationPayment.objects.get()
    admin, _ = admin_client()
    assert (
        admin.post(
            f"/api/admin/registration-payments/{pay.pk}/reject/", {"reason": ""}, format="json"
        ).status_code
        == 400
    )
    admin.post(
        f"/api/admin/registration-payments/{pay.pk}/reject/",
        {"reason": "TrxID not found in our bKash"},
        format="json",
    )
    status = (
        APIClient()
        .post(
            "/api/public/registration/status/",
            {"reference": body["reference"], "phone": "01755000010"},
            format="json",
        )
        .json()
    )
    assert status["rejection_reason"] == "TrxID not found in our bKash" and status["can_resubmit"] is True
    assert PromoRedemption.objects.get().status == "reserved"  # kept for the corrected payment
    assert not get_user_model().objects.filter(email="sadia@example.com").exists()
    resub = APIClient().post(
        "/api/public/registration/resubmit/",
        {
            "reference": body["reference"],
            "phone": "01755000010",
            "sender_number": "01811000000",
            "amount_sent": str(pay.amount_due),
            "trx_id": "FIXED1234A",
        },
        format="json",
    )
    assert resub.status_code == 200, resub.json()
    assert resub.json()["status"] == "payment_review" and len(resub.json()["history"]) == 2
    assert RegistrationPayment.objects.count() == 2  # rejected one kept
    new = RegistrationPayment.objects.filter(status="pending_verification").get()
    admin.post(
        f"/api/admin/registration-payments/{new.pk}/reject/",
        {"reason": "Duplicate business", "allow_resubmit": False},
        format="json",
    )
    assert PromoRedemption.objects.get().status == "released"
    assert TurfApplication.objects.get().status == "rejected"


def test_reservations_expire_and_snapshots_never_change():
    p = promo(reservation_hours=1)
    body = register("TURFSTART20").json()
    pay = RegistrationPayment.objects.get()
    admin, _ = admin_client()
    admin.post(
        f"/api/admin/registration-payments/{pay.pk}/reject/", {"reason": "Wrong amount"}, format="json"
    )
    PromoRedemption.objects.update(reserved_until=timezone.now() - timedelta(minutes=1))
    assert expire_reservations()["expired_promo_reservations"] == 1
    assert PromoRedemption.objects.get().status == "expired"
    # A payment still under review keeps its reservation even past the hold time.
    register("TURFSTART20", phone="01755000040", email="q@example.com")
    PromoRedemption.objects.filter(status="reserved").update(
        reserved_until=timezone.now() - timedelta(minutes=1)
    )
    assert expire_reservations()["expired_promo_reservations"] == 0
    # Editing or archiving the code never rewrites what was submitted.
    p.percent_off = 90
    p.save()
    admin.patch(f"/api/admin/promo-codes/{p.pk}/", {"is_archived": True}, format="json")
    pay.refresh_from_db()
    assert pay.promo_snapshot["percent_off"] == 20 and pay.discount == monthly().price * Decimal("0.2")
    assert quote("TURFSTART20").json()["error"]["fields"]["promo_code"] == ["Invalid promo code."]
    assert body["reference"]


# ------------------------------------------------------------------ eligibility
def test_new_registration_codes_and_per_person_limits():
    promo("NEWONLY", new_registrations_only=True)
    turf, owner = make_turf()
    client = client_for(owner)
    inv = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json").json()
    used = client.post(
        f"/api/workspace/subscription/invoices/{inv['id']}/promo/", {"code": "NEWONLY"}, format="json"
    )
    assert used.status_code == 400 and "new turf registrations" in str(used.json())
    existing = quote("NEWONLY", email=owner.email, phone="01755000050")
    assert existing.status_code == 400 and existing.json()["error"]["fields"]["promo_error"] == ["new_only"]
    assert register("NEWONLY").status_code == 201  # a brand-new person may use it
    # One person (phone or email) can't take the same code twice, even while the first is pending.
    promo("TWICE")
    assert register("TWICE", phone="01755000061", email="t@example.com").status_code == 201
    twice = quote("TWICE", phone="01755000061", email="other2@example.com")
    assert twice.status_code == 400 and twice.json()["error"]["fields"]["promo_error"] == ["already_used"]


def test_submissions_are_rate_limited_per_address():
    body = {"plan": "monthly", "turf_name": "X"}
    codes = [
        APIClient().post("/api/public/applications/", body, format="json", REMOTE_ADDR="10.9.9.9").status_code
        for _ in range(4)
    ]
    assert codes[-1] == 429


def test_full_discount_needs_no_bkash_but_still_needs_approval():
    promo("FREE", percent_off=100)
    body = register("FREE", trx="", sender_number="", amount=Decimal("0")).json()
    assert body["payable"] == "0.00" and body["status"] == "payment_review"
    pay = RegistrationPayment.objects.get()
    assert pay.trx_id is None and pay.method == "promo"
    admin, _ = admin_client()
    assert admin.post(f"/api/admin/registration-payments/{pay.pk}/approve/").status_code == 200
    assert Invoice.objects.get(turf__name="New Ground").status == "paid"
