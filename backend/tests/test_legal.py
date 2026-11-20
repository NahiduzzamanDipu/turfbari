"""Legal & Compliance management: versioned platform/sector documents, mandatory acceptance at
registration / first sign-in / booking / plan orders / SMS recharges, immutable records, admin tools."""

import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.common.models import PlatformSettings, TermsVersion
from apps.legal.models import LegalAcceptance, LegalDocument, LegalDocumentVersion, Sector
from apps.turfs.models import TenantMembership

from .legal_helpers import doc_id, draft, publish
from .test_account_security import sign_in
from .test_core import PASSWORD, bkash, client_for, make_turf, tomorrow_at
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def page(turf):
    return APIClient().get(f"/api/public/turfs/{turf.slug}/").json()


def book(turf, accepted=None, hour=18, phone="01912345678", agree=True):
    body = {
        "field": str(turf.fields.first().id),
        "start": tomorrow_at(hour).isoformat(),
        "end": tomorrow_at(hour + 1).isoformat(),
        "name": "Rafi",
        "phone": phone,
        "agree_terms": agree,
        "accepted_versions": accepted
        if accepted is not None
        else [d["version_id"] for d in page(turf)["legal"]],
        **bkash(),
    }
    return APIClient().post(f"/api/public/turfs/{turf.slug}/book/", body, format="json")


def new_sector(admin, name="Badminton Courts", slug="badminton"):
    r = admin.post("/api/admin/legal/sectors/", {"name_en": name, "slug": slug}, format="json")
    assert r.status_code == 201, r.json()
    return Sector.objects.get(slug=slug)


APPLICATION = {
    "turf_name": "New Ground",
    "owner_name": "Sadia",
    "phone": "01755000010",
    "email": "sadia@example.com",
    "district": "dhaka",
    "address": "Road 5",
    "turf_type": "outdoor",
    "number_of_fields": 2,
}


# 1 ------------------------------------------------------------------ drafts never public
def test_1_draft_preview_publish_and_only_published_is_public():
    admin, _ = admin_client()
    assert (
        APIClient().get("/api/public/legal/privacy/").status_code == 404
    )  # module exists, nothing published
    d = draft(
        admin, "privacy", body_en="<p>We keep your phone number to send booking SMS.</p>", title_bn="গোপনীয়তা"
    )
    assert d["state"] == "draft" and admin.get(f"/api/admin/legal/versions/{d['id']}/").status_code == 200
    assert APIClient().get("/api/public/legal/privacy/").status_code == 404  # drafts are never exposed
    assert APIClient().get(f"/api/public/legal/versions/{d['id']}/").status_code == 404
    index = APIClient().get("/api/public/legal/").json()
    assert "privacy" not in [x["category"] for x in index["documents"]]
    publish_r = admin.post(
        f"/api/admin/legal/versions/{d['id']}/publish/", {"reacceptance": "all"}, format="json"
    )
    assert publish_r.status_code == 200
    public = APIClient().get("/api/public/legal/privacy/").json()
    assert public["version"] == 1 and "phone number" in public["body_en"] and public["effective_at"]
    assert public["published_at"] and public["title_bn"] == "গোপনীয়তা"


# 2 ------------------------------------------------------------------ sanitisation
def test_2_rich_text_is_sanitised_on_save():
    admin, _ = admin_client()
    nasty = (
        '<h2 onclick="steal()">Title</h2><script>alert(1)</script>'
        '<p style="x">Hi <a href="javascript:alert(1)">'
        'x</a> <a href="https://example.org">ok</a></p><iframe src="https://evil"></iframe>'
        "<table><tr><td>Cell</td></tr></table><ul><li><strong>Bold</strong></li></ul><img src=x onerror=1>"
    )
    d = draft(admin, "terms", body_en=nasty, body_bn="<p>বাংলা<script>x</script></p>")
    for bad in ("script", "onclick", "javascript:", "iframe", "style=", "onerror", "<img"):
        assert bad not in d["body_en"], bad
    assert (
        "<table>" in d["body_en"]
        and "<strong>Bold</strong>" in d["body_en"]
        and "<h2>Title</h2>" in d["body_en"]
    )
    assert 'href="https://example.org"' in d["body_en"] and "noopener" in d["body_en"]
    assert d["body_bn"] == "<p>বাংলা</p>"


