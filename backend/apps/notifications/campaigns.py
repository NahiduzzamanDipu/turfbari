"""Owner-sent SMS: one customised message, or a bulk campaign with {{placeholders}}.

Recipients only ever come from the turf's own customers/bookings, numbers the owner types, or a CSV the
owner uploads — never another turf's data. Every message is a normal SmsMessage, so the wallet checks,
charging, refunds and logs are the same as for automatic SMS. Campaign messages are queued and sent in
batches by the tick (and a first batch right away); cancelling stops anything not yet sent at no cost.
"""

import csv
import io
import re
import threading
import uuid
from decimal import Decimal

from django.db import IntegrityError, close_old_connections, transaction
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
from apps.bookings.models import Booking, Customer
from apps.common.pagination import StandardPagination
from apps.common.tenancy import IsTenantMember

from . import wallet
from .models import SmsCampaign, SmsKind, SmsMessage
from .providers import bd_msisdn, segment_count
from .services import deliver, queue_sms

PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
VARIABLES = ("customer_name", "turf_name", "booking_date", "booking_time", "booking_id", "customer_phone")
MAX_RECIPIENTS = 2000
MAX_CSV_BYTES = 300_000
FIRST_BATCH = 50


def local_phone(msisdn: str) -> str:
    return "0" + msisdn[3:] if msisdn.startswith("880") else msisdn


def fill(template: str, values: dict) -> str:
    return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), "")), template).strip()


def check_template(template: str) -> None:
    unknown = {m.group(1) for m in PLACEHOLDER.finditer(template)} - set(VARIABLES)
    if unknown:
        raise ValidationError(
            {"template": [f"Unknown placeholder: {', '.join('{{' + u + '}}' for u in sorted(unknown))}"]}
        )


def booking_values(booking: Booking | None) -> dict:
    if booking is None:
        return {}
    start, end = timezone.localtime(booking.start), timezone.localtime(booking.end)
    return {
        "booking_date": f"{start:%d/%m/%Y}",
        "booking_time": f"{start:%I:%M %p}–{end:%I:%M %p}".replace(" 0", " ").lstrip("0"),
        "booking_id": booking.reference,
    }


def parse_csv(text: str) -> list[tuple[str, str]]:
    """(phone, name) pairs from a CSV: a 'phone'/'mobile' column (or the first column) and an optional
    'name' column. Only text is read; nothing in the file is executed or stored as-is."""
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValidationError({"csv": ["The CSV is too large (max 300 KB)."]})
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    phone_col = next(
        (
            i
            for i, h in enumerate(header)
            if h in ("phone", "mobile", "number", "phone number", "mobile number")
        ),
        None,
    )
    name_col = next((i for i, h in enumerate(header) if h in ("name", "customer", "customer name")), None)
    data = rows[1:] if phone_col is not None else rows
    phone_col = phone_col or 0
    out = []
    for r in data[: MAX_RECIPIENTS * 2]:
        if len(r) > phone_col:
            name = r[name_col].strip()[:120] if name_col is not None and len(r) > name_col else ""
            out.append((r[phone_col].strip(), name.lstrip("=+-@")))
    return out


class RecipientsSerializer(serializers.Serializer):
    template = serializers.CharField(max_length=1000)
    # From this turf's own bookings / customers
    from_bookings = serializers.BooleanField(default=False)
    booking_from = serializers.DateField(required=False, allow_null=True)
    booking_to = serializers.DateField(required=False, allow_null=True)
    booking_statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=Booking.Status.choices), required=False
    )
    all_customers = serializers.BooleanField(default=False)
    customer_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=MAX_RECIPIENTS
    )
    numbers = serializers.CharField(
        required=False, allow_blank=True, max_length=40000
    )  # typed, any separator
    csv = serializers.CharField(required=False, allow_blank=True, max_length=MAX_CSV_BYTES)


