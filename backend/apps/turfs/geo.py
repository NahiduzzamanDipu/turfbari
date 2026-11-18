"""Small geo helpers: Google Maps links and approximate distances (no external services)."""

import math
import re
from decimal import Decimal
from urllib.parse import unquote, urlparse

GOOGLE_MAPS_HOSTS = ("google.com", "goo.gl", "g.co", "google.com.bd")

_COORD = r"(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)"
_PATTERNS = [
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)"),  # exact place pin
    re.compile(r"[?&](?:q|query|ll|destination|center)=" + _COORD),
    re.compile(r"/place/" + _COORD),
    re.compile(r"@" + _COORD),  # map viewport centre
]


def is_google_maps_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in GOOGLE_MAPS_HOSTS):
        return False
    if host.endswith("goo.gl") or host.endswith("g.co"):
        return True  # short share links (maps.app.goo.gl / goo.gl/maps)
    return host.startswith("maps.") or urlparse(url).path.startswith("/maps")


def valid_coords(lat, lng) -> bool:
    return lat is not None and lng is not None and -90 <= float(lat) <= 90 and -180 <= float(lng) <= 180


def coords_from_maps_url(url: str) -> tuple[Decimal, Decimal] | None:
    """Pull coordinates out of a full Google Maps URL. Short links carry none -> None."""
    text = unquote(url or "")
    for pattern in _PATTERNS:
        if m := pattern.search(text):
            lat, lng = Decimal(m.group(1)), Decimal(m.group(2))
            if valid_coords(lat, lng):
                q = Decimal("0.000001")
                return lat.quantize(q), lng.quantize(q)
    return None


def google_maps_link(lat, lng) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    lat1, lng1, lat2, lng2 = map(lambda v: math.radians(float(v)), (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))