# 3 ------------------------------------------------------------------ immutability and history
def test_3_published_versions_are_immutable_and_history_is_kept():
    admin, admin_user = admin_client()
    v1 = publish(admin, "rules", body_en="<p>Rule one</p>")
    edit = admin.put(
        f"/api/admin/legal/versions/{v1['id']}/", {"title_en": "X", "body_en": "<p>x</p>"}, format="json"
    )
    assert edit.status_code == 400
    assert admin.delete(f"/api/admin/legal/versions/{v1['id']}/").status_code == 400
    row = LegalDocumentVersion.objects.get(pk=v1["id"])
    row.body_en = "<p>tampered</p>"
    with pytest.raises(ValueError):
        row.save()
    v2 = publish(admin, "rules", body_en="<p>Rule one</p><p>Rule two</p>", change_summary="Added rule two")
    assert v2["version"] == 2 and v2["published_by"] == (admin_user.full_name or admin_user.email)
    doc = admin.get(f"/api/admin/legal/documents/{doc_id('rules')}/").json()
    assert [(v["version"], v["state"]) for v in doc["versions"]] == [(2, "current"), (1, "superseded")]
    assert LegalDocumentVersion.objects.get(pk=v1["id"]).body_en == "<p>Rule one</p>"
    cmp = admin.get(f"/api/admin/legal/versions/{v1['id']}/compare/{v2['id']}/").json()
    assert cmp["changes"] == 1 and {"type": "added", "text": "Rule two"} in cmp["rows"]
    history = APIClient().get("/api/public/legal/rules/").json()["history"]
    assert [h["version"] for h in history] == [2, 1] and history[0]["change_summary"] == "Added rule two"
    # Withdrawing v2 makes v1 current again; v2's text and record stay.
    admin.post(f"/api/admin/legal/versions/{v2['id']}/unpublish/")
    assert APIClient().get("/api/public/legal/rules/").json()["version"] == 1


# 4 ------------------------------------------------------------------ no placeholders
def test_4_empty_documents_cannot_be_published_and_unpublished_modules_block_nobody():
    admin, _ = admin_client()
    d = draft(admin, "sms", body_en="<p> </p><script>x</script>")
    r = admin.post(f"/api/admin/legal/versions/{d['id']}/publish/", {"reacceptance": "all"}, format="json")
    assert r.status_code == 400 and "body" in r.json()["error"]["fields"]
    turf, owner = make_turf()
    assert page(turf)["legal"] == []  # nothing published: booking needs no ticks
    assert book(turf, accepted=[], agree=False).status_code == 201
    assert client_for(owner).get("/api/workspace/dashboard/").status_code == 200
    # Core platform documents can't be made optional.
    r = admin.patch(f"/api/admin/legal/documents/{doc_id('terms')}/", {"is_mandatory": False}, format="json")
    assert r.status_code == 400


# 5 ------------------------------------------------------------------ sectors and inheritance
def test_5_sector_documents_apply_only_to_their_sector_in_inheritance_order():
    admin, _ = admin_client()
    football, _ = make_turf()
    other, _ = make_turf("Shuttle Club", "shuttle@example.com")
    badminton = new_sector(admin)
    other.sector = badminton
    other.save()
    assert LegalDocument.objects.filter(sector=badminton).count() == 2  # its own terms + rules modules
    publish(admin, "booking", body_en="<p>Booking policy</p>")
    publish(admin, "sector_rules", sector="badminton", body_en="<p>Non-marking shoes only</p>")
    publish(admin, "terms", body_en="<p>General terms</p>")
    publish(admin, "sector_terms", sector="football-turf", body_en="<p>Football terms</p>")
    publish(admin, "refund", body_en="<p>Refunds</p>")
    assert [d["category"] for d in page(football)["legal"]] == ["terms", "sector_terms", "booking", "refund"]
    assert [d["category"] for d in page(other)["legal"]] == ["terms", "sector_rules", "booking", "refund"]
    sector_page = APIClient().get("/api/public/legal/sector/badminton/").json()
    assert [d["category"] for d in sector_page["documents"]] == ["sector_rules"]
    assert {d["category"] for d in sector_page["inherited"]} == {"terms", "booking", "refund"}
    # Deactivating a sector hides its documents everywhere.
    admin.patch(f"/api/admin/legal/sectors/{badminton.pk}/", {"is_active": False}, format="json")
    assert [d["category"] for d in page(other)["legal"]] == ["terms", "booking", "refund"]
    assert APIClient().get("/api/public/legal/sector/badminton/").status_code == 404


