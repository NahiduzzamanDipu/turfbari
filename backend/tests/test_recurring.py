"""Advance & recurring bookings made by the turf (requirements 1-22)."""

import threading
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings import recurring
from apps.bookings.models import Booking, BookingSeries, Customer, MaintenanceBlock
from apps.common.models import PlatformSettings
from apps.notifications import wallet
from apps.notifications.models import SmsMessage
from apps.notifications.providers import MemoryProvider
from apps.turfs import schedule
from apps.turfs.models import OperatingHours, PricingRule, TenantMembership

from .test_core import client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db
PHONE = "01912345678"


def day(n: int) -> date:
    return timezone.localdate() + timedelta(days=n)


def plan(turf, **kw) -> dict:
    body = {
        "field": str(turf.fields.first().id),
        "start_time": "17:00",
        "end_time": "19:00",
        "recurrence": "daily",
        "start_date": day(1).isoformat(),
        "end_date": day(7).isoformat(),
        "customer_name": "Rafi",
        "customer_phone": PHONE,
    }
    body.update(kw)
    return body


def preview(client, turf, **kw):
    r = client.post("/api/workspace/booking-series/preview/", plan(turf, **kw), format="json")
    assert r.status_code == 200, r.json()
    return r.json()


def create(client, turf, key=None, **kw):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client.post("/api/workspace/booking-series/", plan(turf, **kw), format="json", **headers)


def settings_(**kw):
    PlatformSettings.objects.update_or_create(pk=1, defaults=kw)
    cache.delete("platform:settings")


def series_sms():
    return SmsMessage.objects.filter(kind__startswith="series_")


# 1, 4 ----------------------------------------------------------------- daily, one month
def test_1_4_daily_series_for_a_month_creates_one_booking_per_date():
    turf, owner = make_turf()
    c = client_for(owner)
    p = preview(c, turf, end_date=day(30).isoformat())
    assert p["summary"]["dates"] == 30 and p["summary"]["available"] == 30
    assert p["summary"]["total"] == "60000.00" and p["summary"]["minutes_each"] == 120  # 30 × 2 h × ৳1000
    assert p["summary"]["advance_required"] == "15000.00"  # ৳500 per booking, same rule as single bookings
    r = create(c, turf, end_date=day(30).isoformat())
    assert r.status_code == 201, r.json()
    s = BookingSeries.objects.get()
    occ = list(s.occurrences.order_by("start"))
    assert len(occ) == 30 and s.occurrences_count == 30 and s.total == Decimal("60000.00")
    assert [b.occurrence_number for b in occ] == list(range(1, 31))
    assert all(b.status == "confirmed" and b.created_by == owner and b.price_snapshot for b in occ)
    first = timezone.localtime(occ[0].start)
    assert (first.date(), first.time(), timezone.localtime(occ[0].end).time()) == (day(1), time(17), time(19))
    # Calendar / booking list see them as normal bookings, marked as part of the series.
    rows = c.get("/api/workspace/bookings/", {"kind": "recurring", "date": day(3).isoformat()}).json()[
        "results"
    ]
    assert rows[0]["series"] == {
        "id": str(s.pk),
        "reference": s.reference,
        "number": 3,
        "total": 30,
        "status": "active",
    }
    assert c.get("/api/workspace/bookings/", {"kind": "single"}).json()["count"] == 0


