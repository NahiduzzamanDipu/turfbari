"""SMS wallet APIs: owner wallet + bKash recharge requests; admin pricing, recharge approval, account
SMS controls, wallet adjustments and the financial overview.

Money is Decimal end to end. Wallets change only through wallet.post() (immutable ledger rows).
The bKash charge on a recharge is kept separately on the request and is never wallet money.
"""

import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.bookings.phone import normalize_bd_phone
from apps.common.models import PlatformSettings
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsPlatformAdmin
from apps.common.tenancy import IsTenantMember
from apps.turfs.models import Turf

from . import wallet
from .models import (
    SmsAccountControl,
    SmsKind,
    SmsMessage,
    SmsPricing,
    SmsRechargeRequest,
    SmsWallet,
    WalletTransaction,
)
from .services import queue_sms, retry_blocked

TWO = Decimal("0.01")
TRX = re.compile(r"^[A-Z0-9]{8,12}$")
CREDITED_BN = "TURFBARI: আপনার SMS Wallet-এ ৳{amount} সফলভাবে যোগ হয়েছে। বর্তমান ব্যালেন্স ৳{balance}। ধন্যবাদ।"
RECHARGE_REJECTED_BN = "TURFBARI: আপনার ৳{amount} SMS Wallet রিচার্জ অনুরোধ (TrxID {trx}) গ্রহণ করা যায়নি।{reason}"


def taka(value) -> str:
    return f"{Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP):,.2f}".rstrip("0").rstrip(".")


def recharge_quote(amount: Decimal, s: PlatformSettings | None = None) -> dict:
    s = s or PlatformSettings.load()
    amount = Decimal(amount).quantize(TWO, rounding=ROUND_HALF_UP)
    fee = (amount * s.recharge_fee_percent / 100).quantize(TWO, rounding=ROUND_HALF_UP)
    return {"wallet_amount": amount, "fee_percent": s.recharge_fee_percent, "fee": fee, "total": amount + fee}


def recharge_number(s: PlatformSettings | None = None) -> str:
    """Where owners send recharges: the number set for recharges, else TurfBari's subscription bKash number
    (Admin -> API, or TURFBARI_BKASH_NUMBER), so recharge works without extra setup."""
    from django.conf import settings

    s = s or PlatformSettings.load()
    return (
        s.recharge_bkash_number
        or s.subscription_bkash_number
        or settings.SUBSCRIPTION_PAYMENT_ACCOUNTS.get("bkash", "")
    )


def recharge_settings(s: PlatformSettings | None = None) -> dict:
    s = s or PlatformSettings.load()
    number = recharge_number(s)
    return {
        "enabled": bool(s.recharge_enabled and number),
        "switched_off": not s.recharge_enabled,
        "bkash_number": number or None,
        "instructions": s.recharge_instructions,
        "fee_percent": str(s.recharge_fee_percent),
        "min_amount": str(s.recharge_min_amount),
        "max_amount": str(s.recharge_max_amount) if s.recharge_max_amount else None,
    }


def owner_phones(turf) -> list[str]:
    from .tick import owner_phones as phones

    return phones(turf)


def recharge_row(r: SmsRechargeRequest, *, admin: bool = False) -> dict:
    row = {
        "id": str(r.id),
        "status": r.status,
        "status_label": r.get_status_display(),
        "wallet_amount": str(r.wallet_amount),
        "fee_percent": str(r.fee_percent),
        "fee": str(r.fee),
        "total_expected": str(r.total_expected),
        "amount_sent": str(r.amount_sent),
        "sender_number": r.sender_number,
        "trx_id": r.trx_id,
        "note": r.note,
        "submitted_at": r.created_at,
        "reviewed_at": r.reviewed_at,
        "rejection_reason": r.rejection_reason or None,
    }
    if admin:
        owner = next((m.user for m in r.turf.memberships.all() if m.role == "owner" and m.is_active), None)
        row["turf"] = {"id": str(r.turf_id), "name": r.turf.name}
        row["owner"] = (
            {"name": owner.full_name, "email": owner.email, "phone": owner.phone} if owner else None
        )
        row["reviewed_by"] = (r.reviewed_by.full_name or r.reviewed_by.email) if r.reviewed_by_id else None
    return row


