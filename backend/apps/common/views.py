import logging

from django.core.cache import cache
from django.db import connection
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Liveness/readiness probe. Reports only up/down — no versions or hostnames."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT}, tags=["system"])
    def get(self, request):
        checks = {"database": _check_database(), "cache": _check_cache()}
        healthy = all(checks.values())
        body = {
            "status": "ok" if healthy else "degraded",
            "checks": {name: "up" if ok else "down" for name, ok in checks.items()},
        }
        return Response(body, status=200 if healthy else 503)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the CSRF cookie so the SPA can send X-CSRFToken on unsafe requests."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: OpenApiTypes.OBJECT}, tags=["auth"])
    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


def _check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:
        logger.exception("Health check: database unavailable")
        return False


def _check_cache() -> bool:
    try:
        cache.set("health:ping", "pong", 5)
        return cache.get("health:ping") == "pong"
    except Exception:
        logger.exception("Health check: cache unavailable")
        return False
