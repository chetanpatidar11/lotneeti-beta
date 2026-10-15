from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets

from accounts.models import Workspace, WorkspaceMembership
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from investors.models import DematAccount, Investor
from investors.serializers import DematAccountSerializer, InvestorSerializer


class SensitiveNoStoreMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class InvestorViewSet(
    SensitiveNoStoreMixin,
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
        return Investor.objects.filter(workspace=self.get_workspace(), is_deleted=False).order_by(
            "planning_priority", "id"
        )

    def get_serializer_context(self):
        workspace = self.get_workspace()
        can_reveal = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=self.request.user,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists()
        return {
            **super().get_serializer_context(),
            "workspace": workspace,
            "reveal_details": can_reveal,
        }

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
    SensitiveNoStoreMixin,
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
            Investor.objects.filter(
                workspace__memberships__user=self.request.user, is_deleted=False
            ),
            pk=self.kwargs["investor_id"],
            workspace_id=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return DematAccount.objects.filter(investor=self.get_investor()).order_by("id")

    def get_serializer_context(self):
        investor = self.get_investor()
        can_edit = WorkspaceMembership.objects.filter(
            workspace=investor.workspace,
            user=self.request.user,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
        ).exists()
        return {
            **super().get_serializer_context(),
            "investor": investor,
            "reveal_details": self.action == "retrieve" and can_edit,
            "display_details": can_edit,
        }

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