# 2, 3, 5 -------------------------------------------------------------- weekdays, custom, end date
def test_2_3_5_weekdays_custom_dates_and_custom_end_date():
    turf, owner = make_turf()
    c = client_for(owner)
    start, end = day(1), day(21)
    p = preview(
        c,
        turf,
        recurrence="weekdays",
        weekdays=[6, 1, 3],
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    expected = [d for d in (start + timedelta(i) for i in range(21)) if d.weekday() in (6, 1, 3)]
    assert [r["date"] for r in p["rows"]] == [d.isoformat() for d in expected]
    weekly = preview(c, turf, recurrence="weekly", weekdays=[4], end_date=day(28).isoformat())
    assert (
        all(date.fromisoformat(r["date"]).weekday() == 4 for r in weekly["rows"]) and len(weekly["rows"]) == 4
    )
    custom = [day(2), day(9), day(5)]
    p = preview(c, turf, recurrence="custom", custom_dates=[d.isoformat() for d in custom])
    assert [r["date"] for r in p["rows"]] == sorted(d.isoformat() for d in custom)
    once = preview(c, turf, recurrence="once", start_date=day(4).isoformat(), end_date=day(40).isoformat())
    assert [r["date"] for r in once["rows"]] == [day(4).isoformat()]
    r = create(c, turf, recurrence="custom", custom_dates=[d.isoformat() for d in custom])
    assert r.status_code == 201 and r.json()["occurrences_count"] == 3
    # Horizon and size limits come from the platform policy.
    settings_(recurring_max_days=30)
    far = c.post(
        "/api/workspace/booking-series/preview/", plan(turf, end_date=day(45).isoformat()), format="json"
    )
    assert far.status_code == 400 and "end_date" in far.json()["error"]["fields"]


# 6, 7, 10, 11 --------------------------------------------------------- conflicts and exclusion
def test_6_7_10_11_conflicts_are_shown_and_must_be_excluded_explicitly():
    turf, owner = make_turf()
    c = client_for(owner)
    field = turf.fields.first()
    other = Customer.objects.create(turf=turf, name="Other", phone="+8801811111111")
    s3, e3 = recurring.window(day(3), time(17), time(19))
    Booking.objects.create(turf=turf, field=field, customer=other, start=s3, end=e3, status="confirmed")
    s5, e5 = recurring.window(day(5), time(18), time(19))
    Booking.objects.create(  # online request still holding its slot
        turf=turf,
        field=field,
        customer=other,
        start=s5,
        end=e5,
        status="pending",
        hold_expires_at=timezone.now() + timedelta(minutes=10),
    )
    s6, e6 = recurring.window(day(6), time(16), time(17, 30))
    MaintenanceBlock.objects.create(turf=turf, field=field, start=s6, end=e6)
    s4, e4 = recurring.window(day(4), time(17), time(18))
    Booking.objects.create(  # expired hold: no longer blocks
        turf=turf,
        field=field,
        customer=other,
        start=s4,
        end=e4,
        status="pending",
        hold_expires_at=timezone.now() - timedelta(minutes=1),
    )
    p = preview(c, turf)
    by_date = {r["date"]: r for r in p["rows"]}
    assert by_date[day(3).isoformat()]["reason"] == "booked"
    assert by_date[day(5).isoformat()]["reason"] == "held"
    assert by_date[day(6).isoformat()]["reason"] == "maintenance"
    assert by_date[day(4).isoformat()]["available"] is True
    assert p["summary"]["unavailable"] == [day(3).isoformat(), day(5).isoformat(), day(6).isoformat()]
    refused = create(c, turf)
    assert refused.status_code == 400 and refused.json()["error"]["fields"]["code"] == ["dates_unavailable"]
    assert BookingSeries.objects.count() == 0 and Booking.objects.filter(series__isnull=False).count() == 0
    ok = create(c, turf, exclude_dates=[day(3).isoformat(), day(5).isoformat(), day(6).isoformat()])
    assert ok.status_code == 201 and ok.json()["occurrences_count"] == 4


# 8, 9 ----------------------------------------------------------------- pricing
def test_8_9_each_date_is_priced_by_the_turf_pricing_engine():
    turf, owner = make_turf()
    c = client_for(owner)
    friday = next(day(i) for i in range(1, 8) if day(i).weekday() == 4)
    PricingRule.objects.create(
        turf=turf,
        label="Weekend",
        weekdays=[4],
        start_time=time(0),
        end_time=time(0),
        hourly_rate=Decimal("1500"),
    )
    holiday = next(day(i) for i in range(1, 8) if day(i).weekday() not in (4,))
    PricingRule.objects.create(
        turf=turf,
        label="Holiday",
        date=holiday,
        start_time=time(0),
        end_time=time(0),
        hourly_rate=Decimal("2500"),
    )
    schedule.forget_turf_config(turf.pk)
    p = preview(c, turf)
    prices = {r["date"]: r["price"] for r in p["rows"]}
    assert prices[friday.isoformat()] == "3000.00" and prices[holiday.isoformat()] == "5000.00"
    others = [v for k, v in prices.items() if k not in (friday.isoformat(), holiday.isoformat())]
    assert set(others) == {"2000.00"}
    create(c, turf)
    b = next(
        x
        for x in Booking.objects.filter(series__isnull=False)
        if timezone.localtime(x.start).date() == holiday
    )
    assert b.total == Decimal("5000.00") and b.price_snapshot["segments"]
    # A later price change never rewrites what was booked.
    PricingRule.objects.filter(label="Holiday").update(hourly_rate=Decimal("9999"))
    schedule.forget_turf_config(turf.pk)
    b.refresh_from_db()
    assert b.total == Decimal("5000.00")


# 12 ------------------------------------------------------------------- daily limit
def test_12_daily_customer_limit_applies_to_every_date():
    turf, owner = make_turf()
    other_turf, _ = make_turf("Beta Turf", "beta@example.com")
    c = client_for(owner)
    cust = Customer.objects.create(turf=other_turf, name="Rafi", phone="+880" + PHONE[1:])
    s, e = recurring.window(day(2), time(9), time(10))
    Booking.objects.create(
        turf=other_turf, field=other_turf.fields.first(), customer=cust, start=s, end=e, status="confirmed"
    )
    p = preview(c, turf)
    assert {r["date"]: r["reason"] for r in p["rows"] if not r["available"]} == {day(2).isoformat(): "limit"}
    three = preview(c, turf, end_time="20:00")  # 3 one-hour slots a day: over the limit every day
    assert all(r["reason"] == "limit" for r in three["rows"])
    # Platform admin exemption: off by default, explicit and audited.
    admin, _ = admin_client()
    r = admin.put(
        "/api/admin/api-config/recurring/",
        {"max_days": 186, "max_occurrences": 200, "hold_hours": 24, "limit_exempt": True},
        format="json",
    )
    assert r.status_code == 200
    from apps.audit.models import AuditEvent

    assert AuditEvent.objects.filter(action="platform.recurring_policy").exists()
    assert all(row["available"] for row in preview(c, turf)["rows"])


# 13 ------------------------------------------------------------------- tenants & permissions
def test_13_tenants_are_isolated_and_managers_need_permission():
    turf, owner = make_turf()
    other, other_owner = make_turf("Beta Turf", "beta@example.com")
    sid = create(client_for(owner), turf).json()["id"]
    oc = client_for(other_owner)
    assert oc.get(f"/api/workspace/booking-series/{sid}/").status_code == 404
    assert (
        oc.post(
            f"/api/workspace/booking-series/{sid}/cancel/", {"all_future": True}, format="json"
        ).status_code
        == 404
    )
    assert oc.get("/api/workspace/booking-series/").json()["count"] == 0
    assert (
        oc.post("/api/workspace/booking-series/", plan(turf), format="json").status_code == 400
    )  # other turf's field
    from django.contrib.auth import get_user_model

    mgr = get_user_model().objects.create_user("m@example.com", "x" * 12)
    m = TenantMembership.objects.create(user=mgr, turf=turf, role="manager")
    assert client_for(mgr).get("/api/workspace/booking-series/").status_code == 403
    m.permissions = {**m.permissions, "advance_bookings": True}
    m.save()
    assert client_for(mgr).get("/api/workspace/booking-series/").json()["count"] == 1
    assert APIClient().get("/api/workspace/booking-series/").status_code in (401, 403)


# 14, 15 --------------------------------------------------------------- duplicates & concurrency
def test_14_same_request_twice_creates_one_series():
    turf, owner = make_turf()
    c = client_for(owner)
    a = create(c, turf, key="abc-123-def-456")
    b = create(c, turf, key="abc-123-def-456")
    assert a.json()["id"] == b.json()["id"] and BookingSeries.objects.count() == 1
    assert Booking.objects.filter(series__isnull=False).count() == 7
    again = create(c, turf)  # different request for the same slots: every date is now taken
    assert again.status_code == 400 and BookingSeries.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_15_parallel_requests_cannot_double_book():
    from .conftest import reseed_reference_data

    reseed_reference_data()
    turf, owner = make_turf()
    results = []

    def go(phone):
        try:
            c = client_for(owner)
            results.append(create(c, turf, customer_phone=phone).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=go, args=(p,)) for p in ("01912345678", "01812345678")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 400]
    starts = list(Booking.objects.filter(series__isnull=False).values_list("start", flat=True))
    assert len(starts) == len(set(starts)) == 7


