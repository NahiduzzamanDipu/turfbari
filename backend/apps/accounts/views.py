"""Unified login: one form for Super Admin, owners and managers. Destination decided server-side."""

from django.contrib.auth import authenticate, login, logout, password_validation, update_session_auth_hash
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.tenancy import ACTIVE_TURF_SESSION_KEY, memberships_for, resolve_membership
from apps.legal.services import account_gate_pending
from apps.turfs.models import MANAGER_PERMISSIONS

from .passwords import (
    clear_temporary_flags,
    confirm_reset,
    end_sessions,
    find_user,
    request_reset,
    temporary_password_expired,
)
from .two_factor import (
    PENDING_KEY,
    enabled_device,
    finish_login_session,
    mask_email,
    needs_email_code,
    send_email_code,
    start_pending,
)


def me_payload(request) -> dict:
    user = request.user
    if not user.is_authenticated:
        return {"authenticated": False, "user": None, "memberships": [], "active_turf_id": None, "home": "/"}
    memberships = list(memberships_for(user))
    active = resolve_membership(request) if memberships else None
    if user.is_platform_admin:
        home = "/admin"
    elif active:
        home = "/workspace"
    else:
        home = "/"
    return {
        "authenticated": True,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_platform_admin": user.is_platform_admin,
            "must_change_password": user.must_change_password,
            # Owners/managers must accept updated platform documents before using the workspace.
            "legal_pending": bool(memberships) and not user.is_platform_admin and account_gate_pending(user),
        },
        "memberships": [
            {
                "turf_id": str(m.turf_id),
                "turf_name": m.turf.name,
                "turf_slug": m.turf.slug,
                "role": m.role,
                "permissions": {key: m.can(key) for key in MANAGER_PERMISSIONS},
            }
            for m in memberships
        ],
        "active_turf_id": str(active.turf_id) if active else None,
        "home": home,
    }


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    remember = serializers.BooleanField(default=True)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, tags=["auth"])
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(
            request, username=data.validated_data["identifier"], password=data.validated_data["password"]
        )
        if user is None and (
            getattr(request, "axes_locked_out", False) or getattr(request._request, "axes_locked_out", False)
        ):
            from .backends import axes_lockout_response  # noqa: PLC0415

            return axes_lockout_response(request)
        if user is None:
            record(
                "account.login_failed",
                f"Failed sign-in for “{data.validated_data['identifier'][:120]}”",
                category=Category.ACCOUNT,
                request=request,
            )
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Email/username or password is incorrect.",
                        "fields": None,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if temporary_password_expired(user):
            record(
                "account.login_failed",
                f"Expired temporary password for “{user.email}”",
                category=Category.ACCOUNT,
                request=request,
                actor=user,
            )
            return Response(
                {
                    "error": {
                        "code": "temporary_password_expired",
                        "message": "This temporary password has expired. Ask your turf owner or TurfBari "
                        "support for a new one, or use “Forgot password”.",
                        "fields": None,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        has_device = enabled_device(user) is not None
        if needs_email_code(user) or has_device:
            start_pending(request, user, data.validated_data["remember"])
            method, hint = "totp", None
            if needs_email_code(user):
                pending = request.session[PENDING_KEY]
                if send_email_code(user, pending):
                    request.session[PENDING_KEY] = pending
                    method, hint = "email", mask_email(user.email)
                elif not has_device:
                    request.session.pop(PENDING_KEY, None)
                    return Response(
                        {
                            "error": {
                                "code": "email_failed",
                                "message": "Couldn't email your sign-in code. Try again in a minute.",
                                "fields": None,
                            }
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
            return Response(
                {
                    "authenticated": False,
                    "two_factor_required": True,
                    "two_factor_method": method,
                    "email_hint": hint,
                    "can_use_authenticator": has_device,
                    "user": None,
                    "memberships": [],
                    "active_turf_id": None,
                    "home": "/login",
                }
            )
        login(request, user)  # rotates the session key
        membership = resolve_membership(request)
        record(
            "account.login",
            "Signed in",
            category=Category.ACCOUNT,
            request=request,
            actor=user,
            turf=membership.turf if membership else None,
        )
        finish_login_session(request, user, data.validated_data["remember"])
        return Response(me_payload(request))


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, tags=["auth"])
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["auth"])
    def get(self, request):
        return Response(me_payload(request))


class SwitchTurfSerializer(serializers.Serializer):
    turf_id = serializers.UUIDField()


class SwitchTurfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SwitchTurfSerializer, tags=["auth"])
    def post(self, request):
        data = SwitchTurfSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        turf_id = str(data.validated_data["turf_id"])
        if not any(str(m.turf_id) == turf_id for m in memberships_for(request.user)):
            return Response(
                {"error": {"code": "not_found", "message": "Workspace not found.", "fields": None}},
                status=404,
            )
        request.session[ACTIVE_TURF_SESSION_KEY] = turf_id
        return Response(me_payload(request))


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, min_length=10)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": ["Current password is incorrect."]})
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError({"new_password": ["Choose a different password."]})
        try:
            password_validation.validate_password(attrs["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from None
        return attrs


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, tags=["auth"])
    def post(self, request):
        data = ChangePasswordSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        user = request.user
        was_temporary = user.must_change_password
        user.set_password(data.validated_data["new_password"])
        clear_temporary_flags(user)
        user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])
        update_session_auth_hash(request, user)
        end_sessions(user, keep_session_key=request.session.session_key)  # other devices sign out
        membership = resolve_membership(request)
        record(
            "account.password_changed",
            "Replaced temporary password" if was_temporary else "Changed password",
            category=Category.ACCOUNT,
            request=request,
            turf=membership.turf if membership else None,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)


class ResetConfirmSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."})
    new_password = serializers.CharField(trim_whitespace=False, min_length=10, max_length=128)


RESET_SENT_MESSAGE = (
    "If an account matches, we've sent a 6-digit code to its phone (SMS) or email. It expires in 15 minutes."
)


class PasswordResetRequestView(APIView):
    """Step 1 of "forgot password". The answer is the same whether or not the account exists."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=ResetRequestSerializer, tags=["auth"])
    def post(self, request):
        data = ResetRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        request_reset(data.validated_data["identifier"])
        return Response({"detail": RESET_SENT_MESSAGE})


class PasswordResetConfirmView(APIView):
    """Step 2: the code plus a new password. Signs the user out everywhere; they sign in again."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=ResetConfirmSerializer, tags=["auth"])
    def post(self, request):
        data = ResetConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        candidate = find_user(v["identifier"])
        if candidate is not None:
            try:
                password_validation.validate_password(v["new_password"], candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"new_password": list(exc.messages)}) from None
        user = confirm_reset(v["identifier"], v["code"])
        if user is None:
            return Response(
                {
                    "error": {
                        "code": "invalid_code",
                        "message": "That code is wrong or has expired. Request a new one.",
                        "fields": {"code": ["That code is wrong or has expired."]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(v["new_password"])
        clear_temporary_flags(user)
        user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])
        end_sessions(user)
        unlock_user(user)
        record(
            "account.password_reset",
            "Reset password with a one-time code",
            category=Category.ACCOUNT,
            request=request,
            actor=user,
        )
        return Response({"detail": "Password changed. Sign in with your new password."})


def unlock_user(user) -> None:
    """Clear django-axes failed-login lockouts for this account."""
    from axes.utils import reset  # noqa: PLC0415

    for name in [user.email] + ([user.username] if user.username else []):
        reset(username=name)
