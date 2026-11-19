"""Promo codes: Super Admin creates percentage codes; owners apply them to an unpaid subscription invoice."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.subscriptions.models import Invoice, PromoCode
from apps.subscriptions.services import standing
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, client_for, make_turf
from .test_subscriptions import ACCOUNTS, admin_client

pytestmark = pytest.mark.django_db


def promo(code="WELCOME20", percent=20, **kw):
    return PromoCode.objects.create(code=code, percent_off=percent, **kw)


def order(client, plan="yearly"):
    r = client.post("/api/workspace/subscription/order/", {"plan": plan}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def apply(client, invoice, code):
    return client.post(
        f"/api/workspace/subscription/invoices/{invoice['id']}/promo/", {"code": code}, format="json"
    )


# ------------------------------------------------------------------ admin
def test_admin_creates_lists_edits_and_deletes_codes():
    admin, _ = admin_client()
    created = admin.post(
        "/api/admin/promo-codes/",
        {"code": " eid25 ", "percent_off": 25, "description": "Eid offer", "max_uses": 10},
        format="json",
    )
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["code"] == "EID25" and body["percent_off"] == 25 and body["times_used"] == 0
    assert body["is_running"] is True

    assert (
        admin.post("/api/admin/promo-codes/", {"code": "Eid25", "percent_off": 5}, format="json").status_code
        == 400
    )
    for bad in (0, 101):
        r = admin.post("/api/admin/promo-codes/", {"code": f"BAD{bad}", "percent_off": bad}, format="json")
        assert r.status_code == 400
    assert (
        admin.post(
            "/api/admin/promo-codes/", {"code": "has space", "percent_off": 5}, format="json"
        ).status_code
        == 400
    )
    today = timezone.localdate()
    backwards = admin.post(
        "/api/admin/promo-codes/",
        {
            "code": "BACK",
            "percent_off": 5,
            "valid_from": str(today),
            "valid_until": str(today - timedelta(days=1)),
        },
        format="json",
    )
    assert backwards.status_code == 400

    off = admin.patch(f"/api/admin/promo-codes/{body['id']}/", {"is_active": False}, format="json")
    assert off.status_code == 200 and off.json()["is_running"] is False
    assert [p["code"] for p in admin.get("/api/admin/promo-codes/").json()] == ["EID25"]
    assert AuditEvent.objects.filter(action="platform.promo_created").exists()

    assert admin.delete(f"/api/admin/promo-codes/{body['id']}/").status_code == 204
    assert not PromoCode.objects.exists()


def test_only_platform_admin_manages_codes():
    _, owner = make_turf()
    client = client_for(owner)
    assert client.get("/api/admin/promo-codes/").status_code == 403
    assert (
        client.post("/api/admin/promo-codes/", {"code": "X1X", "percent_off": 50}, format="json").status_code
        == 403
    )


def test_used_code_cannot_be_deleted_only_switched_off():
    turf, owner = make_turf()
    code = promo()
    apply(client_for(owner), order(client_for(owner)), "WELCOME20")
    admin, _ = admin_client()
    assert admin.delete(f"/api/admin/promo-codes/{code.id}/").status_code == 400
    assert admin.get("/api/admin/promo-codes/").json()[0]["times_used"] == 1


# ------------------------------------------------------------------ owner
@override_settings(SUBSCRIPTION_PAYMENT_ACCOUNTS=ACCOUNTS)
def test_valid_code_discounts_the_invoice_and_payment_uses_the_new_amount():
    turf, owner = make_turf()
    client = client_for(owner)
    promo()
    invoice = order(client)  # yearly 15000
    applied = apply(client, invoice, " welcome20 ")
    assert applied.status_code == 200, applied.json()
    body = applied.json()
    assert (
        body["amount"] == "12000.00" and body["discount"] == "3000.00" and body["list_amount"] == "15000.00"
    )
    assert body["promo_code"] == {"code": "WELCOME20", "percent_off": 20}
    assert Invoice.objects.get(pk=invoice["id"]).subscription.price == Decimal("12000.00")
    assert client.get("/api/workspace/subscription/").json()["open_invoice"]["amount"] == "12000.00"

    pay = client.post(
        f"/api/workspace/subscription/invoices/{invoice['id']}/manual-payment/",
        {"method": "bkash", "reference": "PROMO12345"},
        format="json",
    )
    assert pay.status_code == 201 and pay.json()["amount"] == "12000.00"
    assert AuditEvent.objects.filter(action="subscription.promo_applied", turf=turf).exists()


def test_removing_the_code_restores_the_price_and_codes_do_not_stack():
    _, owner = make_turf()
    client = client_for(owner)
    promo()
    promo("BIG50", 50)
    invoice = order(client)
    apply(client, invoice, "WELCOME20")
    swapped = apply(client, invoice, "BIG50").json()  # replaces, priced from the plan price
    assert swapped["amount"] == "7500.00" and swapped["discount"] == "7500.00"
    removed = client.delete(f"/api/workspace/subscription/invoices/{invoice['id']}/promo/").json()
    assert removed["amount"] == "15000.00" and removed["discount"] == "0.00" and removed["promo_code"] is None


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"is_active": False}, "not valid"),
        ({"valid_until": timezone.localdate() - timedelta(days=1)}, "expired"),
        ({"valid_from": timezone.localdate() + timedelta(days=3)}, "starts on"),
    ],
)
def test_unusable_codes_are_refused(kwargs, message):
    _, owner = make_turf()
    client = client_for(owner)
    promo(**kwargs)
    invoice = order(client)
    r = apply(client, invoice, "WELCOME20")
    assert r.status_code == 400 and message in str(r.json())
    assert apply(client, invoice, "NOPE").status_code == 400
    assert Invoice.objects.get(pk=invoice["id"]).amount == Decimal("15000.00")


def test_usage_limit_counts_open_and_paid_invoices_and_cancelling_releases():
    promo(max_uses=1)
    _, a_owner = make_turf("Alpha", "a@example.com")
    _, b_owner = make_turf("Beta", "b@example.com")
    a, b = client_for(a_owner), client_for(b_owner)
    a_invoice = order(a)
    assert apply(a, a_invoice, "WELCOME20").status_code == 200
    b_invoice = order(b)
    full = apply(b, b_invoice, "WELCOME20")
    assert full.status_code == 400 and "fully used" in str(full.json())
    a.post(f"/api/workspace/subscription/invoices/{a_invoice['id']}/cancel/")
    assert apply(b, b_invoice, "WELCOME20").status_code == 200


def test_a_turf_can_pay_with_a_code_only_once():
    turf, owner = make_turf()
    client = client_for(owner)
    promo()
    from apps.subscriptions.services import mark_paid

    first = order(client)
    apply(client, first, "WELCOME20")
    mark_paid(Invoice.objects.get(pk=first["id"]))
    second = order(client, "monthly")
    again = apply(client, second, "WELCOME20")
    assert again.status_code == 400 and "already used" in str(again.json())


def test_full_discount_activates_the_plan_without_payment():
    turf, owner = make_turf()
    client = client_for(owner)
    promo("FREE100", 100)
    Invoice.objects.filter(turf=turf).update(status="cancelled")  # pretend the turf has no paid time
    turf.subscriptions.update(status="cancelled")
    invoice = order(client, "monthly")
    body = apply(client, invoice, "FREE100").json()
    assert body["amount"] == "0.00" and body["status"] == "paid"
    assert body["transactions"][0]["method"] == "promo"
    assert standing(turf).state == "active"


def test_code_cannot_change_once_payment_is_under_review():
    _, owner = make_turf()
    client = client_for(owner)
    promo()
    invoice = order(client)
    Invoice.objects.filter(pk=invoice["id"]).update(status="pending_verification")
    assert apply(client, invoice, "WELCOME20").status_code == 400


def test_manager_and_other_turfs_cannot_apply_codes():
    turf, _ = make_turf()
    promo()
    beta, beta_owner = make_turf("Beta", "beta@example.com")
    invoice = order(client_for(beta_owner))
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=beta, role=TenantMembership.Role.MANAGER)
    assert apply(client_for(manager), invoice, "WELCOME20").status_code == 403
    _, alpha_owner = make_turf("Alpha", "alpha@example.com")
    assert apply(client_for(alpha_owner), invoice, "WELCOME20").status_code == 404
