"""Pure cash availability at an application cutoff."""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from decimal import Decimal

from planner.dto import BankInput, CashBlockInput, RecurringDebitInput


@dataclass(frozen=True, slots=True)
class PlannedAllocation:
    id: str
    bank_id: str
    amount: Decimal
    cutoff_at: datetime
    release_at: datetime


@dataclass(frozen=True, slots=True)
class CashAtCutoff:
    balance: Decimal
    blocked: Decimal
    planned: Decimal
    scheduled_payments: Decimal
    raw_available: Decimal
    available: Decimal


def expected_release_at(allotment_date: date, zone: tzinfo) -> datetime:
    """Funds become reusable at local midnight after the allotment date."""
    if zone is None:
        raise ValueError("Expected release timezone is required")
    release = datetime.combine(allotment_date + timedelta(days=1), time.min, tzinfo=zone)
    if release.utcoffset() is None:
        raise ValueError("Expected release timezone is required")
    return release


def _next_due(schedule: RecurringDebitInput, due: date) -> date:
    if schedule.frequency == "DAILY":
        return due + timedelta(days=1)
    if schedule.frequency == "WEEKLY":
        return due + timedelta(days=7)
    if schedule.frequency == "MONTHLY":
        year = due.year + (due.month == 12)
        month = due.month % 12 + 1
        day = min(schedule.start_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    raise ValueError("Unsupported recurring payment frequency")


def cash_at_cutoff(
    *,
    bank: BankInput,
    cutoff: datetime,
    blocks: tuple[CashBlockInput, ...] = (),
    allocations: tuple[PlannedAllocation, ...] = (),
    recurring_debits: tuple[RecurringDebitInput, ...] = (),
) -> CashAtCutoff:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("Application cutoff must have a timezone")

    blocked = sum(
        (
            block.amount
            for block in blocks
            if block.bank_id == bank.id
            and block.blocked_at <= cutoff
            and (block.release_at is None or cutoff < block.release_at)
        ),
        Decimal("0.00"),
    )
    planned = sum(
        (
            row.amount
            for row in allocations
            if row.bank_id == bank.id and row.cutoff_at <= cutoff < row.release_at
        ),
        Decimal("0.00"),
    )
    cutoff_date = cutoff.date()
    scheduled = Decimal("0.00")
    for debit in recurring_debits:
        if not debit.active or debit.bank_id != bank.id:
            continue
        due = debit.next_due_date
        while due <= cutoff_date and (debit.end_date is None or due <= debit.end_date):
            scheduled += debit.amount
            due = _next_due(debit, due)

    raw = bank.balance - blocked - planned - scheduled
    return CashAtCutoff(
        balance=bank.balance,
        blocked=blocked,
        planned=planned,
        scheduled_payments=scheduled,
        raw_available=raw,
        available=max(Decimal("0.00"), raw),
    )
