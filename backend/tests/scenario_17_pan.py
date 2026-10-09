"""Deterministic, wholly synthetic 17-applicant planner fixture."""

from datetime import UTC, date, datetime
from decimal import Decimal

from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    FundingPreferenceInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    UPIInput,
)
from planner.engine import PLANNER_VERSION


def founder_17_snapshot(
    *,
    balances: tuple[str, ...] | None = None,
    mode: str = "RETAIL_ONLY",
    two_ipos: bool = False,
) -> PlannerSnapshot:
    """Aliases, IDs and balances are synthetic; no PAN or payment handle exists here."""
    amounts = balances or ("30000.00",) * 17
    if len(amounts) != 17:
        raise ValueError("Expected 17 synthetic balances")
    applicants = tuple(ApplicantInput(f"member-{index:02d}", index, True) for index in range(1, 18))
    demats = tuple(
        DematInput(f"demat-{index:02d}", applicant.id, True)
        for index, applicant in enumerate(applicants, 1)
    )
    banks = tuple(
        BankInput(f"bank-{index:02d}", applicant.id, Decimal(amount), True, "DEFAULT")
        for index, (applicant, amount) in enumerate(zip(applicants, amounts, strict=True), 1)
    )
    upis = tuple(
        UPIInput(f"upi-{index:02d}", bank.id, bank.owner_id, True, True)
        for index, bank in enumerate(banks, 1)
    )
    ipos = (
        IPOInput(
            "ipo-higher",
            True,
            Decimal("35.00"),
            Decimal("100.00"),
            150,
            datetime(2030, 10, 3, 17, tzinfo=UTC),
            date(2030, 10, 10),
            mode,
        ),
    )
    if two_ipos:
        ipos += (
            IPOInput(
                "ipo-lower",
                True,
                Decimal("22.00"),
                Decimal("100.00"),
                150,
                datetime(2030, 10, 3, 17, tzinfo=UTC),
                date(2030, 10, 10),
                "RETAIL_ONLY",
            ),
        )
    return PlannerSnapshot(
        as_of=datetime(2030, 9, 27, 10, tzinfo=UTC),
        config=PlannerConfig(PLANNER_VERSION, "DISALLOW", "DEFAULT"),
        ipos=ipos,
        applicants=applicants,
        demats=demats,
        banks=banks,
        upis=upis,
        funding_preferences=(
            FundingPreferenceInput("member-17", "bank-01", 1, True),
            FundingPreferenceInput("member-17", "bank-02", 2, True),
        ),
    )