def ledger_row(t: WalletTransaction) -> dict:
    return {
        "id": t.pk,
        "at": t.created_at,
        "kind": t.kind,
        "kind_label": t.get_kind_display(),
        "amount": str(t.amount),
        "balance_after": str(t.balance_after),
        "segments": t.segments,
        "price_per_segment": str(t.price_per_segment) if t.price_per_segment is not None else None,
        "note": t.note,
        "sms_id": str(t.sms_id) if t.sms_id else None,
    }


def pricing_row(p: SmsPricing | None) -> dict | None:
    if p is None:
        return None
    return {
        "id": p.pk,
        "price_per_segment": str(p.price_per_segment),
        "masking_price_per_segment": str(p.masking_price_per_segment),
        "bulk_price_per_segment": str(p.bulk_price_per_segment),
        "effective_from": p.effective_from,
        "note": p.note,
    }


# ------------------------------------------------------------------ owner
class WalletView(APIView):
    """Balance, current price, blocked SMS, recharge info. Owners and managers allowed to see SMS."""

    permission_classes = [IsTenantMember]
    required_permission = "view_sms"

    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        w = wallet.wallet_for(turf)
        control = wallet.control_for(turf)
        blocked = dict(
            SmsMessage.objects.filter(turf=turf, status=SmsMessage.Status.BLOCKED)
            .exclude(block_reason=SmsMessage.BlockReason.CANCELLED)
            .values_list("block_reason")
            .annotate(n=Count("id"))
        )
        recent = SmsRechargeRequest.objects.filter(turf=turf).order_by("-created_at")[:10]
        return Response(
            {
                "balance": str(w.balance),
                "pricing": pricing_row(wallet.current_pricing()),
                "price_per_segment": str(wallet.price_for(SmsKind.CUSTOM) or "") or None,
                "bulk_price_per_segment": str(wallet.price_for(SmsKind.CAMPAIGN) or "") or None,
                "sms_disabled": not control.all_enabled,
                "disabled_types": [
                    k
                    for k in (
                        "booking_confirmed",
                        "rejection_cancellation",
                        "reminder",
                        "owner_booking",
                        "single",
                        "bulk",
                    )
                    if not getattr(control, k)
                ],
                "disabled_message_bn": wallet.DISABLED_BN if not control.all_enabled else None,
                "blocked": blocked,
                "insufficient_message_bn": wallet.INSUFFICIENT_BN
                if blocked.get(SmsMessage.BlockReason.INSUFFICIENT_BALANCE)
                else None,
                "recharge": recharge_settings(),
                "recharges": [recharge_row(r) for r in recent],
            }
        )


class LedgerView(APIView):
    permission_classes = [IsTenantMember]
    required_permission = "view_sms"

    @extend_schema(tags=["workspace"])
    def get(self, request):
        w = wallet.wallet_for(request.tenant)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(w.transactions.all(), request, view=self)
        return paginator.get_paginated_response([ledger_row(t) for t in page])


