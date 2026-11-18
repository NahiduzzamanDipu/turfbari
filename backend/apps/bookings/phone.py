import re

from rest_framework.exceptions import ValidationError

BD_MOBILE = re.compile(r"^01[3-9]\d{8}$")


def normalize_bd_phone(raw: str) -> str:
    """Accepts 01XXXXXXXXX, +8801XXXXXXXXX, 8801XXXXXXXXX (spaces/dashes ok) -> +8801XXXXXXXXX."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("880"):
        digits = digits[2:]
    if not BD_MOBILE.match(digits):
        raise ValidationError({"phone": ["Enter a valid Bangladeshi mobile number, e.g. 01712345678."]})
    return "+88" + digits
