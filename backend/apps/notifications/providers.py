"""SMS providers. BulkSMSBD is the real one; console/memory/disabled exist for development and tests.

BulkSMSBD HTTP API (as documented for API-key accounts; confirm in your BulkSMSBD panel):
  POST https://bulksmsbd.net/api/smsapi       api_key, senderid, number (8801XXXXXXXXX), message
  POST https://bulksmsbd.net/api/getBalanceApi api_key
Response code 202 = accepted. BulkSMSBD documents no delivery-report endpoint, so "sent" means
"accepted by BulkSMSBD", not "delivered to the handset".
"""

import json
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

log = logging.getLogger(__name__)
# Text a provider may write to logs for the current send (the stored, masked text — never a password).
LOG_BODY: ContextVar[str | None] = ContextVar("sms_log_body", default=None)

# What each BulkSMSBD code means, and whether trying again later can help.
CODES: dict[str, tuple[str, bool]] = {
    "202": ("Accepted by BulkSMSBD", False),
    "1001": ("Invalid number", False),
    "1002": ("Sender ID is incorrect or disabled", False),
    "1003": ("Required fields missing", False),
    "1005": ("BulkSMSBD internal error", True),
    "1006": ("Balance validity not available", True),
    "1007": ("Insufficient SMS balance", True),
    "1011": ("BulkSMSBD user ID not found", False),
    "1012": ("Masking SMS must be in Bengali", False),
    "1013": ("Sender ID has no gateway for this API key", False),
    "1014": ("Sender type not found for this sender ID", False),
    "1015": ("No valid gateway for this sender ID", False),
    "1016": ("No active price for this sender type", False),
    "1017": ("No price for this sender type", False),
    "1018": ("BulkSMSBD account is disabled", False),
    "1019": ("Price for this sender type is disabled", False),
    "1020": ("BulkSMSBD parent account not found", False),
    "1021": ("No active parent price for this sender type", False),
    "1031": ("BulkSMSBD account not verified", False),
    "1032": ("Server IP not whitelisted in BulkSMSBD", False),
}


@dataclass
class SendResult:
    ok: bool
    code: str
    message: str
    retryable: bool
    ref: str = ""  # provider's message id, when it returns one


def describe(code: str) -> tuple[str, bool]:
    return CODES.get(code, (f"BulkSMSBD code {code}", True))


