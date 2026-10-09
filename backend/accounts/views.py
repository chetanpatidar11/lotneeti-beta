from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from accounts.models import Workspace
from accounts.permissions import IsWorkspaceOwnerOrReadOnly
from accounts.serializers import WorkspaceSerializer
from core.audit import record_event


class WorkspaceViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated, IsWorkspaceOwnerOrReadOnly]

    def get_queryset(self):
        return Workspace.objects.filter(memberships__user=self.request.user).order_by(
            "created_at", "id"
        )

    def perform_update(self, serializer):
        with transaction.atomic():
            workspace = serializer.save()
            record_event(
                action="workspace.updated",
                target=workspace,
                actor=self.request.user,
                workspace=workspace,
                metadata={"fields": sorted(serializer.validated_data)},
            )
