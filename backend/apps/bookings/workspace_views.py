"""Workspace API for bookings, customers, payments, maintenance, dashboard and reports."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from openpyxl import Workbook
from openpyxl.styles import Font
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import Category, booking_label, record
from apps.common.tenancy import IsTenantMember, TenantViewSet
from apps.expenses.models import Expense
from apps.turfs.models import TurfField
from apps.turfs.pricing import quote
from apps.turfs.serializers import TenantScopedPK

from . import payments
from .models import Booking, Customer, MaintenanceBlock, Payment, PaymentSubmission
from .phone import normalize_bd_phone
from .services import (
    availability,
    change_status,
    get_or_create_customer,
    opening_window,
    overlapping_bookings,
    overlapping_maintenance,
    record_payment,
    reserve_slot,
)

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))


def parse_date(value, name="date"):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({name: ["Use YYYY-MM-DD."]}) from None


def day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()), tz)
    return start, start + timedelta(days=1)


def date_range(params, default_days=30) -> tuple[date, date]:
    today = timezone.localdate()
    end = parse_date(params["to"], "to") if params.get("to") else today
    start = (
        parse_date(params["from"], "from") if params.get("from") else end - timedelta(days=default_days - 1)
    )
    if start > end:
        raise ValidationError({"from": ["Start date must be before end date."]})
    if (end - start).days > 366:
        raise ValidationError({"from": ["Choose a range of one year or less."]})
    return start, end


# ---------------------------------------------------------------- serializers
class PaymentSerializer(serializers.ModelSerializer):
    received_by_name = serializers.CharField(source="received_by.full_name", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = ["id", "amount", "kind", "method", "reference", "paid_at", "received_by_name"]
        read_only_fields = ["id", "paid_at", "received_by_name"]


class CustomerMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email"]


class BookingSerializer(serializers.ModelSerializer):
    customer = CustomerMiniSerializer(read_only=True)
    field_name = serializers.CharField(source="field.name", read_only=True)
    payment_status = serializers.CharField(read_only=True)
    due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "field",
            "field_name",
            "customer",
            "start",
            "end",
            "status",
            "status_label",
            "source",
            "source_label",
            "team_name",
            "notes",
            "subtotal",
            "discount",
            "total",
            "amount_paid",
            "due",
            "payment_status",
            "price_snapshot",
            "created_at",
            "confirmed_at",
        ]


class BookingDetailSerializer(BookingSerializer):
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + ["payments"]


class BookingWriteSerializer(serializers.Serializer):
    field = TenantScopedPK(queryset=TurfField.objects.all())
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    customer_name = serializers.CharField(max_length=120)
    customer_phone = serializers.CharField(max_length=20)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    team_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0"))
    status = serializers.ChoiceField(
        choices=[Booking.Status.CONFIRMED, Booking.Status.PENDING], default=Booking.Status.CONFIRMED
    )
    source = serializers.ChoiceField(choices=Booking.Source.choices, default=Booking.Source.STAFF)
    advance_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    advance_method = serializers.ChoiceField(choices=Payment.Method.choices, default=Payment.Method.CASH)


class StatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Booking.Status.choices)


# ---------------------------------------------------------------- bookings
class BookingViewSet(TenantViewSet):
    queryset = Booking.objects.select_related("customer", "field")
    audit_auto = False  # bookings write their own, richer events
    http_method_names = ["get", "post", "put", "head", "options"]
    filter_backends = []

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BookingDetailSerializer
        return BookingSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if self.action == "retrieve":
            return qs.prefetch_related("payments__received_by")
        if params.get("date"):
            start, end = day_bounds(parse_date(params["date"]))
            qs = qs.filter(start__lt=end, end__gt=start)
        if params.get("from"):
            qs = qs.filter(start__gte=day_bounds(parse_date(params["from"], "from"))[0])
        if params.get("to"):
            qs = qs.filter(start__lt=day_bounds(parse_date(params["to"], "to"))[1])
        if status := params.get("status"):
            qs = qs.filter(status__in=status.split(","))
        if field := params.get("field"):
            qs = qs.filter(field_id=field)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(reference__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__phone__icontains=q)
                | Q(team_name__icontains=q)
            )
        if params.get("ordering") == "start":
            qs = qs.order_by("start")
        return qs

    @extend_schema(request=BookingWriteSerializer, responses=BookingDetailSerializer)
    def create(self, request, *args, **kwargs):
        data = BookingWriteSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        turf = request.tenant
        customer = get_or_create_customer(
            turf, name=v["customer_name"], phone=v["customer_phone"], email=v.get("customer_email", "")
        )
        booking = reserve_slot(
            turf=turf,
            field_id=v["field"].id,
            start=v["start"],
            end=v["end"],
            customer=customer,
            status=v["status"],
            source=v["source"],
            team_name=v.get("team_name", ""),
            notes=v.get("notes", ""),
            discount=v["discount"],
            created_by=request.user,
        )
        if v["advance_amount"] and v["advance_amount"] > 0:
            if v["advance_amount"] > booking.total:
                raise ValidationError({"advance_amount": ["Advance cannot exceed the booking total."]})
            record_payment(
                booking,
                amount=v["advance_amount"],
                method=v["advance_method"],
                kind=Payment.Kind.PAYMENT,
                user=request.user,
            )
        extra = f", advance ৳{v['advance_amount']}" if v["advance_amount"] else ""
        discount = f", discount ৳{booking.discount}" if booking.discount else ""
        record(
            "booking.created",
            f"Booked {booking_label(booking)} — ৳{booking.total}{discount}{extra}",
            category=Category.BOOKING,
            request=request,
            target=booking,
            data={"status": booking.status, "total": str(booking.total), "discount": str(booking.discount)},
        )
        return Response(BookingDetailSerializer(self.get_queryset().get(pk=booking.pk)).data, status=201)

    @extend_schema(request=BookingWriteSerializer, responses=BookingDetailSerializer)
    def update(self, request, *args, **kwargs):
        booking = self.get_object()
        if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            raise ValidationError({"status": ["Only pending or confirmed bookings can be changed."]})
        data = BookingWriteSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        customer = get_or_create_customer(
            request.tenant,
            name=v["customer_name"],
            phone=v["customer_phone"],
            email=v.get("customer_email", ""),
        )
        reserve_slot(
            turf=request.tenant,
            field_id=v["field"].id,
            start=v["start"],
            end=v["end"],
            customer=customer,
            team_name=v.get("team_name", ""),
            notes=v.get("notes", ""),
            discount=v["discount"],
            booking=booking,
        )
        booking.refresh_from_db()
        record(
            "booking.updated",
            f"Changed booking {booking_label(booking)}",
            category=Category.BOOKING,
            request=request,
            target=booking,
        )
        return Response(BookingDetailSerializer(self.get_queryset().get(pk=booking.pk)).data)

    @extend_schema(request=StatusSerializer, responses=BookingDetailSerializer)
    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        data = StatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        before = self.get_object()
        old_status = before.get_status_display()
        target = data.validated_data["status"]
        submission = PaymentSubmission.objects.filter(
            booking=before, status__in=[PaymentSubmission.Status.PENDING, PaymentSubmission.Status.EXPIRED]
        ).first()
        if submission and target in (Booking.Status.CONFIRMED, Booking.Status.REJECTED):
            # Online bookings with a bKash submission are confirmed/rejected only through verification.
            if not request.membership.can("approve_payments"):
                raise PermissionDenied("Your turf owner hasn't allowed you to approve or reject payments.")
            if target == Booking.Status.CONFIRMED:
                booking = payments.approve(submission, user=request.user)
            else:
                booking = payments.reject(submission, user=request.user)
        else:
            booking = change_status(before, target)
            if submission and booking.status == Booking.Status.CANCELLED:
                submission.status = PaymentSubmission.Status.REJECTED
                submission.rejection_reason = "Booking cancelled by the turf"
                submission.reviewed_by, submission.reviewed_at = request.user, timezone.now()
                submission.save(
                    update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"]
                )
            payments.notify_cancelled(booking, before.status)
        record(
            "booking.status",
            f"{old_status} → {booking.get_status_display()}: {booking_label(booking)}",
            category=Category.BOOKING,
            request=request,
            target=booking,
            data={"from": old_status, "to": booking.status},
        )
        return Response(BookingDetailSerializer(self.get_queryset().get(pk=booking.pk)).data)

    @extend_schema(request=PaymentSerializer, responses=BookingDetailSerializer)
    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        booking = self.get_object()
        data = PaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("kind", Payment.Kind.PAYMENT) == Payment.Kind.PAYMENT and v["amount"] > booking.due:
            raise ValidationError({"amount": [f"Only ৳{booking.due} is due on this booking."]})
        record_payment(
            booking,
            amount=v["amount"],
            method=v.get("method", Payment.Method.CASH),
            kind=v.get("kind", Payment.Kind.PAYMENT),
            reference=v.get("reference", ""),
            user=request.user,
        )
        kind = v.get("kind", Payment.Kind.PAYMENT)
        verb = "Refunded" if kind == Payment.Kind.REFUND else "Received"
        record(
            "payment.recorded",
            f"{verb} ৳{v['amount']} ({v.get('method', Payment.Method.CASH)}) for {booking_label(booking)}",
            category=Category.PAYMENT,
            request=request,
            target=booking,
            data={"amount": str(v["amount"]), "kind": kind, "method": v.get("method", "cash")},
        )
        return Response(BookingDetailSerializer(self.get_queryset().get(pk=booking.pk)).data, status=201)


class AvailabilityView(APIView):
    permission_classes = [IsTenantMember]

    @extend_schema(tags=["workspace"])
    def get(self, request):
        day = parse_date(request.query_params.get("date") or timezone.localdate().isoformat())
        fields = TurfField.objects.filter(turf=request.tenant, is_active=True).select_related("turf")
        if field_id := request.query_params.get("field"):
            fields = fields.filter(pk=field_id)
        detail = request.query_params.get("detail") == "1"
        return Response(
            {
                "date": day.isoformat(),
                "fields": [
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "size": f.size,
                        "slots": slot_board(f, day) if detail else availability(f, day),
                    }
                    for f in fields
                ],
            }
        )


def slot_board(field, day):
    """Availability plus what occupies each taken slot, for the owner's booking board."""
    slots = availability(field, day)
    window = opening_window(field.turf, day)
    if not slots or window is None:
        return slots
    opens, closes = window
    bookings = list(
        overlapping_bookings(field.id, opens, closes).select_related("customer").order_by("start")
    )
    blocks = list(overlapping_maintenance(field.id, opens, closes))
    now = timezone.now()
    for slot in slots:
        start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
        booking = next((b for b in bookings if b.start < end and b.end > start), None)
        block = None if booking else next((m for m in blocks if m.start < end and m.end > start), None)
        if booking:
            slot["state"] = "pending" if booking.status == Booking.Status.PENDING else "booked"
            slot["booking"] = {
                "id": str(booking.id),
                "reference": booking.reference,
                "status": booking.status,
                "customer_name": booking.customer.name,
                "customer_phone": booking.customer.phone,
                "team_name": booking.team_name,
                "start": timezone.localtime(booking.start).isoformat(),
                "end": timezone.localtime(booking.end).isoformat(),
                "total": str(booking.total),
                "amount_paid": str(booking.amount_paid),
            }
        elif block:
            slot["state"] = "maintenance"
            slot["reason"] = block.reason
        elif start <= now:
            slot["state"] = "past"
        else:
            slot["state"] = "free"
    return slots


