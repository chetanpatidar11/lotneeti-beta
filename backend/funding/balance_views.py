from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import WorkspaceMembership
from accounts.permissions import WorkspaceDataPermission
from funding.models import ArchivedBalanceChange, BalanceChange, BankAccount
from funding.serializers import BankAccountSerializer
from funding.services import add_money, remove_money, set_balance, transfer_money


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


class TransferSerializer(serializers.Serializer):
    source_bank = serializers.UUIDField()
    destination_bank = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["source_bank"] == attrs["destination_bank"]:
            raise ValidationError("Choose two different bank accounts.")
        return attrs


class BankTransferView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def post(self, request, workspace_id):
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        details = serializer.validated_data
        banks = BankAccount.objects.filter(workspace_id=workspace_id)
        source = get_object_or_404(banks, pk=details["source_bank"])
        destination = get_object_or_404(banks, pk=details["destination_bank"])
        try:
            from_change, to_change = transfer_money(
                source=source,
                destination=destination,
                amount=details["amount"],
                actor=request.user,
                note=details.get("note", "").strip(),
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        response = Response(
            {
                "transfer_id": str(from_change.transfer_id),
                "source_balance": str(from_change.new_balance),
                "destination_balance": str(to_change.new_balance),
            },
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "private, no-store"
        return response


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
                    "transfer_id": str(change.transfer_id) if change.transfer_id else None,
                    "counterparty_label": change.counterparty_label,
                    "created_at": change.created_at.isoformat(),
                }
                for change in changes
            ]
        )


class WorkspaceBalanceStatementView(APIView):
    permission_classes = [WorkspaceDataPermission]

    def get(self, request, workspace_id):
        bank_id = request.query_params.get("bank", "")
        banks = BankAccount.objects.filter(workspace_id=workspace_id)
        if bank_id:
            try:
                parsed_bank_id = UUID(bank_id)
            except ValueError as exc:
                raise ValidationError("Choose a valid bank account.") from exc
            bank = get_object_or_404(banks, pk=parsed_bank_id)
            banks = banks.filter(pk=bank.pk)
        try:
            page_number = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError("Page must be a positive number.") from exc
        if page_number < 1:
            raise ValidationError("Page must be a positive number.")
        changes = (
            BalanceChange.objects.filter(bank__in=banks)
            .select_related("bank", "bank__owner")
            .prefetch_related("bank__upis")
            .order_by("-created_at", "-id")
        )
        reveal = WorkspaceMembership.objects.filter(
            workspace_id=workspace_id, user=request.user, role__in=("OWNER", "OPERATOR")
        ).exists()
        bank_serializer = BankAccountSerializer(context={"display_details": reveal})
        pages = Paginator(changes, 50)
        page = pages.get_page(page_number)
        page_changes = list(page.object_list)
        transfer_ids = {change.transfer_id for change in page_changes if change.transfer_id}
        counterparties = {}
        for paired in (
            BalanceChange.objects.filter(
                bank__workspace_id=workspace_id, transfer_id__in=transfer_ids
            )
            .select_related("bank", "bank__owner")
            .prefetch_related("bank__upis")
        ):
            counterparties.setdefault(paired.transfer_id, []).append(paired.bank)

        def counterparty_label(change):
            for bank in counterparties.get(change.transfer_id, []):
                if bank.pk == change.bank_id:
                    continue
                identifiers = dict.fromkeys(
                    [
                        bank_serializer.get_account_display(bank),
                        *bank_serializer.get_linked_upis(bank),
                    ]
                )
                return " · ".join([bank.bank_name, bank.owner.name, *identifiers])
            return change.counterparty_label

        return Response(
            {
                "results": [
                    {
                        "id": change.pk,
                        "bank_id": str(change.bank_id),
                        "bank_name": change.bank.bank_name,
                        "owner_name": change.bank.owner.name,
                        "account_masked": change.bank.account_masked,
                        "account_display": bank_serializer.get_account_display(change.bank),
                        "linked_upis": bank_serializer.get_linked_upis(change.bank),
                        "operation": change.operation,
                        "delta": str(change.delta),
                        "amount": str(
                            change.new_balance
                            if change.operation == BalanceChange.Operation.SET
                            else abs(change.delta)
                        ),
                        "balance": str(change.new_balance),
                        "note": change.note,
                        "transfer_id": str(change.transfer_id) if change.transfer_id else None,
                        "counterparty_label": counterparty_label(change),
                        "created_at": change.created_at.isoformat(),
                    }
                    for change in page_changes
                ],
                "next_page": page.next_page_number() if page.has_next() else None,
                "total": pages.count,
            }
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