# 6 ------------------------------------------------------------------ booking agreement
def test_6_every_booking_records_acceptance_of_each_exact_version():
    admin, _ = admin_client()
    turf, _ = make_turf()
    terms = publish(admin, "terms", body_en="<p>Terms</p>")
    policy = publish(admin, "refund", body_en="<p>Advance is non-refundable within 2 hours</p>")
    unticked = book(turf, agree=False)
    assert unticked.status_code == 400 and unticked.json()["error"]["fields"]["code"] == [
        "legal_acceptance_required"
    ]
    partial = book(turf, accepted=[terms["id"]])
    assert partial.status_code == 400 and partial.json()["error"]["fields"]["code"] == [
        "legal_versions_changed"
    ]
    ok = book(turf)
    assert ok.status_code == 201, ok.json()
    booking = Booking.objects.get(reference=ok.json()["reference"])
    rows = list(booking.legal_acceptances.order_by("category"))
    assert {r.version_id for r in rows} == {terms["id"], policy["id"]}
    assert all(r.action == "booking" and r.turf_id == turf.pk and r.sector_id == turf.sector_id for r in rows)
    assert rows[0].related_ref == f"booking:{booking.reference}" and rows[0].user_id is None
    second = book(turf, hour=20, phone="01812345678")  # every booking asks again
    assert second.status_code == 201 and LegalAcceptance.objects.filter(action="booking").count() == 4


# 7 ------------------------------------------------------------------ registration
def test_7_registration_requires_acceptance_and_owner_is_not_asked_again():
    admin, _ = admin_client()
    publish(admin, "terms", body_en="<p>Terms</p>")
    rules = publish(admin, "rules", body_en="<p>Platform rules</p>")
    needed = APIClient().get("/api/public/legal/required/", {"action": "registration"}).json()
    ids = [d["version_id"] for d in needed["documents"]]
    assert len(ids) == 2 and needed["sector"]["slug"] == "football-turf"
    refused = APIClient().post("/api/public/applications/", APPLICATION, format="json")
    assert refused.status_code == 400 and "agree_legal" in refused.json()["error"]["fields"]
    stale = APIClient().post(
        "/api/public/applications/",
        {**APPLICATION, "agree_legal": True, "accepted_versions": ids[:1]},
        format="json",
    )
    assert stale.status_code == 400
    ok = APIClient().post(
        "/api/public/applications/",
        {**APPLICATION, "agree_legal": True, "accepted_versions": ids},
        format="json",
    )
    assert ok.status_code == 201
    assert LegalAcceptance.objects.filter(action="registration", user__isnull=True).count() == 2
    from apps.applications.models import TurfApplication

    application = TurfApplication.objects.get()
    approved = admin.post(f"/api/admin/applications/{application.id}/approve/", {}, format="json").json()
    owner = get_user_model().objects.get(email="sadia@example.com")
    assert LegalAcceptance.objects.filter(user=owner, version_id=rules["id"], action="registration").exists()
    from .test_account_security import sms_password

    assert approved["temporary_password"] is None
    client, r = sign_in("sadia@example.com", sms_password())
    assert r.json()["user"]["legal_pending"] is False  # already accepted when applying


# 8 ------------------------------------------------------------------ first sign-in gate
def test_8_first_sign_in_gate_blocks_workspace_until_accepted():
    admin, _ = admin_client()
    turf, owner = make_turf()
    v = publish(admin, "account_usage", body_en="<p>Keep your password private</p>")
    client, r = sign_in(owner.email, PASSWORD)
    assert r.json()["user"]["legal_pending"] is True
    blocked = client.get("/api/workspace/bookings/")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "legal_acceptance_required"
    assert client_for(owner).get("/api/workspace/dashboard/").status_code == 403  # API-level too, not just UI
    assert APIClient().get(f"/api/public/turfs/{turf.slug}/").status_code == 200  # public pages unaffected
    status = client.get("/api/legal/status/").json()
    assert [p["version_id"] for p in status["pending"]] == [v["id"]] and "password" in status["pending"][0][
        "body_en"
    ]
    assert (
        client.post(
            "/api/legal/accept/", {"accepted_versions": [v["id"]], "agree": False}, format="json"
        ).status_code
        == 400
    )
    ok = client.post("/api/legal/accept/", {"accepted_versions": [v["id"]], "agree": True}, format="json")
    assert ok.status_code == 200
    assert client.get("/api/workspace/bookings/").status_code == 200
    assert client.get("/api/auth/me/").json()["user"]["legal_pending"] is False
    history = client.get("/api/legal/status/").json()["history"]
    assert history[0]["version"] == 1 and history[0]["action"] == "account"
    # Platform admins are never gated.
    assert admin.get("/api/admin/legal/").status_code == 200