class QuoteSerializer(serializers.Serializer):
    field = TenantScopedPK(queryset=TurfField.objects.all())
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    exclude = serializers.UUIDField(required=False)


class QuoteView(APIView):
    permission_classes = [IsTenantMember]

    @extend_schema(request=QuoteSerializer, tags=["workspace"])
    def post(self, request):
        data = QuoteSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v["end"] <= v["start"]:
            raise ValidationError({"end": ["End must be after start."]})
        q = quote(v["field"], v["start"], v["end"])
        clash = overlapping_bookings(
            v["field"].id, v["start"], v["end"], exclude_id=v.get("exclude")
        ).exists()
        return Response({"subtotal": str(q.subtotal), "segments": q.segments, "available": not clash})


# ---------------------------------------------------------------- customers
class CustomerSerializer(serializers.ModelSerializer):
    bookings_count = serializers.IntegerField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    last_booking = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "notes",
            "bookings_count",
            "total_paid",
            "last_booking",
            "created_at",
        ]

    def validate_phone(self, value):
        phone = normalize_bd_phone(value)
        request = self.context["request"]
        qs = Customer.objects.filter(turf=request.tenant, phone=phone)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A customer with this phone number already exists.")
        return phone


class CustomerViewSet(TenantViewSet):
    audit_noun = "customer"
    audit_category = Category.CUSTOMER
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = []

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .annotate(
                bookings_count=Count("bookings", distinct=True),
                total_paid=Coalesce(Sum("bookings__amount_paid"), ZERO),
                last_booking=Max("bookings__start"),
            )
        )
        if q := self.request.query_params.get("q", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q))
        return (
            qs.order_by("-last_booking", "name") if self.request.query_params.get("sort") == "recent" else qs
        )


