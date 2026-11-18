"""The single-host deploy serves the React build from Django (config/spa.py)."""

import pytest
from django.test import override_settings
from django.urls import clear_url_caches


@pytest.fixture
def dist(tmp_path, settings):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    import importlib

    import config.urls

    with override_settings(FRONTEND_DIST=str(tmp_path)):
        importlib.reload(config.urls)
        clear_url_caches()
        yield tmp_path
    importlib.reload(config.urls)
    clear_url_caches()


def test_spa_routes_get_index(client, dist):
    response = client.get("/owner/slots")
    assert response.status_code == 200
    assert b"root" in response.content
    assert "Content-Security-Policy" not in response


def test_spa_serves_real_files(client, dist):
    assert client.get("/favicon.svg").status_code == 200
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "immutable" in asset["Cache-Control"]
    assert client.get("/assets/missing.js").status_code == 404


@pytest.mark.django_db
def test_spa_blocks_path_escape_and_leaves_api_alone(client, dist):
    assert b"root" in client.get("/../../etc/passwd").content
    assert client.get("/api/health/")["Content-Type"].startswith("application/json")


def test_serve_media_only_serves_images(client, settings, tmp_path):
    import importlib

    import config.urls

    (tmp_path / "a.webp").write_bytes(b"RIFF")
    (tmp_path / "evil.html").write_text("<script>", encoding="utf-8")
    with override_settings(SERVE_MEDIA=True, MEDIA_ROOT=tmp_path):
        importlib.reload(config.urls)
        clear_url_caches()
        assert client.get("/media/a.webp").status_code == 200
        assert client.get("/media/evil.html").status_code == 404
    importlib.reload(config.urls)
    clear_url_caches()
