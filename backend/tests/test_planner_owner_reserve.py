from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from planner.cash import PlannedAllocation, expected_release_at
from planner.dto import BankInput, IPOInput, RecurringDebitInput
from planner.owner_reserve import cross_fundable_cash, owner_baseline_reserve_at

IST = timezone(timedelta(hours=5, minutes=30))


def ipo(index, *, cutoff_day, allotment_day):
    return IPOInput(
        id=f"ipo-{index}",
        selected=True,
        gmp_percent=Decimal("20.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        cutoff_at=datetime(2026, 10, cutoff_day, 17, tzinfo=IST),
        allotment_date=date(2026, 10, allotment_day),
        mode="RETAIL_ONLY",
    )


def bank(balance="50000.00", id="wife-bank"):
    return BankInput(
        id=id,
        owner_id="wife",
        balance=Decimal(balance),
        active=True,
        cross_funding_policy="DEFAULT",
    )


def surplus(ipos, *, at=None, release_at=None, allocations=(), debits=(), bank_value=None):
    return cross_fundable_cash(
        bank=bank_value or bank(),
        at=at or ipos[0].cutoff_at,
        release_at=release_at or expected_release_at(date(2026, 10, 10), IST),
        owner_ipos=ipos,
        allocations=allocations,
        recurring_debits=debits,
    )


def test_op001_one_ipo_preserves_wife_retail_and_allows_mother():
    first = ipo(1, cutoff_day=3, allotment_day=8)
    assert owner_baseline_reserve_at(at=first.cutoff_at, owner_ipos=(first,)) == 15000
    assert surplus((first,)) == Decimal("35000.00")


def test_op002_two_overlapping_ipos_allow_only_one_mother_row():
    first = ipo(1, cutoff_day=3, allotment_day=8)
    second = ipo(2, cutoff_day=4, allotment_day=9)
    assert surplus((first, second)) == Decimal("20000.00")
    mother_row = PlannedAllocation(
        id="mother-ipo-1",
        bank_id="wife-bank",
        amount=Decimal("15000.00"),
        cutoff_at=first.cutoff_at,
        release_at=expected_release_at(first.allotment_date, IST),
    )
    assert surplus((first, second), at=second.cutoff_at, allocations=(mother_row,)) == 5000


def test_op003_three_overlapping_ipos_leave_only_5000_for_cross_funding():
    ipos = tuple(ipo(index, cutoff_day=index + 2, allotment_day=9) for index in range(1, 4))
    assert surplus(ipos) == Decimal("5000.00")


def test_op004_release_between_ipos_removes_first_reserve():
    first = ipo(1, cutoff_day=3, allotment_day=4)
    second = ipo(2, cutoff_day=6, allotment_day=9)
    assert surplus((first, second)) == Decimal("35000.00")
    assert owner_baseline_reserve_at(at=second.cutoff_at, owner_ipos=(first, second)) == 15000


def test_op005_scheduled_payment_reduces_cross_fundable_surplus():
    first = ipo(1, cutoff_day=3, allotment_day=8)
    second = ipo(2, cutoff_day=6, allotment_day=9)
    payment = RecurringDebitInput(
        id="emi-1",
        bank_id="wife-bank",
        amount=Decimal("10000.00"),
        frequency="MONTHLY",
        start_date=date(2026, 1, 5),
        next_due_date=date(2026, 10, 5),
        end_date=None,
        active=True,
    )
    assert surplus((first, second), debits=(payment,)) == Decimal("10000.00")


def test_existing_owner_allocation_is_counted_in_cash_once():
    first = ipo(1, cutoff_day=3, allotment_day=8)
    second = ipo(2, cutoff_day=6, allotment_day=9)
    owner_row = PlannedAllocation(
        id="wife-ipo-1",
        bank_id="wife-bank",
        amount=Decimal("15000.00"),
        cutoff_at=first.cutoff_at,
        release_at=expected_release_at(first.allotment_date, IST),
    )
    assert cross_fundable_cash(
        bank=bank(),
        at=first.cutoff_at,
        release_at=expected_release_at(second.allotment_date, IST),
        owner_ipos=(first, second),
        covered_ipo_ids=frozenset({first.id}),
        allocations=(owner_row,),
    ) == Decimal("20000.00")
