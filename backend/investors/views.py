from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from investors.models import DematAccount, Investor
from investors.serializers import DematAccountSerializer, InvestorSerializer


class InvestorViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InvestorSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_workspace(self):
        return get_object_or_404(
            Workspace.objects.filter(memberships__user=self.request.user),
            pk=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return Investor.objects.filter(workspace=self.get_workspace()).order_by(
            "planning_priority", "id"
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "workspace": self.get_workspace()}

    def perform_create(self, serializer):
        with transaction.atomic():
            investor = serializer.save()
            record_event(
                action="investor.created",
                target=investor,
                actor=self.request.user,
                workspace=investor.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            investor = serializer.save()
            record_event(
                action="investor.updated",
                target=investor,
                actor=self.request.user,
                workspace=investor.workspace,
            )


class DematAccountViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DematAccountSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_investor(self):
        return get_object_or_404(
            Investor.objects.filter(workspace__memberships__user=self.request.user),
            pk=self.kwargs["investor_id"],
            workspace_id=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return DematAccount.objects.filter(investor=self.get_investor()).order_by("id")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "investor": self.get_investor()}

    def perform_create(self, serializer):
        with transaction.atomic():
            demat = serializer.save()
            record_event(
                action="demat.created",
                target=demat,
                actor=self.request.user,
                workspace=demat.investor.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            demat = serializer.save()
            record_event(
                action="demat.updated",
                target=demat,
                actor=self.request.user,
                workspace=demat.investor.workspace,
            )
