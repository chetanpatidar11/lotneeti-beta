from datetime import UTC, date, datetime
from decimal import Decimal

from planner.coverage import baseline_retail_coverage
from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    FundingPreferenceInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    RollingUsageInput,
    UPIInput,
)
from planner.wallets import choose_retail_wallet


def bank(id, owner, *, balance="50000.00", active=True, policy="DEFAULT"):
    return BankInput(id, owner, Decimal(balance), active, policy)


def upi(id, bank_id, holder, *, active=True, verified=True):
    return UPIInput(id, bank_id, holder, active, verified)


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
                cutoff_at=datetime(2026, 10, 3, 17, tzinfo=UTC),
                allotment_date=date(2026, 10, 9),
                mode="RETAIL_ONLY",
            ),
        ),
        "applicants": (ApplicantInput("wife", 1, True),),
        "demats": (DematInput("wife-demat", "wife", True),),
        "banks": (bank("a-cross", "mother"), bank("z-own", "wife")),
        "upis": (upi("cross-upi", "a-cross", "mother"), upi("own-upi", "z-own", "wife")),
    }
    values.update(changes)
    return PlannerSnapshot(**values)


def test_cf001_own_feasible_bank_precedes_lexically_earlier_cross_bank():
    result = baseline_retail_coverage(snapshot(), choose_retail_wallet)
    assert [(row.bank_id, row.upi_id, row.warnings) for row in result.rows] == [
        ("z-own", "own-upi", ())
    ]


def test_cf003_cross_funding_fallback_when_own_cash_is_insufficient():
    data = snapshot(banks=(bank("a-cross", "mother"), bank("z-own", "wife", balance="0.00")))
    result = baseline_retail_coverage(data, choose_retail_wallet)
    assert result.rows[0].bank_id == "a-cross"
    assert "CROSS_FUNDING" in result.rows[0].warnings


def test_cf005_cf006_policy_and_el005_to_el007_wallet_eligibility():
    own = bank("z-own", "wife", balance="0.00")
    denied = snapshot(
        banks=(bank("a-cross", "mother", policy="DISALLOW"), own),
    )
    assert baseline_retail_coverage(denied, choose_retail_wallet).rows == ()
    inactive = snapshot(
        banks=(bank("a-cross", "mother", active=False), own),
    )
    assert baseline_retail_coverage(inactive, choose_retail_wallet).rows == ()
    inactive_upi = snapshot(
        banks=(bank("a-cross", "mother"), own),
        upis=(upi("cross-upi", "a-cross", "mother", active=False),),
    )
    assert baseline_retail_coverage(inactive_upi, choose_retail_wallet).rows == ()
    unverified = snapshot(
        banks=(bank("a-cross", "mother"), own),
        upis=(upi("cross-upi", "a-cross", "mother", verified=False),),
    )
    assert baseline_retail_coverage(unverified, choose_retail_wallet).rows == ()


def test_cf005_workspace_cross_funding_disallow_prevents_automatic_assignment():
    base = snapshot(
        banks=(bank("a-cross", "mother"), bank("z-own", "wife", balance="0.00")),
    )
    denied = PlannerSnapshot(
        as_of=base.as_of,
        config=PlannerConfig("planner-v2.0", "ALLOW", "DISALLOW"),
        ipos=base.ipos,
        applicants=base.applicants,
        demats=base.demats,
        banks=base.banks,
        upis=base.upis,
    )
    assert baseline_retail_coverage(denied, choose_retail_wallet).rows == ()


def test_owner_guard_prefers_safe_cross_bank_when_another_owner_needs_cash():
    data = snapshot(
        applicants=(ApplicantInput("beneficiary", 1, True), ApplicantInput("wife", 2, True)),
        demats=(
            DematInput("beneficiary-demat", "beneficiary", True),
            DematInput("wife-demat", "wife", True),
        ),
        banks=(bank("a-wife", "wife", balance="15000.00"), bank("b-neutral", "neutral")),
        upis=(upi("wife-upi", "a-wife", "wife"), upi("neutral-upi", "b-neutral", "neutral")),
    )
    result = baseline_retail_coverage(data, choose_retail_wallet)
    assert result.rows[0].applicant_id == "beneficiary"
    assert result.rows[0].bank_id == "b-neutral"
    assert result.rows[1].bank_id == "a-wife"


