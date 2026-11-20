"""SSLCommerz hosted checkout (cards, bKash, Nagad, Rocket, internet banking).

Enabled only when SSLCOMMERZ_STORE_ID / SSLCOMMERZ_STORE_PASSWORD are set. Use the sandbox store from
https://developer.sslcommerz.com while testing (SSLCOMMERZ_SANDBOX=True).

The browser's "success" redirect is never trusted: every callback is confirmed server-to-server with
the validation API, and the amount, currency and transaction ID must match what we issued.
"""

import json
import logging
from decimal import Decimal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from apps.audit.services import Category, record

from .models import Invoice, PaymentTransaction

log = logging.getLogger(__name__)
TIMEOUT = 20


class GatewayError(Exception):
    pass


def enabled() -> bool:
    return bool(settings.SSLCOMMERZ_STORE_ID and settings.SSLCOMMERZ_STORE_PASSWORD)


def _base() -> str:
    return (
        "https://sandbox.sslcommerz.com"
        if settings.SSLCOMMERZ_SANDBOX
        else "https://securepay.sslcommerz.com"
    )


def _post(url: str, data: dict) -> dict:
    req = Request(url, data=urlencode(data).encode(), method="POST")  # noqa: S310 - fixed https host
    with urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def _get(url: str, params: dict) -> dict:
    with urlopen(f"{url}?{urlencode(params)}", timeout=TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def initiate(invoice: Invoice, *, user, callback_base: str) -> tuple[PaymentTransaction, str]:
    """Create a transaction and return the hosted checkout URL to redirect the owner to."""
    if not enabled():
        raise GatewayError("Online payment is not configured yet.")
    if invoice.status != Invoice.Status.UNPAID:
        raise GatewayError("This invoice is not awaiting payment.")
    tx = PaymentTransaction.objects.create(
        invoice=invoice,
        method=PaymentTransaction.Method.ONLINE,
        channel=PaymentTransaction.Channel.GATEWAY,
        amount=invoice.amount,
        status=PaymentTransaction.Status.INITIATED,
        submitted_by=user,
    )
    turf = invoice.turf
    plan = invoice.subscription.plan
    payload = {
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "total_amount": str(invoice.amount),
        "currency": "BDT",
        "tran_id": tx.tran_id,
        "success_url": f"{callback_base}/success/",
        "fail_url": f"{callback_base}/fail/",
        "cancel_url": f"{callback_base}/cancel/",
        "ipn_url": f"{callback_base}/ipn/",
        "product_name": f"TurfBari {plan.name} plan",
        "product_category": "Subscription",
        "product_profile": "non-physical-goods",
        "shipping_method": "NO",
        "num_of_item": 1,
        "cus_name": (user.full_name or user.email)[:50],
        "cus_email": user.email,
        "cus_phone": turf.owner_phone or turf.public_phone or "01700000000",
        "cus_add1": turf.address[:50],
        "cus_city": turf.district.name,
        "cus_country": "Bangladesh",
        "value_a": invoice.number,
    }
    try:
        data = _post(f"{_base()}/gwprocess/v4/api.php", payload)
    except (URLError, TimeoutError, ValueError) as exc:
        tx.status = PaymentTransaction.Status.FAILED
        tx.note = "Could not reach the payment gateway."
        tx.save(update_fields=["status", "note", "updated_at"])
        raise GatewayError("The payment gateway is not responding. Please try again.") from exc
    url = data.get("GatewayPageURL")
    if data.get("status") != "SUCCESS" or not url:
        tx.status = PaymentTransaction.Status.FAILED
        tx.note = str(data.get("failedreason") or "Gateway refused the session")[:255]
        tx.save(update_fields=["status", "note", "updated_at"])
        raise GatewayError("The payment gateway could not start the payment.")
    tx.gateway_response = {"sessionkey": data.get("sessionkey")}
    tx.save(update_fields=["gateway_response", "updated_at"])
    return tx, url


def validate(val_id: str) -> dict:
    return _get(
        f"{_base()}/validator/api/validationserverAPI.php",
        {
            "val_id": val_id,
            "store_id": settings.SSLCOMMERZ_STORE_ID,
            "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
            "format": "json",
        },
    )


@transaction.atomic
def settle(tran_id: str, val_id: str | None, outcome: str) -> PaymentTransaction | None:
    """Handle success/fail/cancel/IPN callbacks. Safe to call repeatedly for the same transaction."""
    tx = (
        PaymentTransaction.objects.select_for_update()
        .select_related("invoice")
        .filter(tran_id=tran_id, channel=PaymentTransaction.Channel.GATEWAY)
        .first()
    )
    if tx is None:
        return None
    if tx.status == PaymentTransaction.Status.VERIFIED:
        return tx  # already settled (e.g. IPN arrived first)

    if outcome != "success" or not val_id:
        if tx.status == PaymentTransaction.Status.INITIATED:
            tx.status = (
                PaymentTransaction.Status.CANCELLED
                if outcome == "cancel"
                else PaymentTransaction.Status.FAILED
            )
            tx.save(update_fields=["status", "updated_at"])
        return tx

    try:
        data = validate(val_id)
    except (URLError, TimeoutError, ValueError):
        log.warning("SSLCommerz validation unreachable for %s", tran_id)
        return tx  # stays initiated; the IPN or a retry will settle it
    ok = (
        data.get("status") in ("VALID", "VALIDATED")
        and data.get("tran_id") == tx.tran_id
        and data.get("currency_type", data.get("currency")) == "BDT"
        and Decimal(str(data.get("currency_amount", data.get("amount", "0")))) == tx.amount
    )
    tx.gateway_response = {
        k: data.get(k) for k in ("status", "val_id", "bank_tran_id", "card_type", "amount", "tran_date")
    }
    if not ok:
        tx.status = PaymentTransaction.Status.FAILED
        tx.note = "Gateway validation did not match this payment."
        tx.save(update_fields=["status", "note", "gateway_response", "updated_at"])
        return tx
    # The gateway confirmed the money; the plan still changes only when a TurfBari admin approves.
    tx.status = PaymentTransaction.Status.PENDING_VERIFICATION
    tx.reference = str(data.get("bank_tran_id") or val_id)[:60]
    tx.note = "Paid online (SSLCommerz validated) — approve to activate the plan"
    tx.save(update_fields=["status", "reference", "note", "gateway_response", "updated_at"])
    invoice = tx.invoice
    if invoice.status == Invoice.Status.CANCELLED:
        # The owner switched plan while this checkout was open, but the money did arrive: honour it.
        invoice.status = Invoice.Status.UNPAID
        invoice.save(update_fields=["status", "updated_at"])
        invoice.subscription.status = invoice.subscription.Status.PENDING_PAYMENT
        invoice.subscription.save(update_fields=["status", "updated_at"])
    if invoice.status == Invoice.Status.UNPAID:
        invoice.status = Invoice.Status.PENDING_VERIFICATION
        invoice.save(update_fields=["status", "updated_at"])
    record(
        "subscription.paid_online",
        f"Paid ৳{tx.amount} online for invoice {invoice.number} ({tx.reference})",
        category=Category.SUBSCRIPTION,
        actor=tx.submitted_by,
        turf=invoice.turf,
        target=tx,
    )
    return tx
