from datetime import UTC, date, datetime
from decimal import Decimal

from planner.coverage import WalletChoice, baseline_retail_coverage
from planner.dto import (
    ApplicantInput,
    DematInput,
    ExistingApplicationInput,
    IPOInput,
    LockedRowInput,
    PlannerConfig,
    PlannerSnapshot,
)


def ipo(id, *, gmp="25.00", mode="RETAIL_ONLY"):
    return IPOInput(
        id=id,
        selected=True,
        gmp_percent=Decimal(gmp),
        upper_price=Decimal("100.00"),
        lot_size=150,
        cutoff_at=datetime(2026, 10, 3, 17, tzinfo=UTC),
        allotment_date=date(2026, 10, 9),
        mode=mode,
    )


def snapshot(**changes):
    values = {
        "as_of": datetime(2026, 9, 27, 10, tzinfo=UTC),
        "config": PlannerConfig(
            version="planner-v2.0",
            platform_cross_funding_policy="ALLOW",
            workspace_cross_funding_policy="DEFAULT",
        ),
        "ipos": (ipo("lower", gmp="20.00"), ipo("higher", gmp="35.00")),
        "applicants": (
            ApplicantInput("b", priority=2, active=True),
            ApplicantInput("a", priority=1, active=True),
        ),
        "demats": (DematInput("demat-a", "a", True), DematInput("demat-b", "b", True)),
    }
    values.update(changes)
    return PlannerSnapshot(**values)


def test_priority_and_ipo_order_with_scarce_capacity():
    calls = []

    def choose(_snapshot, current_ipo, applicant, _quote, rows):
        calls.append((current_ipo.id, applicant.id))
        if rows:
            return None
        return WalletChoice("bank-1", "upi-1")

    result = baseline_retail_coverage(snapshot(), choose)
    assert calls == [
        ("higher", "a"),
        ("higher", "b"),
        ("lower", "a"),
        ("lower", "b"),
    ]
    assert [(row.ipo_id, row.applicant_id, row.amount) for row in result.rows] == [
        ("higher", "a", Decimal("15000.00"))
    ]
    assert len(result.uncovered) == 3


def test_inactive_missing_demat_existing_application_and_lock_are_excluded():
    base = snapshot()
    locked = LockedRowInput(
        id="locked-1",
        ipo_id="lower",
        applicant_id="a",
        category="RETAIL",
        lots=1,
        amount=Decimal("15000.00"),
        demat_id="demat-a",
        bank_id="bank-1",
        upi_id="upi-1",
    )
    data = snapshot(
        applicants=(*base.applicants, ApplicantInput("inactive", priority=0, active=False)),
        demats=(DematInput("demat-a", "a", True),),
        existing_applications=(ExistingApplicationInput("app-1", "higher", "a", False),),
        locked_rows=(locked,),
    )
    result = baseline_retail_coverage(data, lambda *_: WalletChoice("bank-1", "upi-1"))
    assert result.rows == ()
    assert [(item.ipo_id, item.applicant_id, item.reason) for item in result.uncovered] == [
        ("higher", "b", "NO_ACTIVE_DEMAT"),
        ("lower", "b", "NO_ACTIVE_DEMAT"),
    ]


def test_cancelled_application_allows_new_row_and_custom_requires_user_choice():
    result = baseline_retail_coverage(
        snapshot(
            ipos=(ipo("retail"), ipo("custom", mode="CUSTOM")),
            applicants=(ApplicantInput("a", priority=1, active=True),),
            demats=(DematInput("demat-a", "a", True),),
            existing_applications=(ExistingApplicationInput("app-1", "retail", "a", True),),
        ),
        lambda *_: WalletChoice("bank-1", "upi-1"),
    )
    assert [(row.ipo_id, row.applicant_id) for row in result.rows] == [("retail", "a")]
    assert result.uncovered[0].reason == "CUSTOM_CATEGORY_REQUIRED"


def test_duplicate_snapshot_applicant_cannot_create_second_pan_ipo_row():
    applicant = ApplicantInput("a", priority=1, active=True)
    result = baseline_retail_coverage(
        snapshot(
            ipos=(ipo("retail"),),
            applicants=(applicant, applicant),
            demats=(DematInput("demat-a", "a", True),),
        ),
        lambda *_: WalletChoice("bank-1", "upi-1"),
    )
    assert len(result.rows) == 1
