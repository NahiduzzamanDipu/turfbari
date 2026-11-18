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

    call_command("ensure_admin", email="")
    assert "already exists" in capsys.readouterr().out
    assert get_user_model().objects.filter(is_platform_admin=True).count() == 1


@pytest.mark.django_db
def test_ensure_admin_moves_the_only_admin_to_the_configured_email(capsys):
    call_command("ensure_admin", email="boss@example.com")
    capsys.readouterr()
    call_command("ensure_admin", email="New.Boss@Example.com")
    assert "changed from boss@example.com to new.boss@example.com" in capsys.readouterr().out
    admin = get_user_model().objects.get(is_platform_admin=True)
    assert admin.email == "new.boss@example.com"
    call_command("ensure_admin", email="new.boss@example.com")
    assert "nothing to do" in capsys.readouterr().out
