"""Online booking with a manual bKash advance: submit, hold, verify (approve/reject), expire, SMS."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.bookings.models import Booking, Payment, PaymentSubmission
from apps.bookings.payments import booking_reminders, expire_lapsed, required_advance
from apps.notifications.models import SmsMessage
from apps.notifications.providers import MemoryProvider
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, bkash, client_for, make_turf, tomorrow_at

pytestmark = pytest.mark.django_db
ACCEPTED = "আপনার বুকিং অনুরোধ গ্রহণ করা হয়েছে।"


def request_booking(turf, hour=18, phone="01912345678", **payment):
    body = {
        "field": str(turf.fields.first().id),
        "start": tomorrow_at(hour).isoformat(),
        "end": tomorrow_at(hour + 1).isoformat(),
        "name": "Rafi",
        "phone": phone,
        **bkash(),
        **payment,
    }
    return APIClient().post(f"/api/public/turfs/{turf.slug}/book/", body, format="json")


def queue(client, status="pending"):
    return client.get(f"/api/workspace/payment-verifications/?status={status}").json()


# ------------------------------------------------------------------ rules
def test_advance_is_at_least_500_but_never_more_than_the_price():
    turf, _ = make_turf()
    assert required_advance(turf, Decimal("1000")) == Decimal("500.00")
    assert required_advance(turf, Decimal("300")) == Decimal("300.00")  # cheap slot: pay it all
    turf.advance_amount = Decimal("800")
    assert required_advance(turf, Decimal("1000")) == Decimal("800.00")
    assert required_advance(turf, Decimal("600")) == Decimal("600.00")
    turf.advance_amount = Decimal("100")  # below the platform floor
    assert required_advance(turf, Decimal("1000")) == Decimal("500.00")


def test_submission_is_validated_on_the_server():
    turf, _ = make_turf()  # 1000/hour, advance 500
    cases = [
        ({"payment_amount": "499"}, "payment_amount"),
        ({"payment_amount": "1001"}, "payment_amount"),
        ({"trx_id": "abc"}, "trx_id"),
        ({"bkash_sender": "12345"}, "bkash_sender"),
    ]
    for override, field in cases:
        r = request_booking(turf, **override)
        assert r.status_code == 400 and field in str(r.json()), (override, r.json())
    assert not Booking.objects.exists()  # nothing half-created
    missing = APIClient().post(
        f"/api/public/turfs/{turf.slug}/book/",
        {
            "field": str(turf.fields.first().id),
            "start": tomorrow_at(18).isoformat(),
            "end": tomorrow_at(19).isoformat(),
            "name": "x",
            "phone": "01912345678",
        },
        format="json",
    )
    assert missing.status_code == 400


def test_valid_submission_is_pending_not_paid_and_shows_the_bengali_notice():
    turf, _ = make_turf()
    r = request_booking(turf, trx_id=" 9c7a 6b5d4e ", payment_amount="600")
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["status"] == "pending" and body["message_bn"].startswith(ACCEPTED)
    assert body["payment"] == {
        "amount": "600.00",
        "trx_id": "9C7A6B5D4E",
        "status": "pending",
        "rejection_reason": None,
    }
    booking = Booking.objects.get(reference=body["reference"])
    assert booking.amount_paid == 0 and booking.confirmed_at is None and not booking.payments.exists()
    assert booking.hold_expires_at > timezone.now() + timedelta(minutes=55)
    assert MemoryProvider.outbox == []  # no SMS before a person approves

    reused = request_booking(turf, hour=20, trx_id="9C7A6B5D4E")
    assert reused.status_code == 400 and "already used" in str(reused.json())


def test_online_booking_follows_the_owner_switch_and_uses_the_turfs_own_number():
    turf, _ = make_turf()
    turf.bkash_number = ""  # never set: falls back to the turf's own registered mobile
    turf.save()
    page = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["payment"]
    assert page["accepts_online"] is True and page["bkash_number"] == "01711000000"
    assert request_booking(turf).status_code == 201
    turf.public_booking_enabled = False
    turf.save()
    page = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()
    assert page["payment"]["accepts_online"] is False and page["public_phone"] == turf.public_phone
    assert request_booking(turf, hour=20, phone="01812345678").status_code == 403


# ------------------------------------------------------------------ holds
def test_pending_request_holds_the_slot_until_its_hold_expires():
    turf, _ = make_turf()
    first = request_booking(turf).json()
    assert request_booking(turf, phone="01812345678").status_code == 400  # slot taken
    Booking.objects.filter(reference=first["reference"]).update(
        hold_expires_at=timezone.now() - timedelta(seconds=1)
    )
    lookup = (
        APIClient()
        .get(f"/api/public/bookings/lookup/?reference={first['reference']}&phone=01912345678")
        .json()
    )
    assert lookup["status"] == "expired"  # truthful even before the tick runs
    second = request_booking(turf, phone="01812345678")
    assert second.status_code == 201  # freed for the next customer
    assert expire_lapsed() == {"expired_holds": 1}
    assert Booking.objects.get(reference=first["reference"]).status == "expired"
    assert PaymentSubmission.objects.get(booking__reference=first["reference"]).status == "expired"


# ------------------------------------------------------------------ verification
def test_owner_approves_payment_confirms_booking_records_money_and_sms():
    turf, owner = make_turf()
    ref = request_booking(turf, payment_amount="700").json()["reference"]
    client = client_for(owner)
    items = queue(client)
    assert items["counts"]["pending"] == 1 and items["can_review"] is True
    row = items["results"][0]
    assert (
        row["trx_id"].startswith("TEST")
        and row["booking"]["total"] == "1000.00"
        and row["slot_conflict"] is False
    )

    approved = client.post(f"/api/workspace/payment-verifications/{row['id']}/approve/")
    assert approved.status_code == 200, approved.json()
    assert approved.json()["status"] == "approved"
    booking = Booking.objects.get(reference=ref)
    assert (
        booking.status == "confirmed"
        and booking.amount_paid == Decimal("700.00")
        and booking.hold_expires_at is None
    )
    payment = Payment.objects.get(booking=booking)
    assert payment.method == "bkash" and payment.received_by == owner and row["trx_id"] in payment.reference
    sms = SmsMessage.objects.get(booking=booking, kind="booking_confirmed")
    assert sms.status == "sent" and ref in sms.body and "কনফার্ম" in sms.body
    assert client.post(f"/api/workspace/payment-verifications/{row['id']}/approve/").status_code == 400
    assert SmsMessage.objects.filter(kind="booking_confirmed").count() == 1  # never twice
    assert AuditEvent.objects.filter(action="booking.payment_approved", turf=turf).exists()
    status = APIClient().get(f"/api/public/bookings/lookup/?reference={ref}&phone=01912345678").json()
    assert status["status"] == "confirmed" and status["amount_paid"] == "700.00"


def test_reject_frees_the_slot_and_tells_the_customer_why():
    turf, owner = make_turf()
    ref = request_booking(turf).json()["reference"]
    client = client_for(owner)
    row = queue(client)["results"][0]
    r = client.post(
        f"/api/workspace/payment-verifications/{row['id']}/reject/",
        {"reason": "TrxID not found"},
        format="json",
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    booking = Booking.objects.get(reference=ref)
    assert booking.status == "rejected" and not booking.payments.exists()
    sms = SmsMessage.objects.get(kind="payment_rejected")
    assert "TrxID not found" in sms.body
    assert request_booking(turf, phone="01812345678").status_code == 201  # slot free again


def test_approving_after_the_slot_was_taken_is_refused():
    turf, owner = make_turf()
    first = request_booking(turf).json()
    Booking.objects.filter(reference=first["reference"]).update(
        hold_expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert request_booking(turf, phone="01812345678").status_code == 201
    client = client_for(owner)
    late = queue(client, "expired")["results"][0]
    assert late["status"] == "expired" and late["slot_conflict"] is True
    refused = client.post(f"/api/workspace/payment-verifications/{late['id']}/approve/")
    assert refused.status_code == 400 and "refund" in str(refused.json())
    assert Booking.objects.get(reference=first["reference"]).status != "confirmed"


def test_expired_request_can_still_be_approved_if_the_slot_is_free():
    turf, owner = make_turf()
    first = request_booking(turf).json()
    Booking.objects.filter(reference=first["reference"]).update(
        hold_expires_at=timezone.now() - timedelta(seconds=1)
    )
    expire_lapsed()
    client = client_for(owner)
    row = queue(client, "expired")["results"][0]
    assert client.post(f"/api/workspace/payment-verifications/{row['id']}/approve/").status_code == 200
    assert Booking.objects.get(reference=first["reference"]).status == "confirmed"


def test_reviewing_needs_the_permission_and_stays_inside_the_turf():
    turf, owner = make_turf()
    request_booking(turf)
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    membership = TenantMembership.objects.create(user=manager, turf=turf, role="manager")
    mgr = client_for(manager)
    row = queue(mgr)["results"][0]  # managers can always see the queue
    membership.permissions = {**membership.permissions, "approve_payments": False}
    membership.save()
    assert queue(mgr)["can_review"] is False
    assert mgr.post(f"/api/workspace/payment-verifications/{row['id']}/approve/").status_code == 403
    booking_id = row["booking"]["id"]
    assert (
        mgr.post(
            f"/api/workspace/bookings/{booking_id}/status/", {"status": "confirmed"}, format="json"
        ).status_code
        == 403
    )
    _, other_owner = make_turf("Beta Turf", "beta@example.com")
    assert (
        client_for(other_owner).post(f"/api/workspace/payment-verifications/{row['id']}/approve/").status_code
        == 404
    )
    membership.permissions = {**membership.permissions, "approve_payments": True}
    membership.save()
    assert mgr.post(f"/api/workspace/payment-verifications/{row['id']}/approve/").status_code == 200


def test_old_status_buttons_go_through_verification_and_cancel_sends_sms():
    turf, owner = make_turf()
    ref = request_booking(turf).json()["reference"]
    booking = Booking.objects.get(reference=ref)
    client = client_for(owner)
    confirmed = client.post(
        f"/api/workspace/bookings/{booking.id}/status/", {"status": "confirmed"}, format="json"
    )
    assert confirmed.status_code == 200
    booking.refresh_from_db()
    assert booking.amount_paid == Decimal("500.00")  # the bKash advance was recorded
    client.post(f"/api/workspace/bookings/{booking.id}/status/", {"status": "cancelled"}, format="json")
    assert SmsMessage.objects.filter(booking=booking, kind="booking_cancelled", status="sent").count() == 1


def test_booking_reminder_sms_when_the_turf_turns_it_on():
    turf, owner = make_turf()
    ref = request_booking(turf, hour=18).json()["reference"]
    booking = Booking.objects.get(reference=ref)
    client = client_for(owner)
    client.post(f"/api/workspace/payment-verifications/{booking.payment_submission.id}/approve/")
    Booking.objects.filter(pk=booking.pk).update(
        start=timezone.now() + timedelta(hours=2),
        end=timezone.now() + timedelta(hours=3),
        confirmed_at=timezone.now() - timedelta(days=1),
    )
    assert booking_reminders() == {"booking_reminders": 0}  # off by default
    client.patch(
        "/api/workspace/sms/settings/", {"booking_reminder": True, "reminder_hours": 3}, format="json"
    )
    assert booking_reminders() == {"booking_reminders": 1}
    assert booking_reminders() == {"booking_reminders": 0}
    assert SmsMessage.objects.filter(kind="booking_reminder").count() == 1


def test_owner_sets_bkash_number_and_advance_with_server_rules():
    _, owner = make_turf()
    client = client_for(owner)
    low = client.patch("/api/workspace/settings/", {"advance_amount": "300"}, format="json")
    assert low.status_code == 400
    ok = client.patch(
        "/api/workspace/settings/",
        {"bkash_number": "+880 1712-345678", "advance_amount": "800", "payment_hold_minutes": 90},
        format="json",
    )
    assert ok.status_code == 200, ok.json()
    assert ok.json()["bkash_number"] == "01712345678" and ok.json()["advance_amount"] == "800.00"
