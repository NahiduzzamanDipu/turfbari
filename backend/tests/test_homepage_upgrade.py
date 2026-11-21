from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.models import PlatformSettings
from apps.homepage.models import ClientShowcaseOverride, ClientShowcaseSettings, HomepageFAQ, TurfOnboarding
from apps.notifications.models import SmsKind, SmsMessage, SmsPricing
from apps.notifications.wallet import blocked_by_admin
from apps.subscriptions.models import Plan, Subscription

from .test_core import client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def test_public_plan_listing_respects_visibility_and_display_order():
    monthly = Plan.objects.get(period=Plan.Period.MONTHLY)
    monthly.features = ["Custom slots"]
    monthly.display_order = 4
    monthly.save()
    hidden = Plan.objects.get(period=Plan.Period.YEARLY)
    hidden.is_public = False
    hidden.save()
    half_year = Plan.objects.get(period=Plan.Period.HALF_YEARLY)
    half_year.display_order = 5
    half_year.save()
    response = APIClient().get("/api/public/plans/")
    assert response.status_code == 200
    assert [item["period"] for item in response.data] == ["monthly", "half_yearly"]
    assert response.data[0]["features"] == ["Custom slots"]
    assert response.data[0]["sms_enabled"] is True


def test_public_sms_rate_and_cost_examples_come_from_current_configuration():
    SmsPricing.objects.all().delete()
    SmsPricing.objects.create(
        price_per_segment=Decimal("0.4200"),
        masking_price_per_segment=Decimal("0.5000"),
        bulk_price_per_segment=Decimal("0.3000"),
        effective_from=timezone.now() - timedelta(minutes=1),
    )
    response = APIClient().get("/api/public/sms-pricing/")
    assert response.status_code == 200
    assert response.data["price_per_segment"] == "0.4200"
    assert response.data["examples"][1] == {"segments": 2, "cost": "0.84"}


def test_global_youtube_setting_is_public_and_dynamic():
    PlatformSettings.objects.update_or_create(pk=1, defaults={"youtube_video_id": "dQw4w9WgXcQ"})
    assert APIClient().get("/api/public/youtube/").data["video_id"] == "dQw4w9WgXcQ"
    settings = PlatformSettings.objects.get(pk=1)
    settings.youtube_video_id = "M7lc1UVf-VE"
    settings.save()
    assert APIClient().get("/api/public/youtube/").data["video_id"] == "M7lc1UVf-VE"


def test_public_faqs_hide_drafts_and_admin_can_edit():
    published = HomepageFAQ.objects.create(question_en="Live?", answer_en="Yes", is_published=True)
    HomepageFAQ.objects.create(question_en="Draft?", answer_en="No", is_published=False)
    assert "Live?" in [row["question_en"] for row in APIClient().get("/api/public/faqs/").data]
    admin, _ = admin_client()
    response = admin.put(
        f"/api/admin/homepage/faqs/{published.pk}/",
        {
            "question_en": "Updated?",
            "question_bn": "",
            "answer_en": "Updated answer",
            "answer_bn": "",
            "display_order": 2,
            "is_published": False,
        },
        format="json",
    )
    assert response.status_code == 200
    public_questions = [row["question_en"] for row in APIClient().get("/api/public/faqs/").data]
    assert "Updated?" not in public_questions
    assert "Draft?" not in public_questions


def test_client_showcase_uses_active_subscriptions_and_exposes_only_public_logo_fields():
    turf, _ = make_turf("Logo Turf", "logo@example.com")
    turf.profile_image.name = f"turfs/{turf.pk}/profile.webp"
    turf.save(update_fields=["profile_image", "updated_at"])
    pending_turf, _ = make_turf("Pending Logo Turf", "pending-logo@example.com")
    pending_turf.profile_image.name = f"turfs/{pending_turf.pk}/profile.webp"
    pending_turf.save(update_fields=["profile_image", "updated_at"])
    pending_turf.subscriptions.update(status=Subscription.Status.PENDING_PAYMENT)
    expired_turf, _ = make_turf("Expired Logo Turf", "expired-logo@example.com")
    expired_turf.profile_image.name = f"turfs/{expired_turf.pk}/profile.webp"
    expired_turf.save(update_fields=["profile_image", "updated_at"])
    expired_turf.subscriptions.update(ends_on=timezone.localdate() - timedelta(days=1))
    suspended_turf, _ = make_turf("Suspended Logo Turf", "suspended-logo@example.com")
    suspended_turf.profile_image.name = f"turfs/{suspended_turf.pk}/profile.webp"
    suspended_turf.status = suspended_turf.Status.SUSPENDED
    suspended_turf.save(update_fields=["profile_image", "status", "updated_at"])

    response = APIClient().get("/api/public/client-showcase/")

    assert response.status_code == 200
    assert [client["slug"] for client in response.data["clients"]] == [turf.slug]
    assert response.data["clients"][0]["logo_url"].endswith("profile.webp")
    assert set(response.data["clients"][0]) == {"slug", "name", "logo_url", "display_order"}
    assert "owner_phone" not in response.data["clients"][0]
    assert "email" not in response.data["clients"][0]


