from decimal import Decimal

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
