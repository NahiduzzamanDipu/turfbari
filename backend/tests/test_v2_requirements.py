"""Version 2 requirements: global video, terms agreement, SMS usage, drafts/idempotency, 2-slot limit,
online-booking switch, performance budget, credential safety. Numbers refer to the requirement list."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.common.models import PlatformSettings
from apps.notifications.models import SmsAttempt, SmsConfig, SmsMessage
from apps.notifications.providers import MemoryProvider
from apps.notifications.services import queue_sms, retry_due
from apps.turfs.models import TenantMembership

from .legal_helpers import doc_id, draft, publish
from .test_core import PASSWORD, bkash, client_for, make_turf, tomorrow_at
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db
VIDEO = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
LIMIT_BN = "একজন গ্রাহক প্রতিদিন সর্বোচ্চ ২টি স্লট বুক করতে পারবেন।"


def page(turf):
    return APIClient().get(f"/api/public/turfs/{turf.slug}/").json()


def book(turf, hour=18, phone="01912345678", visitor=None, key=None, terms=None, field=None, length=1):
    headers = {}
    if visitor:
        headers["HTTP_X_VISITOR_ID"] = visitor
    if key:
        headers["HTTP_IDEMPOTENCY_KEY"] = key
    body = {
        "field": str((field or turf.fields.first()).id),
        "start": tomorrow_at(hour).isoformat(),
        "end": tomorrow_at(hour + length).isoformat(),
        "name": "Rafi",
        "phone": phone,
        **bkash(),
    }
    if terms:
        body.update(agree_terms=True, accepted_versions=terms)
    return APIClient().post(f"/api/public/turfs/{turf.slug}/book/", body, format="json", **headers)


# ------------------------------------------------------------------ 1-4 global YouTube
def test_1_2_3_global_video_is_admin_only_and_same_on_every_page():
    a, owner = make_turf()
    b, _ = make_turf("Beta Turf", "beta@example.com")
    assert page(a)["youtube_video_id"] is None  # nothing configured: icon hidden
    admin, _ = admin_client()
    assert (
        admin.put(
            "/api/admin/api-config/youtube/",
            {"url": "https://evil.example/watch?v=aqz-KE-bpKQ"},
            format="json",
        ).status_code
        == 400
    )
    assert admin.put("/api/admin/api-config/youtube/", {"url": VIDEO}, format="json").status_code == 200
    assert page(a)["youtube_video_id"] == page(b)["youtube_video_id"] == "aqz-KE-bpKQ"
    assert APIClient().get("/api/public/youtube/").json()["video_id"] == page(a)["youtube_video_id"]
    admin.put("/api/admin/api-config/youtube/", {"url": "https://youtu.be/dQw4w9WgXcQ"}, format="json")
    assert page(a)["youtube_video_id"] == page(b)["youtube_video_id"] == "dQw4w9WgXcQ"  # updated everywhere
    assert APIClient().get("/api/public/youtube/").json()["video_id"] == page(b)["youtube_video_id"]
    owner_client = client_for(owner)
    assert (
        owner_client.put("/api/admin/api-config/youtube/", {"url": VIDEO}, format="json").status_code == 403
    )
    assert owner_client.put("/api/workspace/design/video/", {"url": VIDEO}, format="json").status_code == 404
    admin.put("/api/admin/api-config/youtube/", {"url": ""}, format="json")
    assert page(b)["youtube_video_id"] is None


def test_homepage_and_booking_youtube_videos_are_independent():
    turf, owner = make_turf()
    admin, _ = admin_client()
    booking_response = admin.put(
        "/api/admin/api-config/youtube/booking/",
        {"url": "https://youtu.be/aqz-KE-bpKQ", "title": "Booking guide", "enabled": True},
        format="json",
    )
    homepage_response = admin.put(
        "/api/admin/api-config/youtube/homepage/",
        {"url": "https://youtu.be/dQw4w9WgXcQ", "title": "About TurfBari", "enabled": True},
        format="json",
    )
    assert booking_response.status_code == homepage_response.status_code == 200
    assert APIClient().get("/api/public/youtube/").json() == {
        "video_id": "aqz-KE-bpKQ",
        "url": "https://youtu.be/aqz-KE-bpKQ",
        "title": "Booking guide",
        "enabled": True,
    }
    assert APIClient().get("/api/public/youtube/homepage/").json()["video_id"] == "dQw4w9WgXcQ"
    assert page(turf)["youtube_video_id"] == "aqz-KE-bpKQ"

    admin.put(
        "/api/admin/api-config/youtube/homepage/",
        {"url": "https://youtu.be/M7lc1UVf-VE", "title": "New homepage intro", "enabled": True},
        format="json",
    )
    assert APIClient().get("/api/public/youtube/homepage/").json()["video_id"] == "M7lc1UVf-VE"
    assert APIClient().get("/api/public/youtube/").json()["video_id"] == "aqz-KE-bpKQ"

    admin.put(
        "/api/admin/api-config/youtube/homepage/",
        {"url": "https://youtu.be/M7lc1UVf-VE", "title": "New homepage intro", "enabled": False},
        format="json",
    )
    assert APIClient().get("/api/public/youtube/homepage/").json()["enabled"] is False
    assert APIClient().get("/api/public/youtube/").json()["enabled"] is True

    admin.put(
        "/api/admin/api-config/youtube/booking/",
        {"url": "https://youtu.be/aqz-KE-bpKQ", "title": "Booking guide", "enabled": False},
        format="json",
    )
    assert APIClient().get("/api/public/youtube/").json()["enabled"] is False
    assert APIClient().get("/api/public/youtube/homepage/").json()["video_id"] == "M7lc1UVf-VE"
    assert page(turf)["youtube_video_id"] is None

    assert (
        admin.put(
            "/api/admin/api-config/youtube/homepage/", {"url": "https://evil.example/video"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client_for(owner)
        .put(
            "/api/admin/api-config/youtube/homepage/", {"url": "https://youtu.be/M7lc1UVf-VE"}, format="json"
        )
        .status_code
        == 403
    )
    assert (
        client_for(owner)
        .put("/api/admin/api-config/youtube/booking/", {"url": "https://youtu.be/aqz-KE-bpKQ"}, format="json")
        .status_code
        == 403
    )


# ------------------------------------------------------------------ 5-8 terms (now the legal system)
def test_5_admin_publishes_and_updates_terms_with_history():
    admin, _ = admin_client()
    v1 = publish(admin, "terms", body_en="<h2>Terms</h2><ul><li>Be on time</li></ul>")
    assert v1["version"] == 1 and APIClient().get("/api/public/legal/terms/").json()["version"] == 1
    draft(admin, "terms", body_en="<p>Draft only</p>")
    assert "Be on time" in APIClient().get("/api/public/legal/terms/").json()["body_en"]  # draft not public
    d = admin.get(f"/api/admin/legal/documents/{doc_id('terms')}/").json()
    v2 = admin.post(
        f"/api/admin/legal/versions/{d['draft']['id']}/publish/", {"reacceptance": "none"}, format="json"
    )
    assert v2.json()["version"] == 2
    d = admin.get(f"/api/admin/legal/documents/{doc_id('terms')}/").json()
    assert [v["state"] for v in d["versions"]] == ["current", "superseded"]
    old = APIClient().get("/api/public/legal/terms/?version=1").json()
    assert "Be on time" in old["body_en"] and old["is_current"] is False
    _, owner = make_turf()
    assert client_for(owner).get("/api/admin/legal/documents/").status_code == 403


def test_6_7_8_agreement_is_required_stored_and_kept_after_updates():
    turf, _ = make_turf()
    admin, _ = admin_client()
    v1 = publish(admin, "booking", body_en="<p>Pay the advance</p>")
    assert [d["version_id"] for d in page(turf)["legal"]] == [v1["id"]]
    refused = book(turf)
    assert refused.status_code == 400 and "agree_terms" in refused.json()["error"]["fields"]
    ok = book(turf, terms=[v1["id"]])
    assert ok.status_code == 201, ok.json()
    booking = Booking.objects.get(reference=ok.json()["reference"])
    assert booking.terms_agreed_at is not None
    assert list(booking.legal_acceptances.values_list("version_id", flat=True)) == [v1["id"]]
    v2 = publish(admin, "booking", body_en="<p>New rules</p>")
    stale = book(turf, hour=20, phone="01812345678", terms=[v1["id"]])  # page opened before the update
    assert stale.status_code == 400 and str(v2["id"]) in str(stale.json())
    # The existing booking keeps exactly what was agreed, and that text is unchanged.
    assert booking.legal_acceptances.get().version.body_en == "<p>Pay the advance</p>"


# ------------------------------------------------------------------ 9-11 SMS usage
def test_9_10_11_usage_per_tenant_platform_separate_retries_counted_once():
    a, owner_a = make_turf()
    b, _ = make_turf("Beta Turf", "beta@example.com")
    queue_sms(to="01712345678", body="a1", kind="booking_confirmed", turf=a)
    queue_sms(to="01712345678", body="a2", kind="payment_rejected", turf=a)
    MemoryProvider.fail_with = "1005"
    flaky = queue_sms(to="01812345678", body="b1", kind="booking_confirmed", turf=b)
    MemoryProvider.fail_with = None
    SmsMessage.objects.filter(pk=flaky.pk).update(next_attempt_at=timezone.now())
    retry_due()  # second attempt succeeds
    queue_sms(to="01712345678", body="plan", kind="subscription_reminder", turf=a)  # platform notice

    flaky.refresh_from_db()
    assert flaky.status == "sent" and SmsAttempt.objects.filter(message=flaky).count() == 2
    mine = client_for(owner_a).get("/api/workspace/sms/usage/").json()
    assert mine["all_time"]["sent"] == 2 and mine["all_time"]["booking_confirmations"] == 1
    assert mine["all_time"]["rejections_cancellations"] == 1 and mine["plan_notices_from_turfbari"] == 1

    admin, _ = admin_client()
    usage = admin.get("/api/admin/sms/usage/", {"from": str(timezone.localdate())}).json()
    rows = {r["turf"]["name"]: r for r in usage["turfs"]}
    assert rows["Alpha Turf"]["sent"] == 2 and rows["Beta Turf"]["sent"] == 1  # retry counted once
    assert rows["Beta Turf"]["attempts"] == 2 and usage["platform"]["sent"] == 1
    failed_only = admin.get("/api/admin/sms/usage/", {"status": "failed"}).json()
    assert failed_only["totals"]["sent"] == 0
    csv = admin.get("/api/admin/sms/usage/", {"export": "csv"})
    assert csv["Content-Type"].startswith("text/csv") and "Beta Turf" in csv.content.decode("utf-8")
    log = admin.get("/api/admin/sms/messages/", {"turf": str(b.id)}).json()["results"]
    assert len(log) == 1 and log[0]["scope"] == "tenant" and log[0]["turf"]["id"] == str(b.id)


# ------------------------------------------------------------------ 12 performance budget
def test_12_public_page_query_budget(django_assert_max_num_queries):
    turf, _ = make_turf()
    field = turf.fields.first()
    APIClient().get(f"/api/public/turfs/{turf.slug}/")  # warm the config cache
    with django_assert_max_num_queries(9):
        assert APIClient().get(f"/api/public/turfs/{turf.slug}/").status_code == 200
    url = f"/api/public/turfs/{turf.slug}/availability/?field={field.id}&date={tomorrow_at(0).date()}"
    APIClient().get(url)
    with django_assert_max_num_queries(8):
        assert APIClient().get(url).status_code == 200


# ------------------------------------------------------------------ 13-15 drafts, visitors, idempotency
def test_13_reload_recovers_the_hold_by_browser_id_not_ip():
    turf, _ = make_turf()
    field = turf.fields.first()
    me, other = str(uuid.uuid4()), str(uuid.uuid4())
    hold = APIClient().post(
        f"/api/public/turfs/{turf.slug}/hold/",
        {"field": str(field.id), "start": tomorrow_at(18).isoformat(), "end": tomorrow_at(19).isoformat()},
        format="json",
        HTTP_X_VISITOR_ID=me,
    )
    assert hold.status_code in (200, 201), hold.json()
    url = f"/api/public/turfs/{turf.slug}/availability/?field={field.id}&date={tomorrow_at(0).date()}"
    reloaded = APIClient().get(url, HTTP_X_VISITOR_ID=me).json()  # no token: page was reloaded
    assert reloaded["my_hold"]["token"] == hold.json()["token"]
    states = {s["start"][11:13]: s["state"] for s in reloaded["slots"]}
    assert states["18"] == "yours"
    neighbour = APIClient().get(url, HTTP_X_VISITOR_ID=other).json()  # same IP, different browser
    assert {s["start"][11:13]: s["state"] for s in neighbour["slots"]}["18"] == "held"
    assert neighbour["my_hold"] is None


def test_14_expired_draft_cannot_be_submitted_over_someone_else():
    turf, _ = make_turf()
    assert book(turf, phone="01812345678").status_code == 201  # someone books it meanwhile
    late = book(turf, phone="01912345678", visitor=str(uuid.uuid4()))
    assert late.status_code == 400


def test_15_retried_submit_returns_the_same_booking():
    turf, _ = make_turf()
    key = str(uuid.uuid4())
    first = book(turf, key=key)
    again = book(turf, key=key)  # double click / network retry
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["reference"] == again.json()["reference"]
    assert Booking.objects.filter(turf=turf).count() == 1


# ------------------------------------------------------------------ 16-18 two-slot limit
def test_16_17_limit_is_two_slots_across_turfs_and_pending_counts():
    a, _ = make_turf()
    b, _ = make_turf("Beta Turf", "beta@example.com")
    assert book(a, hour=10).status_code == 201  # pending (awaiting verification) counts
    assert book(b, hour=12).status_code == 201  # another turf, same phone
    third = book(a, hour=14, phone="+880 1912-345678")  # same number, other format
    assert third.status_code == 400 and LIMIT_BN in str(third.json())
    two_at_once = book(b, hour=16, phone="01712000111", length=2)
    assert (
        two_at_once.status_code == 201
        and Booking.objects.get(reference=two_at_once.json()["reference"]).slot_count == 2
    )
    assert book(b, hour=19, phone="01712000111").status_code == 400


def test_18_cancelled_rejected_expired_and_past_do_not_count():
    turf, owner = make_turf()
    refs = [book(turf, hour=h).json()["reference"] for h in (10, 12)]
    assert book(turf, hour=14).status_code == 400
    first = Booking.objects.get(reference=refs[0])
    first.payment_submission.status = "pending"
    client_for(owner).post(f"/api/workspace/payment-verifications/{first.payment_submission.id}/reject/")
    assert book(turf, hour=14).status_code == 201  # rejected one freed a place
    Booking.objects.filter(reference=refs[1]).update(hold_expires_at=timezone.now() - timedelta(seconds=1))
    assert book(turf, hour=16).status_code == 201  # expired hold freed another
    PlatformSettings.objects.update_or_create(pk=1, defaults={"max_slots_per_customer": 3})
    from django.core.cache import cache

    cache.clear()  # settings cache + this test's own booking rate-limit counter
    assert book(turf, hour=20).status_code == 201  # configurable limit


# ------------------------------------------------------------------ 19-21 online booking & isolation
def test_19_20_21_online_switch_uses_each_turfs_own_contact():
    a, _ = make_turf()
    b, _ = make_turf("Beta Turf", "beta@example.com")
    b.owner_phone = b.public_phone = "+8801812999888"
    b.public_booking_enabled = False
    b.save()
    pa, pb = page(a), page(b)
    assert pa["payment"]["accepts_online"] is True and pa["payment"]["bkash_number"] == "01711000000"
    assert pb["payment"]["accepts_online"] is False and pb["public_phone"] == "+8801812999888"
    assert book(b).status_code == 403


# ------------------------------------------------------------------ 22 credentials
def test_22_api_credentials_are_encrypted_masked_and_admin_only():
    admin, _ = admin_client()
    secret = "BULK-SECRET-KEY-123456"
    saved = admin.put(
        "/api/admin/api-config/bulksmsbd/", {"api_key": secret, "sender_id": "8809617"}, format="json"
    )
    assert saved.status_code == 200 and secret not in str(saved.json())
    assert saved.json()["api_key_masked"].startswith("BUL") and saved.json()["api_key_source"] == "admin"
    stored = SmsConfig.load().api_key_encrypted
    assert stored and secret not in stored
    assert secret not in str(admin.get("/api/admin/api-config/").json())
    _, owner = make_turf()
    assert client_for(owner).get("/api/admin/api-config/").status_code == 403
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=owner.memberships.first().turf, role="manager")
    assert client_for(manager).get("/api/admin/api-config/").status_code == 403
    assert APIClient().get("/api/admin/api-config/").status_code in (401, 403)
    assert secret not in str(
        APIClient().get(f"/api/public/turfs/{owner.memberships.first().turf.slug}/").json()
    )