class RechargeSerializer(serializers.Serializer):
    wallet_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))
    amount_sent = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))
    sender_number = serializers.CharField(max_length=20)
    trx_id = serializers.CharField(max_length=30)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class RechargeView(APIView):
    """GET: quote for ?amount=. POST: submit a bKash recharge (owner only; credited after admin approval)."""

    permission_classes = [IsTenantMember]
    owner_only_writes = True
    allow_inactive_subscription = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sms_recharge"

    @extend_schema(tags=["workspace"])
    def get(self, request):
        try:
            amount = Decimal(request.query_params.get("amount", "0"))
        except ArithmeticError:
            raise ValidationError({"amount": ["Enter an amount."]}) from None
        q = recharge_quote(amount)
        return Response({k: str(v) for k, v in q.items()} | {"settings": recharge_settings()})

    @extend_schema(tags=["workspace"], request=RechargeSerializer)
    def post(self, request):
        s = PlatformSettings.load()
        if not (s.recharge_enabled and recharge_number(s)):
            raise ValidationError(
                {"non_field_errors": ["Wallet recharge is not open right now. Contact TurfBari."]}
            )
        data = RechargeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        errors = {}
        if v["wallet_amount"] < s.recharge_min_amount:
            errors["wallet_amount"] = [f"The minimum recharge is ৳{taka(s.recharge_min_amount)}."]
        elif s.recharge_max_amount and v["wallet_amount"] > s.recharge_max_amount:
            errors["wallet_amount"] = [f"The maximum recharge is ৳{taka(s.recharge_max_amount)}."]
        q = recharge_quote(v["wallet_amount"], s)
        # bKash amounts are often whole taka: accept up to ৳1 either way of the exact total.
        if not errors and abs(v["amount_sent"] - q["total"]) > 1:
            errors["amount_sent"] = [
                f"For ৳{taka(q['wallet_amount'])} of credit send ৳{taka(q['total'])} "
                f"(includes the {s.recharge_fee_percent}% bKash charge of ৳{taka(q['fee'])})."
            ]
        try:
            sender = "0" + normalize_bd_phone(v["sender_number"])[4:]
        except ValidationError:
            errors["sender_number"] = ["Enter the bKash number you paid from, e.g. 01712345678."]
            sender = ""
        trx = re.sub(r"\s", "", v["trx_id"]).upper()
        if not TRX.match(trx):
            errors["trx_id"] = ["Enter the bKash Transaction ID exactly as in the bKash SMS."]
        elif SmsRechargeRequest.objects.filter(trx_id=trx).exists():
            errors["trx_id"] = ["This Transaction ID was already submitted."]
        if errors:
            raise ValidationError(errors)
        from apps.legal.services import require_for_user

        require_for_user(request.user, "sms_recharge", request.tenant, request)
        try:
            with transaction.atomic():
                r = SmsRechargeRequest.objects.create(
                    turf=request.tenant,
                    wallet_amount=q["wallet_amount"],
                    fee_percent=q["fee_percent"],
                    fee=q["fee"],
                    total_expected=q["total"],
                    amount_sent=v["amount_sent"],
                    sender_number=sender,
                    trx_id=trx,
                    note=v.get("note", ""),
                    submitted_by=request.user,
                )
        except IntegrityError:
            raise ValidationError({"trx_id": ["This Transaction ID was already submitted."]}) from None
        record(
            "sms.recharge_requested",
            f"Asked to recharge the SMS wallet with ৳{taka(r.wallet_amount)} (bKash ৳{taka(r.amount_sent)}, TrxID {trx})",  # noqa: E501
            category=Category.SUBSCRIPTION,
            request=request,
            target=r,
        )
        return Response(recharge_row(r), status=status.HTTP_201_CREATED)


class RetryBlockedView(APIView):
    """Retry one blocked SMS (<id>) or every message blocked for low balance (no id)."""

    permission_classes = [IsTenantMember]
    required_permission = "view_sms"

    @extend_schema(tags=["workspace"], request=None)
    def post(self, request, pk=None):
        qs = SmsMessage.objects.filter(turf=request.tenant, status=SmsMessage.Status.BLOCKED)
        if pk:
            messages = [get_object_or_404(qs, pk=pk)]
        else:
            messages = list(
                qs.filter(block_reason=SmsMessage.BlockReason.INSUFFICIENT_BALANCE).order_by("created_at")[
                    :200
                ]
            )
        sent = blocked = 0
        for m in messages:
            m = retry_blocked(m, user=request.user)
            sent += m.status == SmsMessage.Status.SENT
            blocked += m.status == SmsMessage.Status.BLOCKED
        return Response(
            {
                "tried": len(messages),
                "sent": sent,
                "still_blocked": blocked,
                "balance": str(wallet.wallet_for(request.tenant).balance),
            }
        )


