# ruff: noqa: E501
"""Turf registration with plan choice, promo code and a bKash payment that TurfBari verifies by hand.

Flow: quote (server-calculated price) → submit (application + promo reservation + payment request,
status "payment under review") → admin approves (account, plan invoice paid with the discount, promo
redeemed, login details SMS) or rejects (reason shown on the status page; resubmission allowed or not).

Nothing is activated by a submitted Transaction ID: approval is a person checking the bKash account.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.audit.services import Category, record
from apps.bookings.payments import normalize_trx_id
from apps.bookings.phone import normalize_bd_phone
from apps.common.money import to_money
from apps.subscriptions import promos
from apps.subscriptions.models import (
    Invoice,
    PaymentTransaction,
    Plan,
    PromoCode,
    PromoRedemption,
    Subscription,
)

from .models import RegistrationPayment, TurfApplication, new_registration_reference

PAY = RegistrationPayment.Status


# ------------------------------------------------------------------ settings & price
def receiving() -> dict:
    """TurfBari's bKash receiving details (Admin → API → Payments; env fallback)."""
    from apps.common.models import PlatformSettings
    from apps.subscriptions.views import payment_accounts

    s = PlatformSettings.load()
    return {
        "number": payment_accounts().get("bkash", ""),
        "account_type": s.subscription_bkash_account_type or "Personal",
        "instructions": s.subscription_instructions,
    }


def payments_open() -> bool:
    return bool(receiving()["number"])


def plans() -> list[dict]:
    return [
        {
            "id": str(p.pk),
            "period": p.period,
            "name": p.name,
            "months": p.months,
            "price": str(p.price),
            "description": p.description,
            "features": p.features,
            "limits": p.limits,
            "featured": p.featured,
        }
        for p in Plan.objects.filter(is_active=True, is_public=True).order_by("display_order", "months")
    ]


def _plan(value) -> Plan:
    from django.core.exceptions import ValidationError as DjangoValidationError

    plan = Plan.objects.filter(is_active=True, is_public=True, period=value).first() if value else None
    if plan is None and value:
        try:
            plan = Plan.objects.filter(is_active=True, is_public=True, pk=value).first()
        except (ValueError, DjangoValidationError):
            plan = None
    if plan is None:
        raise ValidationError({"plan": ["Choose a plan."]})
    return plan


def quote(
    plan: Plan, code: str = "", *, phone: str = "", email: str = "", lock=False, exclude_redemption=None
) -> dict:
    """Server-side price. Raises a ValidationError with promo_code/promo_error if the code can't be used."""
    base = to_money(plan.price)
    promo = None
    discount = Decimal("0.00")
    if promos.normalize_code(code):
        promo = promos.check(
            code,
            plan=plan,
            price=base,
            phone=phone,
            email=email,
            registration=True,
            lock=lock,
            exclude_redemption=exclude_redemption,
        )
        discount = promos.discount_for(promo, base)
    return {
        "plan": {"id": str(plan.pk), "period": plan.period, "name": plan.name, "months": plan.months},
        "original": str(base),
        "discount": str(discount),
        "payable": str(base - discount),
        "promo": promo_snapshot(promo, base, discount) if promo else None,
        "_promo": promo,
    }


def promo_snapshot(promo: PromoCode, base: Decimal, discount: Decimal) -> dict:
    return {
        "id": str(promo.pk),
        "code": promo.code,
        "discount_type": promo.discount_type,
        "percent_off": promo.percent_off,
        "amount_off": str(promo.amount_off),
        "max_discount": str(promo.max_discount) if promo.max_discount else None,
        "label": promo.label,
        "discount": str(discount),
        "original": str(base),
        "final": str(base - discount),
        "applied_at": timezone.now().isoformat(),
    }


def public_quote(data: dict) -> dict:
    plan = _plan(data.get("plan"))
    phone = _phone(data.get("phone"), required=False)
    email = (data.get("email") or "").strip().lower()
    if promos.normalize_code(data.get("promo_code", "")) and _existing_account(phone, email):
        promo = PromoCode.objects.filter(code=promos.normalize_code(data["promo_code"])).first()
        if promo and promo.new_registrations_only:
            raise promos.reject("new_only")
    q = quote(plan, data.get("promo_code", ""), phone=phone, email=email)
    q.pop("_promo")
    return q | {"receiving": receiving()}


