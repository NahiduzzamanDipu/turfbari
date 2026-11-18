from django.utils import timezone
from rest_framework import serializers

from .models import Invoice, PaymentTransaction, Plan, Subscription
from .services import standing


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "period", "name", "months", "price", "description", "is_active"]
        read_only_fields = ["id", "period", "months"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be more than zero.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "tran_id",
            "method",
            "method_label",
            "channel",
            "amount",
            "status",
            "status_label",
            "reference",
            "sender_number",
            "note",
            "created_at",
            "reviewed_at",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ["id", "plan", "status", "state", "starts_on", "ends_on", "price", "note", "created_at"]

    def get_state(self, obj):
        """pending_payment | cancelled | scheduled | current | ended"""
        if obj.status != Subscription.Status.ACTIVE:
            return obj.status
        today = timezone.localdate()
        if obj.starts_on > today:
            return "scheduled"
        return "current" if obj.ends_on >= today else "ended"


class InvoiceSerializer(serializers.ModelSerializer):
    subscription = SubscriptionSerializer(read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "amount",
            "status",
            "status_label",
            "paid_at",
            "created_at",
            "subscription",
            "transactions",
        ]


def standing_payload(turf) -> dict:
    s = standing(turf)
    return {
        "state": s.state,
        "can_operate": s.can_operate,
        "plan": PlanSerializer(s.current.plan).data if s.current else None,
        "current": SubscriptionSerializer(s.current).data if s.current else None,
        "paid_until": s.paid_until,
        "days_left": s.days_left,
        "grace_until": s.grace_until,
        "auto_renew": False,
    }


class AdminPaymentSerializer(TransactionSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    turf_name = serializers.CharField(source="invoice.turf.name", read_only=True)
    plan_name = serializers.CharField(source="invoice.subscription.plan.name", read_only=True)
    submitted_by_email = serializers.CharField(source="submitted_by.email", read_only=True, default=None)

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + [
            "invoice_number",
            "turf_name",
            "plan_name",
            "submitted_by_email",
        ]
