"""Plans, prepaid (never auto-renewing) subscriptions, payments, gating, admin tools, slot board."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import TurfApplication
from apps.bookings.models import Booking, MaintenanceBlock
from apps.bookings.services import get_or_create_customer, reserve_slot
from apps.locations.models import District
from apps.subscriptions import gateway
from apps.subscriptions.models import Invoice, PaymentTransaction, Plan, Subscription
from apps.subscriptions.services import create_order, period_end, standing
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, booking_payload, client_for, make_turf, tomorrow_at

pytestmark = pytest.mark.django_db
ACCOUNTS = {"bkash": "01700000000", "nagad": "01800000000", "rocket": "", "bank": ""}


def admin_client():
    admin = get_user_model().objects.create_superuser("boss@example.com", PASSWORD)
    return client_for(admin), admin


def set_period(turf, start, end):
    sub = Subscription.objects.get(turf=turf, status="active")
    sub.starts_on, sub.ends_on = start, end
    sub.save()
    return sub


def is_public(turf):
    return APIClient().get(f"/api/public/turfs/{turf.slug}/").status_code == 200


# ------------------------------------------------------------------ basics
def test_new_turf_gets_paid_monthly_plan_by_default():
    turf, _ = make_turf()
    s = standing(turf)
    assert s.state == "active" and s.current.plan.period == "monthly"
    today = timezone.localdate()
    assert (s.current.starts_on, s.current.ends_on) == (today, period_end(today, 1))
    assert Invoice.objects.get(turf=turf).status == "paid"


def test_period_end_handles_month_lengths():
    from datetime import date

    assert period_end(date(2026, 1, 31), 1) == date(2026, 2, 27)
    assert period_end(date(2026, 1, 1), 6) == date(2026, 6, 30)
    assert period_end(date(2026, 3, 15), 12) == date(2027, 3, 14)


# ------------------------------------------------------------------ unpaid start -> pay -> active
@override_settings(SUBSCRIPTION_PAYMENT_ACCOUNTS=ACCOUNTS)
def test_unpaid_turf_is_paused_until_manual_payment_verified():
    from apps.applications.services import create_turf_with_owner

    turf, owner, _ = create_turf_with_owner(
        name="Unpaid Turf",
        district=District.objects.get(slug="dhaka"),
        area=None,
        address="Road 9",
        turf_type="outdoor",
        owner_email="unpaid@example.com",
        owner_name="Owner",
        owner_phone="+8801711000009",
        plan=Plan.objects.get(period="yearly"),
        payment_received=False,
    )
    turf.is_listed = True
    turf.save()
    client = client_for(owner)

    assert standing(turf).state == "none" and not is_public(turf)
    blocked = client.post("/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json")
    assert blocked.status_code == 402 and blocked.json()["error"]["code"] == "subscription_inactive"

    overview = client.get("/api/workspace/subscription/").json()
    invoice = overview["open_invoice"]
    assert invoice["subscription"]["plan"]["period"] == "yearly" and invoice["amount"] == "15000.00"
    assert [m["method"] for m in overview["payment_options"]["manual"]] == ["bkash", "nagad"]
    assert overview["standing"]["auto_renew"] is False

    paid = client.post(
        f"/api/workspace/subscription/invoices/{invoice['id']}/manual-payment/",
        {"method": "bkash", "reference": "9bg7xk2lq1", "sender_number": "01711111111"},
        format="json",
    )
    assert paid.status_code == 201, paid.json()
    assert standing(turf).state == "none"  # not active until TurfBari verifies

    admin, _ = admin_client()
    queue = admin.get("/api/admin/payments/?status=pending_verification").json()["results"]
    assert [p["reference"] for p in queue] == ["9BG7XK2LQ1"]
    assert admin.post(f"/api/admin/payments/{queue[0]['id']}/verify/").status_code == 200

    s = standing(turf)
    assert s.state == "active" and s.current.plan.period == "yearly"
    assert is_public(turf)
    ok = client.post("/api/workspace/bookings/", booking_payload(turf.fields.first().id), format="json")
    assert ok.status_code == 201


@override_settings(SUBSCRIPTION_PAYMENT_ACCOUNTS=ACCOUNTS)
def test_manual_payment_rules():
    turf, owner = make_turf()
    client = client_for(owner)
    invoice = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json").json()
    url = f"/api/workspace/subscription/invoices/{invoice['id']}/manual-payment/"

    bad_method = client.post(url, {"method": "rocket", "reference": "ABC12345"}, format="json")
    assert bad_method.status_code == 400  # rocket has no account configured
    bad_ref = client.post(url, {"method": "bkash", "reference": "x"}, format="json")
    assert bad_ref.status_code == 400

    first = client.post(url, {"method": "bkash", "reference": "TRX1234567"}, format="json")
    assert first.status_code == 201
    again = client.post(url, {"method": "bkash", "reference": "TRX1234567"}, format="json")
    assert again.status_code == 400  # invoice is under review now

    # Rejected -> invoice reopens; the same TrxID can't be reused by another turf while claimed.
    admin, _ = admin_client()
    tx = PaymentTransaction.objects.get(reference="TRX1234567")
    admin.post(f"/api/admin/payments/{tx.id}/reject/", {"note": "Not found"}, format="json")
    assert Invoice.objects.get(pk=invoice["id"]).status == "unpaid"

    other_turf, other_owner = make_turf("Other", "other@example.com")
    other_invoice = create_order(other_turf, Plan.objects.get(period="monthly"))
    tx2 = client_for(other_owner).post(
        f"/api/workspace/subscription/invoices/{other_invoice.id}/manual-payment/",
        {"method": "bkash", "reference": "TRX1234567"},
        format="json",
    )
    assert tx2.status_code == 201  # rejected IDs are released
    third = client.post(url, {"method": "bkash", "reference": "TRX1234567"}, format="json")
    assert third.status_code == 400 and "already been submitted" in str(third.json())


def test_renewal_is_queued_after_paid_time_and_never_automatic():
    turf, owner = make_turf()
    current = Subscription.objects.get(turf=turf, status="active")
    client = client_for(owner)
    invoice = client.post("/api/workspace/subscription/order/", {"plan": "half_yearly"}, format="json").json()
    # Switching choice replaces the unpaid order instead of stacking orders.
    invoice = client.post("/api/workspace/subscription/order/", {"plan": "yearly"}, format="json").json()
    assert Invoice.objects.filter(turf=turf, status="unpaid").count() == 1

    admin, _ = admin_client()
    from apps.subscriptions.services import mark_paid

    mark_paid(Invoice.objects.get(pk=invoice["id"]))
    nxt = Subscription.objects.get(invoice__id=invoice["id"])
    assert nxt.starts_on == current.ends_on + timedelta(days=1)
    assert nxt.ends_on == period_end(nxt.starts_on, 12)
    assert standing(turf).current == current  # current period unchanged
    periods = client.get("/api/workspace/subscription/").json()["periods"]
    assert {p["state"] for p in periods} == {"current", "scheduled"}

    # After everything ends nothing renews by itself.
    count = Subscription.objects.count()
    standing(turf, today=nxt.ends_on + timedelta(days=30))
    assert Subscription.objects.count() == count


def test_expiry_grace_then_paused():
    turf, owner = make_turf()
    client = client_for(owner)
    today = timezone.localdate()
    payload = booking_payload(turf.fields.first().id)

    set_period(turf, today - timedelta(days=40), today - timedelta(days=2))  # ended 2 days ago
    assert standing(turf).state == "grace" and is_public(turf)
    assert client.post("/api/workspace/bookings/", payload, format="json").status_code == 201

    set_period(turf, today - timedelta(days=40), today - timedelta(days=5))  # past the 3-day grace
    assert standing(turf).state == "expired" and not is_public(turf)
    payload2 = booking_payload(turf.fields.first().id, start_hour=20)
    assert client.post("/api/workspace/bookings/", payload2, format="json").status_code == 402
    assert client.get("/api/workspace/bookings/").status_code == 200  # history stays readable
    # Renewing still works while paused.
    assert (
        client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json").status_code
        == 201
    )


def test_expiring_soon_state():
    turf, _ = make_turf()
    today = timezone.localdate()
    set_period(turf, today - timedelta(days=25), today + timedelta(days=4))
    s = standing(turf)
    assert s.state == "expiring" and s.days_left == 4


def test_manager_can_view_but_not_change_plan():
    turf, _ = make_turf()
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=turf, role=TenantMembership.Role.MANAGER)
    client = client_for(manager)
    assert client.get("/api/workspace/subscription/").status_code == 200
    assert (
        client.post("/api/workspace/subscription/order/", {"plan": "yearly"}, format="json").status_code
        == 403
    )


def test_cannot_touch_another_turfs_invoice():
    _, alpha_owner = make_turf()
    beta, _ = make_turf("Beta", "beta@example.com")
    invoice = create_order(beta, Plan.objects.get(period="monthly"))
    response = client_for(alpha_owner).post(f"/api/workspace/subscription/invoices/{invoice.id}/cancel/")
    assert response.status_code == 404


# ------------------------------------------------------------------ admin
def test_admin_sees_plans_filters_and_assigns():
    yearly_turf, _ = make_turf("Yearly Turf", "y@example.com")
    monthly_turf, _ = make_turf("Monthly Turf", "m@example.com")
    admin, _ = admin_client()
    response = admin.post(
        f"/api/admin/turfs/{yearly_turf.id}/assign-plan/", {"plan": "yearly", "paid": True}, format="json"
    )
    assert response.status_code == 200
    # Paid yearly queues after the running monthly period.
    assert response.json()["standing"]["plan"]["period"] == "monthly"
    # Move time on: the monthly period is over and the yearly one is running.
    today = timezone.localdate()
    Subscription.objects.filter(turf=yearly_turf, plan__period="monthly").update(
        starts_on=today - timedelta(days=60), ends_on=today - timedelta(days=31)
    )
    Subscription.objects.filter(turf=yearly_turf, plan__period="yearly").update(
        starts_on=today - timedelta(days=30)
    )

    rows = admin.get("/api/admin/turfs/").json()["results"]
    plans = {r["name"]: r["subscription"]["plan"]["period"] for r in rows}
    assert plans == {"Yearly Turf": "yearly", "Monthly Turf": "monthly"}
    only_yearly = admin.get("/api/admin/turfs/?plan=yearly").json()["results"]
    assert [r["name"] for r in only_yearly] == ["Yearly Turf"]
    dash = admin.get("/api/admin/dashboard/").json()
    assert {p["period"]: p["turfs"] for p in dash["plans"]} == {"monthly": 1, "half_yearly": 0, "yearly": 1}
    assert monthly_turf.name in [
        r["name"] for r in admin.get("/api/admin/turfs/?plan=monthly").json()["results"]
    ]


def test_admin_picks_plan_when_creating_and_approving():
    admin, _ = admin_client()
    created = admin.post(
        "/api/admin/turfs/",
        {
            "name": "Admin Made",
            "district": "dhaka",
            "address": "Road 5",
            "owner_email": "made@example.com",
            "owner_name": "Made",
            "owner_phone": "01711000055",
            "plan": "half_yearly",
            "payment_received": True,
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    assert created.json()["turf"]["subscription"]["plan"]["period"] == "half_yearly"

    application = TurfApplication.objects.create(
        turf_name="Applied Turf",
        owner_name="Applicant",
        phone="+8801711000066",
        email="applied@example.com",
        district=District.objects.get(slug="dhaka"),
        address="Road 6",
        number_of_fields=1,
    )
    approved = admin.post(
        f"/api/admin/applications/{application.id}/approve/",
        {"plan": "yearly", "payment_received": False},
        format="json",
    )
    assert approved.status_code == 200, approved.json()
    invoice = Invoice.objects.get(turf__name="Applied Turf")
    assert invoice.status == "unpaid" and invoice.subscription.plan.period == "yearly"


def test_admin_edits_plan_price_for_new_orders_only():
    turf, _ = make_turf()
    admin, _ = admin_client()
    monthly = Plan.objects.get(period="monthly")
    assert (
        admin.patch(f"/api/admin/plans/{monthly.id}/", {"price": "2000.00"}, format="json").status_code == 200
    )
    assert Subscription.objects.get(turf=turf, status="active").price == Decimal("1500.00")
    assert create_order(turf, Plan.objects.get(period="monthly")).amount == Decimal("2000.00")
    assert admin.patch(f"/api/admin/plans/{monthly.id}/", {"price": "0"}, format="json").status_code == 400


def test_plan_and_payment_admin_endpoints_need_admin():
    _, owner = make_turf()
    client = client_for(owner)
    assert client.get("/api/admin/plans/").status_code == 403
    assert client.get("/api/admin/payments/").status_code == 403


# ------------------------------------------------------------------ online gateway (SSLCommerz)
GATEWAY_SETTINGS = {
    "SSLCOMMERZ_STORE_ID": "testbox",
    "SSLCOMMERZ_STORE_PASSWORD": "qwerty",
    "SSLCOMMERZ_SANDBOX": True,
}


@override_settings(**GATEWAY_SETTINGS)
def test_online_payment_flow_is_validated_server_side():
    turf, owner = make_turf()
    client = client_for(owner)
    invoice = client.post("/api/workspace/subscription/order/", {"plan": "yearly"}, format="json").json()

    with mock.patch.object(
        gateway, "_post", return_value={"status": "SUCCESS", "GatewayPageURL": "https://sandbox.example/pay"}
    ) as post:
        start = client.post(f"/api/workspace/subscription/invoices/{invoice['id']}/pay-online/")
    assert start.status_code == 200 and start.json()["redirect_url"] == "https://sandbox.example/pay"
    sent = post.call_args.args[1]
    assert sent["total_amount"] == "15000.00" and sent["currency"] == "BDT"
    assert sent["success_url"].endswith("/api/payments/sslcommerz/success/")
    tx = PaymentTransaction.objects.get(tran_id=sent["tran_id"])

    # A forged "success" redirect whose server-side validation says the amount differs is refused.
    forged = {"status": "VALID", "tran_id": tx.tran_id, "currency_type": "BDT", "currency_amount": "10.00"}
    with mock.patch.object(gateway, "validate", return_value=forged):
        r = APIClient().post("/api/payments/sslcommerz/success/", {"tran_id": tx.tran_id, "val_id": "v1"})
    assert r.status_code == 302 and r["Location"].endswith("payment=failed")
    tx.refresh_from_db()
    assert tx.status == "failed" and Invoice.objects.get(pk=invoice["id"]).status == "unpaid"

    # Genuine payment: new attempt, validated -> plan activated; repeated callbacks are harmless.
    with mock.patch.object(
        gateway, "_post", return_value={"status": "SUCCESS", "GatewayPageURL": "https://x/pay"}
    ) as post:
        client.post(f"/api/workspace/subscription/invoices/{invoice['id']}/pay-online/")
    tran_id = post.call_args.args[1]["tran_id"]
    valid = {
        "status": "VALID",
        "tran_id": tran_id,
        "currency_type": "BDT",
        "currency_amount": "15000.00",
        "bank_tran_id": "BANK123",
    }
    with mock.patch.object(gateway, "validate", return_value=valid):
        r = APIClient().post("/api/payments/sslcommerz/success/", {"tran_id": tran_id, "val_id": "v2"})
        ipn = APIClient().post("/api/payments/sslcommerz/ipn/", {"tran_id": tran_id, "val_id": "v2"})
    assert r["Location"].endswith("/workspace/subscription?payment=success")
    assert ipn.status_code == 200
    assert Invoice.objects.get(pk=invoice["id"]).status == "paid"
    assert Subscription.objects.filter(turf=turf, status="active", plan__period="yearly").count() == 1


@override_settings(**GATEWAY_SETTINGS)
def test_online_cancel_and_unknown_transactions():
    turf, owner = make_turf()
    client = client_for(owner)
    invoice = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json").json()
    with mock.patch.object(
        gateway, "_post", return_value={"status": "SUCCESS", "GatewayPageURL": "https://x/pay"}
    ) as post:
        client.post(f"/api/workspace/subscription/invoices/{invoice['id']}/pay-online/")
    tran_id = post.call_args.args[1]["tran_id"]
    r = APIClient().post("/api/payments/sslcommerz/cancel/", {"tran_id": tran_id})
    assert r["Location"].endswith("payment=cancelled")
    assert PaymentTransaction.objects.get(tran_id=tran_id).status == "cancelled"
    unknown = APIClient().post("/api/payments/sslcommerz/success/", {"tran_id": "NOPE", "val_id": "x"})
    assert unknown["Location"].endswith("payment=failed")


def test_online_payment_hidden_without_gateway_keys():
    _, owner = make_turf()
    client = client_for(owner)
    overview = client.get("/api/workspace/subscription/").json()
    assert overview["payment_options"]["online"] is False
    invoice = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json").json()
    r = client.post(f"/api/workspace/subscription/invoices/{invoice['id']}/pay-online/")
    assert r.status_code == 400


# ------------------------------------------------------------------ slot board
def test_slot_board_shows_who_holds_each_slot():
    turf, owner = make_turf()
    field = turf.fields.first()
    customer = get_or_create_customer(turf, name="Rafi", phone="01812345678")
    reserve_slot(
        turf=turf,
        field_id=field.id,
        customer=customer,
        start=tomorrow_at(18),
        end=tomorrow_at(19),
        team_name="Banani FC",
    )
    reserve_slot(
        turf=turf,
        field_id=field.id,
        customer=customer,
        start=tomorrow_at(20),
        end=tomorrow_at(21),
        status=Booking.Status.PENDING,
    )
    MaintenanceBlock.objects.create(
        turf=turf, field=field, start=tomorrow_at(22), end=tomorrow_at(23), reason="Net repair"
    )

    day = (timezone.localdate() + timedelta(days=1)).isoformat()
    board = client_for(owner).get(f"/api/workspace/availability/?date={day}&field={field.id}&detail=1").json()
    by_hour = {s["start"][11:13]: s for s in board["fields"][0]["slots"]}
    assert by_hour["18"]["state"] == "booked" and by_hour["18"]["booking"]["team_name"] == "Banani FC"
    assert by_hour["20"]["state"] == "pending" and by_hour["20"]["booking"]["customer_name"] == "Rafi"
    assert by_hour["22"]["state"] == "maintenance" and by_hour["22"]["reason"] == "Net repair"
    assert by_hour["19"]["state"] == "free" and by_hour["19"]["available"] is True


def test_booking_with_discount_from_slot_board():
    turf, owner = make_turf()
    payload = {**booking_payload(turf.fields.first().id), "discount": "150.00", "advance_amount": "500.00"}
    response = client_for(owner).post("/api/workspace/bookings/", payload, format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["subtotal"], body["discount"], body["total"]) == ("1000.00", "150.00", "850.00")
    assert body["amount_paid"] == "500.00" and body["due"] == "350.00"

    too_much = {**booking_payload(turf.fields.first().id, start_hour=20), "discount": "1500.00"}
    assert client_for(owner).post("/api/workspace/bookings/", too_much, format="json").status_code == 400
    over_advance = {
        **booking_payload(turf.fields.first().id, start_hour=21),
        "discount": "900.00",
        "advance_amount": "300.00",
    }
    assert client_for(owner).post("/api/workspace/bookings/", over_advance, format="json").status_code == 400
