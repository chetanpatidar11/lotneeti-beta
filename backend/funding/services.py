from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import record_event
from funding.models import BalanceChange, BankAccount


@transaction.atomic
def _apply_delta(
    *, bank: BankAccount, delta: Decimal, operation: str, action: str, actor, note: str
) -> BalanceChange:
    locked_bank = BankAccount.objects.select_for_update().get(pk=bank.pk)
    old_balance = locked_bank.current_balance
    new_balance = old_balance + delta
    locked_bank.current_balance = new_balance
    locked_bank.save(update_fields=["current_balance", "updated_at"])
    change = BalanceChange.objects.create(
        bank=locked_bank,
        operation=operation,
        old_balance=old_balance,
        delta=delta,
        new_balance=new_balance,
        note=note,
        actor=actor,
    )
    record_event(action=action, target=change, actor=actor, workspace=locked_bank.workspace)
    return change


def add_money(*, bank: BankAccount, amount: Decimal, actor, note: str = "") -> BalanceChange:
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero")
    return _apply_delta(
        bank=bank,
        delta=amount,
        operation=BalanceChange.Operation.ADD,
        action="balance.added",
        actor=actor,
        note=note,
    )


def remove_money(*, bank: BankAccount, amount: Decimal, actor, note: str = "") -> BalanceChange:
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero")
    return _apply_delta(
        bank=bank,
        delta=-amount,
        operation=BalanceChange.Operation.REMOVE,
        action="balance.removed",
        actor=actor,
        note=note,
    )


@transaction.atomic
def set_balance(*, bank: BankAccount, amount: Decimal, actor, note: str = "") -> BalanceChange:
    locked_bank = BankAccount.objects.select_for_update().get(pk=bank.pk)
    old_balance = locked_bank.current_balance
    delta = amount - old_balance
    locked_bank.current_balance = amount
    locked_bank.save(update_fields=["current_balance", "updated_at"])
    change = BalanceChange.objects.create(
        bank=locked_bank,
        operation=BalanceChange.Operation.SET,
        old_balance=old_balance,
        delta=delta,
        new_balance=amount,
        note=note,
        actor=actor,
    )
    record_event(action="balance.set", target=change, actor=actor, workspace=locked_bank.workspace)
    return change


@transaction.atomic
def transfer_money(
    *, source: BankAccount, destination: BankAccount, amount: Decimal, actor, note: str = ""
) -> tuple[BalanceChange, BalanceChange]:
    if source.pk == destination.pk:
        raise ValidationError("Choose two different bank accounts.")
    if source.workspace_id != destination.workspace_id:
        raise ValidationError("Both bank accounts must belong to the same workspace.")
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")

    # A stable lock order keeps simultaneous opposite-direction transfers safe.
    locked = {
        bank.pk: bank
        for bank in BankAccount.objects.select_for_update()
        .select_related("owner")
        .filter(pk__in=[source.pk, destination.pk])
        .order_by("pk")
    }
    if len(locked) != 2:
        raise ValidationError("Choose two existing bank accounts.")
    from_bank, to_bank = locked[source.pk], locked[destination.pk]
    if not from_bank.active or not to_bank.active:
        raise ValidationError("Both bank accounts must be active.")
    if from_bank.is_placeholder or to_bank.is_placeholder:
        raise ValidationError("Complete the real bank details before recording a transfer.")
    if from_bank.current_balance < amount:
        raise ValidationError("The transfer amount exceeds the source bank balance.")
    if to_bank.current_balance + amount > Decimal("999999999999.99"):
        raise ValidationError("The destination bank balance would exceed the allowed limit.")

    transfer_id = uuid4()
    from_old, to_old = from_bank.current_balance, to_bank.current_balance
    from_bank.current_balance -= amount
    to_bank.current_balance += amount
    from_bank.save(update_fields=["current_balance", "updated_at"])
    to_bank.save(update_fields=["current_balance", "updated_at"])
    from_change = BalanceChange.objects.create(
        bank=from_bank,
        operation=BalanceChange.Operation.TRANSFER_OUT,
        old_balance=from_old,
        delta=-amount,
        new_balance=from_bank.current_balance,
        note=note,
        actor=actor,
        transfer_id=transfer_id,
        counterparty_label=(
            f"{to_bank.bank_name} · {to_bank.owner.name} · {to_bank.account_masked}"[:180]
        ),
    )
    to_change = BalanceChange.objects.create(
        bank=to_bank,
        operation=BalanceChange.Operation.TRANSFER_IN,
        old_balance=to_old,
        delta=amount,
        new_balance=to_bank.current_balance,
        note=note,
        actor=actor,
        transfer_id=transfer_id,
        counterparty_label=(
            f"{from_bank.bank_name} · {from_bank.owner.name} · {from_bank.account_masked}"[:180]
        ),
    )
    record_event(
        action="balance.transferred_out",
        target=from_change,
        actor=actor,
        workspace=from_bank.workspace,
        metadata={"transfer_id": str(transfer_id)},
    )
    record_event(
        action="balance.transferred_in",
        target=to_change,
        actor=actor,
        workspace=to_bank.workspace,
        metadata={"transfer_id": str(transfer_id)},
    )
    return from_change, to_change
