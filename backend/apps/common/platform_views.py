"""Platform-wide settings owned by the Super Admin.

- Admin -> API: the global "how to book" YouTube video (same on every turf page) and BulkSMSBD
  credentials (key stored encrypted; responses only ever show a masked key).
- Admin -> Terms: Terms & Conditions + Booking Rules, versioned. Publishing freezes a revision;
  bookings keep a reference to the exact revision the customer agreed to.
- Public: the published terms, and the global video id.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, record

from .crypto import decrypt, encrypt, mask
from .models import PlatformSettings
from .permissions import IsPlatformAdmin


def youtube_payload(s: PlatformSettings) -> dict:
    return {"video_id": s.youtube_video_id or None, "url": s.youtube_url or None}


def bulksmsbd_payload(*, with_balance: bool = False) -> dict:
    from django.conf import settings

    from apps.notifications.models import SmsConfig
    from apps.notifications.providers import api_key, get_provider
    from apps.notifications.services import sender_id

    config = SmsConfig.load()
    key, source = api_key()
    provider = get_provider()
    stored_unreadable = bool(config.api_key_encrypted) and decrypt(config.api_key_encrypted) is None
    data = {
        "api_key_masked": mask(key),
        "api_key_source": source,  # admin | environment | none
        "stored_key_unreadable": stored_unreadable,
        "sender_id": sender_id(),
        "sender_id_source": "admin"
        if config.sender_id
        else ("environment" if settings.BULKSMSBD_SENDER_ID else "none"),
        "provider": provider.name,
        "enabled": config.enabled,
        "connected": provider.name not in ("disabled",),
        "panel_url": "https://bulksmsbd.net/",
        "iframe_supported": False,  # BulkSMSBD documents no embeddable dashboard; we use its API instead
    }
    if with_balance and provider.name in ("bulksmsbd", "memory"):
        value = provider.balance()
        data["balance"] = str(value) if value is not None else None
        data["balance_checked"] = True
    return data


class AdminApiConfigView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        s = PlatformSettings.load()
        return Response(
            {
                "youtube": youtube_payload(s),
                "bulksmsbd": bulksmsbd_payload(),
                "booking": {"max_slots_per_customer": s.max_slots_per_customer},
            }
        )


class YoutubeSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=300, allow_blank=True)


class AdminYoutubeView(APIView):
    """PUT {url}: set the global video (validated, ID extracted). Empty url removes it everywhere."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=YoutubeSerializer)
    def put(self, request):
        from apps.turfs.design_views import youtube_id

        data = YoutubeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        url = data.validated_data["url"].strip()
        s = PlatformSettings.objects.get_or_create(pk=1)[0]
        if url:
            video = youtube_id(url)
            if video is None:
                raise serializers.ValidationError(
                    {"url": ["Paste a YouTube video link (youtube.com/watch?v=…, youtu.be/…, /shorts/…)."]}
                )
            s.youtube_video_id, s.youtube_url = video, url[:300]
            summary = f"Set the booking-guide video (YouTube {video}) for every turf page"
        else:
            s.youtube_video_id, s.youtube_url = "", ""
            summary = "Removed the booking-guide video from every turf page"
        s.save()
        record("platform.youtube", summary, category=Category.PLATFORM, request=request)
        return Response(youtube_payload(s))


class BulkSmsSerializer(serializers.Serializer):
    api_key = serializers.CharField(max_length=200, required=False, allow_blank=True, trim_whitespace=True)
    sender_id = serializers.RegexField(r"^[A-Za-z0-9 ._-]{0,20}$", required=False, allow_blank=True)
    clear_api_key = serializers.BooleanField(required=False, default=False)


class AdminBulkSmsView(APIView):
    """PUT: save BulkSMSBD key/sender (key encrypted, never echoed). POST: test the connection."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=BulkSmsSerializer)
    def put(self, request):
        from apps.notifications.models import SmsConfig

        data = BulkSmsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        config = SmsConfig.load()
        changed = []
        if v.get("clear_api_key"):
            config.api_key_encrypted = ""
            changed.append("API key removed (environment key used if set)")
        elif v.get("api_key"):
            config.api_key_encrypted = encrypt(v["api_key"])
            changed.append("API key")
        if "sender_id" in v:
            config.sender_id = v["sender_id"].strip()
            changed.append("sender ID")
        config.save()
        if changed:
            record(
                "platform.bulksmsbd",
                "Updated BulkSMSBD settings: " + ", ".join(changed),
                category=Category.PLATFORM,
                request=request,
            )
        return Response(bulksmsbd_payload())

    @extend_schema(tags=["admin"], request=None)
    def post(self, request):
        """Connection test: asks BulkSMSBD for the balance (sends no SMS)."""
        payload = bulksmsbd_payload(with_balance=True)
        ok = payload["connected"] and payload.get("balance") is not None
        payload["test"] = {
            "ok": ok,
            "message": (
                "Connected — BulkSMSBD answered with your balance."
                if ok
                else "No balance returned. Check the API key, IP whitelist and SMS_BACKEND=bulksmsbd."
                if payload["connected"]
                else "Not connected: no API key."
            ),
        }
        record(
            "platform.bulksmsbd_test",
            f"Tested the BulkSMSBD connection: {'OK' if ok else 'failed'}",
            category=Category.PLATFORM,
            request=request,
        )
        return Response(payload)


class BookingPolicySerializer(serializers.Serializer):
    max_slots_per_customer = serializers.IntegerField(min_value=1, max_value=20)


class AdminBookingPolicyView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=BookingPolicySerializer)
    def put(self, request):
        data = BookingPolicySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        s = PlatformSettings.objects.get_or_create(pk=1)[0]
        s.max_slots_per_customer = data.validated_data["max_slots_per_customer"]
        s.save()
        record(
            "platform.booking_limit",
            f"Customers can hold at most {s.max_slots_per_customer} upcoming slots",
            category=Category.PLATFORM,
            request=request,
        )
        return Response({"max_slots_per_customer": s.max_slots_per_customer})
