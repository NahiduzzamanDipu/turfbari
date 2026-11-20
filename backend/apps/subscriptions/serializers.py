from django.utils import timezone
from rest_framework import serializers

from .models import Invoice, PaymentTransaction, Plan, PromoCode, Subscription
from .services import normalize_code, promo_uses, standing


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
            "amount_sent",
            "fee",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "state",
            "starts_on",
            "ends_on",
            "price",
            "note",
            "created_at",
            "change_type",
        ]

    def get_state(self, obj):
        """pending_payment | cancelled | scheduled | current | ended"""
        if obj.status != Subscription.Status.ACTIVE:
            return obj.status
        today = timezone.localdate()
        if obj.starts_on > today:
            return "scheduled"
        return "current" if obj.ends_on >= today else "ended"


class PromoCodeSerializer(serializers.ModelSerializer):
    """Super Admin: create / edit promo codes."""

    code = serializers.RegexField(
        r"^\s*[A-Za-z0-9_-]{3,30}\s*$",
        error_messages={"invalid": "Use 3-30 letters, numbers, - or _ (no spaces)."},
    )
    percent_off = serializers.IntegerField(min_value=1, max_value=100)
    max_uses = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    times_used = serializers.SerializerMethodField()
    is_running = serializers.SerializerMethodField()

    class Meta:
        model = PromoCode
        fields = [
            "id",
            "code",
            "percent_off",
            "description",
            "is_active",
            "valid_from",
            "valid_until",
            "max_uses",
            "times_used",
            "is_running",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_times_used(self, obj) -> int:
        return promo_uses(obj)

    def get_is_running(self, obj) -> bool:
        today = timezone.localdate()
        return bool(
            obj.is_active
            and (obj.valid_from is None or obj.valid_from <= today)
            and (obj.valid_until is None or obj.valid_until >= today)
            and (obj.max_uses is None or promo_uses(obj) < obj.max_uses)
        )

    def validate_code(self, value):
        code = normalize_code(value)
        clash = PromoCode.objects.filter(code=code)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A promo code with this name already exists.")
        return code

    def validate(self, attrs):
        start = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        end = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if start and end and end < start:
            raise serializers.ValidationError({"valid_until": ["The end date is before the start date."]})
        return attrs


class InvoicePromoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = ["code", "percent_off"]


class InvoiceSerializer(serializers.ModelSerializer):
    subscription = SubscriptionSerializer(read_only=True)
    promo_code = InvoicePromoSerializer(read_only=True)
    list_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "amount",
            "list_amount",
            "discount",
            "promo_code",
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
    plan_months = serializers.IntegerField(source="invoice.subscription.plan.months", read_only=True)
    change_type = serializers.CharField(source="invoice.subscription.change_type", read_only=True)
    submitted_by_email = serializers.CharField(source="submitted_by.email", read_only=True, default=None)
    payable = serializers.SerializerMethodField()
    current = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + [
            "invoice_number",
            "turf_name",
            "plan_name",
            "plan_months",
            "change_type",
            "submitted_by_email",
            "payable",
            "current",
            "owner",
        ]

    def get_payable(self, obj):
        return str(obj.invoice.amount + (obj.fee or 0))

    def get_current(self, obj):
        from .services import standing

        s = standing(obj.invoice.turf)
        return {
            "plan": s.current.plan.name if s.current else None,
            "paid_until": s.paid_until,
            "state": s.state,
        }

    def get_owner(self, obj):
        m = next((m for m in obj.invoice.turf.memberships.all() if m.role == "owner" and m.is_active), None)
        return {"name": m.user.full_name, "email": m.user.email, "phone": m.user.phone} if m else None
