"""Turf serializers. PUBLIC serializers use explicit field whitelists — never `__all__`."""

import re

from rest_framework import serializers

from apps.locations.models import Area, District

from .geo import coords_from_maps_url, google_maps_link, is_google_maps_url
from .models import Amenity, OperatingHours, PricingRule, Turf, TurfField

HEX_COLOR = re.compile(r"#[0-9a-f]{6}")


def contrast_with_white(hex_color: str) -> float:
    """WCAG contrast ratio of white text on this colour."""

    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return 1.05 / (lum + 0.05)


class MediaURLField(serializers.Field):
    """Site-relative URL of a stored file ("/media/..."), or None. Works behind any proxy/host."""

    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return value.url if value else None


def photo_payload(photo) -> dict:
    return {
        "url": photo.image.url,
        "thumbnail_url": photo.thumbnail.url,
        "width": photo.width,
        "height": photo.height,
        "caption": photo.caption,
    }


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["name", "slug"]


class PlaceSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()


# ------------------------------------------------------------------- public
class PublicTurfCardSerializer(serializers.ModelSerializer):
    district = PlaceSerializer()
    area = PlaceSerializer(allow_null=True)
    amenities = serializers.SerializerMethodField()
    min_price = serializers.SerializerMethodField()
    fields_count = serializers.IntegerField(read_only=True)
    map_link = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    profile_image_url = MediaURLField(source="profile_image")
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = Turf
        fields = [
            "name",
            "slug",
            "short_description",
            "district",
            "area",
            "address",
            "latitude",
            "longitude",
            "map_link",
            "distance_km",
            "profile_image_url",
            "cover_url",
            "turf_type",
            "surface",
            "amenities",
            "min_price",
            "fields_count",
            "is_featured",
            "public_booking_enabled",
        ]

    def get_amenities(self, obj):
        return [a.name for a in obj.amenities.all()]

    def get_min_price(self, obj):
        return str(obj.min_public_price) if obj.show_pricing and obj.min_public_price is not None else None

    def get_cover_url(self, obj):
        photos = list(obj.photos.all())  # prefetched by the views
        return photos[0].thumbnail.url if photos else None

    def get_map_link(self, obj):
        if obj.maps_url:
            return obj.maps_url
        if obj.latitude is not None and obj.longitude is not None:
            return google_maps_link(obj.latitude, obj.longitude)
        return None

    def get_distance_km(self, obj):
        distance = getattr(obj, "distance_km", None)
        return round(distance, 1) if distance is not None else None


class PublicFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurfField
        fields = ["id", "name", "size", "surface", "is_indoor", "has_lighting", "slot_minutes"]


class HoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperatingHours
        fields = ["weekday", "opens_at", "closes_at", "is_closed"]


class PublicPriceSerializer(serializers.ModelSerializer):
    field_name = serializers.CharField(source="field.name", default=None)

    class Meta:
        model = PricingRule
        fields = ["label", "weekdays", "date", "start_time", "end_time", "hourly_rate", "field_name"]


class PublicTurfDetailSerializer(PublicTurfCardSerializer):
    fields_list = serializers.SerializerMethodField()
    hours = HoursSerializer(many=True)
    pricing = serializers.SerializerMethodField()
    base_rates = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    theme = serializers.SerializerMethodField()

    class Meta(PublicTurfCardSerializer.Meta):
        fields = PublicTurfCardSerializer.Meta.fields + [
            "description",
            "maps_url",
            "public_phone",
            "public_email",
            "booking_instructions",
            "cancellation_policy",
            "payment_methods_text",
            "fields_list",
            "hours",
            "pricing",
            "base_rates",
            "photos",
            "theme",
            "payment",
        ]

    payment = serializers.SerializerMethodField()

    def get_payment(self, obj):
        """bKash details for the booking form. Online booking needs a bKash number to pay to."""
        from apps.bookings.payments import MIN_ADVANCE

        return {
            "accepts_online": bool(obj.public_booking_enabled and obj.bkash_number),
            "bkash_number": obj.bkash_number or None,
            "advance_amount": str(max(obj.advance_amount or MIN_ADVANCE, MIN_ADVANCE)),
            "min_advance": str(MIN_ADVANCE),
            "hold_minutes": obj.payment_hold_minutes,
        }

    def get_theme(self, obj):
        return {"preset": obj.theme_preset, "color": obj.theme_color or None}

    def get_photos(self, obj):
        return [photo_payload(p) for p in obj.photos.all()]

    def get_fields_list(self, obj):
        return PublicFieldSerializer([f for f in obj.fields.all() if f.is_active], many=True).data

    def get_pricing(self, obj):
        if not obj.show_pricing:
            return []
        rules = [r for r in obj.pricing_rules.all() if r.is_active and (r.field is None or r.field.is_active)]
        return PublicPriceSerializer(rules, many=True).data

    def get_base_rates(self, obj):
        if not obj.show_pricing:
            return []
        return [
            {"field": f.name, "hourly_rate": str(f.default_hourly_rate)}
            for f in obj.fields.all()
            if f.is_active
        ]


# ---------------------------------------------------------------- workspace
class TenantScopedPK(serializers.PrimaryKeyRelatedField):
    """FK input restricted to the current tenant's rows (other tenants' IDs -> 'does not exist')."""

    def get_queryset(self):
        request = self.context["request"]
        return super().get_queryset().filter(turf=request.tenant)


class FieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurfField
        fields = [
            "id",
            "name",
            "size",
            "surface",
            "is_indoor",
            "has_lighting",
            "is_active",
            "sort_order",
            "slot_minutes",
            "default_hourly_rate",
        ]

    def validate_slot_minutes(self, value):
        if value not in (30, 45, 60, 90, 120):
            raise serializers.ValidationError("Choose 30, 45, 60, 90 or 120 minutes.")
        return value

    def validate_default_hourly_rate(self, value):
        if value < 0:
            raise serializers.ValidationError("Rate cannot be negative.")
        return value

    def validate_name(self, value):
        request = self.context["request"]
        qs = TurfField.objects.filter(turf=request.tenant, name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A field with this name already exists.")
        return value.strip()


class PricingRuleSerializer(serializers.ModelSerializer):
    field = TenantScopedPK(queryset=TurfField.objects.all(), allow_null=True, required=False)
    field_name = serializers.CharField(source="field.name", read_only=True, default=None)

    class Meta:
        model = PricingRule
        fields = [
            "id",
            "field",
            "field_name",
            "label",
            "weekdays",
            "date",
            "start_time",
            "end_time",
            "hourly_rate",
            "priority",
            "is_active",
        ]

    def validate_weekdays(self, value):
        if not isinstance(value, list) or any(not isinstance(d, int) or d < 0 or d > 6 for d in value):
            raise serializers.ValidationError("Weekdays must be a list of numbers 0 (Mon) – 6 (Sun).")
        return sorted(set(value))

    def validate_hourly_rate(self, value):
        if value < 0:
            raise serializers.ValidationError("Rate cannot be negative.")
        return value


class TurfSettingsSerializer(serializers.ModelSerializer):
    """What an owner can edit about their own turf. Status/slug/featured stay with the Super Admin."""

    amenities = serializers.SlugRelatedField(slug_field="slug", many=True, queryset=Amenity.objects.all())
    district = serializers.SlugRelatedField(slug_field="slug", queryset=District.objects.all())
    area = serializers.SlugRelatedField(slug_field="slug", queryset=Area.objects.all(), allow_null=True)
    profile_image_url = MediaURLField(source="profile_image")

    class Meta:
        model = Turf
        fields = [
            "name",
            "slug",
            "status",
            "district",
            "area",
            "address",
            "maps_url",
            "latitude",
            "longitude",
            "turf_type",
            "surface",
            "amenities",
            "short_description",
            "description",
            "public_phone",
            "public_email",
            "booking_instructions",
            "cancellation_policy",
            "payment_methods_text",
            "is_listed",
            "public_booking_enabled",
            "show_pricing",
            "weekend_days",
            "profile_image_url",
            "theme_preset",
            "theme_color",
            "bkash_number",
            "advance_amount",
            "payment_hold_minutes",
        ]
        read_only_fields = ["slug", "status"]

    def validate_bkash_number(self, value):
        from apps.bookings.phone import normalize_bd_phone

        value = (value or "").strip()
        if not value:
            return ""
        try:
            return "0" + normalize_bd_phone(value)[4:]  # stored the way customers type it: 01XXXXXXXXX
        except serializers.ValidationError:
            raise serializers.ValidationError("Enter your bKash number, e.g. 01712345678.") from None

    def validate_advance_amount(self, value):
        from apps.bookings.payments import MIN_ADVANCE

        if value < MIN_ADVANCE:
            raise serializers.ValidationError(f"The advance must be at least ৳{MIN_ADVANCE:,.0f}.")
        return value

    def validate_payment_hold_minutes(self, value):
        if not 15 <= value <= 24 * 60:
            raise serializers.ValidationError("Hold a request between 15 minutes and 24 hours.")
        return value

    def validate_theme_color(self, value):
        value = (value or "").strip().lower()
        if value and not HEX_COLOR.fullmatch(value):
            raise serializers.ValidationError("Use a colour like #1f7a4d.")
        if value and contrast_with_white(value) < 3:
            raise serializers.ValidationError(
                "This colour is too light — white text on buttons would be hard to read. Pick a darker shade."
            )
        return value

    def validate_maps_url(self, value):
        value = (value or "").strip()
        if value and not is_google_maps_url(value):
            raise serializers.ValidationError(
                "Paste a Google Maps link (google.com/maps or maps.app.goo.gl)."
            )
        return value

    def validate(self, attrs):
        district = attrs.get("district", getattr(self.instance, "district", None))
        area = attrs.get("area", getattr(self.instance, "area", None))
        if area and district and area.district_id != district.id:
            raise serializers.ValidationError({"area": ["This area is not in the selected district."]})

        old_lat = getattr(self.instance, "latitude", None)
        old_lng = getattr(self.instance, "longitude", None)
        lat = attrs.get("latitude", old_lat)
        lng = attrs.get("longitude", old_lng)
        # A changed map link that carries coordinates moves the pin, unless the owner moved it too.
        maps_url = attrs.get("maps_url")
        link_changed = maps_url and maps_url != getattr(self.instance, "maps_url", "")
        if link_changed and (lat, lng) == (old_lat, old_lng):
            if coords := coords_from_maps_url(maps_url):
                lat, lng = coords
                attrs["latitude"], attrs["longitude"] = coords
        if (lat is None) != (lng is None):
            raise serializers.ValidationError(
                {"latitude": ["Enter both latitude and longitude, or neither."]}
            )
        if lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise serializers.ValidationError({"latitude": ["These coordinates are not on the map."]})
        return attrs

    def validate_weekend_days(self, value):
        if not isinstance(value, list) or any(not isinstance(d, int) or d < 0 or d > 6 for d in value):
            raise serializers.ValidationError("Weekend days must be numbers 0 (Mon) – 6 (Sun).")
        return sorted(set(value))