def test_client_showcase_hides_missing_logos_and_admin_can_hide_and_restore_clients():
    turf, _ = make_turf("Showcase Candidate", "candidate@example.com")
    admin, _ = admin_client()

    public_url = "/api/public/client-showcase/"
    assert APIClient().get(public_url).data["clients"] == []

    turf.profile_image.name = f"turfs/{turf.pk}/logo.webp"
    turf.save(update_fields=["profile_image", "updated_at"])
    visible = APIClient().get(public_url).data["clients"]
    assert [item["slug"] for item in visible] == [turf.slug]

    changed = admin.patch(
        f"/api/admin/homepage/client-showcase/{turf.pk}/",
        {"mode": ClientShowcaseOverride.Mode.HIDE, "display_order": 4},
        format="json",
    )
    assert changed.status_code == 200
    assert APIClient().get(public_url).data["clients"] == []

    restored = admin.patch(
        f"/api/admin/homepage/client-showcase/{turf.pk}/",
        {"mode": ClientShowcaseOverride.Mode.AUTO, "display_order": 2},
        format="json",
    )
    assert restored.status_code == 200
    visible = APIClient().get(public_url).data["clients"]
    assert visible[0]["slug"] == turf.slug
    assert visible[0]["display_order"] == 2


def test_client_showcase_admin_settings_control_enabled_auto_and_plan_eligibility():
    turf, _ = make_turf("Plan Logo Turf", "plan-logo@example.com")
    turf.profile_image.name = f"turfs/{turf.pk}/logo.webp"
    turf.save(update_fields=["profile_image", "updated_at"])
    settings, _ = ClientShowcaseSettings.objects.get_or_create(key="homepage")
    admin, _ = admin_client()

    plan = Plan.objects.get(pk=turf.subscriptions.first().plan_id)
    response = admin.patch(
        "/api/admin/homepage/client-showcase/",
        {"enabled": False, "auto_include": False, "eligible_plan_ids": [str(plan.pk)]},
        format="json",
    )
    assert response.status_code == 200
    assert APIClient().get("/api/public/client-showcase/").data["clients"] == []

    settings.refresh_from_db()
    assert list(settings.eligible_plans.values_list("pk", flat=True)) == [plan.pk]

    admin.patch(f"/api/admin/homepage/client-showcase/{turf.pk}/", {"mode": "include"}, format="json")
    admin.patch("/api/admin/homepage/client-showcase/", {"enabled": True}, format="json")
    assert [item["slug"] for item in APIClient().get("/api/public/client-showcase/").data["clients"]] == [
        turf.slug
    ]


def test_plan_edits_do_not_rewrite_existing_subscription_snapshot():
    turf, owner = make_turf()
    subscription = Subscription.objects.get(turf=turf, status=Subscription.Status.ACTIVE)
    original_name = subscription.plan_snapshot["name"]
    plan = subscription.plan
    admin, _ = admin_client()
    response = admin.patch(
        f"/api/admin/plans/{plan.pk}/",
        {
            "name": "Revised Plan",
            "features": ["New benefit"],
            "limits": {"managers": 2},
        },
        format="json",
    )
    assert response.status_code == 200
    subscription.refresh_from_db()
    assert subscription.plan_snapshot["name"] == original_name
    assert subscription.plan_snapshot["features"] != ["New benefit"]
    assert client_for(owner).get("/api/admin/onboarding/").status_code == 403


def test_admin_onboarding_tracker_lists_active_accounts_and_records_updates():
    turf, _ = make_turf()
    admin, _ = admin_client()
    response = admin.get("/api/admin/onboarding/")
    assert response.status_code == 200
    item = TurfOnboarding.objects.get(turf=turf)
    assert any(row["id"] == str(item.pk) for row in response.data["results"])
    response = admin.patch(
        f"/api/admin/onboarding/{item.pk}/",
        {
            "status": "scheduled",
            "notes": "Owner requested a morning session",
            "topics": ["Account setup"],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "scheduled"
    assert item.events.count() == 1
    item.refresh_from_db()
    assert item.events.count() == 1


def test_sms_disabled_in_historical_plan_snapshot_blocks_tenant_message():
    turf, _ = make_turf()
    sub = Subscription.objects.get(turf=turf, status=Subscription.Status.ACTIVE)
    sub.plan_snapshot["sms_enabled"] = False
    sub.save(update_fields=["plan_snapshot", "updated_at"])
    assert blocked_by_admin(turf, SmsKind.CUSTOM) == SmsMessage.BlockReason.PLAN_DISABLED


def test_configured_manager_plan_limit_is_enforced_server_side():
    turf, owner = make_turf()
    sub = Subscription.objects.get(turf=turf, status=Subscription.Status.ACTIVE)
    sub.plan_snapshot["limits"] = {"managers": 0}
    sub.save(update_fields=["plan_snapshot", "updated_at"])
    response = client_for(owner).post(
        "/api/workspace/managers/",
        {"email": "new.manager@example.com", "full_name": "New Manager", "phone": "01712345678"},
        format="json",
    )
    assert response.status_code == 400
    assert "plan_limit" in response.data["error"]["fields"]