# ---------------------------------------------------------------- maintenance
class MaintenanceSerializer(serializers.ModelSerializer):
    field = TenantScopedPK(queryset=TurfField.objects.all())
    field_name = serializers.CharField(source="field.name", read_only=True)

    class Meta:
        model = MaintenanceBlock
        fields = ["id", "field", "field_name", "start", "end", "reason"]

    def validate(self, attrs):
        start, end = attrs.get("start"), attrs.get("end")
        if start and end and end <= start:
            raise serializers.ValidationError({"end": ["End must be after start."]})
        if overlapping_bookings(attrs["field"].id, start, end).exists():
            raise serializers.ValidationError(
                {"start": ["There are active bookings in this window. Move or cancel them first."]}
            )
        return attrs


class MaintenanceViewSet(TenantViewSet):
    audit_noun = "maintenance block"
    queryset = MaintenanceBlock.objects.select_related("field")
    serializer_class = MaintenanceSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    filter_backends = []

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("upcoming") == "1":
            qs = qs.filter(end__gte=timezone.now()).order_by("start")
        return qs


# ---------------------------------------------------------------- dashboard
def daily_net_payments(turf, start: datetime, end: datetime) -> dict[date, Decimal]:
    """Net collections per Dhaka calendar day. Grouped in Python because MySQL/MariaDB
    installs without timezone tables (e.g. XAMPP) return NULL for CONVERT_TZ."""
    totals: dict[date, Decimal] = {}
    rows = Payment.objects.filter(turf=turf, paid_at__gte=start, paid_at__lt=end).values_list(
        "paid_at", "kind", "amount"
    )
    for paid_at, kind, amount in rows:
        day = timezone.localtime(paid_at).date()
        totals[day] = totals.get(day, Decimal("0")) + (amount if kind == Payment.Kind.PAYMENT else -amount)
    return totals


