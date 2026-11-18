"""RFC 6238 time-based one-time passwords (what Google Authenticator, Authy, Microsoft
Authenticator use): HMAC-SHA1, 6 digits, 30-second steps. Standard library only."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

DIGITS = 6
STEP = 30
WINDOW = 1  # accept the previous/next 30 s step for clock drift


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def code_at(secret: str, counter: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_counter(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP)


def match(secret: str, code: str, *, after_counter: int = -1, now: float | None = None) -> int | None:
    """Return the matching counter, or None. Counters <= after_counter are rejected (no replays)."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    base = current_counter(now)
    for counter in range(base - WINDOW, base + WINDOW + 1):
        if counter > after_counter and hmac.compare_digest(code_at(secret, counter), code):
            return counter
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode({"secret": secret, "issuer": issuer, "digits": DIGITS, "period": STEP})
    return f"otpauth://totp/{label}?{query}"


RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_recovery_codes(count: int = 10) -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(count)]


def hash_recovery(code: str) -> str:
    normal = code.strip().lower().replace(" ", "").replace("-", "")
    return hashlib.sha256(normal.encode()).hexdigest()