# 9 ------------------------------------------------------------------ re-acceptance scopes
def test_9_reacceptance_scopes_only_block_the_affected_users():
    admin, _ = admin_client()
    football, owner = make_turf()
    shuttle, shuttle_owner = make_turf("Shuttle Club", "shuttle@example.com")
    badminton = new_sector(admin)
    shuttle.sector = badminton
    shuttle.save()
    v1 = publish(admin, "terms", body_en="<p>v1</p>")
    for user in (owner, shuttle_owner):
        client_for(user).post(
            "/api/legal/accept/", {"accepted_versions": [v1["id"]], "agree": True}, format="json"
        )

    def gated(user):
        return client_for(user).get("/api/workspace/dashboard/").status_code == 403

    publish(admin, "terms", body_en="<p>v2 typo fix</p>", reaccept="none")
    assert not gated(owner) and not gated(shuttle_owner)
    publish(admin, "terms", body_en="<p>v3</p>", reaccept="sector", reaccept_sector="badminton")
    assert not gated(owner) and gated(shuttle_owner)
    publish(admin, "terms", body_en="<p>v4</p>", reaccept="next_action")
    assert not gated(owner)  # not at sign-in: only at the next action the document covers
    plan_v1 = publish(admin, "subscription", body_en="<p>Plan policy</p>")
    order = {"plan": "monthly", "agree_legal": True, "accepted_versions": [plan_v1["id"]]}
    invoice = client_for(owner).post("/api/workspace/subscription/order/", order, format="json").json()
    client_for(owner).post(f"/api/workspace/subscription/invoices/{invoice['id']}/cancel/")
    publish(admin, "subscription", body_en="<p>Plan policy v2</p>", reaccept="next_action")
    pending = client_for(owner).get("/api/legal/pending/", {"action": "subscription"}).json()["documents"]
    assert [(p["category"], p["version"]) for p in pending] == [("subscription", 2)]
    publish(admin, "terms", body_en="<p>v5</p>", reaccept="all")
    assert gated(owner)
    # A brand-new user must always accept the current version, whatever the scope.
    publish(admin, "privacy", body_en="<p>Privacy</p>", reaccept="none")
    newbie_turf, newbie = make_turf("Gamma", "gamma@example.com")
    assert {p["category"] for p in client_for(newbie).get("/api/legal/status/").json()["pending"]} == {
        "terms",
        "privacy",
    }


# 10 ----------------------------------------------------------------- plan orders and recharges
def test_10_plan_orders_and_recharges_ask_only_for_relevant_unaccepted_documents():
    admin, _ = admin_client()
    turf, owner = make_turf()
    client = client_for(owner)
    sub = publish(admin, "subscription", body_en="<p>Plans renew only when paid</p>")
    sms = publish(admin, "sms", body_en="<p>Credit is non-refundable</p>")
    assert client.get("/api/workspace/dashboard/").status_code == 200  # neither blocks the workspace
    refused = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json")
    assert refused.status_code == 400 and "agree_legal" in refused.json()["error"]["fields"]
    ok = client.post(
        "/api/workspace/subscription/order/",
        {"plan": "monthly", "agree_legal": True, "accepted_versions": [sub["id"]]},
        format="json",
    )
    assert ok.status_code == 201, ok.json()
    # Accepted once: the next order doesn't ask again.
    client.post(f"/api/workspace/subscription/invoices/{ok.json()['id']}/cancel/")
    again = client.post("/api/workspace/subscription/order/", {"plan": "monthly"}, format="json")
    assert again.status_code == 201, again.json()
    PlatformSettings.objects.update_or_create(pk=1, defaults={"recharge_bkash_number": "01999000111"})
    from django.core.cache import cache

    cache.delete("platform:settings")
    body = {
        "wallet_amount": "1000",
        "amount_sent": "1019",
        "sender_number": "01712345678",
        "trx_id": "RCH0000001",
    }
    assert client.post("/api/workspace/sms/wallet/recharge/", body, format="json").status_code == 400
    assert [
        p["version_id"]
        for p in client.get("/api/legal/pending/", {"action": "sms_recharge"}).json()["documents"]
    ] == [sms["id"]]
    done = client.post(
        "/api/workspace/sms/wallet/recharge/",
        {**body, "agree_legal": True, "accepted_versions": [sms["id"]]},
        format="json",
    )
    assert done.status_code == 201, done.json()
    assert (
        LegalAcceptance.objects.filter(user=owner, action="sms_recharge", version_id=sms["id"]).count() == 1
    )