# ------------------------------------------------------------------ helpers
def _phone(value, *, required=True) -> str:
    if not value:
        if required:
            raise ValidationError({"phone": ["Enter your mobile number."]})
        return ""
    try:
        return normalize_bd_phone(value)
    except ValidationError:
        if required:
            raise
        return ""


def _existing_account(phone: str, email: str) -> bool:
    User = get_user_model()
    digits = phone[-10:] if phone else ""
    return User.objects.filter(
        Q(email__iexact=email) | (Q(phone__endswith=digits) if digits else Q(pk=None))
    ).exists()


def _trx_taken(trx: str) -> bool:
    from apps.bookings.models import PaymentSubmission
    from apps.notifications.models import SmsRechargeRequest

    return (
        RegistrationPayment.objects.filter(trx_id=trx).exists()
        or PaymentTransaction.objects.filter(reference__iexact=trx).exists()
        or SmsRechargeRequest.objects.filter(trx_id=trx).exists()
        or PaymentSubmission.objects.filter(trx_id=trx).exists()
    )


def _payment_fields(data: dict, amount_due: Decimal) -> dict:
    """Validated bKash details; the amount must be exactly the server-calculated payable amount."""
    if amount_due <= 0:
        return {"sender_number": "", "amount_sent": Decimal("0.00"), "trx_id": None, "method": "promo"}
    errors = {}
    try:
        sender = "0" + normalize_bd_phone(data.get("sender_number") or "")[4:]
    except ValidationError:
        errors["sender_number"] = ["Enter the bKash number you paid from, e.g. 01712345678."]
        sender = ""
    try:
        amount = to_money(Decimal(str(data.get("amount_sent") or "0")))
    except (ArithmeticError, ValueError):
        amount = Decimal("-1")
    if amount != amount_due:
        errors["amount_sent"] = [f"Send exactly ৳{amount_due:,.2f} — the amount after the discount."]
    try:
        trx = normalize_trx_id(data.get("trx_id") or "")
    except ValidationError:
        errors["trx_id"] = ["Enter the bKash Transaction ID exactly as in the bKash SMS (e.g. 9C7A6B5D4E)."]
        trx = ""
    if trx and _trx_taken(trx):
        errors["trx_id"] = ["This Transaction ID was already submitted."]
    if errors:
        raise ValidationError(errors)
    return {"sender_number": sender, "amount_sent": amount, "trx_id": trx, "method": "bkash"}


def _reserve(promo: PromoCode | None, application, phone, email, discount) -> PromoRedemption | None:
    if promo is None:
        return None
    return PromoRedemption.objects.create(
        promo=promo,
        application=application,
        phone=phone,
        email=email,
        discount=discount,
        reserved_until=timezone.now() + timedelta(hours=max(1, promo.reservation_hours)),
    )


def _new_payment(application, plan, q, promo, redemption, pay, note) -> RegistrationPayment:
    r = receiving()
    return RegistrationPayment.objects.create(
        application=application,
        plan=plan,
        list_price=Decimal(q["original"]),
        discount=Decimal(q["discount"]),
        amount_due=Decimal(q["payable"]),
        promo=promo,
        promo_snapshot=q["promo"] or {},
        redemption=redemption,
        note=(note or "")[:255],
        receiving_number=r["number"],
        instructions=r["instructions"],
        **pay,
    )


# ------------------------------------------------------------------ submit (called inside the application view)
def start(application: TurfApplication, data: dict, *, request=None) -> RegistrationPayment:
    """Attach plan + promo reservation + payment request to a just-created application (same transaction)."""
    plan = _plan(data.get("plan"))
    phone, email = application.phone, application.email.lower()
    pending = (
        TurfApplication.objects.filter(status=TurfApplication.Status.PAYMENT_REVIEW)
        .filter(Q(phone=phone) | Q(email__iexact=email))
        .exclude(pk=application.pk)
        .first()
    )
    if pending:
        raise ValidationError(
            {
                "email": [
                    f"A registration with this phone or email is already awaiting verification ({pending.reference})."
                ]
            }
        )
    code = data.get("promo_code", "")
    if promos.normalize_code(code) and _existing_account(phone, email):
        promo = PromoCode.objects.filter(code=promos.normalize_code(code)).first()
        if promo and promo.new_registrations_only:
            raise promos.reject("new_only")
    q = quote(plan, code, phone=phone, email=email, lock=True)  # locks the promo row: no over-use
    promo = q["_promo"]
    if data.get("expected_payable") not in (None, "") and to_money(
        Decimal(str(data["expected_payable"]))
    ) != Decimal(q["payable"]):
        raise ValidationError(
            {
                "promo_code": ["The price changed — please check the payment summary again."],
                "code": ["price_changed"],
            }
        )
    pay = _payment_fields(data, Decimal(q["payable"]))
    application.reference = new_registration_reference()
    while TurfApplication.objects.filter(reference=application.reference).exists():
        application.reference = new_registration_reference()
    application.plan = plan
    application.status = TurfApplication.Status.PAYMENT_REVIEW
    application.save(update_fields=["reference", "plan", "status", "updated_at"])
    redemption = _reserve(promo, application, phone, email, Decimal(q["discount"]))
    payment = _new_payment(application, plan, q, promo, redemption, pay, data.get("payment_note"))
    record(
        "registration.payment_submitted",
        f"Registration {application.reference} ({application.turf_name}): {plan.name} ৳{payment.amount_due}"
        + (f" after {promo.code} (−৳{payment.discount})" if promo else "")
        + (f", bKash TrxID {payment.trx_id}" if payment.trx_id else ", nothing to pay (100% off)"),
        category=Category.PLATFORM,
        request=request,
        target=application,
    )
    return payment


