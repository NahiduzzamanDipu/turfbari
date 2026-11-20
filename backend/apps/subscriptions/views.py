"""Subscription API for owners (workspace), the Super Admin, and the payment gateway callbacks."""

from decimal import Decimal

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.permissions import IsPlatformAdmin
from apps.common.tenancy import IsTenantMember
from apps.turfs.models import Turf

from . import gateway
from .models import Invoice, PaymentTransaction, Plan, PromoCode
from .serializers import (
    AdminPaymentSerializer,
    InvoiceSerializer,
    PlanSerializer,
    PromoCodeSerializer,
    SubscriptionSerializer,
    TransactionSerializer,
    standing_payload,
)
from .services import (
    apply_promo,
    assign_plan,
    cancel_order,
    create_order,
    remove_promo,
    review_payment,
    submit_manual_payment,
)

MANUAL_METHODS = {
    PaymentTransaction.Method.BKASH: "bKash",
    PaymentTransaction.Method.NAGAD: "Nagad",
    PaymentTransaction.Method.ROCKET: "Rocket",
    PaymentTransaction.Method.BANK: "Bank transfer",
}


def payment_accounts() -> dict:
    from apps.common.models import PlatformSettings

    accounts = dict(settings.SUBSCRIPTION_PAYMENT_ACCOUNTS)
    if number := PlatformSettings.load().subscription_bkash_number:
        accounts["bkash"] = number  # set in Admin -> API -> Payments; wins over the environment
    return accounts


def payment_options() -> dict:
    from apps.common.models import PlatformSettings

    s = PlatformSettings.load()
    accounts = payment_accounts()
    return {
        "instructions": s.subscription_instructions,
        "fee_percent": str(s.subscription_fee_percent),
        "online": gateway.enabled(),
        "online_sandbox": gateway.enabled() and settings.SSLCOMMERZ_SANDBOX,
        "manual": [
            {"method": method, "label": label, "account": accounts.get(method, "")}
            for method, label in MANUAL_METHODS.items()
            if accounts.get(method)
        ],
    }


# ------------------------------------------------------------------ workspace
class WorkspaceSubscriptionMixin:
    permission_classes = [IsTenantMember]
    owner_only_writes = True
    allow_inactive_subscription = True  # an expired turf must still be able to renew

    def open_invoice(self, request, pk):
        return get_object_or_404(Invoice, pk=pk, turf=request.tenant)


class SubscriptionOverviewView(WorkspaceSubscriptionMixin, APIView):
    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        subs = turf.subscriptions.select_related("plan").exclude(status="cancelled")
        open_invoice = (
            Invoice.objects.filter(turf=turf, status__in=Invoice.OPEN)
            .select_related("subscription__plan")
            .prefetch_related("transactions")
            .first()
        )
        invoices = (
            Invoice.objects.filter(turf=turf)
            .select_related("subscription__plan")
            .prefetch_related("transactions")[:20]
        )
        return Response(
            {
                "standing": standing_payload(turf),
                "turf_status": turf.status,
                "periods": SubscriptionSerializer(subs.filter(status="active"), many=True).data,
                "open_invoice": InvoiceSerializer(open_invoice).data if open_invoice else None,
                "invoices": InvoiceSerializer(invoices, many=True).data,
                "plans": PlanSerializer(Plan.objects.filter(is_active=True), many=True).data,
                "payment_options": payment_options(),
            }
        )


class OrderSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(slug_field="period", queryset=Plan.objects.filter(is_active=True))


class SubscriptionOrderView(WorkspaceSubscriptionMixin, APIView):
    """Choose a plan to renew with or switch to. Creates an unpaid invoice; nothing renews by itself."""

    @extend_schema(request=OrderSerializer, tags=["workspace"])
    def post(self, request):
        data = OrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        from apps.legal.services import require_for_user

        require_for_user(request.user, "subscription", request.tenant, request)
        invoice = create_order(request.tenant, data.validated_data["plan"], created_by=request.user)
        record(
            "subscription.ordered",
            f"Chose the {invoice.subscription.plan.name} plan — invoice {invoice.number} (৳{invoice.amount})",
            category=Category.SUBSCRIPTION,
            request=request,
            target=invoice,
        )
        return Response(InvoiceSerializer(invoice).data, status=201)


class ManualPaymentSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=list(MANUAL_METHODS))
    reference = serializers.RegexField(
        r"^[A-Za-z0-9-]{6,40}$",
        error_messages={"invalid": "Enter the transaction ID exactly as shown in your payment SMS."},
    )
    sender_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    amount_sent = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )

    def validate_method(self, value):
        if not payment_accounts().get(value):
            raise serializers.ValidationError("This payment method is not available.")
        return value


