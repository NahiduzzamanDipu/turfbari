"""Turf profile picture and public-page photo gallery."""

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.turfs.models import TenantMembership, TurfPhoto

from .test_core import PASSWORD, client_for, make_turf

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def picture(name="pic.jpg", size=(1200, 800), fmt="JPEG", color=(30, 140, 60), exif_gps=False):
    buf = BytesIO()
    image = Image.new("RGB", size, color)
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        exif[0x8825] = {2: (23.0, 48.0, 0.0)}  # GPSInfo
        kwargs["exif"] = exif
    image.save(buf, fmt, **kwargs)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


def stored(media_root, url):
    """Load fully and close the file (Windows keeps open files locked)."""
    with Image.open(media_root / url.removeprefix("/media/")) as img:
        img.load()
        img.info["exif_present"] = bool(img.getexif())
        return img


def test_profile_picture_upload_replace_remove(media_root):
    turf, owner = make_turf()
    client = client_for(owner)
    first = client.post("/api/workspace/profile-picture/", {"image": picture()}, format="multipart")
    assert first.status_code == 200, first.json()
    url = first.json()["profile_image_url"]
    assert url.startswith(f"/media/turfs/{turf.id}/") and url.endswith(".webp")
    img = stored(media_root, url)
    assert img.format == "WEBP" and img.size == (512, 512)  # square crop

    second = client.post(
        "/api/workspace/profile-picture/", {"image": picture("b.png", fmt="PNG")}, format="multipart"
    )
    assert second.status_code == 200
    assert not (media_root / url.removeprefix("/media/")).exists()  # old file cleaned up

    assert (
        client.get("/api/workspace/settings/").json()["profile_image_url"]
        == second.json()["profile_image_url"]
    )
    assert client.delete("/api/workspace/profile-picture/").status_code == 204
    assert client.get("/api/workspace/settings/").json()["profile_image_url"] is None


def test_gallery_upload_resizes_strips_metadata_and_goes_public(media_root):
    turf, owner = make_turf()
    client = client_for(owner)
    response = client.post(
        "/api/workspace/photos/",
        {
            "image": [picture("a.jpg", size=(4000, 3000), exif_gps=True), picture("b.jpg")],
            "caption": "Night game",
        },
        format="multipart",
    )
    assert response.status_code == 201, response.json()
    photos = response.json()
    assert len(photos) == 2 and photos[0]["caption"] == "Night game"
    big = stored(media_root, photos[0]["url"])
    assert (
        big.format == "WEBP"
        and max(big.size) == 1920
        and (photos[0]["width"], photos[0]["height"]) == (1920, 1440)
    )
    assert big.info["exif_present"] is False  # location/camera data removed
    assert max(stored(media_root, photos[0]["thumbnail_url"]).size) == 640

    detail = APIClient().get(f"/api/public/turfs/{turf.slug}/").json()
    assert [p["url"] for p in detail["photos"]] == [p["url"] for p in photos]
    card = APIClient().get("/api/public/turfs/").json()["results"][0]
    assert card["cover_url"] == photos[0]["thumbnail_url"]


def test_gallery_rejects_non_images_and_respects_limit(media_root):
    turf, owner = make_turf()
    client = client_for(owner)
    fake = SimpleUploadedFile("evil.jpg", b"<?php echo 'hi'; ?>", content_type="image/jpeg")
    assert client.post("/api/workspace/photos/", {"image": fake}, format="multipart").status_code == 400
    gif = picture("anim.gif", fmt="GIF")
    assert client.post("/api/workspace/photos/", {"image": gif}, format="multipart").status_code == 400
    assert client.post("/api/workspace/photos/", {}, format="multipart").status_code == 400

    for i in range(TurfPhoto.MAX_PER_TURF):
        TurfPhoto.objects.create(turf=turf, image=f"x{i}.webp", thumbnail=f"x{i}t.webp", sort_order=i)
    full = client.post("/api/workspace/photos/", {"image": picture()}, format="multipart")
    assert full.status_code == 400 and "up to 12" in str(full.json())


def test_reorder_caption_delete(media_root):
    turf, owner = make_turf()
    client = client_for(owner)
    ids = [
        p["id"]
        for p in client.post(
            "/api/workspace/photos/", {"image": [picture(), picture(), picture()]}, format="multipart"
        ).json()
    ]
    reordered = client.post("/api/workspace/photos/reorder/", {"ids": ids[::-1]}, format="json")
    assert [p["id"] for p in reordered.json()] == ids[::-1]
    assert client.post("/api/workspace/photos/reorder/", {"ids": ids[:2]}, format="json").status_code == 400

    patched = client.patch(f"/api/workspace/photos/{ids[0]}/", {"caption": "Main pitch"}, format="json")
    assert patched.status_code == 200 and patched.json()["caption"] == "Main pitch"

    victim = TurfPhoto.objects.get(pk=ids[1])
    path = media_root / victim.image.name
    assert path.exists()
    assert client.delete(f"/api/workspace/photos/{ids[1]}/").status_code == 204
    assert not path.exists()
    assert list(TurfPhoto.objects.filter(turf=turf).values_list("sort_order", flat=True)) == [0, 1]


def test_pictures_are_owner_only_and_tenant_scoped(media_root):
    turf, _ = make_turf()
    _, other_owner = make_turf("Other", "other@example.com")
    manager = get_user_model().objects.create_user("mgr@example.com", PASSWORD)
    TenantMembership.objects.create(user=manager, turf=turf, role=TenantMembership.Role.MANAGER)
    mgr = client_for(manager)
    assert mgr.get("/api/workspace/photos/").status_code == 200
    assert mgr.post("/api/workspace/photos/", {"image": picture()}, format="multipart").status_code == 403
    assert (
        mgr.post("/api/workspace/profile-picture/", {"image": picture()}, format="multipart").status_code
        == 403
    )

    photo = TurfPhoto.objects.create(turf=turf, image="a.webp", thumbnail="b.webp")
    assert client_for(other_owner).delete(f"/api/workspace/photos/{photo.id}/").status_code == 404


def test_public_page_theme_preset_and_custom_colour():
    turf, owner = make_turf()
    client = client_for(owner)
    assert APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["theme"] == {
        "preset": "turfbari",
        "color": None,
    }

    ok = client.patch(
        "/api/workspace/settings/", {"theme_preset": "ocean", "theme_color": "#1D4ED8"}, format="json"
    )
    assert ok.status_code == 200 and ok.json()["theme_color"] == "#1d4ed8"
    assert APIClient().get(f"/api/public/turfs/{turf.slug}/").json()["theme"] == {
        "preset": "ocean",
        "color": "#1d4ed8",
    }

    for bad in ("blue", "#12345", "#ggggggg", "url(x)"):
        assert (
            client.patch("/api/workspace/settings/", {"theme_color": bad}, format="json").status_code == 400
        )
    too_light = client.patch("/api/workspace/settings/", {"theme_color": "#f5f5a0"}, format="json")
    assert too_light.status_code == 400 and "too light" in str(too_light.json())
    assert (
        client.patch("/api/workspace/settings/", {"theme_preset": "rainbow"}, format="json").status_code
        == 400
    )
    assert (
        client.patch("/api/workspace/settings/", {"theme_color": ""}, format="json").json()["theme_color"]
        == ""
    )