def _lookup(reference: str, phone: str) -> TurfApplication:
    try:
        phone = normalize_bd_phone(phone or "")
    except ValidationError:
        raise NotFound("No registration matches this reference and mobile number.") from None
    app = TurfApplication.objects.filter(reference=(reference or "").strip().upper(), phone=phone).first()
    if app is None:
        raise NotFound("No registration matches this reference and mobile number.")
    return app


def mask_trx(trx: str | None) -> str:
    return f"{trx[:3]}•••{trx[-2:]}" if trx and len(trx) > 5 else (trx or "")


def status_payload(app: TurfApplication) -> dict:
    latest = app.payments.order_by("-created_at").first()
    history = [
        {
            "submitted_at": p.created_at,
            "amount_sent": str(p.amount_sent),
            "trx": mask_trx(p.trx_id),
            "status": p.status,
            "status_label": p.get_status_display(),
            "rejection_reason": p.rejection_reason,
        }
        for p in app.payments.order_by("-created_at")
    ]
    return {
        "reference": app.reference,
        "turf_name": app.turf_name,
        "status": app.status,
        "status_label": app.get_status_display(),
        "plan": app.plan.name if app.plan_id else None,
        "promo_code": (latest.promo_snapshot or {}).get("code") if latest else None,
        "original": str(latest.list_price) if latest else None,
        "discount": str(latest.discount) if latest else None,
        "payable": str(latest.amount_due) if latest else None,
        "amount_sent": str(latest.amount_sent) if latest else None,
        "trx": mask_trx(latest.trx_id) if latest else "",
        "submitted_at": latest.created_at if latest else app.created_at,
        "rejection_reason": latest.rejection_reason if latest and latest.status == PAY.REJECTED else "",
        "can_resubmit": bool(
            latest
            and latest.status == PAY.REJECTED
            and latest.can_resubmit
            and app.status == TurfApplication.Status.PAYMENT_REJECTED
        ),
        "receiving": receiving(),
        "history": history,
    }


def lookup(reference: str, phone: str) -> dict:
    return status_payload(_lookup(reference, phone))


@transaction.atomic
def resubmit(data: dict, *, request=None) -> dict:
    app = _lookup(data.get("reference"), data.get("phone"))
    app = TurfApplication.objects.select_for_update().get(pk=app.pk)
    latest = app.payments.order_by("-created_at").first()
    if not (app.status == TurfApplication.Status.PAYMENT_REJECTED and latest and latest.can_resubmit):
        raise ValidationError({"reference": ["This registration can't take a new payment right now."]})
    held = (
        latest.redemption
        if latest.redemption and latest.redemption.status == PromoRedemption.Status.RESERVED
        else None
    )
    code = data.get("promo_code", (latest.promo_snapshot or {}).get("code", ""))
    q = quote(app.plan, code or "", phone=app.phone, email=app.email, lock=True, exclude_redemption=held)
    promo = q["_promo"]
    pay = _payment_fields(data, Decimal(q["payable"]))
    if held and (promo is None or held.promo_id != promo.pk):
        held.status, held.finished_at = PromoRedemption.Status.RELEASED, timezone.now()
        held.save(update_fields=["status", "finished_at", "updated_at"])
        held = None
    redemption = held or _reserve(promo, app, app.phone, app.email, Decimal(q["discount"]))
    if redemption and held:
        redemption.reserved_until = max(
            redemption.reserved_until, timezone.now() + timedelta(hours=promo.reservation_hours)
        )
        redemption.save(update_fields=["reserved_until", "updated_at"])
    _new_payment(app, app.plan, q, promo, redemption, pay, data.get("payment_note"))
    app.status = TurfApplication.Status.PAYMENT_REVIEW
    app.save(update_fields=["status", "updated_at"])
    record(
        "registration.payment_resubmitted",
        f"Registration {app.reference}: corrected payment submitted (৳{q['payable']})",
        category=Category.PLATFORM,
        request=request,
        target=app,
    )
    return status_payload(app)