# 16, 17 --------------------------------------------------------------- cancellation
def test_16_17_cancel_some_or_all_future_dates_but_never_the_past():
    turf, owner = make_turf()
    c = client_for(owner)
    data = create(c, turf).json()
    occ = data["occurrences"]
    past = Booking.objects.get(pk=occ[0]["id"])  # pretend the first one already happened
    Booking.objects.filter(pk=past.pk).update(
        start=timezone.now() - timedelta(hours=3), end=timezone.now() - timedelta(hours=1)
    )
    part = c.post(
        f"/api/workspace/booking-series/{data['id']}/cancel/",
        {"booking_ids": [occ[2]["id"], occ[3]["id"]]},
        format="json",
    ).json()
    assert part["result"]["cancelled"] == 2 and part["status"] == "active"
    assert [o["status"] for o in part["occurrences"]].count("cancelled") == 2
    refused = c.post(
        f"/api/workspace/booking-series/{data['id']}/cancel/", {"booking_ids": [occ[0]["id"]]}, format="json"
    )
    assert refused.status_code == 400  # past dates can't be cancelled from here
    rest = c.post(
        f"/api/workspace/booking-series/{data['id']}/cancel/", {"all_future": True}, format="json"
    ).json()
    assert rest["result"]["cancelled"] == 4 and rest["status"] == "cancelled"
    assert Booking.objects.get(pk=past.pk).status == "confirmed"  # history untouched
    assert series_sms().filter(kind="series_cancelled").count() == 2


