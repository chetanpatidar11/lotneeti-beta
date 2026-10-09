from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from planner.cash import PlannedAllocation, cash_at_cutoff, expected_release_at
from planner.dto import BankInput, CashBlockInput, RecurringDebitInput

IST = timezone(timedelta(hours=5, minutes=30))
CUTOFF = datetime(2026, 10, 6, 17, tzinfo=IST)


def bank(balance="250000.00", id="bank-1"):
    return BankInput(
        id=id,
        owner_id="applicant-1",
        balance=Decimal(balance),
        active=True,
        cross_funding_policy="DEFAULT",
    )


def debit(
    *, id="emi-1", due=date(2026, 10, 5), amount="20000.00", active=True, frequency="MONTHLY"
):
    return RecurringDebitInput(
        id=id,
        bank_id="bank-1",
        amount=Decimal(amount),
        frequency=frequency,
        start_date=date(2026, 1, 5),
        next_due_date=due,
        end_date=None,
        active=active,
    )


def block(*, release_at=None, amount="15000.00"):
    return CashBlockInput(
        id="block-1",
        bank_id="bank-1",
        amount=Decimal(amount),
        blocked_at=datetime(2026, 10, 1, 17, tzinfo=IST),
        release_at=release_at,
    )


def test_balance_blocks_planned_and_nonnegative_available():
    row = PlannedAllocation(
        id="row-1",
        bank_id="bank-1",
        amount=Decimal("15000.00"),
        cutoff_at=CUTOFF,
        release_at=expected_release_at(date(2026, 10, 9), IST),
    )
    result = cash_at_cutoff(
        bank=bank("40000.00"), cutoff=CUTOFF, blocks=(block(),), allocations=(row,)
    )
    assert (result.balance, result.blocked, result.planned, result.available) == (
        Decimal("40000.00"),
        Decimal("15000.00"),
        Decimal("15000.00"),
        Decimal("10000.00"),
    )
    insufficient = cash_at_cutoff(
        bank=bank("10000.00"), cutoff=CUTOFF, blocks=(block(),), allocations=(row,)
    )
    assert insufficient.raw_available == Decimal("-20000.00")
    assert insufficient.available == 0


def test_rd001_to_rd006_scheduled_payments_due_by_cutoff_only():
    before = cash_at_cutoff(bank=bank(), cutoff=CUTOFF, recurring_debits=(debit(),))
    assert before.scheduled_payments == Decimal("20000.00")
    assert before.available == Decimal("230000.00")
    assert cash_at_cutoff(
        bank=bank(), cutoff=CUTOFF, recurring_debits=(debit(due=date(2026, 10, 7)),)
    ).available == Decimal("250000.00")
    assert (
        cash_at_cutoff(
            bank=bank(), cutoff=CUTOFF, recurring_debits=(debit(active=False),)
        ).scheduled_payments
        == 0
    )
    assert cash_at_cutoff(
        bank=bank(), cutoff=CUTOFF, recurring_debits=(debit(amount="9000.00"),)
    ).available == Decimal("241000.00")
    second = RecurringDebitInput(
        id="emi-2",
        bank_id="bank-1",
        amount=Decimal("8500.00"),
        frequency="MONTHLY",
        start_date=date(2026, 1, 6),
        next_due_date=date(2026, 10, 6),
        end_date=None,
        active=True,
    )
    assert cash_at_cutoff(
        bank=bank(), cutoff=CUTOFF, recurring_debits=(debit(), second)
    ).scheduled_payments == Decimal("28500.00")


def test_multiple_future_occurrences_and_month_end_match_posting_schedule():
    monthly = RecurringDebitInput(
        id="month-end",
        bank_id="bank-1",
        amount=Decimal("1000.00"),
        frequency="MONTHLY",
        start_date=date(2026, 1, 31),
        next_due_date=date(2026, 1, 31),
        end_date=date(2026, 3, 31),
        active=True,
    )
    result = cash_at_cutoff(
        bank=bank(),
        cutoff=datetime(2026, 4, 1, 17, tzinfo=IST),
        recurring_debits=(monthly,),
    )
    assert result.scheduled_payments == Decimal("3000.00")


def test_expected_release_is_next_local_day_and_reuse_is_inclusive():
    release = expected_release_at(date(2026, 10, 8), IST)
    blocked = block(release_at=release)
    row = PlannedAllocation(
        id="row-1",
        bank_id="bank-1",
        amount=Decimal("15000.00"),
        cutoff_at=datetime(2026, 10, 3, 17, tzinfo=IST),
        release_at=release,
    )
    same_day = cash_at_cutoff(
        bank=bank(),
        cutoff=datetime(2026, 10, 8, 17, tzinfo=IST),
        blocks=(blocked,),
        allocations=(row,),
    )
    next_day = cash_at_cutoff(bank=bank(), cutoff=release, blocks=(blocked,), allocations=(row,))
    assert (same_day.blocked, same_day.planned) == (Decimal("15000.00"),) * 2
    assert (next_day.blocked, next_day.planned) == (0, 0)


def test_actual_allotment_state_replaces_expected_block_and_other_bank_is_ignored():
    current = cash_at_cutoff(bank=bank("35150.00"), cutoff=CUTOFF, blocks=())
    assert current.available == Decimal("35150.00")
    other = CashBlockInput(
        id="other-block",
        bank_id="bank-2",
        amount=Decimal("100000.00"),
        blocked_at=CUTOFF,
        release_at=None,
    )
    assert cash_at_cutoff(bank=bank(), cutoff=CUTOFF, blocks=(other,)).blocked == 0


def test_daily_and_weekly_debits_include_every_due_occurrence():
    daily = debit(due=date(2026, 10, 4), amount="1000.00", frequency="DAILY")
    weekly = debit(id="emi-2", due=date(2026, 9, 29), amount="2000.00", frequency="WEEKLY")
    assert cash_at_cutoff(
        bank=bank(), cutoff=CUTOFF, recurring_debits=(daily, weekly)
    ).scheduled_payments == Decimal("7000.00")


def test_cutoff_and_release_require_timezone():
    with pytest.raises(ValueError, match="timezone"):
        cash_at_cutoff(bank=bank(), cutoff=datetime(2026, 10, 6, 17))
    with pytest.raises(ValueError, match="timezone"):
        expected_release_at(date(2026, 10, 8), None)
