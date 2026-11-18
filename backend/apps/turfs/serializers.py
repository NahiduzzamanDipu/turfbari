"""Turf serializers. PUBLIC serializers use explicit field whitelists — never `__all__`."""

from rest_framework import serializers

from apps.locations.models import Area, District

from .models import Amenity, OperatingHours, PricingRule, Turf, TurfField


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

    class Meta:
        model = Turf
        fields = [
            "name",
            "slug",
            "short_description",
            "district",
            "area",
            "address",
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
        ]

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
        ]
        read_only_fields = ["slug", "status"]

    def validate(self, attrs):
        district = attrs.get("district", getattr(self.instance, "district", None))
        area = attrs.get("area", getattr(self.instance, "area", None))
        if area and district and area.district_id != district.id:
            raise serializers.ValidationError({"area": ["This area is not in the selected district."]})
        return attrs

    def validate_weekend_days(self, value):
        if not isinstance(value, list) or any(not isinstance(d, int) or d < 0 or d > 6 for d in value):
            raise serializers.ValidationError("Weekend days must be numbers 0 (Mon) – 6 (Sun).")
        return sorted(set(value))