# 18 ------------------------------------------------------------------- changing future dates
def test_18_reschedule_upcoming_dates_after_a_dry_run():
    turf, owner = make_turf()
    c = client_for(owner)
    data = create(c, turf).json()
    other = Customer.objects.create(turf=turf, name="Other", phone="+8801811111111")
    s, e = recurring.window(day(4), time(20), time(21))
    Booking.objects.create(
        turf=turf, field=turf.fields.first(), customer=other, start=s, end=e, status="confirmed"
    )
    url = f"/api/workspace/booking-series/{data['id']}/reschedule/"
    dry = c.post(url, {"start_time": "19:00", "end_time": "21:00"}, format="json").json()
    assert [r["date"] for r in dry["result"]["rows"] if not r["available"]] == [day(4).isoformat()]
    starts = {timezone.localtime(x.start).time() for x in Booking.objects.filter(series_id=data["id"])}
    assert starts == {time(17)}  # nothing moved yet
    blocked = c.post(url, {"start_time": "19:00", "end_time": "21:00", "dry_run": False}, format="json")
    assert blocked.status_code == 400
    done = c.post(
        url,
        {"start_time": "19:00", "end_time": "21:00", "dry_run": False, "keep_dates": [day(4).isoformat()]},
        format="json",
    ).json()
    assert done["result"]["changed"] == 6
    times = {
        timezone.localtime(b.start).date(): timezone.localtime(b.start).time()
        for b in Booking.objects.filter(series_id=data["id"])
    }
    assert times[day(4)] == time(17) and times[day(5)] == time(19)
    assert series_sms().filter(kind="series_updated").count() == 1
    # Add a date.
    added = c.post(
        f"/api/workspace/booking-series/{data['id']}/add-date/", {"date": day(9).isoformat()}, format="json"
    ).json()
    assert added["result"]["added"] is True and added["occurrences_count"] == 8


