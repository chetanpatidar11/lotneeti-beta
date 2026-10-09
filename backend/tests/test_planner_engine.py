from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    UPIInput,
)
from planner.engine import PLANNER_VERSION, generate_proposal


def snapshot(*, reverse=False):
    applicants = (ApplicantInput("b", 1, True), ApplicantInput("a", 1, True))
    demats = (DematInput("demat-b", "b", True), DematInput("demat-a", "a", True))
    banks = (
        BankInput("bank-b", "b", Decimal("30000.00"), True, "DEFAULT"),
        BankInput("bank-a", "a", Decimal("30000.00"), True, "DEFAULT"),
    )
    upis = (
        UPIInput("upi-b", "bank-b", "b", True, True),
        UPIInput("upi-a", "bank-a", "a", True, True),
    )
    return PlannerSnapshot(
        as_of=datetime(2026, 9, 27, 10, tzinfo=UTC),
        config=PlannerConfig(PLANNER_VERSION, "ALLOW", "DEFAULT"),
        ipos=(
            IPOInput(
                "ipo-1",
                True,
                Decimal("25.00"),
                Decimal("100.00"),
                150,
                datetime(2026, 10, 3, 17, tzinfo=UTC),
                date(2026, 10, 9),
                "RETAIL_ONLY",
            ),
        ),
        applicants=tuple(reversed(applicants)) if reverse else applicants,
        demats=tuple(reversed(demats)) if reverse else demats,
        banks=tuple(reversed(banks)) if reverse else banks,
        upis=tuple(reversed(upis)) if reverse else upis,
    )


def test_ad005_twenty_repeated_runs_have_identical_logical_output_and_hashes():
    data = snapshot()
    first = generate_proposal(data)
    assert first.audit.valid
    assert [(row.applicant_id, row.bank_id) for row in first.coverage.rows] == [
        ("a", "bank-a"),
        ("b", "bank-b"),
    ]
    assert all(generate_proposal(data) == first for _ in range(20))


def test_ad006_input_tuple_order_does_not_change_snapshot_or_output_hash():
    original = generate_proposal(snapshot())
    reversed_order = generate_proposal(snapshot(reverse=True))
    assert original == reversed_order


def test_ad007_version_metadata_and_settings_hash_change_with_configuration():
    data = snapshot()
    first = generate_proposal(data)
    changed = generate_proposal(replace(data, config=replace(data.config, upi_count_limit=5)))
    assert first.planner_version == PLANNER_VERSION
    assert first.settings_version.startswith("sha256:")
    assert len(first.input_snapshot_hash) == len(first.output_hash) == 64
    assert first.settings_version != changed.settings_version
    assert first.input_snapshot_hash != changed.input_snapshot_hash
    with pytest.raises(ValueError, match="version"):
        generate_proposal(replace(data, config=replace(data.config, version="planner-v1")))
