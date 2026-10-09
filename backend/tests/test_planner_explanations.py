from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from planner.coverage import CoverageResult, CoverageRow
from planner.dto import (
    ApplicantInput,
    BankInput,
    FundingPreferenceInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
)
from planner.explanations import explain_rows


def snapshot(**changes):
    values = {
        "as_of": datetime(2026, 9, 27, 10, tzinfo=UTC),
        "config": PlannerConfig("planner-v2.0", "ALLOW", "DEFAULT"),
        "ipos": (
            IPOInput(
                "ipo-1",
                True,
                Decimal("25.00"),
                Decimal("100.00"),
                150,
                datetime(2026, 10, 3, 17, tzinfo=UTC),
                date(2026, 10, 9),
                "RETAIL_PLUS_SHNI",
            ),
        ),
        "applicants": (ApplicantInput("mother", 4, True), ApplicantInput("wife", 1, True)),
        "banks": (BankInput("wife-bank", "wife", Decimal("50000.00"), True, "DEFAULT"),),
        "funding_preferences": (FundingPreferenceInput("mother", "wife-bank", 1, True),),
    }
    values.update(changes)
    return PlannerSnapshot(**values)


def row(**changes):
    values = {
        "ipo_id": "ipo-1",
        "applicant_id": "mother",
        "category": "RETAIL",
        "lots": 1,
        "amount": Decimal("15000.00"),
        "demat_id": "demat-1",
        "bank_id": "wife-bank",
        "upi_id": "upi-1",
        "warnings": ("CROSS_FUNDING",),
    }
    values.update(changes)
    return CoverageRow(**values)


def test_cross_funded_row_has_ordered_plain_reasons_and_stable_data():
    explained = explain_rows(snapshot(), CoverageResult((row(),), ())).rows[0]
    assert [reason.code for reason in explained.reasons] == [
        "APPLICANT_PRIORITY",
        "OWN_WALLET_UNAVAILABLE",
        "PREFERRED_CROSS_FUNDER",
        "OWNER_CASH_PROTECTED",
        "ROLLING_LIMIT_ROOM",
    ]
    assert explained.reasons[0].data == (("priority", "4"),)
    assert explained.reasons[2].data == (("priority", "1"), ("bank_id", "wife-bank"))
    assert all(reason.message for reason in explained.reasons)


def test_shni_and_owner_conflict_reasons_follow_funding_reason():
    source = row(
        category="SHNI",
        lots=14,
        amount=Decimal("210000.00"),
        warnings=("CROSS_FUNDING", "OWNER_RESERVE_TRADEOFF"),
    )
    explained = explain_rows(snapshot(), CoverageResult((source,), ())).rows[0]
    assert [reason.code for reason in explained.reasons][-3:] == [
        "OWNER_CASH_CONFLICT",
        "MINIMUM_SHNI",
        "ROLLING_LIMIT_ROOM",
    ]


def test_own_funding_and_locked_row_are_handled_without_rewriting_lock():
    own = row(applicant_id="wife", warnings=())
    manual = replace(row(), locked=True, blocking_reasons=("LOCKED_ROW_INFEASIBLE",))
    result = explain_rows(snapshot(), CoverageResult((own, manual), ()))
    assert [reason.code for reason in result.rows[0].reasons] == [
        "APPLICANT_PRIORITY",
        "OWN_FUNDING",
        "ROLLING_LIMIT_ROOM",
    ]
    assert result.rows[1] == manual


def test_preference_source_order_does_not_change_reason():
    base = snapshot(
        funding_preferences=(
            FundingPreferenceInput("mother", "wife-bank", 2, True),
            FundingPreferenceInput("mother", "other-bank", 1, True),
        )
    )
    first = explain_rows(base, CoverageResult((row(),), ()))
    second = explain_rows(
        replace(base, funding_preferences=tuple(reversed(base.funding_preferences))),
        CoverageResult((row(),), ()),
    )
    assert first == second
