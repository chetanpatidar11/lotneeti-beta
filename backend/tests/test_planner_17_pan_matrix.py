from collections import Counter
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from scenario_17_pan import founder_17_snapshot

from planner.dto import RecurringDebitInput
from planner.engine import generate_proposal


def test_ee001_seventeen_pan_retail_plan_has_one_valid_row_each():
    fixture = founder_17_snapshot()
    assert (
        len(fixture.applicants)
        == len(fixture.demats)
        == len(fixture.banks)
        == len(fixture.upis)
        == 17
    )
    assert [item.priority for item in fixture.funding_preferences] == [1, 2]
    result = generate_proposal(fixture)
    assert result.audit.valid
    assert len(result.coverage.rows) == 17
    assert {row.applicant_id for row in result.coverage.rows} == {
        f"member-{index:02d}" for index in range(1, 18)
    }
    assert all(row.category == "RETAIL" and row.lots == 1 for row in result.coverage.rows)


def test_ee002_seventeen_pan_scarce_cash_covers_highest_twelve_priorities():
    balances = ("15000.00",) * 12 + ("0.00",) * 5
    result = generate_proposal(founder_17_snapshot(balances=balances))
    assert result.audit.valid
    assert [row.applicant_id for row in result.coverage.rows] == [
        f"member-{index:02d}" for index in range(1, 13)
    ]
    assert len(result.coverage.uncovered) == 5


def test_ee003_seventeen_pan_shni_preferred_preserves_baseline_then_four_upgrades():
    balances = ("230000.00",) * 4 + ("15000.00",) * 13
    result = generate_proposal(founder_17_snapshot(balances=balances, mode="SHNI_PREFERRED"))
    assert result.audit.valid
    assert len(result.coverage.rows) == 17
    assert Counter(row.category for row in result.coverage.rows) == {"SHNI": 4, "RETAIL": 13}
    assert [row.applicant_id for row in result.coverage.rows if row.category == "SHNI"] == [
        f"member-{index:02d}" for index in range(1, 5)
    ]


def test_mi001_twenty_slots_attempt_all_seventeen_higher_gmp_first():
    balances = ("30000.00",) * 3 + ("15000.00",) * 14
    result = generate_proposal(founder_17_snapshot(balances=balances, two_ipos=True))
    assert result.audit.valid
    assert len(result.coverage.rows) == 20
    assert [row.ipo_id for row in result.coverage.rows] == ["ipo-higher"] * 17 + ["ipo-lower"] * 3


def test_mi004_mi005_cash_reuse_depends_on_first_ipo_release_before_later_cutoff():
    base = founder_17_snapshot(balances=("15000.00",) + ("0.00",) * 16, two_ipos=True)
    later_cutoff = datetime(2030, 10, 6, 17, tzinfo=UTC)
    early = replace(
        base,
        applicants=base.applicants[:1],
        demats=base.demats[:1],
        banks=base.banks[:1],
        upis=base.upis[:1],
        funding_preferences=(),
        ipos=(
            replace(base.ipos[0], allotment_date=date(2030, 10, 4)),
            replace(base.ipos[1], cutoff_at=later_cutoff),
        ),
    )
    reusable = generate_proposal(early)
    assert reusable.audit.valid
    assert [row.ipo_id for row in reusable.coverage.rows] == ["ipo-higher", "ipo-lower"]
    blocked = replace(
        early, ipos=(replace(early.ipos[0], allotment_date=date(2030, 10, 9)), early.ipos[1])
    )
    unavailable = generate_proposal(blocked)
    assert unavailable.audit.valid
    assert [row.ipo_id for row in unavailable.coverage.rows] == ["ipo-higher"]


def test_mi008_emi_between_cutoffs_reduces_only_later_ipo_cash():
    base = founder_17_snapshot(balances=("30000.00",) + ("0.00",) * 16, two_ipos=True)
    later_cutoff = datetime(2030, 10, 6, 17, tzinfo=UTC)
    trimmed = replace(
        base,
        applicants=base.applicants[:1],
        demats=base.demats[:1],
        banks=base.banks[:1],
        upis=base.upis[:1],
        funding_preferences=(),
        ipos=(base.ipos[0], replace(base.ipos[1], cutoff_at=later_cutoff)),
    )
    assert [row.ipo_id for row in generate_proposal(trimmed).coverage.rows] == [
        "ipo-higher",
        "ipo-lower",
    ]
    payment = RecurringDebitInput(
        id="synthetic-emi",
        bank_id="bank-01",
        amount=Decimal("10000.00"),
        frequency="MONTHLY",
        start_date=date(2030, 10, 5),
        next_due_date=date(2030, 10, 5),
        end_date=None,
        active=True,
    )
    with_emi = generate_proposal(replace(trimmed, recurring_debits=(payment,)))
    assert with_emi.audit.valid
    assert [row.ipo_id for row in with_emi.coverage.rows] == ["ipo-higher"]


def test_mi006_baseline_for_lower_ipo_precedes_higher_ipo_shni_upgrade():
    base = founder_17_snapshot(
        balances=("225000.00",) + ("0.00",) * 16,
        mode="SHNI_PREFERRED",
        two_ipos=True,
    )
    data = replace(
        base,
        applicants=base.applicants[:1],
        demats=base.demats[:1],
        banks=base.banks[:1],
        upis=base.upis[:1],
        funding_preferences=(),
    )
    result = generate_proposal(data)
    assert result.audit.valid
    assert [(row.ipo_id, row.category, row.amount) for row in result.coverage.rows] == [
        ("ipo-higher", "SHNI", Decimal("210000.00")),
        ("ipo-lower", "RETAIL", Decimal("15000.00")),
    ]


def test_mi007_same_cutoff_ipos_share_upi_count_immediately():
    base = founder_17_snapshot(balances=("30000.00",) + ("0.00",) * 16, two_ipos=True)
    data = replace(
        base,
        applicants=base.applicants[:1],
        demats=base.demats[:1],
        banks=base.banks[:1],
        upis=(replace(base.upis[0], count_limit_override=1),),
        funding_preferences=(),
    )
    result = generate_proposal(data)
    assert result.audit.valid
    assert [row.ipo_id for row in result.coverage.rows] == ["ipo-higher"]
