"""Two-factor sign-in (TOTP authenticator app + one-time recovery codes) for Super Admins.

Login flow when enabled: password OK -> session holds a short-lived "pending" marker (the user is
NOT logged in yet) -> POST /api/auth/2fa/verify/ with a 6-digit code or a recovery code -> login().
"""

import time

import segno
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import Category, record

from . import totp
from .models import TwoFactorDevice

PENDING_KEY = "2fa_pending"
PENDING_TTL = 300  # seconds to enter the code after the password
MAX_ATTEMPTS = 5


def _error(code: str, message: str, http=status.HTTP_400_BAD_REQUEST, fields=None):
    return Response({"error": {"code": code, "message": message, "fields": fields}}, status=http)


class IsPlatformAdminUser(BasePermission):
    message = "Two-factor sign-in is available for TurfBari administrators."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_active and u.is_platform_admin)


def enabled_device(user) -> TwoFactorDevice | None:
    return TwoFactorDevice.objects.filter(user=user, confirmed=True).first()


def start_pending(request, user, remember: bool) -> None:
    request.session.cycle_key()
    request.session[PENDING_KEY] = {
        "user": str(user.pk),
        "at": time.time(),
        "remember": bool(remember),
        "attempts": 0,
    }


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20, trim_whitespace=True)


class DisableSerializer(CodeSerializer):
    password = serializers.CharField(trim_whitespace=False)


def _check(device: TwoFactorDevice, code: str) -> str | None:
    """'totp' / 'recovery' if the code is valid (and consumes it), else None."""
    counter = totp.match(device.secret, code, after_counter=device.last_counter)
    if counter is not None:
        device.last_counter = counter
        device.save(update_fields=["last_counter", "updated_at"])
        return "totp"
    digest = totp.hash_recovery(code)
    if digest in device.recovery_hashes:
        device.recovery_hashes = [h for h in device.recovery_hashes if h != digest]
        device.save(update_fields=["recovery_hashes", "updated_at"])
        return "recovery"
    return None


class TwoFactorStatusView(APIView):
    permission_classes = [IsPlatformAdminUser]

    @extend_schema(tags=["auth"])
    def get(self, request):
        device = enabled_device(request.user)
        return Response(
            {"enabled": bool(device), "recovery_codes_left": len(device.recovery_hashes) if device else 0}
        )


class TwoFactorSetupView(APIView):
    """Start (or restart) enrolment. Nothing changes for sign-in until the code is confirmed."""

    permission_classes = [IsPlatformAdminUser]

    @extend_schema(request=None, tags=["auth"])
    def post(self, request):
        if enabled_device(request.user):
            return _error("already_enabled", "Two-factor sign-in is already on. Turn it off first.")
        secret = totp.new_secret()
        TwoFactorDevice.objects.update_or_create(
            user=request.user,
            defaults={"secret": secret, "confirmed": False, "last_counter": -1, "recovery_hashes": []},
        )
        uri = totp.provisioning_uri(secret, request.user.email, settings.PLATFORM_NAME)
        qr = segno.make(uri, error="m").svg_data_uri(scale=5, border=2, dark="#065f46")
        return Response({"secret": secret, "otpauth_uri": uri, "qr_svg": qr})


