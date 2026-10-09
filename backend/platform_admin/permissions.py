from rest_framework.permissions import BasePermission


class IsFounderAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.is_active
            and user.is_staff
            and user.is_founder_admin
            and request.session.get("admin_mfa_verified", False)
        )
