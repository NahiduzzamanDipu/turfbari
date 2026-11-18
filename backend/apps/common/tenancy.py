"""Workspace tenancy. The tenant always comes from the user's membership, never from request data."""

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

ACTIVE_TURF_SESSION_KEY = "active_turf_id"


def memberships_for(user):
    from apps.turfs.models import TenantMembership, Turf

    if not (user and user.is_authenticated):
        return TenantMembership.objects.none()
    return (
        TenantMembership.objects.filter(user=user, is_active=True)
        .exclude(turf__status=Turf.Status.ARCHIVED)
        .select_related("turf")
    )


def resolve_membership(request):
    memberships = list(memberships_for(request.user))
    if not memberships:
        return None
    wanted = request.session.get(ACTIVE_TURF_SESSION_KEY) if hasattr(request, "session") else None
    for membership in memberships:
        if str(membership.turf_id) == wanted:
            return membership
    return memberships[0]


class TurfSuspended(PermissionDenied):
    default_code = "turf_suspended"
    default_detail = "This turf is suspended. Contact TURFOS support to reactivate it."


class IsTenantMember(BasePermission):
    """Sets request.tenant / request.membership. Views may declare:
    - owner_only = True          -> every method requires the OWNER role
    - owner_only_writes = True   -> unsafe methods require the OWNER role
    """

    message = "You don't have access to a turf workspace."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        membership = resolve_membership(request)
        if membership is None:
            return False
        request.membership = membership
        request.tenant = membership.turf

        is_owner = membership.role == membership.Role.OWNER
        unsafe = request.method not in SAFE_METHODS
        if getattr(view, "owner_only", False) and not is_owner:
            self.message = "Only the turf owner can do this."
            return False
        if unsafe and getattr(view, "owner_only_writes", False) and not is_owner:
            self.message = "Only the turf owner can change this."
            return False
        if unsafe and not membership.turf.is_operational:
            raise TurfSuspended()
        return True


class TenantViewSet(viewsets.ModelViewSet):
    """Base for every workspace collection: queries and writes are pinned to request.tenant.
    Objects belonging to another tenant are simply not in the queryset -> 404."""

    permission_classes = [IsTenantMember]

    def get_queryset(self):
        return super().get_queryset().filter(turf=self.request.tenant)

    def perform_create(self, serializer):
        serializer.save(turf=self.request.tenant)
