from decimal import Decimal

from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import WorkspaceDataPermission
from funding.models import ArchivedBalanceChange, BalanceChange, BankAccount
from funding.services import add_money, remove_money, set_balance


class BalanceAmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class SetBalanceSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class BalanceActionView(APIView):
    permission_classes = [WorkspaceDataPermission]
    apply_change = None
    serializer_class = BalanceAmountSerializer

    def post(self, request, workspace_id, bank_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        bank = get_object_or_404(
            BankAccount.objects.filter(workspace__memberships__user=request.user),
            workspace_id=workspace_id,
            pk=bank_id,
        )
        if bank.is_placeholder:
            raise ValidationError("Complete the real bank details before setting a balance.")
        change = self.apply_change(
            bank=bank,
            amount=serializer.validated_data["amount"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(
            {
                "id": change.pk,
                "operation": change.operation,
                "amount": str(serializer.validated_data["amount"]),
                "balance": str(change.new_balance),
            },
            status=status.HTTP_201_CREATED,
        )


class AddMoneyView(BalanceActionView):
    apply_change = staticmethod(add_money)


class RemoveMoneyView(BalanceActionView):
    apply_change = staticmethod(remove_money)


class SetBalanceView(BalanceActionView):
    apply_change = staticmethod(set_balance)
    serializer_class = SetBalanceSerializer


class RecentBalanceChangesView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def get(self, request, workspace_id, bank_id):
        bank = BankAccount.objects.filter(workspace_id=workspace_id, pk=bank_id).first()
        if bank is not None:
            changes = BalanceChange.objects.filter(bank=bank).order_by("-created_at", "-id")[:10]
        else:
            changes = ArchivedBalanceChange.objects.filter(
                workspace_id=workspace_id, bank_ref=bank_id
            ).order_by("-created_at", "-source_change_id")
            if not changes.exists():
                raise NotFound("Bank history was not found in this workspace.")
        return Response(
            [
                {
                    "id": change.pk,
                    "operation": change.operation,
                    "amount": str(
                        change.new_balance
                        if change.operation == BalanceChange.Operation.SET
                        else abs(change.delta)
                    ),
                    "balance": str(change.new_balance),
                    "note": change.note,
                    "created_at": change.created_at.isoformat(),
                }
                for change in changes
            ]
        )


class ArchivedBankHistoryListView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def get(self, request, workspace_id):
        banks = (
            ArchivedBalanceChange.objects.filter(workspace_id=workspace_id)
            .values("bank_ref", "bank_name", "account_masked")
            .annotate(last_changed=Max("created_at"))
            .order_by("-last_changed", "bank_ref")
        )
        return Response(
            [
                {
                    "id": str(bank["bank_ref"]),
                    "bank_name": bank["bank_name"],
                    "account_masked": bank["account_masked"],
                    "last_changed": bank["last_changed"].isoformat(),
                }
                for bank in banks
            ]
        )
