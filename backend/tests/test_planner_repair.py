from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from planner.coverage import CoverageResult, CoverageRow
from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    UPIInput,
)
from planner.repair import owner_affinity_cleanup, repair_shni_upgrades, try_rehome_for_shni


def setup(*, rows=2, small_banks=1, small_active=True):
    ipo = IPOInput(
        id="ipo-1",
        selected=True,
        gmp_percent=Decimal("25.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        cutoff_at=datetime(2026, 10, 3, 17, tzinfo=UTC),
        allotment_date=date(2026, 10, 9),
        mode="SHNI_PREFERRED",
    )
    snapshot = PlannerSnapshot(
        as_of=datetime(2026, 9, 27, 10, tzinfo=UTC),
        config=PlannerConfig("planner-v2.0", "ALLOW", "DEFAULT"),
        ipos=(ipo,),
        applicants=tuple(ApplicantInput(f"applicant-{i}", i, True) for i in range(1, rows + 1)),
        demats=tuple(DematInput(f"demat-{i}", f"applicant-{i}", True) for i in range(1, rows + 1)),
        banks=(BankInput("big", "external", Decimal("210000.00"), True, "DEFAULT"),)
        + tuple(
            BankInput(f"small-{i}", "external", Decimal("15000.00"), small_active, "DEFAULT")
            for i in range(1, small_banks + 1)
        ),
        upis=(UPIInput("big-upi", "big", "external", True, True),)
        + tuple(
            UPIInput(f"small-upi-{i}", f"small-{i}", "external", True, True)
            for i in range(1, small_banks + 1)
        ),
    )
    coverage = CoverageResult(
        rows=tuple(
            CoverageRow(
                ipo_id=ipo.id,
                applicant_id=f"applicant-{i}",
                category="RETAIL",
                lots=1,
                amount=Decimal("15000.00"),
                demat_id=f"demat-{i}",
                bank_id="big",
                upi_id="big-upi",
            )
            for i in range(1, rows + 1)
        ),
        uncovered=(),
    )
    return snapshot, coverage


def test_rr001_rehomes_one_retail_and_upgrades_target_atomically():
    data, original = setup()
    repaired = try_rehome_for_shni(data, original, ipo_id="ipo-1", applicant_id="applicant-1")
    assert [(row.applicant_id, row.category, row.bank_id) for row in repaired.rows] == [
        ("applicant-1", "SHNI", "big"),
        ("applicant-2", "RETAIL", "small-1"),
    ]
    assert repaired.rows[0].amount == Decimal("210000.00")
    assert repair_shni_upgrades(data, original) == repaired


def test_rr002_failed_rehome_rolls_back_every_local_change():
    data, original = setup(small_active=False)
    assert (
        try_rehome_for_shni(data, original, ipo_id="ipo-1", applicant_id="applicant-1") == original
    )


def test_rr003_more_than_two_moves_is_outside_bound():
    data, original = setup(rows=4, small_banks=3)
    assert (
        try_rehome_for_shni(data, original, ipo_id="ipo-1", applicant_id="applicant-1") == original
    )


def affinity_case():
    snapshot, coverage = setup()
    snapshot = replace(
        snapshot,
        banks=(
            BankInput("bank-1", "applicant-1", Decimal("15000.00"), True, "DEFAULT"),
            BankInput("bank-2", "applicant-2", Decimal("15000.00"), True, "DEFAULT"),
        ),
        upis=(
            UPIInput("upi-1", "bank-1", "applicant-1", True, True),
            UPIInput("upi-2", "bank-2", "applicant-2", True, True),
        ),
    )
    coverage = replace(
        coverage,
        rows=(
            replace(coverage.rows[0], bank_id="bank-2", upi_id="upi-2"),
            replace(coverage.rows[1], bank_id="bank-1", upi_id="upi-1"),
        ),
    )
    return snapshot, coverage


def test_rr004_equal_timeline_swap_improves_both_own_mappings_deterministically():
    snapshot, original = affinity_case()
    cleaned = owner_affinity_cleanup(snapshot, original)
    assert [(row.applicant_id, row.bank_id, row.upi_id) for row in cleaned.rows] == [
        ("applicant-1", "bank-1", "upi-1"),
        ("applicant-2", "bank-2", "upi-2"),
    ]
    assert all(not row.warnings for row in cleaned.rows)
    assert sum(row.amount for row in cleaned.rows) == sum(row.amount for row in original.rows)
    assert owner_affinity_cleanup(snapshot, cleaned) == cleaned
    reversed_result = owner_affinity_cleanup(snapshot, replace(original, rows=original.rows[::-1]))
    assert sorted((row.applicant_id, row.bank_id) for row in reversed_result.rows) == sorted(
        (row.applicant_id, row.bank_id) for row in cleaned.rows
    )


def test_rr005_locked_row_prevents_owner_affinity_swap():
    snapshot, original = affinity_case()
    locked = replace(original, rows=(replace(original.rows[0], locked=True), original.rows[1]))
    assert owner_affinity_cleanup(snapshot, locked) == locked


def test_rr004_swap_rolls_back_when_new_bank_mapping_is_restricted():
    snapshot, original = affinity_case()
    restricted = replace(
        snapshot,
        banks=(
            replace(snapshot.banks[0], restricted_applicant_id="applicant-2"),
            snapshot.banks[1],
        ),
    )
    assert owner_affinity_cleanup(restricted, original) == original
