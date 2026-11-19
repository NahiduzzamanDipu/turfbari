"""Super Admin account management: find users, fix access problems, manage turf memberships.

Rules: passwords are never shown or set directly — a reset issues a one-time temporary password that
must be replaced at next sign-in. Platform-admin accounts can't be changed here (break-glass deploy
setting only) and nobody acts on their own account. Every action writes an audit event.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.services import Category, record
from apps.bookings.phone import normalize_bd_phone
from apps.common.pagination import StandardPagination
from apps.common.permissions import IsPlatformAdmin
from apps.turfs.models import TenantMembership, Turf

from .models import TwoFactorDevice
from .passwords import create_user_with_temporary_password, end_sessions, issue_temporary_password
from .views import unlock_user

User = get_user_model()


def is_locked(user) -> bool:
    from axes.models import AccessAttempt  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    names = [user.email] + ([user.username] if user.username else [])
    cutoff = timezone.now() - settings.AXES_COOLOFF_TIME
    return AccessAttempt.objects.filter(
        username__in=names, failures_since_start__gte=settings.AXES_FAILURE_LIMIT, attempt_time__gte=cutoff
    ).exists()


def membership_row(m: TenantMembership) -> dict:
    return {
        "id": str(m.id),
        "turf_id": str(m.turf_id),
        "turf_name": m.turf.name,
        "turf_status": m.turf.status,
        "role": m.role,
        "is_active": m.is_active,
        "permissions": m.permissions,
    }


def user_row(user, *, detail: bool = False) -> dict:
    row = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username or "",
        "full_name": user.full_name,
        "phone": user.phone,
        "is_active": user.is_active,
        "is_platform_admin": user.is_platform_admin,
        "must_change_password": user.must_change_password,
        "temp_password_expires_at": user.temp_password_expires_at,
        "last_login": user.last_login,
        "date_joined": user.date_joined,
        "two_factor": hasattr(user, "two_factor") and user.two_factor.confirmed,
        "locked": is_locked(user),
        "memberships": [membership_row(m) for m in user.memberships.all()],
    }
    if detail:
        events = AuditEvent.objects.filter(Q(actor=user) | Q(target_type="user", target_id=str(user.pk)))
        row["security_events"] = [
            {
                "at": e.created_at,
                "action": e.action,
                "summary": e.summary,
                "ip": e.ip,
                "by": e.actor_label if e.actor_id != user.pk else "",
            }
            for e in events.filter(category=Category.ACCOUNT).order_by("-created_at")[:25]
        ]
    return row


def users_qs():
    return User.objects.select_related("two_factor").prefetch_related(
        Prefetch(
            "memberships", queryset=TenantMembership.objects.select_related("turf").order_by("turf__name")
        )
    )


class AccountCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    turf = serializers.UUIDField()
    role = serializers.ChoiceField(choices=TenantMembership.Role.choices)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise ValidationError(
                "An account with this email already exists — add a membership to it instead."
            )
        return value

    def validate_phone(self, value):
        return normalize_bd_phone(value) if value else ""


class AccountUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    username = serializers.RegexField(r"^[a-zA-Z0-9_.-]{3,40}$", required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exclude(pk=self.context["user"].pk).exists():
            raise ValidationError("Another account uses this email.")
        return value

    def validate_username(self, value):
        value = value.strip().lower()
        if value and User.objects.filter(username=value).exclude(pk=self.context["user"].pk).exists():
            raise ValidationError("Another account uses this username.")
        return value

    def validate_phone(self, value):
        return normalize_bd_phone(value) if value else ""


def _editable(request, user):
    if user.is_platform_admin:
        raise ValidationError({"detail": ["Platform administrator accounts can't be changed here."]})
    if user.pk == request.user.pk:
        raise ValidationError({"detail": ["You can't change your own account here."]})


def _audit(request, action: str, summary: str, user, data=None):
    record(
        f"platform.user_{action}", summary, category=Category.ACCOUNT, request=request, target=user, data=data
    )


class AccountListView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request):
        qs = users_qs().order_by("-date_joined")
        params = request.query_params
        if q := params.get("q", "").strip()[:80]:
            digits = "".join(ch for ch in q if ch.isdigit())
            cond = (
                Q(email__icontains=q)
                | Q(username__icontains=q)
                | Q(full_name__icontains=q)
                | Q(memberships__turf__name__icontains=q)
            )
            if len(digits) >= 5:
                cond |= Q(phone__contains=digits[-10:])
            qs = qs.filter(cond).distinct()
        state = params.get("state")
        if state == "inactive":
            qs = qs.filter(is_active=False)
        elif state == "temporary":
            qs = qs.filter(must_change_password=True)
        elif state == "admins":
            qs = qs.filter(is_platform_admin=True)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([user_row(u) for u in page])

    @extend_schema(tags=["admin"], request=AccountCreateSerializer)
    @transaction.atomic
    def post(self, request):
        data = AccountCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        turf = Turf.objects.filter(pk=v["turf"]).first()
        if turf is None:
            raise ValidationError({"turf": ["Unknown turf."]})
        user, password = create_user_with_temporary_password(
            v["email"], full_name=v["full_name"], phone=v.get("phone", "")
        )
        TenantMembership.objects.create(user=user, turf=turf, role=v["role"])
        _audit(request, "created", f"Created {v['role']} account {user.email} for {turf.name}", user)
        user = users_qs().get(pk=user.pk)
        return Response({**user_row(user), "temporary_password": password}, status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"])
    def get(self, request, pk):
        return Response(user_row(get_object_or_404(users_qs(), pk=pk), detail=True))

    @extend_schema(tags=["admin"], request=AccountUpdateSerializer)
    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        _editable(request, user)
        data = AccountUpdateSerializer(data=request.data, context={"user": user}, partial=True)
        data.is_valid(raise_exception=True)
        changed = [
            k
            for k, v in data.validated_data.items()
            if getattr(user, k) != (v or None if k == "username" else v)
        ]
        for key, value in data.validated_data.items():
            setattr(user, key, value)
        user.save()
        if changed:
            _audit(
                request,
                "updated",
                f"Edited account {user.email}: {', '.join(changed)}",
                user,
                {"fields": changed},
            )
        return Response(user_row(users_qs().get(pk=user.pk), detail=True))


ACTIONS = {
    "activate": "Activated",
    "deactivate": "Deactivated",
    "unlock": "Unlocked sign-in for",
    "reset-password": "Issued a temporary password to",
    "force-change": "Required a password change for",
    "end-sessions": "Signed out every session of",
    "disable-2fa": "Turned off two-step sign-in for",
}


class AccountActionView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=None)
    @transaction.atomic
    def post(self, request, pk, action):
        if action not in ACTIONS:
            return Response(status=status.HTTP_404_NOT_FOUND)
        user = get_object_or_404(User.objects.select_for_update(), pk=pk)
        _editable(request, user)
        extra = {}
        if action == "activate":
            user.is_active = True
            user.save(update_fields=["is_active"])
        elif action == "deactivate":
            user.is_active = False
            user.save(update_fields=["is_active"])
            extra["sessions_ended"] = end_sessions(user)
        elif action == "unlock":
            unlock_user(user)
        elif action == "reset-password":
            extra["temporary_password"] = issue_temporary_password(user)
            extra["sessions_ended"] = end_sessions(user)
            unlock_user(user)
        elif action == "force-change":
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])
            extra["sessions_ended"] = 0
        elif action == "end-sessions":
            extra["sessions_ended"] = end_sessions(user)
        elif action == "disable-2fa":
            TwoFactorDevice.objects.filter(user=user).delete()
        _audit(request, action.replace("-", "_"), f"{ACTIONS[action]} {user.email}", user)
        return Response({**user_row(users_qs().get(pk=user.pk), detail=True), **extra})


class MembershipSerializer(serializers.Serializer):
    turf = serializers.UUIDField(required=False)
    role = serializers.ChoiceField(choices=TenantMembership.Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)


def _keeps_an_owner(turf, *, excluding) -> bool:
    return (
        TenantMembership.objects.filter(turf=turf, role=TenantMembership.Role.OWNER, is_active=True)
        .exclude(pk=excluding.pk)
        .exists()
    )


class AccountMembershipsView(APIView):
    """Add the user to a turf (or re-activate an old membership)."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=MembershipSerializer)
    @transaction.atomic
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        _editable(request, user)
        data = MembershipSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        turf = Turf.objects.filter(pk=v.get("turf")).first()
        if turf is None:
            raise ValidationError({"turf": ["Choose a turf."]})
        role = v.get("role", TenantMembership.Role.MANAGER)
        membership, created = TenantMembership.objects.get_or_create(
            user=user, turf=turf, defaults={"role": role}
        )
        if not created:
            if membership.is_active:
                raise ValidationError({"turf": ["This user is already a member of that turf."]})
            membership.is_active, membership.role = True, role
            membership.save(update_fields=["is_active", "role", "updated_at"])
        _audit(request, "membership_added", f"Added {user.email} to {turf.name} as {role}", user)
        return Response(user_row(users_qs().get(pk=user.pk), detail=True), status=status.HTTP_201_CREATED)


class MembershipDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(tags=["admin"], request=MembershipSerializer)
    @transaction.atomic
    def patch(self, request, pk):
        membership = get_object_or_404(TenantMembership.objects.select_related("user", "turf"), pk=pk)
        _editable(request, membership.user)
        data = MembershipSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        role = v.get("role", membership.role)
        active = v.get("is_active", membership.is_active)
        losing_owner = membership.role == TenantMembership.Role.OWNER and membership.is_active
        if losing_owner and (role != TenantMembership.Role.OWNER or not active):
            if not _keeps_an_owner(membership.turf, excluding=membership):
                raise ValidationError({"role": [f"{membership.turf.name} needs at least one active owner."]})
        membership.role, membership.is_active = role, active
        membership.save(update_fields=["role", "is_active", "updated_at"])
        _audit(
            request,
            "membership_changed",
            f"{membership.user.email} at {membership.turf.name}: {role}, {'active' if active else 'removed'}",
            membership.user,
        )
        return Response(user_row(users_qs().get(pk=membership.user_id), detail=True))
