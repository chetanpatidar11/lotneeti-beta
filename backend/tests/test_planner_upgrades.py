from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from planner.coverage import baseline_retail_coverage
from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    UPIInput,
)
from planner.upgrades import upgrade_retail_to_shni
from planner.wallets import choose_retail_wallet


def snapshot(*, mode="RETAIL_PLUS_SHNI", balance="500000.00", applicants=1):
    return PlannerSnapshot(
        as_of=datetime(2026, 9, 27, 10, tzinfo=UTC),
        config=PlannerConfig("planner-v2.0", "ALLOW", "DEFAULT"),
        ipos=(
            IPOInput(
                id="ipo-1",
                selected=True,
                gmp_percent=Decimal("25.00"),
                upper_price=Decimal("100.00"),
                lot_size=150,
                cutoff_at=datetime(2026, 10, 3, 17, tzinfo=UTC),
                allotment_date=date(2026, 10, 9),
                mode=mode,
            ),
        ),
        applicants=tuple(
            ApplicantInput(f"applicant-{i}", i, True) for i in range(1, applicants + 1)
        ),
        demats=tuple(
            DematInput(f"demat-{i}", f"applicant-{i}", True) for i in range(1, applicants + 1)
        ),
        banks=(BankInput("bank-1", "applicant-1", Decimal(balance), True, "DEFAULT"),),
        upis=(UPIInput("upi-1", "bank-1", "applicant-1", True, True),),
    )


def plan(data):
    return baseline_retail_coverage(data, choose_retail_wallet)


def test_qc004_minimum_shni_quote_replaces_retail_without_topping_up():
    data = snapshot()
    baseline = plan(data)
    upgraded = upgrade_retail_to_shni(data, baseline)
    assert len(baseline.rows) == len(upgraded.rows) == 1
    assert (upgraded.rows[0].category, upgraded.rows[0].lots, upgraded.rows[0].amount) == (
        "SHNI",
        14,
        Decimal("210000.00"),
    )


def test_qc006_retail_only_does_not_upgrade():
    data = snapshot(mode="RETAIL_ONLY")
    baseline = plan(data)
    assert upgrade_retail_to_shni(data, baseline) == baseline


def test_priority_gets_scarce_shni_and_other_retail_row_survives():
    data = snapshot(balance="225000.00", applicants=2)
    baseline = plan(data)
    assert len(baseline.rows) == 2
    upgraded = upgrade_retail_to_shni(data, baseline)
    assert [(row.applicant_id, row.category, row.amount) for row in upgraded.rows] == [
        ("applicant-1", "SHNI", Decimal("210000.00")),
        ("applicant-2", "RETAIL", Decimal("15000.00")),
    ]
    assert len({(row.ipo_id, row.applicant_id) for row in upgraded.rows}) == 2


def test_insufficient_extra_cash_keeps_retail_mapping():
    data = snapshot(balance="30000.00")
    baseline = plan(data)
    assert upgrade_retail_to_shni(data, baseline) == baseline


def test_qc007_shni_preferred_maximizes_count_without_consuming_extra_lots():
    base = snapshot(mode="SHNI_PREFERRED", applicants=10)
    data = replace(
        base,
        banks=(
            BankInput("bank-a", "external-a", Decimal("450000.00"), True, "DEFAULT"),
            BankInput("bank-b", "external-b", Decimal("465000.00"), True, "DEFAULT"),
        ),
        upis=(
            UPIInput("upi-a", "bank-a", "external-a", True, True),
            UPIInput("upi-b", "bank-b", "external-b", True, True),
        ),
    )
    baseline = plan(data)
    assert len(baseline.rows) == 10
    upgraded = upgrade_retail_to_shni(data, baseline)
    assert sum(row.category == "SHNI" for row in upgraded.rows) == 3
    assert sum(row.category == "RETAIL" for row in upgraded.rows) == 7
    assert all(
        row.lots == 14 and row.amount == 210000 for row in upgraded.rows if row.category == "SHNI"
    )
    assert upgrade_retail_to_shni(data, upgraded) == upgraded


def test_cf002_sh001_own_wallet_wins_shni_when_cross_is_also_feasible():
    data = replace(
        snapshot(),
        banks=(
            BankInput("a-cross", "other", Decimal("230000.00"), True, "DEFAULT"),
            BankInput("z-own", "applicant-1", Decimal("230000.00"), True, "DEFAULT"),
        ),
        upis=(
            UPIInput("cross-upi", "a-cross", "other", True, True),
            UPIInput("own-upi", "z-own", "applicant-1", True, True),
        ),
    )
    result = upgrade_retail_to_shni(data, plan(data))
    assert [(row.category, row.bank_id) for row in result.rows] == [("SHNI", "z-own")]


def test_cf004_sh002_cross_wallet_can_fund_minimum_shni_when_own_cannot():
    data = replace(
        snapshot(),
        banks=(
            BankInput("a-cross", "other", Decimal("230000.00"), True, "DEFAULT"),
            BankInput("z-own", "applicant-1", Decimal("0.00"), True, "DEFAULT"),
        ),
        upis=(
            UPIInput("cross-upi", "a-cross", "other", True, True),
            UPIInput("own-upi", "z-own", "applicant-1", True, True),
        ),
    )
    result = upgrade_retail_to_shni(data, plan(data))
    assert [(row.category, row.bank_id, row.amount) for row in result.rows] == [
        ("SHNI", "a-cross", Decimal("210000.00"))
    ]


def test_sh003_tightest_sufficient_bank_wins_shni_and_sh005_limit_keeps_retail():
    base = snapshot()
    data = replace(
        base,
        banks=(
            BankInput("a-large", "applicant-1", Decimal("340000.00"), True, "DEFAULT"),
            BankInput("z-tight", "applicant-1", Decimal("252000.00"), True, "DEFAULT"),
        ),
        upis=(
            UPIInput("large-upi", "a-large", "applicant-1", True, True),
            UPIInput("tight-upi", "z-tight", "applicant-1", True, True),
        ),
    )
    result = upgrade_retail_to_shni(data, plan(data))
    assert [(row.category, row.bank_id) for row in result.rows] == [("SHNI", "z-tight")]
    capped = replace(
        base,
        banks=(BankInput("bank-1", "applicant-1", Decimal("230000.00"), True, "DEFAULT"),),
        upis=(
            UPIInput(
                "upi-1",
                "bank-1",
                "applicant-1",
                True,
                True,
                amount_limit_override=Decimal("200000.00"),
            ),
        ),
    )
    kept = upgrade_retail_to_shni(capped, plan(capped))
    assert [(row.category, row.amount) for row in kept.rows] == [("RETAIL", Decimal("15000.00"))]
