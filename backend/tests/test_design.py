"""Booking page design: theme draft/preview/publish with readability rules, YouTube video popup."""

import pytest
from rest_framework.test import APIClient

from apps.turfs.design_views import youtube_id

from .test_core import client_for, make_turf

pytestmark = pytest.mark.django_db

THEME = {
    "preset": "ocean",
    "color": "#0f4c81",
    "secondary": "#fde047",
    "surface": "tinted",
    "buttons": "pill",
    "font": "serif",
}


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
        ("youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://evil.example.com/watch?v=dQw4w9WgXcQ", None),
        ("https://www.youtube.com/watch?v=short", None),
        ("javascript:alert(1)", None),
        ("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ", None),
    ],
)
def test_only_real_youtube_video_ids_are_accepted(url, expected):
    assert youtube_id(url) == expected


def test_draft_is_private_until_published():
    turf, owner = make_turf()
    client = client_for(owner)
    saved = client.put("/api/workspace/design/", THEME, format="json")
    assert saved.status_code == 200 and saved.json()["draft"]["buttons"] == "pill"
    public = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["theme"]
    assert public["preset"] == "turfbari" and public["buttons"] == "rounded"  # not live yet

    published = client.post("/api/workspace/design/publish/")
    assert published.status_code == 200 and published.json()["draft"] is None
    live = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["theme"]
    assert live == {
        "preset": "ocean",
        "color": "#0f4c81",
        "secondary": "#fde047",
        "surface": "tinted",
        "buttons": "pill",
        "font": "serif",
    }
    assert client.post("/api/workspace/design/publish/").status_code == 400  # nothing left to publish


def test_unreadable_or_unknown_choices_are_refused():
    _, owner = make_turf()
    client = client_for(owner)
    for bad in (
        {"color": "#f5f5f5"},
        {"font": "Comic Sans"},
        {"buttons": "blob"},
        {"secondary": "yellow"},
        {"surface": "dark"},
    ):
        assert client.put("/api/workspace/design/", {**THEME, **bad}, format="json").status_code == 400, bad


def test_video_is_validated_shown_publicly_and_removable_by_the_owner_only():
    turf, owner = make_turf()
    client = client_for(owner)
    bad = client.put("/api/workspace/design/video/", {"url": "https://vimeo.com/123"}, format="json")
    assert bad.status_code == 400
    ok = client.put("/api/workspace/design/video/", {"url": "https://youtu.be/dQw4w9WgXcQ"}, format="json")
    assert ok.json()["youtube_video_id"] == "dQw4w9WgXcQ"
    assert APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["youtube_video_id"] == "dQw4w9WgXcQ"
    client.put("/api/workspace/design/video/", {"url": ""}, format="json")
    assert APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["youtube_video_id"] == ""


def test_themes_stay_inside_their_own_turf():
    turf_a, owner_a = make_turf()
    turf_b, _ = make_turf("Beta Turf", "beta@example.com")
    client_for(owner_a).put("/api/workspace/design/", THEME, format="json")
    client_for(owner_a).post("/api/workspace/design/publish/")
    assert APIClient().get(f"/api/public/turfs/{turf_b.slug}/").json()["theme"]["preset"] == "turfbari"
