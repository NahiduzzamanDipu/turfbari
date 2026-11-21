import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.common.models import PlatformSettings

pytestmark = pytest.mark.django_db


def test_public_language_settings_are_available_without_authentication():
    response = APIClient().get("/api/public/language-settings/")
    assert response.status_code == 200
    assert response.json()["available_languages"] == ["en", "bn"]
    assert response.json()["visitors_can_switch"] is True


def test_admin_language_defaults_are_validated_and_audited():
    user = get_user_model().objects.create_superuser("language-admin@example.com", "StrongPass!12345")
    client = APIClient()
    client.force_authenticate(user)
    body = {
        "default_language": "bn",
        "new_account_language": "en",
        "visitors_can_switch": False,
        "available_languages": ["en", "bn"],
    }
    assert client.put("/api/admin/language-settings/", body, format="json").status_code == 200
    settings = PlatformSettings.load()
    assert settings.default_language == "bn"
    assert settings.new_account_language == "en"
    assert settings.visitors_can_switch_language is False
    body["available_languages"] = ["bn"]
    assert client.put("/api/admin/language-settings/", body, format="json").status_code == 400


def test_authenticated_language_preference_persists_and_is_returned_by_me():
    user = get_user_model().objects.create_user("language-user@example.com", "StrongPass!12345")
    client = APIClient()
    client.force_authenticate(user)
    response = client.patch("/api/auth/language/", {"language": "bn"}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.preferred_language == "bn"
    assert client.get("/api/auth/me/").json()["user"]["preferred_language"] == "bn"
    assert client.patch("/api/auth/language/", {"language": "fr"}, format="json").status_code == 400


def test_new_accounts_inherit_configured_language_without_overriding_explicit_choice():
    PlatformSettings.objects.update_or_create(pk=1, defaults={"new_account_language": "bn"})
    User = get_user_model()
    inherited = User.objects.create_user("new-language@example.com", "StrongPass!12345")
    explicit = User.objects.create_user(
        "explicit-language@example.com", "StrongPass!12345", preferred_language="en"
    )
    assert inherited.preferred_language == "bn"
    assert explicit.preferred_language == "en"
