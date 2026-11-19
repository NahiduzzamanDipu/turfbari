import pytest
from django.core.management import call_command


@pytest.mark.django_db(transaction=True)
def test_startup_runs_all_setup_steps(capsys):
    call_command("startup")
    out = capsys.readouterr().out
    assert "Startup tasks finished" in out
    assert "Created Super Admin" in out or "already exists" in out
