"""Workspace tenancy. The tenant always comes from the user's membership, never from request data."""

from rest_framework import viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.audit.services import AuditedViewSetMixin, label

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
    default_detail = "This turf is suspended. Contact TurfBari support to reactivate it."


class SubscriptionInactive(APIException):
    status_code = 402
    default_code = "subscription_inactive"
    default_detail = (
        "Your TurfBari subscription has ended. Renew it from the Subscription page to keep taking bookings."
    )


class IsTenantMember(BasePermission):
    """Sets request.tenant / request.membership. Views may declare:
    - owner_only = True          -> every method requires the OWNER role
    - owner_only_writes = True   -> unsafe methods require the OWNER role
    - allow_inactive_subscription = True -> writes allowed even when the subscription has lapsed
    - manager_permission = "x"   -> with owner_only_writes: managers holding permission "x" may write too
    - required_permission = "x"  -> every method requires permission "x" (owners always have it)
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
            granted = getattr(view, "manager_permission", None)
            if not (granted and membership.can(granted)):
                self.message = "Only the turf owner can change this."
                return False
        required = getattr(view, "required_permission", None)
        if required and not membership.can(required):
            self.message = "Your turf owner hasn't given you access to this."
            return False
        if unsafe and not membership.turf.is_operational:
            raise TurfSuspended()
        if unsafe and not getattr(view, "allow_inactive_subscription", False):
            from apps.subscriptions.services import standing

            if not standing(membership.turf).can_operate:
                raise SubscriptionInactive()
        return True


class TenantViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Base for every workspace collection: queries and writes are pinned to request.tenant.
    Objects belonging to another tenant are simply not in the queryset -> 404."""

    permission_classes = [IsTenantMember]

    def get_queryset(self):
        return super().get_queryset().filter(turf=self.request.tenant)

    def perform_create(self, serializer, **extra):
        serializer.save(turf=self.request.tenant, **extra)
        self._audit("added", serializer.instance)

    def perform_update(self, serializer):
        changed = sorted(serializer.validated_data)
        serializer.save()
        self._audit("updated", serializer.instance, {"fields": changed})

    def perform_destroy(self, instance):
        name, pk, kind = label(instance), instance.pk, type(instance).__name__.lower()
        instance.delete()
        self._audit_deleted(name, pk, kind)