# ------------------------------------------------------------------ admin
class AdminPricingSerializer(serializers.Serializer):
    price_per_segment = serializers.DecimalField(
        max_digits=8, decimal_places=4, min_value=Decimal("0"), required=False
    )
    masking_price_per_segment = serializers.DecimalField(
        max_digits=8, decimal_places=4, min_value=Decimal("0"), required=False
    )
    bulk_price_per_segment = serializers.DecimalField(
        max_digits=8, decimal_places=4, min_value=Decimal("0"), required=False
    )
    effective_from = serializers.DateTimeField(required=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
    sender_is_masking = serializers.BooleanField(required=False)

    def validate(self, attrs):
        prices = {"price_per_segment", "masking_price_per_segment", "bulk_price_per_segment"}
        given = prices & set(attrs)
        if given and given != prices:
            raise serializers.ValidationError({"price_per_segment": ["Set all three prices together."]})
        if not given and "sender_is_masking" not in attrs:
            raise serializers.ValidationError({"price_per_segment": ["Enter the prices."]})
        return attrs


class AdminPricingView(APIView):
    permission_classes = [IsPlatformAdmin]

    @staticmethod
    def payload():
        from .models import SmsConfig

        return {
            "current": pricing_row(wallet.current_pricing()),
            "scheduled": [
                pricing_row(p) for p in SmsPricing.objects.filter(effective_from__gt=timezone.now())
            ],
            "history": [pricing_row(p) for p in SmsPricing.objects.all()[:20]],
            "sender_is_masking": SmsConfig.load().sender_is_masking,
        }

    @extend_schema(tags=["admin"])
    def get(self, request):
        return Response(self.payload())

    @extend_schema(tags=["admin"], request=AdminPricingSerializer)
    def post(self, request):
        from .models import SmsConfig

        data = AdminPricingSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if "sender_is_masking" in v:
            config = SmsConfig.load()
            config.sender_is_masking = v.pop("sender_is_masking")
            config.save()
        if "price_per_segment" not in v:  # only the masking switch changed: no new price row
            return Response(self.payload())
        p = SmsPricing.objects.create(
            price_per_segment=v["price_per_segment"],
            masking_price_per_segment=v["masking_price_per_segment"],
            bulk_price_per_segment=v["bulk_price_per_segment"],
            effective_from=v.get("effective_from") or timezone.now(),
            note=v.get("note", ""),
            created_by=request.user,
        )
        record(
            "platform.sms_pricing",
            f"SMS price from {timezone.localtime(p.effective_from):%d %b %Y %H:%M}: ৳{p.price_per_segment}/segment "  # noqa: E501
            f"(masking ৳{p.masking_price_per_segment}, bulk ৳{p.bulk_price_per_segment})",
            category=Category.PLATFORM,
            request=request,
        )
        return Response(self.payload(), status=status.HTTP_201_CREATED)


class AdminRechargeListView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        qs = SmsRechargeRequest.objects.select_related("turf", "reviewed_by").prefetch_related(
            "turf__memberships__user"
        )
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(
                Q(turf__name__icontains=q) | Q(trx_id__icontains=q) | Q(sender_number__icontains=q)
            )
        counts = dict(SmsRechargeRequest.objects.values_list("status").annotate(n=Count("id")))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response([recharge_row(r, admin=True) for r in page])
        response.data["counts"] = counts
        return response


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


def _owner_sms(turf, kind, body, key):
    if not PlatformSettings.load().platform_owner_sms:
        return
    for phone in owner_phones(turf):
        queue_sms(to=phone, body=body, kind=kind, turf=turf, dedupe_key=f"{key}:{phone[-10:]}")


class AdminRechargeDecisionView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=ReasonSerializer)
    def post(self, request, pk, decision):
        if decision not in ("approve", "reject"):
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            r = SmsRechargeRequest.objects.select_for_update().select_related("turf").get(pk=pk)
            if r.status != SmsRechargeRequest.Status.PENDING:
                raise ValidationError(
                    {"status": [f"This request was already {r.get_status_display().lower()}."]}
                )
            r.reviewed_by, r.reviewed_at = request.user, timezone.now()
            if decision == "approve":
                entry = wallet.credit(
                    r.turf,
                    r.wallet_amount,
                    kind=WalletTransaction.Kind.RECHARGE,
                    key=f"recharge:{r.pk}",  # one credit per request, ever
                    user=request.user,
                    note=f"bKash recharge TrxID {r.trx_id}",
                    recharge=r,
                )
                r.status = SmsRechargeRequest.Status.APPROVED
            else:
                r.status = SmsRechargeRequest.Status.REJECTED
                r.rejection_reason = data.validated_data.get("reason", "").strip()
            r.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
        if decision == "approve":
            _owner_sms(
                r.turf,
                SmsKind.WALLET_CREDITED,
                CREDITED_BN.format(amount=taka(r.wallet_amount), balance=taka(entry.balance_after)),
                f"recharge:{r.pk}:credited",
            )
            summary = (
                f"Approved SMS wallet recharge ৳{taka(r.wallet_amount)} for {r.turf.name} (TrxID {r.trx_id})"
            )
        else:
            reason = f" কারণ: {r.rejection_reason}।" if r.rejection_reason else ""
            _owner_sms(
                r.turf,
                SmsKind.WALLET_RECHARGE_REJECTED,
                RECHARGE_REJECTED_BN.format(amount=taka(r.wallet_amount), trx=r.trx_id, reason=reason),
                f"recharge:{r.pk}:rejected",
            )
            summary = (
                f"Rejected SMS wallet recharge ৳{taka(r.wallet_amount)} for {r.turf.name} (TrxID {r.trx_id})"
            )
        record(
            f"platform.recharge_{decision}d",
            summary[:255],
            category=Category.PLATFORM,
            request=request,
            turf=r.turf,
            target=r,
        )
        return Response(
            recharge_row(
                SmsRechargeRequest.objects.select_related("turf", "reviewed_by")
                .prefetch_related("turf__memberships__user")
                .get(pk=r.pk),
                admin=True,
            )
        )


class ControlSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsAccountControl
        fields = [
            "all_enabled",
            "booking_confirmed",
            "rejection_cancellation",
            "reminder",
            "owner_booking",
            "single",
            "bulk",
            "monthly_limit",
        ]


class AdminTurfSmsView(APIView):
    """One turf's SMS controls, wallet and recent ledger (Admin -> Turfs -> SMS)."""

    permission_classes = [IsPlatformAdmin]

    @staticmethod
    def payload(turf) -> dict:
        control = wallet.control_for(turf)
        w = wallet.wallet_for(turf)
        blocked = dict(
            SmsMessage.objects.filter(turf=turf, status=SmsMessage.Status.BLOCKED)
            .values_list("block_reason")
            .annotate(n=Count("id"))
        )
        return {
            "turf": {"id": str(turf.id), "name": turf.name},
            "controls": ControlSerializer(control).data,
            "controls_updated_at": control.updated_at,
            "controls_updated_by": (control.updated_by.full_name or control.updated_by.email)
            if control.updated_by_id
            else None,
            "balance": str(w.balance),
            "blocked": blocked,
            "ledger": [ledger_row(t) for t in w.transactions.all()[:30]],
        }

    @extend_schema(tags=["admin"])
    def get(self, request, pk):
        return Response(self.payload(get_object_or_404(Turf, pk=pk)))

    @extend_schema(tags=["admin"], request=ControlSerializer)
    def put(self, request, pk):
        turf = get_object_or_404(Turf, pk=pk)
        control = SmsAccountControl.objects.get_or_create(turf=turf)[0]
        data = ControlSerializer(control, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        changed = {k: v for k, v in data.validated_data.items() if getattr(control, k) != v}
        data.save(updated_by=request.user)
        if changed:
            record(
                "platform.sms_controls",
                f"SMS controls for {turf.name}: "
                + ", ".join(
                    f"{k}={'on' if v is True else 'off' if v is False else v}" for k, v in changed.items()
                ),
                category=Category.PLATFORM,
                request=request,
                turf=turf,
                data={k: v for k, v in changed.items()},
            )
        return Response(self.payload(turf))


class AdjustSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(min_length=5, max_length=200)


class AdminWalletAdjustView(APIView):
    """Add (positive) or take back (negative) wallet credit with a reason — a new ledger entry."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=AdjustSerializer)
    def post(self, request, pk):
        turf = get_object_or_404(Turf, pk=pk)
        data = AdjustSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        amount, reason = data.validated_data["amount"], data.validated_data["reason"]
        if amount == 0:
            raise ValidationError({"amount": ["Enter a non-zero amount."]})
        key = f"adjust:{turf.pk}:{request.data.get('idempotency_key') or timezone.now().timestamp()}"
        try:
            wallet.post(
                wallet.wallet_for(turf).pk,
                kind=WalletTransaction.Kind.ADMIN_CREDIT if amount > 0 else WalletTransaction.Kind.ADJUSTMENT,
                amount=amount,
                key=key[:100],
                note=reason,
                created_by=request.user,
            )
        except wallet.InsufficientBalance:
            raise ValidationError({"amount": ["The wallet doesn't have that much to take back."]}) from None
        record(
            "platform.wallet_adjusted",
            f"{'Added' if amount > 0 else 'Took back'} ৳{taka(abs(amount))} SMS credit for {turf.name}: {reason}",  # noqa: E501
            category=Category.PLATFORM,
            request=request,
            turf=turf,
        )
        return Response(AdminTurfSmsView.payload(turf))


class AdminSmsRefundView(APIView):
    """Refund the charge of a message whose provider result was unknown, after checking BulkSMSBD."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=ReasonSerializer)
    def post(self, request, pk):
        message = get_object_or_404(SmsMessage, pk=pk)
        if message.status != SmsMessage.Status.UNKNOWN or not message.turf_id:
            raise ValidationError({"status": ["Only unconfirmed turf messages can be refunded here."]})
        last = message.attempt_log.order_by("-number").first()
        entry = (
            wallet.refund(message, last.number, "Refund: admin confirmed it was not sent", user=request.user)
            if last
            else None
        )
        message.status, message.provider_message = (
            SmsMessage.Status.FAILED,
            "Not sent (confirmed by TurfBari); charge refunded",
        )
        message.charged_amount = wallet.net_charged(message)
        message.save(update_fields=["status", "provider_message", "charged_amount", "updated_at"])
        record(
            "platform.sms_refunded",
            f"Refunded SMS to {message.masked_to} for {message.turf.name}",
            category=Category.PLATFORM,
            request=request,
            turf=message.turf,
        )
        return Response({"refunded": str(entry.amount) if entry else "0", "status": message.status})


class AdminWalletsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        rows = (
            Turf.objects.exclude(status=Turf.Status.ARCHIVED)
            .select_related("sms_wallet", "sms_control")
            .annotate(
                charges=Sum(
                    "sms_wallet__transactions__amount",
                    filter=Q(sms_wallet__transactions__kind__in=["sms_charge", "sms_refund"]),
                ),
                recharged=Sum(
                    "sms_wallet__transactions__amount", filter=Q(sms_wallet__transactions__kind="recharge")
                ),
            )
            .order_by("name")
        )
        out = []
        for t in rows:
            w = getattr(t, "sms_wallet", None)
            c = getattr(t, "sms_control", None)
            out.append(
                {
                    "turf": {"id": str(t.id), "name": t.name},
                    "balance": str(w.balance if w else 0),
                    "recharged": str(t.recharged or 0),
                    "sms_spent": str(-(t.charges or 0)),
                    "sms_enabled": c.all_enabled if c else True,
                }
            )
        return Response(out)


class AdminFinanceView(APIView):
    """Platform money at a glance. Wallet money, bKash charges and subscription revenue are kept apart;
    only approved payments count as received."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        from apps.subscriptions.models import PaymentTransaction

        R = SmsRechargeRequest.Status
        recharge = SmsRechargeRequest.objects.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status=R.PENDING)),
            pending_amount=Sum("wallet_amount", filter=Q(status=R.PENDING)),
            approved=Count("id", filter=Q(status=R.APPROVED)),
            approved_amount=Sum("wallet_amount", filter=Q(status=R.APPROVED)),
            approved_fees=Sum("fee", filter=Q(status=R.APPROVED)),
            rejected=Count("id", filter=Q(status=R.REJECTED)),
        )
        ledger = WalletTransaction.objects.aggregate(
            charged=Sum("amount", filter=Q(kind=WalletTransaction.Kind.SMS_CHARGE)),
            refunded=Sum("amount", filter=Q(kind=WalletTransaction.Kind.SMS_REFUND)),
            charged_segments=Sum("segments", filter=Q(kind=WalletTransaction.Kind.SMS_CHARGE)),
            refunded_segments=Sum("segments", filter=Q(kind=WalletTransaction.Kind.SMS_REFUND)),
            admin_credit=Sum(
                "amount",
                filter=Q(kind__in=[WalletTransaction.Kind.ADMIN_CREDIT, WalletTransaction.Kind.ADJUSTMENT]),
            ),
        )
        P = PaymentTransaction.Status
        subs = PaymentTransaction.objects.exclude(channel="admin").aggregate(
            pending=Count("id", filter=Q(status=P.PENDING_VERIFICATION)),
            pending_amount=Sum("amount", filter=Q(status=P.PENDING_VERIFICATION)),
            approved=Count("id", filter=Q(status=P.VERIFIED)),
            approved_amount=Sum("amount", filter=Q(status=P.VERIFIED)),
            rejected=Count("id", filter=Q(status=P.REJECTED)),
        )
        platform_sms = SmsMessage.objects.filter(
            scope=SmsMessage.Scope.PLATFORM, status=SmsMessage.Status.SENT
        ).aggregate(n=Count("id"), cost=Sum("charged_amount"), seg=Sum("segments"))
        top = (
            WalletTransaction.objects.filter(
                kind__in=["sms_charge", "sms_refund"], created_at__gte=timezone.now() - timedelta(days=30)
            )
            .values("wallet__turf_id", "wallet__turf__name")
            .annotate(spent=Sum("amount"), seg=Sum("segments"))
            .order_by("spent")[:10]
        )
        z = lambda v: str(v or 0)  # noqa: E731
        return Response(
            {
                "sms_wallets": {
                    "total_balance": z(SmsWallet.objects.aggregate(s=Sum("balance"))["s"]),
                    "sms_charged": z(-((ledger["charged"] or 0) + (ledger["refunded"] or 0))),
                    "segments_billed": (ledger["charged_segments"] or 0) - (ledger["refunded_segments"] or 0),
                    "admin_credit": z(ledger["admin_credit"]),
                },
                "recharges": {
                    "total": recharge["total"],
                    "pending": recharge["pending"],
                    "pending_amount": z(recharge["pending_amount"]),
                    "approved": recharge["approved"],
                    "approved_amount": z(recharge["approved_amount"]),
                    "bkash_charges_collected": z(recharge["approved_fees"]),
                    "rejected": recharge["rejected"],
                },
                "subscriptions": {
                    "pending": subs["pending"],
                    "pending_amount": z(subs["pending_amount"]),
                    "approved": subs["approved"],
                    "received": z(subs["approved_amount"]),
                    "rejected": subs["rejected"],
                },
                "platform_sms": {
                    "sent": platform_sms["n"],
                    "segments": platform_sms["seg"] or 0,
                    "cost": z(platform_sms["cost"]),
                },
                "top_sms_spenders_30d": [
                    {
                        "turf": r["wallet__turf__name"],
                        "turf_id": str(r["wallet__turf_id"]),
                        "spent": z(-(r["spent"] or 0)),
                        "segments": r["seg"] or 0,
                    }
                    for r in top
                ],
            }
        )


class RechargeSettingsSerializer(serializers.Serializer):
    recharge_enabled = serializers.BooleanField(required=False)
    recharge_bkash_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    recharge_instructions = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    recharge_fee_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("20"), required=False
    )
    recharge_min_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("1"), required=False
    )
    recharge_max_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    subscription_bkash_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    subscription_instructions = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    subscription_bkash_account_type = serializers.ChoiceField(
        choices=["Personal", "Agent", "Merchant"], required=False
    )
    subscription_fee_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("20"), required=False
    )
    platform_owner_sms = serializers.BooleanField(required=False)

    def _phone(self, value):
        if not value.strip():
            return ""
        try:
            return "0" + normalize_bd_phone(value)[4:]
        except ValidationError:
            raise serializers.ValidationError("Enter a bKash number, e.g. 01712345678.") from None

    def validate_recharge_bkash_number(self, value):
        return self._phone(value)

    def validate_subscription_bkash_number(self, value):
        return self._phone(value)


def payments_settings_payload(s: PlatformSettings) -> dict:
    return {
        "recharge_enabled": s.recharge_enabled,
        "recharge_bkash_number": s.recharge_bkash_number,
        "recharge_instructions": s.recharge_instructions,
        "recharge_fee_percent": str(s.recharge_fee_percent),
        "recharge_min_amount": str(s.recharge_min_amount),
        "recharge_max_amount": str(s.recharge_max_amount),
        "subscription_bkash_number": s.subscription_bkash_number,
        "subscription_instructions": s.subscription_instructions,
        "subscription_bkash_account_type": s.subscription_bkash_account_type,
        "subscription_fee_percent": str(s.subscription_fee_percent),
        "platform_owner_sms": s.platform_owner_sms,
    }


class AdminPaymentSettingsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        return Response(payments_settings_payload(PlatformSettings.load()))

    @extend_schema(tags=["admin"], request=RechargeSettingsSerializer)
    def put(self, request):
        data = RechargeSettingsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        s = PlatformSettings.objects.get_or_create(pk=1)[0]
        for k, v in data.validated_data.items():
            setattr(s, k, v)
        s.save()
        record(
            "platform.payment_settings",
            "Changed bKash payment settings: " + ", ".join(sorted(data.validated_data)),
            category=Category.PLATFORM,
            request=request,
        )
        return Response(payments_settings_payload(s))
