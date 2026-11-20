"""Public page design: theme (draft -> preview -> publish). (The booking-guide video is global: Admin -> API.)

The theme is limited to safe, readable choices: preset palettes, a main colour that keeps white button
text readable, a secondary colour (text colour picked automatically), a light background style, a
button shape and a font from a fixed list. Only the turf's own public page uses it.
"""

import re
from urllib.parse import parse_qs, urlparse

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.tenancy import IsTenantMember

from .models import ThemePreset, Turf
from .serializers import HEX_COLOR, contrast_with_white

SURFACES = ("plain", "tinted")
BUTTONS = ("rounded", "pill", "square")
FONTS = ("inter", "system", "serif", "rounded", "condensed")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
    "youtube-nocookie.com",
}


def youtube_id(url: str) -> str | None:
    """The 11-character video ID from a YouTube link (watch, youtu.be, shorts, embed, live), else None."""
    raw = (url or "").strip()
    if VIDEO_ID.match(raw):
        return raw
    if not re.match(r"^https?://", raw):
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None
    candidate = None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    else:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            candidate = parts[1]
    return candidate if candidate and VIDEO_ID.match(candidate) else None


def published_theme(turf: Turf) -> dict:
    extra = turf.theme_settings or {}
    return {
        "preset": turf.theme_preset,
        "color": turf.theme_color or None,
        "secondary": extra.get("secondary") or None,
        "surface": extra.get("surface", "plain"),
        "buttons": extra.get("buttons", "rounded"),
        "font": extra.get("font", "inter"),
    }


class ThemeSerializer(serializers.Serializer):
    preset = serializers.ChoiceField(choices=ThemePreset.choices)
    color = serializers.CharField(max_length=7, required=False, allow_blank=True, allow_null=True)
    secondary = serializers.CharField(max_length=7, required=False, allow_blank=True, allow_null=True)
    surface = serializers.ChoiceField(choices=SURFACES, default="plain")
    buttons = serializers.ChoiceField(choices=BUTTONS, default="rounded")
    font = serializers.ChoiceField(choices=FONTS, default="inter")

    def validate_color(self, value):
        value = (value or "").strip().lower()
        if value and not HEX_COLOR.fullmatch(value):
            raise serializers.ValidationError("Use a colour like #1f7a4d.")
        if value and contrast_with_white(value) < 3:
            raise serializers.ValidationError(
                "Too light — white text on buttons would be hard to read. Pick a darker shade."
            )
        return value or None

    def validate_secondary(self, value):
        value = (value or "").strip().lower()
        if value and not HEX_COLOR.fullmatch(value):
            raise serializers.ValidationError("Use a colour like #bef264.")
        return value or None


class DesignView(APIView):
    """GET the published theme, the unpublished draft and the video; PUT saves a draft."""

    permission_classes = [IsTenantMember]
    owner_only_writes = True

    @staticmethod
    def payload(turf: Turf) -> dict:
        return {
            "published": published_theme(turf),
            "draft": turf.theme_draft or None,
            "slug": turf.slug,
        }

    @extend_schema(tags=["workspace"])
    def get(self, request):
        return Response(self.payload(request.tenant))

    @extend_schema(tags=["workspace"], request=ThemeSerializer)
    def put(self, request):
        data = ThemeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        turf = request.tenant
        turf.theme_draft = data.validated_data
        turf.save(update_fields=["theme_draft", "updated_at"])
        return Response(self.payload(turf))


class DesignPublishView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], request=None)
    def post(self, request):
        turf = request.tenant
        if not turf.theme_draft:
            raise serializers.ValidationError({"draft": ["There are no unpublished changes."]})
        data = ThemeSerializer(data=turf.theme_draft)
        data.is_valid(raise_exception=True)  # re-check: rules may have tightened since it was saved
        v = data.validated_data
        turf.theme_preset, turf.theme_color = v["preset"], v.get("color") or ""
        turf.theme_settings = {k: v.get(k) for k in ("secondary", "surface", "buttons", "font")}
        turf.theme_draft = None
        turf.save(
            update_fields=["theme_preset", "theme_color", "theme_settings", "theme_draft", "updated_at"]
        )
        record(
            "settings.theme_published",
            "Published a new booking page design",
            category=Category.SETTINGS,
            request=request,
        )
        return Response(DesignView.payload(turf))

    @extend_schema(tags=["workspace"], request=None)
    def delete(self, request):
        """Throw the draft away."""
        turf = request.tenant
        turf.theme_draft = None
        turf.save(update_fields=["theme_draft", "updated_at"])
        return Response(DesignView.payload(turf))
