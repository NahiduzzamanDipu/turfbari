"""Homepage contact details are centrally administered and safely exposed as public data."""

import pytest
from rest_framework.test import APIClient

from apps.common.models import PlatformSettings

from .test_core import client_for, make_turf
from .test_subscriptions import admin_client

pytestmark = pytest.mark.django_db


def test_public_contact_exposes_only_configured_visible_fields():
    settings = PlatformSettings.load()
    settings.contact_phone = "+880 1700-000000"
    settings.contact_email = "help@example.test"
    settings.contact_facebook_url = "https://www.facebook.com/turfbari"
    settings.contact_whatsapp = "8801700000000"
    settings.contact_address = "Dhaka"
    settings.contact_show_phone = False
    settings.save()

    response = APIClient().get("/api/public/contact/")

    assert response.status_code == 200
    assert response.data["phone"] is None
    assert response.data["email"] == "help@example.test"
    assert response.data["facebook_url"].endswith("/turfbari")
    assert response.data["whatsapp"] == "8801700000000"
    assert response.data["address"] == "Dhaka"
    assert "recharge_bkash_number" not in response.data


def test_admin_can_update_contact_details_and_cache_is_invalidated():
    admin, _ = admin_client()
    data = {
        "enabled": True,
        "phone": "+8801700000000",
        "email": "support@example.test",
        "facebook_url": "https://facebook.com/turfbari",
        "whatsapp": "8801700000000",
        "address": "Dhaka",
        "heading": "Get in Touch",
        "description": "We can help.",
        "show_phone": True,
        "show_email": True,
        "show_facebook": True,
        "show_whatsapp": True,
        "show_address": True,
    }
    assert admin.put("/api/admin/contact-settings/", data, format="json").status_code == 200
    assert APIClient().get("/api/public/contact/").data["phone"] == "+8801700000000"
    assert admin.get("/api/admin/contact-settings/").data["email"] == "support@example.test"


def test_contact_settings_validation_and_authorization():
    admin, _ = admin_client()
    _, owner = make_turf()
    invalid = {
        "enabled": True,
        "phone": "not a phone",
        "email": "bad",
        "facebook_url": "https://evil.test/page",
        "whatsapp": "",
        "address": "",
        "heading": "",
        "description": "",
        "show_phone": True,
        "show_email": True,
        "show_facebook": True,
        "show_whatsapp": True,
        "show_address": True,
    }
    assert admin.put("/api/admin/contact-settings/", invalid, format="json").status_code == 400
    assert client_for(owner).put("/api/admin/contact-settings/", invalid, format="json").status_code == 403
    assert PlatformSettings.load().contact_phone == ""


def test_hidden_section_returns_no_contact_values():
    settings = PlatformSettings.load()
    settings.contact_enabled = False
    settings.contact_phone = "+8801700000000"
    settings.save()
    response = APIClient().get("/api/public/contact/")
    assert response.data["enabled"] is False
    assert response.data["phone"] is None
