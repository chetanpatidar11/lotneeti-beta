"""Workspace-scoped removal of account master records without losing history."""

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from applications.models import Application
from core.audit import record_event
from funding.models import BankAccount, RecurringDebit, UPIHandle
from investors.models import DematAccount, Investor


class SettingsSelectionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("investor", "demat", "bank", "upi"))
    action = serializers.ChoiceField(choices=("remove", "restore"))
    ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False, min_length=1, max_length=100
    )


OPEN_APPLICATION_STATES = (
    Application.Status.PLANNED,
    Application.Status.SUBMITTED,
    Application.Status.BLOCKED,
)


def _queryset(kind, workspace):
    if kind == "investor":
        return Investor.objects.filter(workspace=workspace)
    if kind == "demat":
        return DematAccount.objects.filter(investor__workspace=workspace)
    if kind == "bank":
        return BankAccount.objects.filter(workspace=workspace)
    return UPIHandle.objects.filter(bank__workspace=workspace)


def _check_removal(kind, ids, workspace):
    applications = Application.objects.filter(
        workspace=workspace, status__in=OPEN_APPLICATION_STATES
    )
    if kind == "investor":
        banks = BankAccount.objects.filter(workspace=workspace, owner_id__in=ids)
        if banks.exclude(current_balance=0).exists():
            raise ValidationError(
                {"message": "Set linked bank balances to ₹0 before deleting an investor."}
            )
        if RecurringDebit.objects.filter(
            bank__in=banks, active=True, archived_at__isnull=True
        ).exists():
            raise ValidationError({"message": "Pause or delete linked scheduled payments first."})
        in_use = applications.filter(
            Q(applicant_id__in=ids) | Q(bank__owner_id__in=ids) | Q(upi__holder_id__in=ids)
        ).exists()
    elif kind == "bank":
        if BankAccount.objects.filter(pk__in=ids).exclude(current_balance=0).exists():
            raise ValidationError({"message": "Set selected bank balances to ₹0 before deleting."})
        if RecurringDebit.objects.filter(
            bank_id__in=ids, active=True, archived_at__isnull=True
        ).exists():
            raise ValidationError({"message": "Pause or delete linked scheduled payments first."})
        in_use = applications.filter(Q(bank_id__in=ids) | Q(upi__bank_id__in=ids)).exists()
    elif kind == "demat":
        in_use = applications.filter(demat_id__in=ids).exists()
    else:
        in_use = applications.filter(upi_id__in=ids).exists()
    if in_use:
        raise ValidationError(
            {"message": "Record the result of open applications before deleting."}
        )


def _check_restore(kind, ids):
    if kind == "demat" and DematAccount.objects.filter(pk__in=ids, investor__active=False).exists():
        raise ValidationError({"message": "Restore the investor first."})
    if kind == "bank" and BankAccount.objects.filter(pk__in=ids, owner__active=False).exists():
        raise ValidationError({"message": "Restore the investor first."})
    if (
        kind == "upi"
        and UPIHandle.objects.filter(pk__in=ids)
        .filter(Q(bank__active=False) | Q(holder__active=False))
        .exists()
    ):
        raise ValidationError({"message": "Restore the investor and bank first."})


def _archive_related(queryset, kind, request, workspace):
    for item in queryset.select_for_update().filter(active=True):
        item.active = False
        item.save(update_fields=["active", "updated_at"])
        record_event(
            action=f"{kind}.removed",
            target=item,
            actor=request.user,
            workspace=workspace,
        )


class SettingsItemsView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def post(self, request, workspace_id):
        serializer = SettingsSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind = serializer.validated_data["kind"]
        action = serializer.validated_data["action"]
        ids = set(serializer.validated_data["ids"])
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=request.user), pk=workspace_id
        )

        with transaction.atomic():
            items = list(_queryset(kind, workspace).select_for_update().filter(pk__in=ids))
            if len(items) != len(ids):
                raise NotFound("A selected item is no longer available in this workspace.")
            if action == "remove":
                if kind == "investor":
                    # Balance actions lock bank rows; serialize them with this check.
                    list(BankAccount.objects.filter(owner_id__in=ids).select_for_update())
                _check_removal(kind, ids, workspace)
            else:
                _check_restore(kind, ids)

            active = action == "restore"
            changed = []
            for item in items:
                if item.active != active:
                    item.active = active
                    item.save(update_fields=["active", "updated_at"])
                    changed.append(item)

            # An inactive parent must never leave usable child funding accounts behind.
            if action == "remove" and kind == "investor":
                _archive_related(
                    DematAccount.objects.filter(investor_id__in=ids),
                    "demat",
                    request,
                    workspace,
                )
                owned_banks = BankAccount.objects.filter(workspace=workspace, owner_id__in=ids)
                _archive_related(
                    UPIHandle.objects.filter(bank__workspace=workspace).filter(
                        Q(bank__in=owned_banks) | Q(holder_id__in=ids)
                    ),
                    "upi",
                    request,
                    workspace,
                )
                _archive_related(owned_banks, "bank", request, workspace)
            elif action == "remove" and kind == "bank":
                _archive_related(
                    UPIHandle.objects.filter(bank_id__in=ids), "upi", request, workspace
                )

            for item in changed:
                record_event(
                    action=f"{kind}.{action}d" if action == "restore" else f"{kind}.removed",
                    target=item,
                    actor=request.user,
                    workspace=workspace,
                )
        return Response({"updated": len(changed)})
