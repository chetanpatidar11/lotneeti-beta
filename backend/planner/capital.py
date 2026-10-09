"""Simple workspace capital cards from current bank-level amounts."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CapitalTotals:
    balance: Decimal
    blocked: Decimal
    planned: Decimal
    available: Decimal


def capital_totals(
    balances: dict[str, Decimal],
    *,
    blocked_by_bank: dict[str, Decimal],
    planned_by_bank: dict[str, Decimal],
) -> CapitalTotals:
    zero = Decimal("0.00")
    return CapitalTotals(
        balance=sum(balances.values(), zero),
        blocked=sum((blocked_by_bank.get(bank_id, zero) for bank_id in balances), zero),
        planned=sum((planned_by_bank.get(bank_id, zero) for bank_id in balances), zero),
        available=sum(
            (
                max(
                    zero,
                    balance
                    - blocked_by_bank.get(bank_id, zero)
                    - planned_by_bank.get(bank_id, zero),
                )
                for bank_id, balance in balances.items()
            ),
            zero,
        ),
    )