# 11 ----------------------------------------------------------------- immutable records
def test_11_acceptance_records_cannot_be_changed_or_deleted():
    admin, _ = admin_client()
    turf, _ = make_turf()
    publish(admin, "booking", body_en="<p>Booking policy</p>")
    assert book(turf).status_code == 201
    row = LegalAcceptance.objects.get()
    row.action = "account"
    with pytest.raises(ValueError):
        row.save()
    with pytest.raises(ValueError):
        row.delete()
    assert LegalAcceptance.objects.get().action == "booking"


# 12 ----------------------------------------------------------------- access control
def test_12_only_platform_admins_manage_documents_and_owners_cannot_edit():
    admin, _ = admin_client()
    turf, owner = make_turf()
    v = publish(admin, "terms", body_en="<p>Terms</p>")
    client_for(owner).post(
        "/api/legal/accept/", {"accepted_versions": [v["id"]], "agree": True}, format="json"
    )
    owner_client = client_for(owner)
    for method, url in (
        ("get", "/api/admin/legal/"),
        ("get", "/api/admin/legal/documents/"),
        ("post", f"/api/admin/legal/documents/{doc_id('terms')}/versions/"),
        ("put", f"/api/admin/legal/versions/{v['id']}/"),
        ("post", f"/api/admin/legal/versions/{v['id']}/unpublish/"),
        ("get", "/api/admin/legal/acceptances/"),
        ("post", "/api/admin/legal/sectors/"),
    ):
        assert getattr(owner_client, method)(url, {}, format="json").status_code == 403, url
    assert APIClient().get("/api/admin/legal/").status_code in (401, 403)
    # Owners see what applies to them (platform vs sector) and their own business policy, read-only.
    turf.cancellation_policy = "No refunds after 6 pm"
    turf.save()
    status = owner_client.get("/api/legal/status/").json()
    assert status["documents"][0]["scope"] == "platform" and status["business"]["cancellation_policy"]


# 13 ----------------------------------------------------------------- scheduled versions
def test_13_scheduled_version_takes_effect_at_its_time():
    admin, _ = admin_client()
    turf, _ = make_turf()
    v1 = publish(admin, "booking", body_en="<p>Now</p>")
    later = timezone.now() + timedelta(days=2)
    v2 = publish(admin, "booking", body_en="<p>Later</p>", effective_at=later.isoformat())
    assert [d["version_id"] for d in page(turf)["legal"]] == [v1["id"]]
    doc = admin.get(f"/api/admin/legal/documents/{doc_id('booking')}/").json()
    assert {v["version"]: v["state"] for v in doc["versions"]} == {2: "scheduled", 1: "current"}
    LegalDocumentVersion.objects.filter(pk=v2["id"]).update(
        effective_at=timezone.now() - timedelta(seconds=1)
    )
    from apps.legal.services import bump_revision

    bump_revision()
    assert [d["version_id"] for d in page(turf)["legal"]] == [v2["id"]]
    past = draft(admin, "terms", body_en="<p>x</p>")
    r = admin.post(
        f"/api/admin/legal/versions/{past['id']}/publish/",
        {"reacceptance": "all", "effective_at": (timezone.now() - timedelta(days=1)).isoformat()},
        format="json",
    )
    assert r.status_code == 400


# 14 ----------------------------------------------------------------- monitoring and export
def test_14_admin_monitoring_search_export_and_audit_with_minimal_personal_data():
    admin, _ = admin_client()
    turf, owner = make_turf()
    publish(admin, "booking", body_en="<p>Booking policy</p>")
    v = publish(admin, "account_usage", body_en="<p>Account rules</p>")
    assert book(turf, phone="01912345678").status_code == 201
    overview = admin.get("/api/admin/legal/").json()
    assert overview["published"] == 2 and overview["acceptances"] == 1 and overview["pending_accounts"] == 1
    assert admin.get("/api/admin/legal/pending/").json()["results"][0]["email"] == owner.email
    client_for(owner).post(
        "/api/legal/accept/", {"accepted_versions": [v["id"]], "agree": True}, format="json"
    )
    found = admin.get("/api/admin/legal/acceptances/", {"q": turf.name, "action": "booking"}).json()
    assert found["count"] == 1 and found["results"][0]["booking"]
    assert "01912345678" not in str(found)  # customer phone numbers are not exposed
    csv = admin.get("/api/admin/legal/acceptances/", {"export": "csv"})
    text = csv.content.decode("utf-8-sig")
    assert (
        csv.status_code == 200 and "Booking & Reservation Policy" in text and "Account Usage Policy" in text
    )
    assert "01912345678" not in text
    from apps.audit.models import AuditEvent

    assert AuditEvent.objects.filter(action="legal.published").count() == 2
    assert AuditEvent.objects.filter(action="legal.acceptances_exported").exists()


