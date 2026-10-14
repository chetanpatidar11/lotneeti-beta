"""Workspace-scoped removal of account master records without losing history."""

from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Workspace
from accounts.permissions import WorkspaceDataPermission
from applications.models import Application
from core.audit import record_event
from funding.models import (
    ArchivedBalanceChange,
    BalanceChange,
    BankAccount,
    RecurringDebit,
    UPIHandle,
)
from investors.models import DematAccount, Investor
from planner.models import PlannerPolicy, PlanRow, PlanRun


class SettingsSelectionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("investor", "demat", "bank", "upi"))
    action = serializers.ChoiceField(
        choices=("remove", "restore", "deactivate", "activate", "delete")
    )
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
    if kind == "bank" and BankAccount.objects.filter(pk__in=ids, is_placeholder=True).exists():
        raise ValidationError(
            {"message": "Enter the real bank name and account number before activating."}
        )
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


def _check_permanent_delete(kind, ids, workspace):
    """Prevent deletion of records used by applications, plans, or real money history."""
    investors = (
        Investor.objects.filter(workspace=workspace, pk__in=ids)
        if kind == "investor"
        else Investor.objects.none()
    )
    demats = (
        DematAccount.objects.filter(investor__in=investors)
        if kind == "investor"
        else DematAccount.objects.filter(pk__in=ids)
        if kind == "demat"
        else DematAccount.objects.none()
    )
    banks = (
        BankAccount.objects.filter(owner__in=investors)
        if kind == "investor"
        else BankAccount.objects.filter(pk__in=ids)
        if kind == "bank"
        else BankAccount.objects.none()
    )
    upis = (
        UPIHandle.objects.filter(Q(bank__in=banks) | Q(holder__in=investors))
        if kind == "investor"
        else UPIHandle.objects.filter(bank__in=banks)
        if kind == "bank"
        else UPIHandle.objects.filter(pk__in=ids)
        if kind == "upi"
        else UPIHandle.objects.none()
    )
    if (
        Application.objects.filter(workspace=workspace)
        .filter(
            Q(applicant__in=investors) | Q(demat__in=demats) | Q(bank__in=banks) | Q(upi__in=upis)
        )
        .exists()
    ):
        raise ValidationError(
            {"message": "This record is linked to an application. Deactivate it instead."}
        )
    if kind not in {"bank", "investor"} and (
        PlanRow.objects.filter(plan_run__workspace=workspace)
        .filter(
            Q(applicant_ref__in=[str(pk) for pk in investors.values_list("pk", flat=True)])
            | Q(demat_ref__in=[str(pk) for pk in demats.values_list("pk", flat=True)])
            | Q(bank_ref__in=[str(pk) for pk in banks.values_list("pk", flat=True)])
            | Q(upi_ref__in=[str(pk) for pk in upis.values_list("pk", flat=True)])
        )
        .exists()
    ):
        raise ValidationError(
            {"message": "This record is linked to a saved plan. Deactivate it instead."}
        )
    references = [
        str(pk)
        for queryset in (investors, demats, banks, upis)
        for pk in queryset.values_list("pk", flat=True)
    ]
    if kind not in {"bank", "investor"} and any(
        PlanRun.objects.filter(workspace=workspace, input_snapshot__contains=reference).exists()
        for reference in references
    ):
        raise ValidationError(
            {"message": "This record appears in a saved plan. Deactivate it instead."}
        )
    if kind == "investor" and (
        BankAccount.objects.filter(restricted_investor__in=investors).exclude(pk__in=banks).exists()
        or UPIHandle.objects.filter(holder__in=investors).exclude(bank__in=banks).exists()
    ):
        raise ValidationError({"message": "Remove linked funding rules and UPIs first."})
    if kind not in {"bank", "investor"} and banks.exclude(current_balance=0).exists():
        raise ValidationError(
            {"message": "Set linked bank balances to ₹0 before permanent deletion."}
        )
    if kind in {"bank", "investor"}:
        for bank in banks.exclude(current_balance=0):
            if not BalanceChange.objects.filter(bank=bank).exists():
                raise ValidationError(
                    {"message": "This bank has a balance without history. Deactivate it instead."}
                )
    if (
        RecurringDebit.objects.filter(bank__in=banks).exists()
        or PlannerPolicy.objects.filter(bank__in=banks).exists()
    ):
        raise ValidationError(
            {"message": "This bank has payment or policy history. Deactivate it instead."}
        )
    if kind not in {"bank", "investor"}:
        for change in BalanceChange.objects.filter(bank__in=banks):
            if not (
                change.operation == BalanceChange.Operation.SET
                and change.old_balance == 0
                and change.delta == 0
                and change.new_balance == 0
                and change.note
                in {"Opening balance", "Imported account; set the current Balance before planning."}
            ):
                raise ValidationError(
                    {"message": "This bank has balance history. Deactivate it instead."}
                )


def _archive_bank_balance_history(bank, workspace):
    for change in BalanceChange.objects.filter(bank=bank).select_for_update():
        ArchivedBalanceChange.objects.create(
            workspace=workspace,
            bank_ref=bank.pk,
            bank_name=bank.bank_name,
            account_masked=bank.account_masked,
            source_change_id=change.pk,
            operation=change.operation,
            old_balance=change.old_balance,
            delta=change.delta,
            new_balance=change.new_balance,
            note=change.note,
            actor_id=change.actor_id,
            created_at=change.created_at,
        )
    BalanceChange.objects.filter(bank=bank).delete()


def _delete_item(item, kind, request, workspace):
    if kind == "investor":
        banks = list(BankAccount.objects.filter(owner=item).select_for_update())
        for bank in banks:
            _archive_bank_balance_history(bank, workspace)
            bank.delete()
    elif kind == "bank":
        _archive_bank_balance_history(item, workspace)
    record_event(action=f"{kind}.deleted", target=item, actor=request.user, workspace=workspace)
    item.delete()


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
            if action in {"remove", "deactivate"}:
                if kind == "investor":
                    # Balance actions lock bank rows; serialize them with this check.
                    list(BankAccount.objects.filter(owner_id__in=ids).select_for_update())
                _check_removal(kind, ids, workspace)
            elif action in {"restore", "activate"}:
                _check_restore(kind, ids)
            else:
                _check_permanent_delete(kind, ids, workspace)
                try:
                    for item in items:
                        _delete_item(item, kind, request, workspace)
                except ProtectedError as exc:
                    raise ValidationError(
                        {"message": "This record has saved history. Deactivate it instead."}
                    ) from exc
                return Response({"updated": len(items)})

            active = action in {"restore", "activate"}
            changed = []
            for item in items:
                if item.active != active:
                    item.active = active
                    item.save(update_fields=["active", "updated_at"])
                    changed.append(item)

            # An inactive parent must never leave usable child funding accounts behind.
            if not active and kind == "investor":
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
            elif not active and kind == "bank":
                _archive_related(
                    UPIHandle.objects.filter(bank_id__in=ids), "upi", request, workspace
                )

            for item in changed:
                record_event(
                    action=f"{kind}.restored" if active else f"{kind}.removed",
                    target=item,
                    actor=request.user,
                    workspace=workspace,
                )
        return Response({"updated": len(changed)})
