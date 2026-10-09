from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from planner.coverage import baseline_retail_coverage
from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    IPOInput,
    LockedRowInput,
    PlannerConfig,
    PlannerSnapshot,
    RollingUsageInput,
    UPIInput,
)
from planner.locks import locked_coverage
from planner.upgrades import upgrade_retail_to_shni
from planner.wallets import choose_retail_wallet

CUTOFF = datetime(2026, 10, 3, 17, tzinfo=UTC)


def locked(**changes):
    values = {
        "id": "locked-1",
        "ipo_id": "ipo-1",
        "applicant_id": "wife",
        "category": "RETAIL",
        "lots": 1,
        "amount": Decimal("15000.00"),
        "demat_id": "demat-1",
        "bank_id": "bank-1",
        "upi_id": "upi-1",
    }
    values.update(changes)
    return LockedRowInput(**values)


def snapshot(**changes):
    values = {
        "as_of": datetime(2026, 9, 27, 10, tzinfo=UTC),
        "config": PlannerConfig("planner-v2.0", "ALLOW", "DEFAULT"),
        "ipos": (
            IPOInput(
                id="ipo-1",
                selected=True,
                gmp_percent=Decimal("25.00"),
                upper_price=Decimal("100.00"),
                lot_size=150,
                cutoff_at=CUTOFF,
                allotment_date=date(2026, 10, 9),
                mode="RETAIL_PLUS_SHNI",
            ),
        ),
        "applicants": (ApplicantInput("wife", 1, True),),
        "demats": (DematInput("demat-1", "wife", True),),
        "banks": (BankInput("bank-1", "wife", Decimal("50000.00"), True, "DEFAULT"),),
        "upis": (UPIInput("upi-1", "bank-1", "wife", True, True),),
        "locked_rows": (locked(),),
    }
    values.update(changes)
    return PlannerSnapshot(**values)


def test_lm001_lock_remains_exact_and_automation_does_not_duplicate_or_upgrade_it():
    data = snapshot()
    initial = locked_coverage(data)
    assert initial.rows[0].locked
    assert initial.rows[0].blocking_reasons == ()
    baseline = baseline_retail_coverage(data, choose_retail_wallet, initial.rows)
    assert baseline.rows == initial.rows
    assert upgrade_retail_to_shni(data, baseline) == baseline


def test_lm002_insufficient_cash_keeps_row_with_blocking_reason():
    data = snapshot(banks=(BankInput("bank-1", "wife", Decimal("10000.00"), True, "DEFAULT"),))
    row = locked_coverage(data).rows[0]
    assert row.bank_id == "bank-1"
    assert row.blocking_reasons == ("INSUFFICIENT_BALANCE", "LOCKED_ROW_INFEASIBLE")


def test_lm003_rolling_limit_exceeded_keeps_original_mapping():
    usage = tuple(
        RollingUsageInput(
            id=f"existing-{index}",
            bank_id="bank-1",
            upi_id="upi-1",
            amount=Decimal("15000.00"),
            submitted_at=datetime(2026, 10, 3, 16, tzinfo=UTC),
            cancelled=False,
        )
        for index in range(6)
    )
    row = locked_coverage(snapshot(rolling_usage=usage)).rows[0]
    assert row.upi_id == "upi-1"
    assert "UPI_LIMIT_EXCEEDED" in row.blocking_reasons
    assert "BANK_LIMIT_EXCEEDED" in row.blocking_reasons


def test_lm005_cross_funded_lock_preserved_with_warning():
    data = snapshot(
        banks=(BankInput("bank-1", "mother", Decimal("50000.00"), True, "DEFAULT"),),
    )
    row = locked_coverage(data).rows[0]
    assert row.blocking_reasons == ()
    assert row.warnings == ("CROSS_FUNDING",)


def test_manual_lots_amount_mismatch_is_blocking_and_never_recalculated():
    data = snapshot(locked_rows=(locked(lots=2),))
    row = locked_coverage(data).rows[0]
    assert row.lots == 2 and row.amount == Decimal("15000.00")
    assert "INVALID_AMOUNT" in row.blocking_reasons
    assert "INVALID_CATEGORY" in row.blocking_reasons


def test_lm008_unselected_ipo_removes_old_draft_lock_from_new_plan():
    base = snapshot()
    data = replace(base, ipos=(replace(base.ipos[0], selected=False),))
    assert locked_coverage(data).rows == ()
