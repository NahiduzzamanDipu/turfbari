from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "actor_label",
            "category",
            "category_label",
            "action",
            "summary",
            "target_type",
            "target_id",
        ]


class AdminAuditEventSerializer(AuditEventSerializer):
    class Meta(AuditEventSerializer.Meta):
        fields = AuditEventSerializer.Meta.fields + ["turf_name", "ip"]