def bd_msisdn(phone: str) -> str | None:
    """'01712-345678' / '+8801712345678' -> '8801712345678'; None if not a BD mobile number."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("880"):
        digits = digits[2:]
    if not re.fullmatch(r"01[3-9]\d{8}", digits):
        return None
    return "88" + digits


def segment_count(text: str) -> int:
    """SMS parts billed: GSM-7 160/153 chars, Unicode (Bengali) 70/67 chars."""
    unicode = any(ord(ch) > 127 for ch in text)
    single, multi = (70, 67) if unicode else (160, 153)
    n = len(text)
    return 1 if n <= single else -(-n // multi)


class BaseProvider:
    name = "base"

    def send(self, to: str, body: str, sender_id: str) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError

    def balance(self) -> Decimal | None:
        return None


class DisabledProvider(BaseProvider):
    name = "disabled"

    def send(self, to, body, sender_id):
        return SendResult(False, "disabled", "SMS is not configured (BULKSMSBD_API_KEY is empty)", False)


class ConsoleProvider(BaseProvider):
    """Development: log the SMS instead of sending it."""

    name = "console"

    def send(self, to, body, sender_id):
        log.warning("SMS (console) to %s from %s: %s", to, sender_id or "-", LOG_BODY.get() or body)
        return SendResult(True, "console", "Logged to the server console (development)", False)


class MemoryProvider(BaseProvider):
    """Tests: keep messages in `outbox`; set `fail_with` to simulate a provider error."""

    name = "memory"
    outbox: list[dict] = []
    fail_with: str | None = None

    def send(self, to, body, sender_id):
        if MemoryProvider.fail_with:
            text, retryable = describe(MemoryProvider.fail_with)
            return SendResult(False, MemoryProvider.fail_with, text, retryable)
        MemoryProvider.outbox.append({"to": to, "body": body, "sender_id": sender_id})
        return SendResult(True, "202", "Accepted (test)", False)

    def balance(self):
        return Decimal("100.00")


class BulkSMSBDProvider(BaseProvider):
    name = "bulksmsbd"

    def __init__(self, api_key: str, base_url: str, timeout: int = 10):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, fields: dict) -> tuple[int, str]:
        data = urlencode(fields).encode()
        request = Request(  # noqa: S310 - fixed https base URL from settings
            f"{self.base_url}/{path}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed https base URL
            return response.status, response.read().decode("utf-8", "replace")

    @staticmethod
    def _ref(text: str) -> str:
        try:
            payload = json.loads(text)
        except ValueError:
            return ""
        if isinstance(payload, dict):
            for key in ("message_id", "messageid", "msg_id", "id"):
                if payload.get(key):
                    return str(payload[key])[:64]
        return ""

    @staticmethod
    def _code(text: str) -> tuple[str, str]:
        """BulkSMSBD answers JSON like {"response_code": 202, ...} (some accounts get plain text)."""
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            code = payload.get("response_code", payload.get("code", payload.get("status", "")))
            detail = (
                payload.get("success_message") or payload.get("error_message") or payload.get("message") or ""
            )
            return str(code).strip(), str(detail)[:200]
        match = re.search(r"\b(202|1\d{3})\b", text or "")
        return (match.group(1) if match else ""), (text or "")[:200]

    def send(self, to, body, sender_id):
        try:
            _, text = self._post(
                "smsapi",
                {
                    "api_key": self.api_key,
                    "type": "text",
                    "senderid": sender_id,
                    "number": to,
                    "message": body,
                },
            )
        except TimeoutError:
            # The request may or may not have reached BulkSMSBD: don't blindly resend (duplicates).
            return SendResult(
                False, "timeout", "No answer from BulkSMSBD in time — may or may not be sent", False
            )
        except HTTPError as exc:
            return SendResult(
                False, f"http{exc.code}", f"BulkSMSBD returned HTTP {exc.code}", exc.code >= 500
            )
        except URLError as exc:
            return SendResult(False, "network", f"Couldn't reach BulkSMSBD ({exc.reason})"[:200], True)
        code, detail = self._code(text)
        if code == "202":
            return SendResult(True, code, detail or "Accepted by BulkSMSBD", False, self._ref(text))
        meaning, retryable = describe(code or "unknown")
        return SendResult(
            False, code or "unknown", (f"{meaning}: {detail}" if detail else meaning)[:255], retryable
        )

    def balance(self) -> Decimal | None:
        try:
            _, text = self._post("getBalanceApi", {"api_key": self.api_key})
        except (OSError, URLError):
            log.warning("BulkSMSBD balance check failed", exc_info=True)
            return None
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {}
        value = payload.get("balance") if isinstance(payload, dict) else None
        if value is None:
            match = re.search(r"[\d.]+", text or "")
            value = match.group(0) if match else None
        try:
            return Decimal(str(value)) if value is not None else None
        except InvalidOperation:
            return None


def api_key() -> tuple[str, str]:
    """(key, source): the admin-saved key (encrypted in the DB) wins over BULKSMSBD_API_KEY."""
    from apps.common.crypto import decrypt

    from .models import SmsConfig

    saved = decrypt(SmsConfig.load().api_key_encrypted)
    if saved:
        return saved, "admin"
    if settings.BULKSMSBD_API_KEY:
        return settings.BULKSMSBD_API_KEY, "environment"
    return "", "none"


def get_provider() -> BaseProvider:
    backend = settings.SMS_BACKEND
    if backend == "memory":
        return MemoryProvider()
    if backend == "console":
        return ConsoleProvider()
    key, _ = api_key()
    if backend == "bulksmsbd" and key:
        return BulkSMSBDProvider(key, settings.BULKSMSBD_BASE_URL)
    return DisabledProvider()
