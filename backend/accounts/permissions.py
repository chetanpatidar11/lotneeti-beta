from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import WorkspaceMembership


class IsWorkspaceOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return WorkspaceMembership.objects.filter(
            workspace=obj, user=request.user, role=WorkspaceMembership.Role.OWNER
        ).exists()


class WorkspaceDataPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        membership = WorkspaceMembership.objects.filter(
            workspace_id=view.kwargs["workspace_id"], user=request.user
        ).first()
        if membership is None:
            return False
        return request.method in SAFE_METHODS or membership.role in {
            WorkspaceMembership.Role.OWNER,
            WorkspaceMembership.Role.OPERATOR,
        }
