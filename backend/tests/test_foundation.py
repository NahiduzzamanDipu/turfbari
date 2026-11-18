"""Phase 2 foundation checks: MySQL configuration, health, CSRF, user model, auth backend."""

from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, connection
from rest_framework.test import APIClient

from apps.common.money import to_money

pytestmark = pytest.mark.django_db


def test_database_is_mysql8_innodb_utf8mb4_strict():
    assert connection.vendor == "mysql"
    assert not connection.mysql_is_mariadb
    assert connection.mysql_version >= (8, 0, 0)
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@default_storage_engine, @@character_set_database, @@SESSION.sql_mode")
        engine, charset, sql_mode = cursor.fetchone()
    assert engine == "InnoDB"  # row locks + transactions for booking safety
    assert charset == "utf8mb4"
    assert "STRICT_TRANS_TABLES" in sql_mode


def test_bangla_text_round_trips():
    user = get_user_model().objects.create_user("bn@example.com", "a-strong-pass-123", full_name="রহিম উদ্দিন")
    user.refresh_from_db()
    assert user.full_name == "রহিম উদ্দিন"


def test_timezone_is_dhaka():
    assert settings.TIME_ZONE == "Asia/Dhaka"
    assert settings.USE_TZ is True


def test_health_endpoint_reports_up():
    response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "up", "cache": "up"}}


def test_csrf_endpoint_sets_cookie():
    response = APIClient().get("/api/auth/csrf/")
    assert response.status_code == 200
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_unknown_api_route_is_404():
    assert APIClient().get("/api/does-not-exist/").status_code == 404


def test_api_docs_open_in_debug_only(settings):
    # Test settings run with DEBUG=False -> schema requires platform admin.
    response = APIClient().get("/api/schema/")
    assert response.status_code in (401, 403)


class TestUserModel:
    def test_email_is_normalised_and_case_insensitive_unique(self):
        User = get_user_model()
        user = User.objects.create_user("Owner@Example.COM", "a-strong-pass-123")
        assert user.email == "owner@example.com"
        with pytest.raises(IntegrityError):
            User.objects.create_user("OWNER@example.com", "another-pass-456")

    def test_superuser_is_platform_admin(self):
        admin = get_user_model().objects.create_superuser("admin@example.com", "a-strong-pass-123")
        assert admin.is_platform_admin and admin.is_superuser and admin.is_staff

    def test_regular_user_is_not_platform_admin(self):
        user = get_user_model().objects.create_user("u@example.com", "a-strong-pass-123")
        assert not user.is_platform_admin

    def test_primary_key_is_uuid(self):
        user = get_user_model().objects.create_user("u@example.com", "a-strong-pass-123")
        assert len(str(user.pk)) == 36


class TestEmailOrUsernameBackend:
    @pytest.fixture
    def user(self):
        return get_user_model().objects.create_user(
            "manager@example.com", "a-strong-pass-123", username="Gulshan_Mgr"
        )

    def test_login_with_email_any_case(self, user):
        assert authenticate(username="MANAGER@example.com", password="a-strong-pass-123") == user

    def test_login_with_username_any_case(self, user):
        assert authenticate(username="gulshan_mgr", password="a-strong-pass-123") == user

    def test_wrong_password_rejected(self, user):
        assert authenticate(username="manager@example.com", password="wrong") is None

    def test_inactive_user_rejected(self, user):
        user.is_active = False
        user.save()
        assert authenticate(username="manager@example.com", password="a-strong-pass-123") is None

    def test_unknown_user_rejected(self):
        assert authenticate(username="nobody@example.com", password="x") is None


def test_money_rejects_float_and_rounds_half_up():
    assert to_money("10.005") == Decimal("10.01")
    with pytest.raises(TypeError):
        to_money(10.5)