def resolve(turf, v: dict) -> dict:
    """Valid unique recipients (with their personal values), plus invalid and duplicate counts."""
    check_template(v["template"])
    candidates: list[tuple[str, dict]] = []  # (raw phone, values)
    base = {"turf_name": turf.name}
    if v.get("from_bookings"):
        qs = Booking.objects.filter(turf=turf).select_related("customer").order_by("-start")
        if v.get("booking_from"):
            qs = qs.filter(start__date__gte=v["booking_from"])
        if v.get("booking_to"):
            qs = qs.filter(start__date__lte=v["booking_to"])
        if v.get("booking_statuses"):
            qs = qs.filter(status__in=v["booking_statuses"])
        for b in qs[: MAX_RECIPIENTS * 3]:
            candidates.append(
                (b.customer.phone, base | {"customer_name": b.customer.name} | booking_values(b))
            )
    customers = Customer.objects.filter(turf=turf)
    if v.get("all_customers") or v.get("customer_ids"):
        if v.get("customer_ids"):
            customers = customers.filter(pk__in=v["customer_ids"])  # other turfs' ids simply match nothing
        for c in customers[: MAX_RECIPIENTS * 2]:
            last = c.bookings.order_by("-start").first()
            candidates.append((c.phone, base | {"customer_name": c.name} | booking_values(last)))
    for raw in re.split(r"[\s,;]+", v.get("numbers", "") or ""):
        if raw.strip():
            candidates.append((raw, dict(base)))
    for raw, name in parse_csv(v.get("csv", "") or ""):
        candidates.append((raw, base | {"customer_name": name}))

    seen: dict[str, dict] = {}
    invalid, duplicates = [], 0
    for raw, values in candidates:
        msisdn = bd_msisdn(raw)
        if msisdn is None:
            invalid.append(str(raw)[:30])
            continue
        if msisdn in seen:
            duplicates += 1
            continue
        seen[msisdn] = values | {"customer_phone": local_phone(msisdn)}
    if len(seen) > MAX_RECIPIENTS:
        raise ValidationError({"numbers": [f"At most {MAX_RECIPIENTS} recipients per campaign."]})
    return {"recipients": seen, "invalid": invalid, "duplicates": duplicates}


def estimate(turf, template: str, recipients: dict) -> dict:
    price = wallet.price_for(SmsKind.CAMPAIGN)
    messages = [(m, fill(template, values)) for m, values in recipients.items()]
    segments = sum(segment_count(body) for _, body in messages)
    cost = wallet.money((price or 0) * segments)
    balance = wallet.wallet_for(turf).balance
    return {
        "valid": len(messages),
        "segments": segments,
        "price_per_segment": str(price) if price is not None else None,
        "estimated_cost": str(cost),
        "balance": str(balance),
        "enough_balance": price is not None and balance >= cost,
        "samples": [
            {"to": local_phone(m), "text": body, "segments": segment_count(body)} for m, body in messages[:3]
        ],
    }


class SmsSendGate:
    """Shared refusals before any owner-sent SMS is created."""

    @staticmethod
    def check(turf, kind: str, cost: Decimal) -> None:
        if block := wallet.blocked_by_admin(turf, kind):
            raise ValidationError(
                {
                    "non_field_errors": [
                        wallet.DISABLED_BN
                        if block == SmsMessage.BlockReason.ACCOUNT_DISABLED
                        else "TurfBari has turned off this kind of SMS for your account."
                    ]
                }
            )
        if wallet.price_for(kind) is None:
            raise ValidationError(
                {"non_field_errors": ["SMS prices aren't set by TurfBari yet, so SMS can't be sent."]}
            )
        if wallet.wallet_for(turf).balance < cost:
            raise ValidationError(
                {"non_field_errors": [wallet.INSUFFICIENT_BN], "code": ["insufficient_balance"]}
            )


# ------------------------------------------------------------------ single SMS
class SingleSmsSerializer(serializers.Serializer):
    to = serializers.CharField(max_length=20)
    body = serializers.CharField(max_length=1000)
    confirm = serializers.BooleanField(default=False)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9-]{16,64}$", required=False)