# 15 ----------------------------------------------------------------- migration of the old system
def test_15_old_terms_and_booking_agreements_are_migrated():
    turf, _ = make_turf()
    LegalDocumentVersion.objects.all().delete()
    old = TermsVersion.objects.create(
        version=1,
        terms_body="# শর্তাবলী\n- সময়মতো আসুন",
        rules_body="1. Pay the advance\n2. **Be on time**",
        status="published",
        published_at=timezone.now() - timedelta(days=10),
    )
    from apps.bookings.services import get_or_create_customer

    booking = Booking.objects.create(
        turf=turf,
        customer=get_or_create_customer(turf, name="Old", phone="01912345678"),
        field=turf.fields.first(),
        start=tomorrow_at(18),
        end=tomorrow_at(19),
        total=Decimal("1000"),
        terms_version=old,
        terms_agreed_at=timezone.now() - timedelta(days=3),
    )
    migration = importlib.import_module("apps.legal.migrations.0002_seed_and_migrate_terms")
    migration.forwards(global_apps, None)
    terms = LegalDocumentVersion.objects.get(document__category="terms")
    rules = LegalDocumentVersion.objects.get(document__category="booking")
    assert terms.status == "published" and terms.version == 1 and "<h2>শর্তাবলী</h2>" in terms.body_bn
    assert rules.body_en == "<ol><li>Pay the advance</li><li><strong>Be on time</strong></li></ol>"
    rows = LegalAcceptance.objects.filter(booking=booking)
    assert {r.version_id for r in rows} == {terms.pk, rules.pk}
    assert all(abs((r.accepted_at - booking.terms_agreed_at).total_seconds()) < 1 for r in rows)
    assert TenantMembership.objects.filter(turf=turf).exists() and turf.sector.slug == "football-turf"


# 16 ----------------------------------------------------------------- standard text drafts
def test_16_standard_text_drafts_exist_for_every_module_and_nothing_is_published():
    importlib.import_module("apps.legal.migrations.0003_standard_drafts").add_drafts(global_apps, None)
    from apps.legal import content
    from apps.legal.standard_text import DOCS, standard_text

    for doc in LegalDocument.objects.filter(sector__slug="football-turf") | LegalDocument.objects.filter(
        sector__isnull=True
    ):
        draft_v = doc.versions.get(status="draft")
        assert draft_v.title_en and draft_v.title_bn, doc
        assert not content.is_blank(draft_v.body_en) and not content.is_blank(draft_v.body_bn), doc
        assert draft_v.body_en == content.sanitize(draft_v.body_en)  # stored already clean
    assert set(DOCS) == {c for c, _ in LegalDocument.Category.choices}
    assert not LegalDocumentVersion.objects.filter(published_at__isnull=False).exists()
    assert APIClient().get("/api/public/legal/").json()["documents"] == []
    # Running it again doesn't add a second draft.
    importlib.import_module("apps.legal.migrations.0003_standard_drafts").add_drafts(global_apps, None)
    assert LegalDocumentVersion.objects.filter(document__category="terms", status="draft").count() == 1
    # The football wording is never offered for another sport.
    assert standard_text("sector_rules", "Badminton Courts") is None


def test_17_admin_can_load_standard_text_and_publish_after_editing():
    admin, _ = admin_client()
    _, owner = make_turf()
    text = admin.get(f"/api/admin/legal/documents/{doc_id('privacy')}/standard-text/").json()
    assert "bKash" in text["body_en"] and "বিকাশ" in text["body_bn"]
    assert (
        client_for(owner).get(f"/api/admin/legal/documents/{doc_id('privacy')}/standard-text/").status_code
        == 403
    )
    v = draft(
        admin, "privacy", body_en=text["body_en"] + "<p>Our office: Dhaka.</p>", body_bn=text["body_bn"]
    )
    r = admin.post(f"/api/admin/legal/versions/{v['id']}/publish/", {"reacceptance": "all"}, format="json")
    assert r.status_code == 200
    assert "Our office: Dhaka." in APIClient().get("/api/public/legal/privacy/").json()["body_en"]