class InvoiceManualPaymentView(WorkspaceSubscriptionMixin, APIView):
    @extend_schema(request=ManualPaymentSerializer, tags=["workspace"])
    def post(self, request, pk):
        invoice = self.open_invoice(request, pk)
        data = ManualPaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        tx = submit_manual_payment(invoice, user=request.user, **data.validated_data)
        record(
            "subscription.payment_submitted",
            f"Submitted {tx.get_method_display()} payment {tx.reference} for invoice {invoice.number}",
            category=Category.SUBSCRIPTION,
            request=request,
            target=tx,
        )
        return Response(TransactionSerializer(tx).data, status=201)


class InvoicePayOnlineView(WorkspaceSubscriptionMixin, APIView):
    @extend_schema(tags=["workspace"])
    def post(self, request, pk):
        invoice = self.open_invoice(request, pk)
        base = settings.PUBLIC_API_URL.rstrip("/") or request.build_absolute_uri("/api").rstrip("/")
        try:
            _, url = gateway.initiate(invoice, user=request.user, callback_base=f"{base}/payments/sslcommerz")
        except gateway.GatewayError as exc:
            raise ValidationError({"payment": [str(exc)]}) from exc
        return Response({"redirect_url": url})


class InvoiceCancelView(WorkspaceSubscriptionMixin, APIView):
    @extend_schema(tags=["workspace"])
    def post(self, request, pk):
        invoice = self.open_invoice(request, pk)
        if invoice.status != Invoice.Status.UNPAID:
            raise ValidationError({"invoice": ["Only an unpaid order can be cancelled."]})
        cancel_order(invoice)
        record(
            "subscription.order_cancelled",
            f"Cancelled unpaid invoice {invoice.number}",
            category=Category.SUBSCRIPTION,
            request=request,
            target=invoice,
        )
        return Response(status=204)


class PromoApplySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)


class InvoicePromoView(WorkspaceSubscriptionMixin, APIView):
    """Apply (POST) or remove (DELETE) a promo code on the open, unpaid invoice."""

    @extend_schema(request=PromoApplySerializer, tags=["workspace"])
    def post(self, request, pk):
        invoice = self.open_invoice(request, pk)
        data = PromoApplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = apply_promo(invoice, data.validated_data["code"], user=request.user)
        promo = invoice.promo_code
        paid = " — fully covered, plan activated" if invoice.status == Invoice.Status.PAID else ""
        record(
            "subscription.promo_applied",
            f"Applied promo code {promo.code} ({promo.percent_off}% off, −৳{invoice.discount}) to invoice "
            f"{invoice.number}{paid}",
            category=Category.SUBSCRIPTION,
            request=request,
            target=invoice,
        )
        return Response(InvoiceSerializer(invoice).data)

    @extend_schema(tags=["workspace"])
    def delete(self, request, pk):
        invoice = self.open_invoice(request, pk)
        code = invoice.promo_code.code if invoice.promo_code else None
        invoice = remove_promo(invoice)
        if code:
            record(
                "subscription.promo_removed",
                f"Removed promo code {code} from invoice {invoice.number}",
                category=Category.SUBSCRIPTION,
                request=request,
                target=invoice,
            )
        return Response(InvoiceSerializer(invoice).data)