# 19, 20 --------------------------------------------------------------- SMS
def test_19_20_one_sms_per_series_and_an_empty_wallet_never_blocks_the_booking():
    turf, owner = make_turf()
    c = client_for(owner)
    r = create(c, turf).json()
    assert r["sms"]["status"] == "sent" and series_sms().count() == 1
    text = MemoryProvider.outbox[-1]["body"]
    assert turf.name in text and "7" in text and f"{day(1):%d/%m/%Y}" in text
    pending = create(
        c, turf, start_time="20:00", end_time="21:00", customer_phone="01812345678", mode="pending"
    ).json()
    assert pending["status"] == "pending_payment" and series_sms().count() == 1  # no "confirmed" SMS yet
    # Empty wallet: booking still succeeds, the SMS is recorded as blocked and shown to the owner.
    w = wallet.wallet_for(turf)
    type(w).objects.filter(pk=w.pk).update(balance=Decimal("0"))
    poor = create(c, turf, start_time="06:00", end_time="07:00", customer_phone="01712340000")
    assert poor.status_code == 201 and poor.json()["sms"]["status"] == "blocked"


# 5 (payments) --------------------------------------------------------- awaiting payment
def test_awaiting_payment_needs_the_advance_and_expires():
    turf, owner = make_turf()
    c = client_for(owner)
    data = create(c, turf, mode="pending").json()
    assert (
        all(o["status"] == "pending" for o in data["occurrences"]) and data["advance_required"] == "3500.00"
    )
    url = f"/api/workspace/booking-series/{data['id']}/confirm/"
    low = c.post(url, {"amount": "1000", "method": "bkash", "reference": "TRX1234567"}, format="json")
    assert low.status_code == 400
    no_trx = c.post(url, {"amount": "3500", "method": "bkash"}, format="json")
    assert no_trx.status_code == 400
    ok = c.post(url, {"amount": "3500", "method": "bkash", "reference": "TRX1234567"}, format="json").json()
    assert ok["status"] == "active" and all(o["status"] == "confirmed" for o in ok["occurrences"])
    assert ok["paid_total"] == "3500.00" and ok["occurrences"][0]["payment_status"] == "paid"
    # Unpaid series release their dates when the hold runs out.
    d2 = create(
        c, turf, start_time="20:00", end_time="21:00", mode="pending", customer_phone="01712340001"
    ).json()
    Booking.objects.filter(series_id=d2["id"]).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    from apps.bookings.payments import expire_lapsed

    expire_lapsed()
    assert recurring.expire_unpaid()["expired_series"] == 1
    assert c.get(f"/api/workspace/booking-series/{d2['id']}/").json()["status"] == "expired"
    assert (
        preview(c, turf, start_time="20:00", end_time="21:00", customer_phone="01611111111")["summary"][
            "available"
        ]
        == 7
    )


# 21 ------------------------------------------------------------------- subscription
def test_21_lapsed_subscription_blocks_new_series():
    turf, owner = make_turf()
    from apps.subscriptions.models import Subscription

    Subscription.objects.filter(turf=turf).update(
        starts_on=timezone.localdate() - timedelta(days=60), ends_on=timezone.localdate() - timedelta(days=30)
    )
    r = create(client_for(owner), turf)
    assert r.status_code == 402 and BookingSeries.objects.count() == 0


# 22 ------------------------------------------------------------------- overnight & timezone
def test_22_overnight_slots_and_dhaka_days():
    turf, owner = make_turf()
    OperatingHours.objects.filter(turf=turf).update(opens_at=time(6), closes_at=time(2))
    schedule.forget_turf_config(turf.pk)
    c = client_for(owner)
    r = create(c, turf, start_time="23:00", end_time="01:00", end_date=day(3).isoformat())
    assert r.status_code == 201, r.json()
    b = Booking.objects.filter(series__isnull=False).order_by("start").first()
    start, end = timezone.localtime(b.start), timezone.localtime(b.end)
    assert start.tzinfo.key == "Asia/Dhaka" if hasattr(start.tzinfo, "key") else True
    assert (start.date(), start.time()) == (day(1), time(23)) and (end.date(), end.time()) == (
        day(2),
        time(1),
    )
    assert r.json()["overnight"] is True
    closed = c.post(
        "/api/workspace/booking-series/preview/",
        plan(turf, start_time="02:00", end_time="04:00"),
        format="json",
    ).json()
    assert all(row["reason"] == "closed" for row in closed["rows"])
    assert isinstance(datetime.fromisoformat(closed["rows"][0]["start"]), datetime)