class SingleSmsView(APIView):
    """POST without confirm=true returns the estimate; with confirm=true it charges and sends."""

    permission_classes = [IsTenantMember]
    required_permission = "view_sms"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sms_send"

    @extend_schema(tags=["workspace"], request=SingleSmsSerializer)
    def post(self, request):
        data = SingleSmsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if bd_msisdn(v["to"]) is None:
            raise ValidationError({"to": ["Enter a Bangladeshi mobile number, e.g. 01712345678."]})
        turf = request.tenant
        price = wallet.price_for(SmsKind.CUSTOM)
        segments = segment_count(v["body"])
        cost = wallet.money((price or 0) * segments)
        quote = {
            "segments": segments,
            "characters": len(v["body"]),
            "unicode": any(ord(ch) > 127 for ch in v["body"]),
            "price_per_segment": str(price) if price is not None else None,
            "estimated_cost": str(cost),
            "balance": str(wallet.wallet_for(turf).balance),
        }
        if not v["confirm"]:
            return Response(quote)
        SmsSendGate.check(turf, SmsKind.CUSTOM, cost)
        key = v.get("idempotency_key") or uuid.uuid4().hex
        message = queue_sms(
            to=v["to"],
            body=v["body"].strip(),
            kind=SmsKind.CUSTOM,
            turf=turf,
            created_by=request.user,
            dedupe_key=f"single:{turf.pk}:{key}",
        )
        message.refresh_from_db()
        record(
            "sms.single_sent",
            f"Sent an SMS to {message.masked_to}: {message.get_status_display()} (৳{message.charged_amount:.2f})",  # noqa: E501
            category=Category.SETTINGS,
            request=request,
        )
        return Response(
            quote
            | {
                "id": str(message.id),
                "status": message.status,
                "status_label": message.get_status_display(),
                "provider_message": message.provider_message,
                "charged": str(message.charged_amount),
                "balance": str(wallet.wallet_for(turf).balance),
            },
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------ campaigns
class CampaignPreviewView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], request=RecipientsSerializer)
    def post(self, request):
        data = RecipientsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        r = resolve(request.tenant, data.validated_data)
        return Response(
            estimate(request.tenant, data.validated_data["template"], r["recipients"])
            | {
                "invalid": len(r["invalid"]),
                "invalid_examples": r["invalid"][:5],
                "duplicates": r["duplicates"],
            }
        )


class CampaignCreateSerializer(RecipientsSerializer):
    name = serializers.CharField(max_length=120)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9-]{16,64}$")
    confirm = serializers.BooleanField()


def campaign_row(c: SmsCampaign) -> dict:
    stats = c.messages.aggregate(
        sent=Count("id", filter=Q(status=SmsMessage.Status.SENT)),
        failed=Count("id", filter=Q(status__in=[SmsMessage.Status.FAILED, SmsMessage.Status.UNKNOWN])),
        pending=Count("id", filter=Q(status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.SENDING])),
        blocked=Count("id", filter=Q(status__in=[SmsMessage.Status.BLOCKED, SmsMessage.Status.SKIPPED])),
        segments=Sum("segments", filter=Q(status=SmsMessage.Status.SENT)),
        cost=Sum("charged_amount"),
    )
    return {
        "id": str(c.id),
        "name": c.name,
        "template": c.template,
        "status": c.status,
        "status_label": c.get_status_display(),
        "created_at": c.created_at,
        "recipients": c.recipients_count,
        "estimated_cost": str(c.estimated_cost),
        "sent": stats["sent"],
        "failed": stats["failed"],
        "pending": stats["pending"],
        "not_sent": stats["blocked"],
        "segments": stats["segments"] or 0,
        "cost": str(wallet.money(stats["cost"] or 0)),
    }


def send_first_batch(campaign_id) -> None:
    from django.conf import settings

    ids = list(
        SmsMessage.objects.filter(campaign_id=campaign_id, status=SmsMessage.Status.QUEUED).values_list(
            "pk", flat=True
        )[: (10**6 if settings.SMS_DISPATCH == "immediate" else FIRST_BATCH)]
    )

    def send():
        for pk in ids:
            deliver(pk)

    def run_in_thread():
        try:
            send()
        finally:
            close_old_connections()  # this thread's own DB connection only

    if settings.SMS_DISPATCH == "thread":
        transaction.on_commit(lambda: threading.Thread(target=run_in_thread, daemon=True).start())
    else:
        send()