# ------------------------------------------------------------------ admin decisions
@transaction.atomic
def approve(payment: RegistrationPayment, *, admin, note: str = "", request=None) -> dict:
    """Verified in the bKash account: create the owner account + turf, the paid plan (with the discount),
    redeem the promo and send the login details. Idempotent: approving twice changes nothing."""
    from apps.accounts import credentials
    from apps.accounts.models import TemporaryCredential
    from apps.subscriptions.services import mark_paid

    from .services import approve_application

    payment = (
        RegistrationPayment.objects.select_for_update()
        .select_related("application", "plan")
        .get(pk=payment.pk)
    )
    if payment.status == PAY.APPROVED:
        return {"payment": payment, "duplicate": True, "delivery": None}
    if payment.status != PAY.PENDING_VERIFICATION:
        raise ValidationError({"status": ["Only payments awaiting verification can be approved."]})
    app = payment.application
    result = approve_application(app, reviewer=admin, plan=payment.plan, payment_received=False)
    turf = result["turf"]
    invoice = (
        Invoice.objects.select_for_update()
        .filter(turf=turf, status=Invoice.Status.UNPAID)
        .latest("created_at")
    )
    promo = PromoCode.objects.filter(pk=payment.promo_id).first() if payment.promo_id else None
    invoice.discount, invoice.amount, invoice.promo_code = payment.discount, payment.amount_due, promo
    invoice.save(update_fields=["discount", "amount", "promo_code", "updated_at"])
    Subscription.objects.filter(pk=invoice.subscription_id).update(price=payment.amount_due)
    PaymentTransaction.objects.create(
        invoice=invoice,
        method=PaymentTransaction.Method.BKASH if payment.trx_id else PaymentTransaction.Method.PROMO,
        channel=PaymentTransaction.Channel.MANUAL if payment.trx_id else PaymentTransaction.Channel.PROMO,
        amount=payment.amount_sent,
        status=PaymentTransaction.Status.VERIFIED,
        reference=payment.trx_id or (payment.promo_snapshot or {}).get("code", ""),
        sender_number=payment.sender_number,
        reviewed_by=admin,
        reviewed_at=timezone.now(),
        note=f"Registration {app.reference}" + (f" — {note}" if note else ""),
    )
    mark_paid(invoice)
    if payment.redemption_id:
        PromoRedemption.objects.filter(pk=payment.redemption_id).update(
            status=PromoRedemption.Status.REDEEMED,
            finished_at=timezone.now(),
            invoice=invoice,
            updated_at=timezone.now(),
        )
    payment.status, payment.reviewed_by, payment.reviewed_at = PAY.APPROVED, admin, timezone.now()
    payment.review_note = (note or "")[:255]
    payment.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    delivery = None
    if result["temporary_password"]:
        delivery = credentials.start_delivery(
            result["owner"],
            result["temporary_password"],
            purpose=TemporaryCredential.Purpose.ACCOUNT_CREATED,
            by=admin,
            request=request,
        )
    record(
        "registration.payment_approved",
        f"Approved registration {app.reference}: ৳{payment.amount_sent} bKash {payment.trx_id or '(100% promo)'} verified; "
        f"{payment.plan.name} plan active for {turf.name}",
        category=Category.PLATFORM,
        request=request,
        turf=turf,
        target=app,
        data={"note": note},
    )
    return {"payment": payment, "duplicate": False, "delivery": delivery, "turf": turf}


