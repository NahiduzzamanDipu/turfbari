"""Prepaid SMS wallet: pricing, an immutable ledger, and the rules that decide if a turf may send.

Charging policy (applied in services.deliver):
- A turf SMS is checked when queued (account switches, price, enough balance) and again right before
  it is handed to BulkSMSBD.
- The cost (billable segments x the price in force when the message was queued) is taken from the
  wallet in the same database transaction that marks the message "sending", so parallel sends can never
  overdraw a wallet. If BulkSMSBD then clearly refuses the message, the same amount is refunded with a
  separate ledger entry. If BulkSMSBD doesn't answer (timeout) the charge stays and the message is
  marked "check" for the admin, who can refund it after checking the BulkSMSBD panel.
- Each provider attempt has its own idempotency keys (sms:<id>:a<n> / ...:refund), so running deliver
  twice, or a retry, can never charge the same attempt twice; a message is only retried after a
  refunded failure, so at most one charge per logical message stays on the books.
- TurfBari's own messages (sign-in codes, plan notices, wallet/plan confirmations) never touch a turf
  wallet; their cost is recorded on the message as a platform expense.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    SmsAccountControl,
    SmsConfig,
    SmsKind,
    SmsMessage,
    SmsPricing,
    SmsWallet,
    WalletTransaction,
)

FOUR = Decimal("0.0001")
INSUFFICIENT_BN = "আপনার SMS Wallet-এ পর্যাপ্ত ব্যালেন্স নেই। SMS পাঠাতে অনুগ্রহ করে Wallet Recharge করুন।"
DISABLED_BN = (
    "আপনার অ্যাকাউন্টের SMS সেবা বর্তমানে প্রশাসক কর্তৃক বন্ধ রাখা হয়েছে। বিস্তারিত জানতে TURFBARI কর্তৃপক্ষের সাথে যোগাযোগ করুন।"
)

# Which admin switch controls which turf SMS type.
KIND_SWITCH = {
    SmsKind.BOOKING_CONFIRMED: "booking_confirmed",
    SmsKind.OWNER_BOOKING_CONFIRMED: "owner_booking",
    SmsKind.PAYMENT_REJECTED: "rejection_cancellation",
    SmsKind.BOOKING_CANCELLED: "rejection_cancellation",
    SmsKind.BOOKING_REMINDER: "reminder",
    SmsKind.CUSTOM: "single",
    SmsKind.CAMPAIGN: "bulk",
}


class InsufficientBalance(Exception):
    pass


def money(value) -> Decimal:
    return Decimal(value).quantize(FOUR, rounding=ROUND_HALF_UP)


def current_pricing(at=None) -> SmsPricing | None:
    return (
        SmsPricing.objects.filter(effective_from__lte=at or timezone.now())
        .order_by("-effective_from", "-id")
        .first()
    )


def price_for(kind: str, at=None) -> Decimal | None:
    """BDT per segment for a new message of this kind (None = no price configured yet)."""
    pricing = current_pricing(at)
    if pricing is None:
        return None
    if kind == SmsKind.CAMPAIGN:
        return pricing.bulk_price_per_segment
    if SmsConfig.load().sender_is_masking:
        return pricing.masking_price_per_segment
    return pricing.price_per_segment


def wallet_for(turf) -> SmsWallet:
    return SmsWallet.objects.get_or_create(turf=turf)[0]


def control_for(turf) -> SmsAccountControl:
    return SmsAccountControl.objects.filter(turf=turf).first() or SmsAccountControl(turf=turf)


def blocked_by_admin(turf, kind: str) -> str | None:
    """Block reason if TurfBari turned this account's SMS (or this type) off, else None."""
    control = control_for(turf)
    if not control.all_enabled:
        return SmsMessage.BlockReason.ACCOUNT_DISABLED
    switch = KIND_SWITCH.get(kind)
    if switch and not getattr(control, switch):
        return SmsMessage.BlockReason.TYPE_DISABLED
    return None


def post(wallet_id, *, kind: str, amount: Decimal, key: str, **meta) -> WalletTransaction:
    """Add one ledger entry and move the balance with it, atomically. Same key twice = no-op (returns
    the first entry). Raises InsufficientBalance instead of letting a balance go below zero."""
    amount = money(amount)
    try:
        with transaction.atomic():  # a savepoint when nested: a failure undoes the balance change too
            wallet = SmsWallet.objects.select_for_update().get(pk=wallet_id)
            existing = WalletTransaction.objects.filter(idempotency_key=key).first()
            if existing:
                return existing
            new_balance = money(wallet.balance + amount)
            if new_balance < 0:
                raise InsufficientBalance(f"Balance {wallet.balance} can't cover {-amount}")
            wallet.balance = new_balance
            wallet.save(update_fields=["balance", "updated_at"])
            return WalletTransaction.objects.create(
                wallet=wallet,
                kind=kind,
                amount=amount,
                balance_after=new_balance,
                idempotency_key=key,
                **meta,
            )
    except IntegrityError:  # a parallel call wrote the same key first: theirs stands, ours rolled back
        existing = WalletTransaction.objects.filter(idempotency_key=key).first()
        if existing:
            return existing
        raise


def credit(
    turf, amount, *, kind=WalletTransaction.Kind.ADMIN_CREDIT, key: str, user=None, note="", recharge=None
):
    if Decimal(amount) <= 0:
        raise ValueError("Credit must be positive.")
    return post(
        wallet_for(turf).pk,
        kind=kind,
        amount=Decimal(amount),
        key=key,
        created_by=user,
        note=note[:200],
        recharge=recharge,
    )


def message_cost(message: SmsMessage) -> Decimal:
    return money((message.price_per_segment or 0) * message.segments)


def charge(message: SmsMessage, attempt: int) -> WalletTransaction:
    """Take this attempt's cost from the turf wallet (called inside deliver's transaction)."""
    wallet = wallet_for(message.turf)
    return post(
        wallet.pk,
        kind=WalletTransaction.Kind.SMS_CHARGE,
        amount=-message_cost(message),
        key=f"sms:{message.pk}:a{attempt}",
        sms=message,
        segments=message.segments,
        price_per_segment=message.price_per_segment,
        note=f"{message.get_kind_display()} to {message.masked_to}"[:200],
    )


def refund(message: SmsMessage, attempt: int, reason: str, user=None) -> WalletTransaction | None:
    """Give back an attempt's charge (provider refused it, or admin confirmed it never went out)."""
    debit = WalletTransaction.objects.filter(idempotency_key=f"sms:{message.pk}:a{attempt}").first()
    if debit is None or debit.amount >= 0:
        return None
    return post(
        debit.wallet_id,
        kind=WalletTransaction.Kind.SMS_REFUND,
        amount=-debit.amount,
        key=f"sms:{message.pk}:a{attempt}:refund",
        sms=message,
        segments=debit.segments,
        price_per_segment=debit.price_per_segment,
        note=reason[:200],
        created_by=user,
    )


def net_charged(message: SmsMessage) -> Decimal:
    from django.db.models import Sum

    total = WalletTransaction.objects.filter(sms=message).aggregate(s=Sum("amount"))["s"] or 0
    return money(-total)
