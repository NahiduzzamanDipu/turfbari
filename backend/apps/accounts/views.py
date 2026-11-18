"""Unified login: one form for Super Admin, owners and managers. Destination decided server-side."""

from django.contrib.auth import authenticate, login, logout, password_validation, update_session_auth_hash
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.tenancy import ACTIVE_TURF_SESSION_KEY, memberships_for, resolve_membership

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
        },
        "memberships": [
            {"turf_id": str(m.turf_id), "turf_name": m.turf.name, "turf_slug": m.turf.slug, "role": m.role}
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
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, tags=["auth"])
    def post(self, request):
        data = ChangePasswordSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        request.user.set_password(data.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        membership = resolve_membership(request)
        record(
            "account.password_changed",
            "Changed password",
            category=Category.ACCOUNT,
            request=request,
            turf=membership.turf if membership else None,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