def revenue_between(turf, start: datetime, end: datetime) -> Decimal:
    rows = Payment.objects.filter(turf=turf, paid_at__gte=start, paid_at__lt=end)
    paid = rows.filter(kind=Payment.Kind.PAYMENT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    refunded = rows.filter(kind=Payment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    return paid - refunded


class DashboardView(APIView):
    permission_classes = [IsTenantMember]

    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        today = timezone.localdate()
        t0, t1 = day_bounds(today)
        m0 = day_bounds(today.replace(day=1))[0]
        active = Booking.objects.filter(turf=turf).exclude(
            status__in=[Booking.Status.CANCELLED, Booking.Status.REJECTED, Booking.Status.EXPIRED]
        )
        today_bookings = active.filter(start__gte=t0, start__lt=t1)
        upcoming = (
            active.filter(
                start__gte=timezone.now(), status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING]
            )
            .select_related("customer", "field")
            .order_by("start")[:6]
        )
        series_start = today - timedelta(days=13)
        by_day = daily_net_payments(turf, day_bounds(series_start)[0], t1)
        series = [
            {
                "date": (series_start + timedelta(days=i)).isoformat(),
                "revenue": str(by_day.get(series_start + timedelta(days=i), Decimal("0"))),
            }
            for i in range(14)
        ]
        is_owner = request.membership.role == "owner"
        month_expenses = Expense.objects.filter(turf=turf, spent_on__gte=today.replace(day=1)).aggregate(
            s=Sum("amount")
        )["s"] or Decimal("0")
        month_revenue = revenue_between(turf, m0, t1)
        outstanding = active.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED]
        ).aggregate(s=Sum("total"), p=Sum("amount_paid"))
        return Response(
            {
                "turf": {
                    "name": turf.name,
                    "slug": turf.slug,
                    "status": turf.status,
                    "is_listed": turf.is_listed,
                },
                "role": request.membership.role,
                "today": {
                    "bookings": today_bookings.count(),
                    "hours_booked": round(
                        sum((b.end - b.start).total_seconds() for b in today_bookings) / 3600, 1
                    ),
                    "revenue": str(revenue_between(turf, t0, t1)),
                },
                "pending_requests": Booking.objects.awaiting_review()
                .filter(turf=turf, payment_submission__isnull=False)
                .count(),
                "month": {
                    "bookings": active.filter(start__gte=m0, start__lt=t1).count(),
                    "revenue": str(month_revenue),
                    "expenses": str(month_expenses) if is_owner else None,
                    "net": str(month_revenue - month_expenses) if is_owner else None,
                },
                "outstanding_due": str((outstanding["s"] or 0) - (outstanding["p"] or 0)),
                "customers": Customer.objects.filter(turf=turf).count(),
                "upcoming": BookingSerializer(upcoming, many=True).data,
                "revenue_series": series,
            }
        )


