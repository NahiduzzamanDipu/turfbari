import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command


@pytest.mark.django_db
def test_ensure_admin_creates_once(capsys):
    call_command("ensure_admin", email="boss@example.com")
    out = capsys.readouterr().out
    user = get_user_model().objects.get(email="boss@example.com")
    assert user.is_platform_admin
    password = out.split("temporary password: ")[1].split()[0]
    assert user.check_password(password)

    call_command("ensure_admin", email="other@example.com")
    assert "already exists" in capsys.readouterr().out
    assert not get_user_model().objects.filter(email="other@example.com").exists()
