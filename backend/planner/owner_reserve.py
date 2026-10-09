"""Protect an owner's baseline Retail cash before cross-funding a bank."""

from datetime import datetime
from decimal import Decimal

from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.dto import BankInput, CashBlockInput, IPOInput, RecurringDebitInput
from planner.quotes import retail_quote


def owner_baseline_reserve_at(
    *, at: datetime, owner_ipos: tuple[IPOInput, ...], covered_ipo_ids: frozenset[str] = frozenset()
) -> Decimal:
    """Unplaced owner Retail quotes whose cash windows include ``at``."""
    return sum(
        (
            retail_quote(ipo.upper_price, ipo.lot_size).amount
            for ipo in owner_ipos
            if ipo.selected
            and ipo.id not in covered_ipo_ids
            and ipo.cutoff_at <= at < expected_release_at(ipo.allotment_date, ipo.cutoff_at.tzinfo)
        ),
        Decimal("0.00"),
    )


def cross_fundable_cash(
    *,
    bank: BankInput,
    at: datetime,
    release_at: datetime,
    owner_ipos: tuple[IPOInput, ...],
    covered_ipo_ids: frozenset[str] = frozenset(),
    blocks: tuple[CashBlockInput, ...] = (),
    allocations: tuple[PlannedAllocation, ...] = (),
    recurring_debits: tuple[RecurringDebitInput, ...] = (),
) -> Decimal:
    """Smallest surplus through the cross-funded row's active cash window.

    The caller passes only IPOs for which the bank owner still needs baseline
    coverage. Already placed owner rows are supplied as allocations instead.
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Application time must have a timezone")
    if release_at.tzinfo is None or release_at.utcoffset() is None or release_at <= at:
        raise ValueError("Release must be after the application time")
    checkpoints = {at}
    checkpoints.update(
        ipo.cutoff_at for ipo in owner_ipos if ipo.selected and at < ipo.cutoff_at < release_at
    )
    return min(
        (
            cash_at_cutoff(
                bank=bank,
                cutoff=checkpoint,
                blocks=blocks,
                allocations=allocations,
                recurring_debits=recurring_debits,
            ).raw_available
            - owner_baseline_reserve_at(
                at=checkpoint, owner_ipos=owner_ipos, covered_ipo_ids=covered_ipo_ids
            )
            for checkpoint in checkpoints
        ),
        default=bank.balance,
    )