@transaction.atomic
def reject(payment: RegistrationPayment, *, admin, reason: str, allow_resubmit: bool = True, request=None):
    payment = RegistrationPayment.objects.select_for_update().select_related("application").get(pk=payment.pk)
    if payment.status != PAY.PENDING_VERIFICATION:
        raise ValidationError({"status": ["Only payments awaiting verification can be rejected."]})
    if not (reason or "").strip():
        raise ValidationError({"reason": ["Tell the applicant why (they see this message)."]})
    now = timezone.now()
    payment.status, payment.reviewed_by, payment.reviewed_at = PAY.REJECTED, admin, now
    payment.rejection_reason, payment.can_resubmit = reason.strip()[:255], allow_resubmit
    payment.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "can_resubmit",
            "updated_at",
        ]
    )
    app = payment.application
    app.status = (
        TurfApplication.Status.PAYMENT_REJECTED if allow_resubmit else TurfApplication.Status.REJECTED
    )
    app.reviewed_by, app.reviewed_at = admin, now
    app.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    if payment.redemption_id and not allow_resubmit:
        PromoRedemption.objects.filter(
            pk=payment.redemption_id, status=PromoRedemption.Status.RESERVED
        ).update(status=PromoRedemption.Status.RELEASED, finished_at=now, updated_at=now)
    record(
        "registration.payment_rejected",
        f"Rejected payment for registration {app.reference}: {reason.strip()[:120]}"
        + (" (applicant may resubmit)" if allow_resubmit else " (registration closed)"),
        category=Category.PLATFORM,
        request=request,
        target=app,
    )
    return payment


def expire_reservations(now=None) -> dict:
    """Tick step: held promo codes whose time ran out — and that have no payment under review — are freed."""
    now = now or timezone.now()
    due = PromoRedemption.objects.filter(
        status=PromoRedemption.Status.RESERVED, reserved_until__lte=now
    ).exclude(application__status=TurfApplication.Status.PAYMENT_REVIEW)
    n = due.update(status=PromoRedemption.Status.EXPIRED, finished_at=now, updated_at=now)
    return {"expired_promo_reservations": n}


# ------------------------------------------------------------------ reports
def report() -> dict:
    qs = RegistrationPayment.objects.all()
    approved = qs.filter(status=PAY.APPROVED)
    agg = approved.aggregate(original=Sum("list_price"), discount=Sum("discount"), revenue=Sum("amount_sent"))
    apps_with_payment = TurfApplication.objects.filter(payments__isnull=False).distinct()
    by_promo = (
        approved.exclude(promo_snapshot={})
        .values("promo_snapshot__code")
        .annotate(n=Count("id"), discount=Sum("discount"), revenue=Sum("amount_sent"))
        .order_by("-n")
    )
    return {
        "requests": qs.count(),
        "pending": qs.filter(status=PAY.PENDING_VERIFICATION).count(),
        "approved": approved.count(),
        "rejected": qs.filter(status=PAY.REJECTED).count(),
        "original_value": str(to_money(agg["original"] or 0)),
        "discounts": str(to_money(agg["discount"] or 0)),
        "revenue": str(to_money(agg["revenue"] or 0)),  # approved (verified) payments only
        "registrations": apps_with_payment.count(),
        "registrations_approved": apps_with_payment.filter(status=TurfApplication.Status.APPROVED).count(),
        "by_promo": [
            {
                "code": r["promo_snapshot__code"],
                "uses": r["n"],
                "discount": str(to_money(r["discount"] or 0)),
                "revenue": str(to_money(r["revenue"] or 0)),
            }
            for r in by_promo
        ],
    }


def admin_row(p: RegistrationPayment) -> dict:
    app = p.application
    return {
        "id": str(p.pk),
        "reference": app.reference,
        "application_id": str(app.pk),
        "turf_name": app.turf_name,
        "owner_name": app.owner_name,
        "phone": app.phone,
        "email": app.email,
        "plan": p.plan.name,
        "promo_code": (p.promo_snapshot or {}).get("code"),
        "promo_label": (p.promo_snapshot or {}).get("label"),
        "original": str(p.list_price),
        "discount": str(p.discount),
        "payable": str(p.amount_due),
        "amount_sent": str(p.amount_sent),
        "sender_number": p.sender_number,
        "trx_id": p.trx_id,
        "note": p.note,
        "receiving_number": p.receiving_number,
        "submitted_at": p.created_at,
        "status": p.status,
        "status_label": p.get_status_display(),
        "reviewed_by": (p.reviewed_by.full_name or p.reviewed_by.email) if p.reviewed_by_id else None,
        "reviewed_at": p.reviewed_at,
        "review_note": p.review_note,
        "rejection_reason": p.rejection_reason,
        "can_resubmit": p.can_resubmit,
        "turf_id": str(app.turf_id) if app.turf_id else None,
    }
