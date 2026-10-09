from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from planner.audit import audit_plan
from planner.coverage import CoverageRow
from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    IPOInput,
    LockedRowInput,
    PlannerConfig,
    PlannerSnapshot,
    RecurringDebitInput,
    RollingUsageInput,
    UPIInput,
)


def ipo(id="ipo-1", *, cutoff_day=3, allotment_day=9):
    return IPOInput(
        id=id,
        selected=True,
        gmp_percent=Decimal("25.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        cutoff_at=datetime(2026, 10, cutoff_day, 17, tzinfo=UTC),
        allotment_date=date(2026, 10, allotment_day),
        mode="RETAIL_ONLY",
    )


def snapshot(**changes):
    values = {
        "as_of": datetime(2026, 9, 27, 10, tzinfo=UTC),
        "config": PlannerConfig("planner-v2.0", "ALLOW", "DEFAULT"),
        "ipos": (ipo(),),
        "applicants": (ApplicantInput("a", 1, True), ApplicantInput("b", 2, True)),
        "demats": (DematInput("demat-a", "a", True), DematInput("demat-b", "b", True)),
        "banks": (BankInput("bank-1", "a", Decimal("50000.00"), True, "DEFAULT"),),
        "upis": (UPIInput("upi-1", "bank-1", "a", True, True),),
    }
    values.update(changes)
    return PlannerSnapshot(**values)


def row(applicant="a", ipo_id="ipo-1", **changes):
    values = {
        "ipo_id": ipo_id,
        "applicant_id": applicant,
        "category": "RETAIL",
        "lots": 1,
        "amount": Decimal("15000.00"),
        "demat_id": f"demat-{applicant}",
        "bank_id": "bank-1",
        "upi_id": "upi-1",
    }
    values.update(changes)
    return CoverageRow(**values)


def audit(data, rows, total=None):
    return audit_plan(
        data,
        tuple(rows),
        reported_planned_total=total
        if total is not None
        else sum((item.amount for item in rows), Decimal("0.00")),
    )


def codes(result):
    return [issue.code for issue in result.issues]


def test_valid_plan_and_ad001_duplicate_applicant_ipo():
    data = snapshot()
    assert audit(data, (row(),)).valid
    duplicate = audit(data, (row(), row()))
    assert not duplicate.valid
    assert "DUPLICATE_APPLICANT_IPO" in codes(duplicate)


def test_ad002_overlapping_rows_cannot_double_spend_bank_cash():
    data = snapshot(banks=(BankInput("bank-1", "a", Decimal("20000.00"), True, "DEFAULT"),))
    result = audit(data, (row("a"), row("b")))
    assert "CASH_OVERSPEND" in codes(result)


def test_ad003_shared_bank_rolling_cap_is_replayed_from_usage():
    usage = tuple(
        RollingUsageInput(
            id=f"existing-{index}",
            bank_id="bank-1",
            upi_id="other-upi",
            amount=Decimal("15000.00"),
            submitted_at=datetime(2026, 10, 3, 16, tzinfo=UTC),
            cancelled=False,
        )
        for index in range(6)
    )
    result = audit(snapshot(rolling_usage=usage), (row(),))
    assert "BANK_LIMIT_EXCEEDED" in codes(result)
    assert "UPI_LIMIT_EXCEEDED" not in codes(result)


def test_ad004_due_payment_is_included_before_cutoff():
    payment = RecurringDebitInput(
        id="emi-1",
        bank_id="bank-1",
        amount=Decimal("20000.00"),
        frequency="MONTHLY",
        start_date=date(2026, 1, 2),
        next_due_date=date(2026, 10, 2),
        end_date=None,
        active=True,
    )
    data = snapshot(
        banks=(BankInput("bank-1", "a", Decimal("30000.00"), True, "DEFAULT"),),
        recurring_debits=(payment,),
    )
    assert "CASH_OVERSPEND" in codes(audit(data, (row(),)))


def test_expected_release_is_only_available_next_calendar_day():
    early = ipo("early", cutoff_day=3, allotment_day=4)
    later = ipo("later", cutoff_day=5, allotment_day=9)
    base = snapshot(
        ipos=(early, later),
        banks=(BankInput("bank-1", "a", Decimal("15000.00"), True, "DEFAULT"),),
    )
    rows = (row(ipo_id="early"), row(ipo_id="later"))
    assert audit(base, rows).valid
    same_day = replace(
        base, ipos=(early, replace(later, cutoff_at=datetime(2026, 10, 4, 17, tzinfo=UTC)))
    )
    assert "CASH_OVERSPEND" in codes(audit(same_day, rows))


def test_lock_and_reported_total_are_audited_independently():
    manual = LockedRowInput(
        "locked-1", "ipo-1", "a", "RETAIL", 1, Decimal("15000.00"), "demat-a", "bank-1", "upi-1"
    )
    data = snapshot(locked_rows=(manual,))
    changed = audit(data, (row(locked=True, bank_id="other-bank"),), total=Decimal("0.00"))
    assert "LOCKED_ROW_CHANGED" in codes(changed)
    assert "PLANNED_TOTAL_MISMATCH" in codes(changed)


def test_shni_uses_earlier_category_cutoff_for_rolling_limits():
    issue = replace(
        ipo(),
        mode="SHNI_PREFERRED",
        shni_cutoff_at=datetime(2026, 10, 3, 16, tzinfo=UTC),
    )
    usage = tuple(
        RollingUsageInput(
            id=f"later-{index}",
            bank_id="bank-1",
            upi_id="upi-1",
            amount=Decimal("1000.00"),
            submitted_at=datetime(2026, 10, 3, 16, 30, tzinfo=UTC),
            cancelled=False,
        )
        for index in range(6)
    )
    data = snapshot(
        ipos=(issue,),
        banks=(BankInput("bank-1", "a", Decimal("210000.00"), True, "DEFAULT"),),
        rolling_usage=usage,
    )
    shni = row(category="SHNI", lots=14, amount=Decimal("210000.00"))
    assert audit(data, (shni,)).valid