class TwoFactorConfirmView(APIView):
    permission_classes = [IsPlatformAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "two_factor"

    @extend_schema(request=CodeSerializer, tags=["auth"])
    def post(self, request):
        data = CodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        device = TwoFactorDevice.objects.filter(user=request.user, confirmed=False).first()
        if device is None:
            return _error("not_started", "Start the set-up again.")
        counter = totp.match(device.secret, data.validated_data["code"])
        if counter is None:
            return _error(
                "invalid_code",
                "That code didn't match. Check your phone's time and try again.",
                fields={"code": ["Incorrect code."]},
            )
        codes = totp.new_recovery_codes()
        device.confirmed, device.last_counter = True, counter
        device.recovery_hashes = [totp.hash_recovery(c) for c in codes]
        device.save()
        record(
            "account.2fa_enabled", "Turned on two-factor sign-in", category=Category.ACCOUNT, request=request
        )
        return Response({"enabled": True, "recovery_codes": codes})


class TwoFactorDisableView(APIView):
    permission_classes = [IsPlatformAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "two_factor"

    @extend_schema(request=DisableSerializer, tags=["auth"])
    def post(self, request):
        data = DisableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        device = enabled_device(request.user)
        if device is None:
            return Response({"enabled": False})
        if not request.user.check_password(data.validated_data["password"]):
            return _error(
                "invalid_password", "Password is incorrect.", fields={"password": ["Incorrect password."]}
            )
        if _check(device, data.validated_data["code"]) is None:
            return _error("invalid_code", "That code didn't match.", fields={"code": ["Incorrect code."]})
        device.delete()
        record(
            "account.2fa_disabled",
            "Turned off two-factor sign-in",
            category=Category.ACCOUNT,
            request=request,
        )
        return Response({"enabled": False})


class RecoveryCodesView(APIView):
    """Replace all recovery codes (needs a current authenticator code)."""

    permission_classes = [IsPlatformAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "two_factor"

    @extend_schema(request=CodeSerializer, tags=["auth"])
    def post(self, request):
        data = CodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        device = enabled_device(request.user)
        if device is None:
            return _error("not_enabled", "Two-factor sign-in is off.")
        counter = totp.match(device.secret, data.validated_data["code"], after_counter=device.last_counter)
        if counter is None:
            return _error("invalid_code", "That code didn't match.", fields={"code": ["Incorrect code."]})
        codes = totp.new_recovery_codes()
        device.last_counter = counter
        device.recovery_hashes = [totp.hash_recovery(c) for c in codes]
        device.save()
        record("account.2fa_codes", "Created new recovery codes", category=Category.ACCOUNT, request=request)
        return Response({"recovery_codes": codes})


class TwoFactorVerifyView(APIView):
    """Second step of sign-in."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "two_factor"

    @extend_schema(request=CodeSerializer, tags=["auth"])
    def post(self, request):
        from .views import me_payload

        data = CodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        pending = request.session.get(PENDING_KEY)
        if not pending or time.time() - pending.get("at", 0) > PENDING_TTL:
            request.session.pop(PENDING_KEY, None)
            return _error(
                "two_factor_expired",
                "Sign-in timed out. Enter your password again.",
                http=status.HTTP_401_UNAUTHORIZED,
            )
        user = get_user_model().objects.filter(pk=pending["user"], is_active=True).first()
        with transaction.atomic():
            device = (
                TwoFactorDevice.objects.select_for_update().filter(user=user, confirmed=True).first()
                if user
                else None
            )
            used = _check(device, data.validated_data["code"]) if device else None
        if used is None:
            pending["attempts"] = pending.get("attempts", 0) + 1
            if pending["attempts"] >= MAX_ATTEMPTS:
                request.session.pop(PENDING_KEY, None)
                return _error(
                    "two_factor_expired",
                    "Too many wrong codes. Enter your password again.",
                    http=status.HTTP_401_UNAUTHORIZED,
                )
            request.session[PENDING_KEY] = pending
            record(
                "account.2fa_failed",
                "Wrong two-factor code at sign-in",
                category=Category.ACCOUNT,
                request=request,
                actor=user,
            )
            return _error("invalid_code", "That code didn't match.", fields={"code": ["Incorrect code."]})
        request.session.pop(PENDING_KEY, None)
        login(request, user, backend="apps.accounts.backends.EmailOrUsernameBackend")
        if not pending.get("remember", True):
            request.session.set_expiry(0)
        note = " with a recovery code" if used == "recovery" else ""
        record(
            "account.login",
            f"Signed in (two-factor{note})",
            category=Category.ACCOUNT,
            request=request,
            actor=user,
        )
        return Response(me_payload(request))
