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
    RecurringDebitInput,
    UPIInput,
)
from planner.engine import PLANNER_VERSION, generate_proposal


def test_ee004_three_ipos_owner_reserve_preference_and_emi_timeline():
    ipos = tuple(
        IPOInput(
            id=f"ipo-{name}",
            selected=True,
            gmp_percent=Decimal(gmp),
            upper_price=Decimal("100.00"),
            lot_size=150,
            cutoff_at=datetime(2030, 10, day, 17, tzinfo=UTC),
            allotment_date=date(2030, 10, 10),
            mode="RETAIL_ONLY",
        )
        for name, gmp, day in (("a", "35.00", 3), ("b", "25.00", 6), ("c", "15.00", 7))
    )
    snapshot = PlannerSnapshot(
        as_of=datetime(2030, 9, 27, 10, tzinfo=UTC),
        config=PlannerConfig(PLANNER_VERSION, "ALLOW", "DEFAULT"),
        ipos=ipos,
        applicants=(ApplicantInput("wife", 1, True), ApplicantInput("mother", 2, True)),
        demats=(DematInput("wife-demat", "wife", True), DematInput("mother-demat", "mother", True)),
        banks=(
            BankInput("wife-bank", "wife", Decimal("60000.00"), True, "DEFAULT"),
            BankInput("neutral-bank", "external", Decimal("30000.00"), True, "DEFAULT"),
        ),
        upis=(
            UPIInput("wife-upi", "wife-bank", "wife", True, True),
            UPIInput("neutral-upi", "neutral-bank", "external", True, True),
        ),
        funding_preferences=(
            FundingPreferenceInput("mother", "neutral-bank", 1, True),
            FundingPreferenceInput("mother", "wife-bank", 2, True),
        ),
        recurring_debits=(
            RecurringDebitInput(
                "synthetic-emi",
                "wife-bank",
                Decimal("10000.00"),
                "MONTHLY",
                date(2030, 10, 5),
                date(2030, 10, 5),
                None,
                True,
            ),
        ),
    )
    result = generate_proposal(snapshot)
    assert result.audit.valid
    assert [(row.ipo_id, row.applicant_id, row.bank_id) for row in result.coverage.rows] == [
        ("ipo-a", "wife", "wife-bank"),
        ("ipo-a", "mother", "neutral-bank"),
        ("ipo-b", "wife", "wife-bank"),
        ("ipo-b", "mother", "neutral-bank"),
        ("ipo-c", "wife", "wife-bank"),
    ]
    assert [(item.ipo_id, item.applicant_id) for item in result.coverage.uncovered] == [
        ("ipo-c", "mother")
    ]
