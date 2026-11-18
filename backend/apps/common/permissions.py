from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    """Super Admin only. Determined from the database user row, never from request data."""

    message = "Platform administrator access required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_platform_admin)
