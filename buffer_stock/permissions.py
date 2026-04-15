from rest_framework import permissions


def _get_role(user):
    """Return the user's role from their profile, or empty string."""
    profile = getattr(user, "userprofile", None)
    return getattr(profile, "role", "")


def _get_region(user):
    """Return the user's region from their profile, or empty string."""
    profile = getattr(user, "userprofile", None)
    return getattr(profile, "region", "") or ""


class IsSuperAdminOrManager(permissions.BasePermission):
    """Only super_admin / admin / manager may access."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = _get_role(request.user)
        return role in ("super_admin", "admin", "manager")


class CanApproveOOW(permissions.BasePermission):
    """Only super_admin / admin / manager may approve OOW requests."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = _get_role(request.user)
        return role in ("super_admin", "admin", "manager")


class CanApproveTransfer(permissions.BasePermission):
    """Super admin, admin, or manager may approve inter-region transfers."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = _get_role(request.user)
        return role in ("super_admin", "admin", "manager")


class IsAuthenticated(permissions.BasePermission):
    """Standard authentication check."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
