from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from core.audit import record_event
from funding.models import BankAccount, FundingPreference, RecurringDebit, UPIHandle
from funding.serializers import (
    BankAccountSerializer,
    FundingPreferenceSerializer,
    RecurringDebitSerializer,
    UPIHandleSerializer,
)
from investors.models import Investor


class BankAccountViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = BankAccountSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_workspace(self):
        return get_object_or_404(
            Workspace.objects.filter(memberships__user=self.request.user),
            pk=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return BankAccount.objects.filter(workspace=self.get_workspace()).order_by(
            "bank_name", "id"
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "workspace": self.get_workspace()}

    def perform_create(self, serializer):
        with transaction.atomic():
            bank = serializer.save()
            record_event(
                action="bank.created",
                target=bank,
                actor=self.request.user,
                workspace=bank.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            bank = serializer.save()
            record_event(
                action="bank.updated",
                target=bank,
                actor=self.request.user,
                workspace=bank.workspace,
            )


class UPIHandleViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UPIHandleSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_bank(self):
        return get_object_or_404(
            BankAccount.objects.filter(workspace__memberships__user=self.request.user),
            pk=self.kwargs["bank_id"],
            workspace_id=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return UPIHandle.objects.filter(bank=self.get_bank()).order_by("id")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "bank": self.get_bank()}

    def perform_create(self, serializer):
        with transaction.atomic():
            upi = serializer.save()
            record_event(
                action="upi.created",
                target=upi,
                actor=self.request.user,
                workspace=upi.bank.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            upi = serializer.save()
            record_event(
                action="upi.updated",
                target=upi,
                actor=self.request.user,
                workspace=upi.bank.workspace,
            )


class RecurringDebitViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = RecurringDebitSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_bank(self):
        return get_object_or_404(
            BankAccount.objects.filter(workspace__memberships__user=self.request.user),
            pk=self.kwargs["bank_id"],
            workspace_id=self.kwargs["workspace_id"],
        )

    def get_queryset(self):
        return RecurringDebit.objects.filter(
            bank=self.get_bank(), archived_at__isnull=True
        ).order_by("next_due_date", "id")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "bank": self.get_bank()}

    def perform_create(self, serializer):
        with transaction.atomic():
            schedule = serializer.save()
            record_event(
                action="recurring_debit.created",
                target=schedule,
                actor=self.request.user,
                workspace=schedule.bank.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            schedule = serializer.save()
            record_event(
                action="recurring_debit.updated",
                target=schedule,
                actor=self.request.user,
                workspace=schedule.bank.workspace,
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance.active = False
            instance.archived_at = timezone.now()
            instance.save(update_fields=["active", "archived_at", "updated_at"])
            record_event(
                action="recurring_debit.deleted",
                target=instance,
                actor=self.request.user,
                workspace=instance.bank.workspace,
            )


class FundingPreferenceViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FundingPreferenceSerializer
    permission_classes = [WorkspaceDataPermission]

    def get_beneficiary(self):
        return get_object_or_404(
            Investor.objects.filter(workspace__memberships__user=self.request.user),
            workspace_id=self.kwargs["workspace_id"],
            pk=self.kwargs["investor_id"],
        )

    def get_queryset(self):
        return FundingPreference.objects.filter(beneficiary=self.get_beneficiary()).order_by(
            "priority", "bank_id"
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "beneficiary": self.get_beneficiary()}

    def perform_create(self, serializer):
        with transaction.atomic():
            preference = serializer.save()
            record_event(
                action="funding_preference.created",
                target=preference,
                actor=self.request.user,
                workspace=preference.beneficiary.workspace,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            preference = serializer.save()
            record_event(
                action="funding_preference.updated",
                target=preference,
                actor=self.request.user,
                workspace=preference.beneficiary.workspace,
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            record_event(
                action="funding_preference.deleted",
                target=instance,
                actor=self.request.user,
                workspace=instance.beneficiary.workspace,
            )
            instance.delete()