# ------------------------------------------------------------------ gateway callbacks
@method_decorator(csrf_exempt, name="dispatch")
class SSLCommerzCallbackView(APIView):
    """SSLCommerz POSTs here (browser redirect for success/fail/cancel, server call for IPN)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [FormParser, MultiPartParser, JSONParser]
    outcome = "success"

    @extend_schema(exclude=True)
    def post(self, request):
        tran_id = request.data.get("tran_id", "")
        tx = gateway.settle(tran_id, request.data.get("val_id"), self.outcome) if tran_id else None
        if self.outcome == "ipn":
            return Response({"received": bool(tx)})
        result = (
            "success"
            if tx
            and tx.status
            in (PaymentTransaction.Status.VERIFIED, PaymentTransaction.Status.PENDING_VERIFICATION)
            else ("cancelled" if self.outcome == "cancel" else "failed")
        )
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/workspace/subscription?payment={result}")


# ------------------------------------------------------------------ super admin
class PlanAdminViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PlanSerializer
    queryset = Plan.objects.all()
    pagination_class = None
    filter_backends = []

    def perform_update(self, serializer):
        before = {k: str(getattr(serializer.instance, k)) for k in serializer.validated_data}
        serializer.save()
        plan = serializer.instance
        record(
            "platform.plan_updated",
            f"Updated {plan.name} plan (price ৳{plan.price}, {'offered' if plan.is_active else 'hidden'})",
            category=Category.PLATFORM,
            request=self.request,
            target=plan,
            data={"before": before},
        )


class PromoCodeAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PromoCodeSerializer
    queryset = PromoCode.objects.all()
    pagination_class = None
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete"]

    def _record(self, action, verb, promo, **extra):
        state = "" if promo.is_active else ", switched off"
        record(
            action,
            f"{verb} promo code {promo.code} ({promo.label}{state})",
            category=Category.PLATFORM,
            request=self.request,
            target=promo,
            **extra,
        )

    def perform_create(self, serializer):
        self._record("platform.promo_created", "Created", serializer.save(created_by=self.request.user))

    def perform_update(self, serializer):
        before = {k: str(getattr(serializer.instance, k)) for k in serializer.validated_data}
        self._record("platform.promo_updated", "Updated", serializer.save(), data={"before": before})

    def get_queryset(self):
        qs = PromoCode.objects.prefetch_related("plans")
        if self.request.query_params.get("archived") != "1" and self.action == "list":
            qs = qs.filter(is_archived=False)
        return qs

    @action(detail=True, methods=["get"])
    def redemptions(self, request, pk=None):
        """Every use of the code: plan invoices (existing turfs) and registrations."""
        from apps.applications.models import RegistrationPayment

        promo = self.get_object()
        rows = [
            {
                "kind": "invoice",
                "who": inv.turf.name,
                "reference": inv.number,
                "status": inv.status,
                "discount": str(inv.discount),
                "amount": str(inv.amount),
                "at": inv.paid_at or inv.created_at,
            }
            for inv in promo.invoices.select_related("turf").order_by("-created_at")[:200]
        ]
        for r in promo.redemptions.select_related("application").order_by("-created_at")[:200]:
            pay = RegistrationPayment.objects.filter(redemption=r).order_by("-created_at").first()
            rows.append(
                {
                    "kind": "registration",
                    "who": r.application.turf_name,
                    "reference": r.application.reference,
                    "status": r.status,
                    "discount": str(r.discount),
                    "amount": str(pay.amount_due) if pay else None,
                    "at": r.finished_at or r.created_at,
                    "reserved_until": r.reserved_until,
                }
            )
        rows.sort(key=lambda x: x["at"], reverse=True)
        return Response({"results": rows})

    def perform_destroy(self, instance):
        if instance.redemptions.exists():
            raise ValidationError(
                {"code": [f"{instance.code} was used in registrations. Archive it instead."]}
            )
        if instance.invoices.exists():
            msg = f"{instance.code} is already on invoices. Switch it off instead."
            raise ValidationError({"code": [msg]})
        self._record("platform.promo_deleted", "Deleted", instance)
        instance.delete()


class PaymentAdminViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminPaymentSerializer
    filter_backends = []

    def get_queryset(self):
        qs = (
            PaymentTransaction.objects.select_related(
                "invoice__turf", "invoice__subscription__plan", "submitted_by"
            )
            .prefetch_related("invoice__turf__memberships__user")
            .exclude(status=PaymentTransaction.Status.INITIATED)
        )
        if status := self.request.query_params.get("status"):
            qs = qs.filter(status=status)
        return qs

    def _review(self, request, pk, approve):
        tx = review_payment(
            self.get_object(), approve=approve, reviewer=request.user, note=str(request.data.get("note", ""))
        )
        verb = "Verified" if approve else "Rejected"
        record(
            "subscription.payment_verified" if approve else "subscription.payment_rejected",
            f"{verb} {tx.get_method_display()} payment {tx.reference} (৳{tx.amount}) for invoice "
            f"{tx.invoice.number}" + (f": {tx.note}" if tx.note and not approve else ""),
            category=Category.SUBSCRIPTION,
            request=request,
            turf=tx.invoice.turf,
            target=tx,
        )
        return Response(AdminPaymentSerializer(tx).data)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        return self._review(request, pk, True)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review(request, pk, False)


class AssignPlanSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(slug_field="period", queryset=Plan.objects.all())
    paid = serializers.BooleanField(default=True)
    method = serializers.ChoiceField(choices=PaymentTransaction.Method.choices, default="cash")
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class AssignPlanView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(request=AssignPlanSerializer, tags=["admin"])
    def post(self, request, pk):
        turf = get_object_or_404(Turf, pk=pk)
        data = AssignPlanSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = assign_plan(turf, by=request.user, **data.validated_data)
        paid = "paid" if data.validated_data["paid"] else "invoice sent"
        record(
            "subscription.plan_assigned",
            f"TurfBari set the {invoice.subscription.plan.name} plan ({paid}, ৳{invoice.amount})",
            category=Category.SUBSCRIPTION,
            request=request,
            turf=turf,
            target=invoice,
        )
        return Response({"invoice": InvoiceSerializer(invoice).data, "standing": standing_payload(turf)})
