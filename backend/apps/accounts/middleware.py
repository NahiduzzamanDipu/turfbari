"""Session rules: Super Admin sessions end ADMIN_SESSION_HOURS after sign-in; a user on a
temporary password can do nothing but change it."""

import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import JsonResponse

from .two_factor import AUTH_AT_KEY


@receiver(user_logged_in)
def _stamp_sign_in_time(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session[AUTH_AT_KEY] = time.time()


class AdminSessionLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_platform_admin:
            started = request.session.get(AUTH_AT_KEY)
            if started is None or time.time() - started > settings.ADMIN_SESSION_HOURS * 3600:
                logout(request)
        return self.get_response(request)


class LegalAcceptanceRequiredMiddleware:
    """Server-side sign-in gate: an owner/manager with unaccepted mandatory platform documents gets 403
    from every workspace API until they accept (via /api/legal/). Only the workspace is blocked — public
    pages, sign-out and the legal endpoints keep working. Other actions (bookings, plan orders, SMS
    recharges) check their own documents when they happen."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not user.is_platform_admin
            and not user.must_change_password
            and request.path.startswith("/api/workspace/")
        ):
            from apps.legal.services import account_gate_pending

            if account_gate_pending(user):
                return _error(
                    "legal_acceptance_required",
                    "Please review and accept the updated TurfBari terms and policies to continue.",
                    403,
                )
        return self.get_response(request)


# What a user on a temporary password may still call.
PASSWORD_CHANGE_ALLOWED = (
    "/api/auth/me/",
    "/api/auth/csrf/",
    "/api/auth/logout/",
    "/api/auth/change-password/",
    "/api/live/",
    "/api/health/",
)


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message, "fields": None}}, status=status)


class PasswordChangeRequiredMiddleware:
    """Server-side enforcement of the first-login password change (the SPA redirect is only UX)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.must_change_password
            and request.path.startswith("/api/")
            and not request.path.startswith(PASSWORD_CHANGE_ALLOWED)
        ):
            from .passwords import temporary_password_expired

            if temporary_password_expired(user):
                logout(request)
                return _error("temporary_password_expired", "Your temporary password has expired.", 401)
            return _error("password_change_required", "Set your own password before continuing.", 403)
        return self.get_response(request)