class CampaignListView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sms_send"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(tags=["workspace"])
    def get(self, request):
        qs = SmsCampaign.objects.filter(turf=request.tenant)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(name__icontains=q)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([campaign_row(c) for c in page])

    @extend_schema(tags=["workspace"], request=CampaignCreateSerializer)
    def post(self, request):
        data = CampaignCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        turf = request.tenant
        if existing := SmsCampaign.objects.filter(idempotency_key=v["idempotency_key"], turf=turf).first():
            return Response(campaign_row(existing))  # double submit: same campaign, nothing sent twice
        if not v["confirm"]:
            raise ValidationError({"confirm": ["Confirm the recipients and cost to send."]})
        r = resolve(turf, v)
        if not r["recipients"]:
            raise ValidationError({"numbers": ["There are no valid recipients."]})
        est = estimate(turf, v["template"], r["recipients"])
        SmsSendGate.check(turf, SmsKind.CAMPAIGN, Decimal(est["estimated_cost"]))
        try:
            with transaction.atomic():
                campaign = SmsCampaign.objects.create(
                    turf=turf,
                    name=v["name"],
                    template=v["template"],
                    recipients_count=est["valid"],
                    estimated_segments=est["segments"],
                    estimated_cost=Decimal(est["estimated_cost"]),
                    price_per_segment=Decimal(est["price_per_segment"]),
                    idempotency_key=v["idempotency_key"],
                    created_by=request.user,
                )
                for msisdn, values in r["recipients"].items():
                    queue_sms(
                        to=msisdn,
                        body=fill(v["template"], values),
                        kind=SmsKind.CAMPAIGN,
                        turf=turf,
                        campaign=campaign,
                        created_by=request.user,
                        dedupe_key=f"campaign:{campaign.pk}:{msisdn}",
                        auto_dispatch=False,
                    )
        except IntegrityError:
            return Response(campaign_row(SmsCampaign.objects.get(idempotency_key=v["idempotency_key"])))
        send_first_batch(campaign.pk)
        record(
            "sms.campaign_started",
            f"Started bulk SMS “{campaign.name}” to {campaign.recipients_count} customers (est. ৳{campaign.estimated_cost:.2f})",  # noqa: E501
            category=Category.SETTINGS,
            request=request,
        )
        return Response(campaign_row(campaign), status=status.HTTP_201_CREATED)


class CampaignDetailView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"])
    def get(self, request, pk):
        return Response(campaign_row(get_object_or_404(SmsCampaign, pk=pk, turf=request.tenant)))

    @extend_schema(tags=["workspace"], request=None)
    def delete(self, request, pk):
        """Cancel: anything not yet handed to BulkSMSBD is dropped and never charged."""
        campaign = get_object_or_404(SmsCampaign, pk=pk, turf=request.tenant)
        with transaction.atomic():
            campaign = SmsCampaign.objects.select_for_update().get(pk=campaign.pk)
            if campaign.status == SmsCampaign.Status.SENDING:
                campaign.status, campaign.cancelled_at = SmsCampaign.Status.CANCELLED, timezone.now()
                campaign.save(update_fields=["status", "cancelled_at", "updated_at"])
                campaign.messages.filter(
                    status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.BLOCKED, SmsMessage.Status.FAILED]
                ).update(
                    status=SmsMessage.Status.BLOCKED,
                    block_reason=SmsMessage.BlockReason.CANCELLED,
                    provider_message="Campaign cancelled",
                    next_attempt_at=None,
                    updated_at=timezone.now(),
                )
        record(
            "sms.campaign_cancelled",
            f"Cancelled bulk SMS “{campaign.name}”",
            category=Category.SETTINGS,
            request=request,
        )
        return Response(campaign_row(campaign))


def finish_campaigns() -> dict:
    """Tick step: campaigns with nothing left to send are marked completed."""
    done = 0
    for c in SmsCampaign.objects.filter(status=SmsCampaign.Status.SENDING):
        open_ = c.messages.filter(status__in=[SmsMessage.Status.QUEUED, SmsMessage.Status.SENDING]).exists()
        retrying = c.messages.filter(status=SmsMessage.Status.FAILED, next_attempt_at__isnull=False).exists()
        if not open_ and not retrying:
            SmsCampaign.objects.filter(pk=c.pk, status=SmsCampaign.Status.SENDING).update(
                status=SmsCampaign.Status.COMPLETED, updated_at=timezone.now()
            )
            done += 1
    return {"campaigns_completed": done}