def test_existing_rolling_limit_moves_coverage_to_another_feasible_wallet():
    submitted = datetime(2026, 10, 3, 16, tzinfo=UTC)
    usage = tuple(
        RollingUsageInput(
            id=f"existing-{index}",
            bank_id="z-own",
            upi_id="own-upi",
            amount=Decimal("15000.00"),
            submitted_at=submitted,
            cancelled=False,
        )
        for index in range(6)
    )
    result = baseline_retail_coverage(snapshot(rolling_usage=usage), choose_retail_wallet)
    assert result.rows[0].bank_id == "a-cross"


def test_prior_row_reserves_cash_before_next_applicant():
    data = snapshot(
        applicants=(ApplicantInput("wife", 1, True), ApplicantInput("mother", 2, True)),
        demats=(DematInput("wife-demat", "wife", True), DematInput("mother-demat", "mother", True)),
        banks=(bank("z-own", "wife", balance="15000.00"),),
        upis=(upi("own-upi", "z-own", "wife"),),
    )
    result = baseline_retail_coverage(data, choose_retail_wallet)
    assert [(row.applicant_id, row.bank_id) for row in result.rows] == [("wife", "z-own")]
    assert result.uncovered[0].applicant_id == "mother"


def test_el008_restricted_bank_cannot_fund_the_wrong_applicant():
    restricted = BankInput(
        "restricted-bank",
        "external",
        Decimal("50000.00"),
        True,
        "DEFAULT",
        restricted_applicant_id="someone-else",
    )
    data = snapshot(
        banks=(restricted,),
        upis=(upi("restricted-upi", restricted.id, "external"),),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows == ()


def test_ap004_priority_considers_cross_funded_applicant_before_own_wallet():
    data = snapshot(
        applicants=(ApplicantInput("beneficiary", 1, True), ApplicantInput("owner", 2, True)),
        demats=(
            DematInput("beneficiary-demat", "beneficiary", True),
            DematInput("owner-demat", "owner", True),
        ),
        banks=(bank("owner-bank", "owner", balance="30000.00"),),
        upis=(upi("owner-upi", "owner-bank", "owner"),),
    )
    result = baseline_retail_coverage(data, choose_retail_wallet)
    assert [(row.applicant_id, row.bank_id) for row in result.rows] == [
        ("beneficiary", "owner-bank"),
        ("owner", "owner-bank"),
    ]


def test_fp001_fp005_enabled_cross_funder_rank_after_own_wallet():
    preferences = (
        FundingPreferenceInput("wife", "c-second", 2, True),
        FundingPreferenceInput("wife", "b-first", 1, True),
    )
    data = snapshot(
        banks=(
            bank("a-unlisted", "other"),
            bank("b-first", "mother"),
            bank("c-second", "father"),
            bank("z-own", "wife"),
        ),
        upis=(
            upi("unlisted-upi", "a-unlisted", "other"),
            upi("first-upi", "b-first", "mother"),
            upi("second-upi", "c-second", "father"),
            upi("own-upi", "z-own", "wife"),
        ),
        funding_preferences=preferences,
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "z-own"
    cross_only = snapshot(
        banks=data.banks[:-1],
        upis=data.upis[:-1],
        funding_preferences=preferences,
    )
    assert baseline_retail_coverage(cross_only, choose_retail_wallet).rows[0].bank_id == "b-first"


def test_fp002_insufficient_preferred_bank_falls_back_to_next_ranked_bank():
    data = snapshot(
        banks=(bank("a-first", "mother", balance="0.00"), bank("b-second", "father")),
        upis=(upi("first-upi", "a-first", "mother"), upi("second-upi", "b-second", "father")),
        funding_preferences=(
            FundingPreferenceInput("wife", "a-first", 1, True),
            FundingPreferenceInput("wife", "b-second", 2, True),
        ),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "b-second"


def test_fp003_rolling_exhausted_preferred_bank_falls_back_to_next_ranked_bank():
    submitted = datetime(2026, 10, 3, 16, tzinfo=UTC)
    data = snapshot(
        banks=(bank("a-first", "mother"), bank("b-second", "father")),
        upis=(upi("first-upi", "a-first", "mother"), upi("second-upi", "b-second", "father")),
        funding_preferences=(
            FundingPreferenceInput("wife", "a-first", 1, True),
            FundingPreferenceInput("wife", "b-second", 2, True),
        ),
        rolling_usage=tuple(
            RollingUsageInput(
                id=f"existing-{index}",
                bank_id="a-first",
                upi_id="first-upi",
                amount=Decimal("15000.00"),
                submitted_at=submitted,
                cancelled=False,
            )
            for index in range(6)
        ),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "b-second"


def test_disabled_preference_is_ignored():
    data = snapshot(
        banks=(bank("a-unlisted", "mother"), bank("z-disabled", "father")),
        upis=(upi("a-upi", "a-unlisted", "mother"), upi("z-upi", "z-disabled", "father")),
        funding_preferences=(FundingPreferenceInput("wife", "z-disabled", 1, False),),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "a-unlisted"


def test_fp004_disabled_first_preference_skips_to_next_enabled_preference():
    data = snapshot(
        banks=(bank("a-unlisted", "other"), bank("b-disabled", "mother"), bank("c-next", "father")),
        upis=(
            upi("unlisted-upi", "a-unlisted", "other"),
            upi("disabled-upi", "b-disabled", "mother"),
            upi("next-upi", "c-next", "father"),
        ),
        funding_preferences=(
            FundingPreferenceInput("wife", "b-disabled", 1, False),
            FundingPreferenceInput("wife", "c-next", 2, True),
        ),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "c-next"


def test_rw001_stranded_small_own_balance_preserves_shni_capable_cash():
    data = snapshot(
        banks=(
            bank("a-large", "wife", balance="210000.00"),
            bank("z-small", "wife", balance="30000.00"),
        ),
        upis=(upi("large-upi", "a-large", "wife"), upi("small-upi", "z-small", "wife")),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "z-small"


def test_rw002_better_limit_headroom_precedes_bank_id():
    usage = tuple(
        RollingUsageInput(
            id=f"used-{index}",
            bank_id="a-near-limit",
            upi_id="near-upi",
            amount=Decimal("1000.00"),
            submitted_at=datetime(2026, 10, 3, 16, tzinfo=UTC),
            cancelled=False,
        )
        for index in range(4)
    )
    data = snapshot(
        banks=(
            bank("a-near-limit", "wife", balance="30000.00"),
            bank("z-roomy", "wife", balance="30000.00"),
        ),
        upis=(upi("near-upi", "a-near-limit", "wife"), upi("roomy-upi", "z-roomy", "wife")),
        rolling_usage=usage,
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == "z-roomy"


def test_rw003_tighter_sufficient_balance_and_rw004_stable_id():
    smaller = bank("z-small", "wife", balance="30000.00")
    larger = bank("a-large", "wife", balance="60000.00")
    data = snapshot(
        banks=(larger, smaller),
        upis=(upi("large-upi", larger.id, "wife"), upi("small-upi", smaller.id, "wife")),
    )
    assert baseline_retail_coverage(data, choose_retail_wallet).rows[0].bank_id == smaller.id
    equal = snapshot(
        banks=(
            bank("z-bank", "wife", balance="30000.00"),
            bank("a-bank", "wife", balance="30000.00"),
        ),
        upis=(upi("z-upi", "z-bank", "wife"), upi("a-upi", "a-bank", "wife")),
    )
    assert baseline_retail_coverage(equal, choose_retail_wallet).rows[0].bank_id == "a-bank"