# ---------------------------------------------------------------- reports
class ReportSummaryView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"])
    def get(self, request):
        turf = request.tenant
        start_day, end_day = date_range(request.query_params)
        start, end = day_bounds(start_day)[0], day_bounds(end_day)[1]
        bookings = Booking.objects.filter(turf=turf, start__gte=start, start__lt=end)
        by_status = dict(bookings.values_list("status").annotate(c=Count("id")))
        active = bookings.exclude(status__in=[Booking.Status.CANCELLED, Booking.Status.REJECTED])
        by_field = [
            {"field": r["field__name"], "bookings": r["c"], "billed": str(r["t"] or 0), "hours": 0}
            for r in active.values("field__name")
            .annotate(c=Count("id"), t=Sum("total"))
            .order_by("field__name")
        ]
        # hours per field computed in Python (portable across MySQL/MariaDB)
        hours = {}
        for b in active.select_related("field").only("start", "end", "field__name"):
            hours[b.field.name] = hours.get(b.field.name, 0) + (b.end - b.start).total_seconds() / 3600
        for row in by_field:
            row["hours"] = round(hours.get(row["field"], 0), 1)

        revenue = revenue_between(turf, start, end)
        expenses_qs = Expense.objects.filter(turf=turf, spent_on__gte=start_day, spent_on__lte=end_day)
        expenses_total = expenses_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        by_category = [
            {"category": r["category"], "total": str(r["t"])}
            for r in expenses_qs.values("category").annotate(t=Sum("amount")).order_by("-t")
        ]
        by_method = [
            {"method": r["method"], "total": str(r["t"])}
            for r in Payment.objects.filter(
                turf=turf, paid_at__gte=start, paid_at__lt=end, kind=Payment.Kind.PAYMENT
            )
            .values("method")
            .annotate(t=Sum("amount"))
            .order_by("-t")
        ]
        daily = daily_net_payments(turf, start, end)
        span = (end_day - start_day).days + 1
        return Response(
            {
                "from": start_day.isoformat(),
                "to": end_day.isoformat(),
                "revenue": str(revenue),
                "billed": str(active.aggregate(s=Sum("total"))["s"] or Decimal("0")),
                "expenses": str(expenses_total),
                "net": str(revenue - expenses_total),
                "bookings": active.count(),
                "by_status": by_status,
                "by_field": by_field,
                "by_method": by_method,
                "expenses_by_category": by_category,
                "daily": [
                    {
                        "date": (start_day + timedelta(days=i)).isoformat(),
                        "revenue": str(daily.get(start_day + timedelta(days=i), Decimal("0"))),
                    }
                    for i in range(span)
                ],
            }
        )


class BookingsExportView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], responses={200: bytes})
    def get(self, request):
        start_day, end_day = date_range(request.query_params)
        start, end = day_bounds(start_day)[0], day_bounds(end_day)[1]
        rows = (
            Booking.objects.filter(turf=request.tenant, start__gte=start, start__lt=end)
            .select_related("customer", "field")
            .order_by("start")
        )
        wb = Workbook()
        ws = wb.active
        ws.title = "Bookings"
        header = [
            "Reference",
            "Date",
            "Start",
            "End",
            "Field",
            "Customer",
            "Phone",
            "Team",
            "Status",
            "Source",
            "Subtotal",
            "Discount",
            "Total",
            "Paid",
            "Due",
        ]
        ws.append(header)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for b in rows:
            s, e = timezone.localtime(b.start), timezone.localtime(b.end)
            ws.append(
                [
                    b.reference,
                    s.date(),
                    s.strftime("%H:%M"),
                    e.strftime("%H:%M"),
                    b.field.name,
                    b.customer.name,
                    b.customer.phone,
                    b.team_name,
                    b.get_status_display(),
                    b.get_source_display(),
                    b.subtotal,
                    b.discount,
                    b.total,
                    b.amount_paid,
                    b.due,
                ]
            )
        for col, width in zip(
            "ABCDEFGHIJKLMNO", [16, 12, 8, 8, 14, 22, 16, 18, 12, 14, 11, 10, 11, 11, 11], strict=True
        ):
            ws.column_dimensions[col].width = width
        buffer = BytesIO()
        wb.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="bookings-{request.tenant.slug}-{start_day}-to-{end_day}.xlsx"'
        )
        return response
