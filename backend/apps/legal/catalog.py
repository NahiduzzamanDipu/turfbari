# ruff: noqa: E501
"""The document modules and their defaults. Admins can change audiences/actions per document; these are
only the starting values and the reading order. (No model imports: migrations use this too.)"""

ALL_AUDIENCES = ["customer", "owner", "manager"]
BUSINESS = ["owner", "manager"]

# Reading / inheritance order: general terms → general rules → sector terms → sector rules → policies.
ORDER = [
    "terms",
    "privacy",
    "rules",
    "account_usage",
    "prohibited",
    "sector_terms",
    "sector_rules",
    "booking",
    "refund",
    "subscription",
    "sms",
]

SECTOR_CATEGORIES = {"sector_terms", "sector_rules"}

# category -> (public slug, title_en, title_bn, audiences, actions)
DEFAULTS: dict[str, tuple[str, str, str, list[str], list[str]]] = {
    "terms": (
        "terms",
        "Terms & Conditions",
        "শর্তাবলী",
        ALL_AUDIENCES,
        ["registration", "account", "booking"],
    ),
    "privacy": ("privacy", "Privacy Policy", "গোপনীয়তা নীতি", ALL_AUDIENCES, ["registration", "account", "booking"]),
    "rules": ("rules", "Platform Rules & Regulations", "প্ল্যাটফর্মের নিয়মাবলী", BUSINESS, ["registration", "account"]),
    "account_usage": ("account-usage", "Account Usage Policy", "অ্যাকাউন্ট ব্যবহারের নীতি", BUSINESS, ["registration", "account"]),
    "prohibited": (
        "prohibited-activities",
        "Prohibited Activities & User Responsibilities",
        "নিষিদ্ধ কার্যকলাপ ও ব্যবহারকারীর দায়িত্ব",
        ALL_AUDIENCES,
        ["registration", "account", "booking"],
    ),
    "sector_terms": ("terms", "Sector Terms & Conditions", "সেক্টরের শর্তাবলী", ALL_AUDIENCES, ["registration", "account", "booking"]),
    "sector_rules": ("rules", "Sector Rules & Regulations", "সেক্টরের নিয়মাবলী", ALL_AUDIENCES, ["registration", "booking"]),
    "booking": ("booking-policy", "Booking & Reservation Policy", "বুকিং ও রিজার্ভেশন নীতি", ["customer", "owner", "manager"], ["booking"]),
    "refund": (
        "refund-policy",
        "Payment, Refund & Cancellation Policy",
        "পেমেন্ট, রিফান্ড ও বাতিলকরণ নীতি",
        ["customer", "owner"],
        ["booking", "subscription", "sms_recharge"],
    ),
    "subscription": ("subscription-policy", "Subscription & Billing Policy", "সাবস্ক্রিপশন ও বিলিং নীতি", ["owner"], ["registration", "subscription"]),
    "sms": ("sms-policy", "SMS Wallet & Communication Policy", "এসএমএস ওয়ালেট ও যোগাযোগ নীতি", BUSINESS, ["sms_recharge"]),
}  # fmt: skip


def sort_key(category: str) -> int:
    return ORDER.index(category) if category in ORDER else len(ORDER)
