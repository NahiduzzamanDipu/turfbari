from django.core.management import call_command


def test_check_media_storage_reports_ok(capsys, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("check_media_storage")
    assert "Media storage OK: FileSystemStorage" in capsys.readouterr().out
    assert not any(tmp_path.rglob("*.txt"))
