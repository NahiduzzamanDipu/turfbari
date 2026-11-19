"""Custom weekly slots, Morning/Evening/Night/Midnight pricing, slot price overrides."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.services import availability
from apps.turfs.models import OperatingHours, PricingRule, SlotTemplate, TenantMembership
from apps.turfs.pricing import quote
from apps.turfs.schedule import local_dt

from .test_core import PASSWORD, bkash, client_for, make_turf

pytestmark = pytest.mark.django_db

CATEGORIES = {
    "enabled": True,
    "categories": [
        {"key": "morning", "starts_at": "06:00", "hourly_rate": "800"},
        {"key": "evening", "starts_at": "12:00", "hourly_rate": "1200"},
        {"key": "night", "starts_at": "18:00", "hourly_rate": "2000"},
        {"key": "midnight", "starts_at": "00:00", "hourly_rate": "1000"},
    ],
}


def at(day_offset: int, hhmm: str):
    from datetime import time

    h, m = map(int, hhmm.split(":"))
    return local_dt(timezone.localdate() + timedelta(days=day_offset), time(h, m))


def open_all_day(turf):
    from datetime import time

    OperatingHours.objects.filter(turf=turf).update(
        opens_at=time(0, 0), closes_at=time(0, 0), is_closed=False
    )


# ------------------------------------------------------------------ categories
def test_categories_must_cover_the_day_in_order():
    _, owner = make_turf()
    client = client_for(owner)
    bad_order = {
        "enabled": True,
        "categories": [
            {"key": "morning", "starts_at": "18:00", "hourly_rate": "1"},
            {"key": "evening", "starts_at": "06:00", "hourly_rate": "1"},
            {"key": "night", "starts_at": "12:00", "hourly_rate": "1"},
            {"key": "midnight", "starts_at": "00:00", "hourly_rate": "1"},
        ],
    }
    assert client.put("/api/workspace/price-categories/", bad_order, format="json").status_code == 400
    missing = {"enabled": True, "categories": CATEGORIES["categories"][:3]}
    assert client.put("/api/workspace/price-categories/", missing, format="json").status_code == 400
    ok = client.put("/api/workspace/price-categories/", CATEGORIES, format="json").json()
    assert [(b["key"], b["start"], b["end"]) for b in ok["categories"]] == [
        ("morning", "06:00", "12:00"),
        ("evening", "12:00", "18:00"),
        ("night", "18:00", "00:00"),
        ("midnight", "00:00", "06:00"),
    ]
    off = client.put("/api/workspace/price-categories/", {"enabled": False}, format="json").json()
    assert off["enabled"] is False and len(off["suggested"]) == 4


def test_slot_is_priced_by_the_category_it_starts_in_including_after_midnight():
    turf, owner = make_turf()
    open_all_day(turf)
    client_for(owner).put("/api/workspace/price-categories/", CATEGORIES, format="json")
    field = turf.fields.first()
    assert quote(field, at(1, "07:00"), at(1, "08:00")).subtotal == Decimal("800.00")
    assert quote(field, at(1, "19:00"), at(1, "20:00")).subtotal == Decimal("2000.00")
    assert quote(field, at(1, "01:00"), at(1, "02:00")).subtotal == Decimal("1000.00")
    # 17:30–18:30 starts in Evening: the whole slot is Evening (not silently split).
    SlotTemplate.objects.create(
        turf=turf,
        field=field,
        weekday=at(1, "00:00").weekday(),
        start_time=at(1, "17:30").time(),
        end_time=at(1, "18:30").time(),
    )
    crossing = quote(field, at(1, "17:30"), at(1, "18:30"))
    assert crossing.subtotal == Decimal("1200.00") and crossing.segments[0]["label"] == "Evening"
    # Overnight slot 23:30–00:30 starts at Night.
    slot = SlotTemplate.objects.create(
        turf=turf,
        field=field,
        weekday=at(1, "00:00").weekday(),
        start_time=at(1, "23:30").time(),
        end_time=at(1, "00:30").time(),
    )
    assert slot.minutes == 60
    assert quote(field, at(1, "23:30"), at(2, "00:30")).subtotal == Decimal("2000.00")


def test_special_date_rule_beats_slot_price_and_categories():
    turf, owner = make_turf()
    open_all_day(turf)
    client_for(owner).put("/api/workspace/price-categories/", CATEGORIES, format="json")
    field = turf.fields.first()
    SlotTemplate.objects.create(
        turf=turf,
        field=field,
        weekday=at(1, "00:00").weekday(),
        start_time=at(1, "19:00").time(),
        end_time=at(1, "20:30").time(),
        price=Decimal("2500"),
    )
    assert quote(field, at(1, "19:00"), at(1, "20:30")).subtotal == Decimal("2500.00")  # whole-slot price
    PricingRule.objects.create(
        turf=turf,
        label="Eid",
        date=at(1, "00:00").date(),
        start_time=at(1, "00:00").time(),
        end_time=at(1, "00:00").time(),
        hourly_rate=Decimal("3000"),
    )
    assert quote(field, at(1, "19:00"), at(1, "20:30")).subtotal == Decimal("4500.00")


# ------------------------------------------------------------------ custom slots
def test_custom_slots_replace_the_grid_and_overlaps_are_refused():
    turf, owner = make_turf()
    client = client_for(owner)
    field = turf.fields.first()
    day = at(1, "00:00")
    wd = day.weekday()
    gen = client.post(
        "/api/workspace/slot-templates/generate/",
        {"field": str(field.id), "weekdays": [wd], "start": "16:00", "end": "22:00", "minutes": 90},
        format="json",
    )
    assert gen.status_code == 200, gen.json()
    assert [r["start_time"] for r in gen.json()] == ["16:00:00", "17:30:00", "19:00:00", "20:30:00"]
    slots = availability(field, day.date())
    assert [s["start"][11:16] for s in slots] == ["16:00", "17:30", "19:00", "20:30"]

    clash = client.post(
        "/api/workspace/slot-templates/",
        {"field": str(field.id), "weekday": wd, "start_time": "17:00", "end_time": "18:00"},
        format="json",
    )
    assert clash.status_code == 400 and "Overlaps" in str(clash.json())
    # Sunday 23:00–01:00 overlaps Monday 00:30 (week wraps).
    client.post(
        "/api/workspace/slot-templates/",
        {"field": str(field.id), "weekday": 0, "start_time": "00:30", "end_time": "01:30"},
        format="json",
    )
    wrap = client.post(
        "/api/workspace/slot-templates/",
        {"field": str(field.id), "weekday": 6, "start_time": "23:00", "end_time": "01:00"},
        format="json",
    )
    assert wrap.status_code == 400

    first = gen.json()[0]
    client.patch(f"/api/workspace/slot-templates/{first['id']}/", {"is_active": False}, format="json")
    assert [s["start"][11:16] for s in availability(field, day.date())] == ["17:30", "19:00", "20:30"]

    copied = client.post(
        "/api/workspace/slot-templates/copy/",
        {"field": str(field.id), "from_weekday": wd, "to_weekdays": [(wd + 2) % 7]},
        format="json",
    )
    assert copied.status_code == 200 and len([r for r in copied.json() if r["weekday"] == (wd + 2) % 7]) == 4
    client.post(
        "/api/workspace/slot-templates/clear/", {"field": str(field.id), "weekdays": [wd]}, format="json"
    )
    assert availability(field, day.date())[0]["start"][11:16] != "17:30"  # back to the automatic grid


def test_public_booking_must_match_whole_custom_slots():
    turf, owner = make_turf()
    field = turf.fields.first()
    wd = at(1, "00:00").weekday()
    client_for(owner).post(
        "/api/workspace/slot-templates/generate/",
        {"field": str(field.id), "weekdays": [wd], "start": "16:00", "end": "19:00", "minutes": 90},
        format="json",
    )

    def book(start, end, **extra):
        return APIClient().post(
            f"/api/public/turfs/{turf.slug}/book/",
            {
                "field": str(field.id),
                "start": at(1, start).isoformat(),
                "end": at(1, end).isoformat(),
                "name": "R",
                "phone": "01912345678",
                **bkash(),
                **extra,
            },
            format="json",
        )

    assert book("16:30", "17:30").status_code == 400  # not a listed slot
    ok = book("16:00", "19:00", phone="01812345678")  # two back-to-back slots
    assert ok.status_code == 201, ok.json()


def test_only_owner_or_permitted_manager_edits_slots_and_prices():
    turf, owner = make_turf()
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    membership = TenantMembership.objects.create(user=manager, turf=turf, role="manager")
    mgr = client_for(manager)
    assert mgr.get("/api/workspace/price-categories/").status_code == 200
    assert mgr.put("/api/workspace/price-categories/", CATEGORIES, format="json").status_code == 403
    membership.permissions = {**membership.permissions, "manage_slots": True}
    membership.save()
    assert mgr.put("/api/workspace/price-categories/", CATEGORIES, format="json").status_code == 200
    _, other = make_turf("Beta Turf", "beta@example.com")
    foreign = client_for(other).post(
        "/api/workspace/slot-templates/",
        {"field": str(turf.fields.first().id), "weekday": 1, "start_time": "10:00", "end_time": "11:00"},
        format="json",
    )
    assert foreign.status_code == 400  # another turf's field is not selectable


def test_public_page_lists_categories_and_slot_categories():
    turf, owner = make_turf()
    open_all_day(turf)
    client_for(owner).put("/api/workspace/price-categories/", CATEGORIES, format="json")
    page = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()
    assert [c["label"] for c in page["price_categories"]] == ["Morning", "Evening", "Night", "Midnight"]
    slots = availability(turf.fields.first(), at(1, "00:00").date())
    by_hour = {s["start"][11:13]: (s["category"], s["price"]) for s in slots}
    assert by_hour["07"] == ("morning", "800.00") and by_hour["19"] == ("night", "2000.00")
