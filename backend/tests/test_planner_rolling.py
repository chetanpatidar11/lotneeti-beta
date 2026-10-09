from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from planner.dto import PlannerConfig, RollingUsageInput, UPIInput
from planner.rolling import RollingLimitTracker

CUTOFF = datetime(2026, 10, 3, 17, tzinfo=UTC)


def config(**changes):
    values = {
        "version": "planner-v2.0",
        "platform_cross_funding_policy": "ALLOW",
        "workspace_cross_funding_policy": "DEFAULT",
    }
    values.update(changes)
    return PlannerConfig(**values)


def upi(id="upi-1", **changes):
    values = {
        "id": id,
        "bank_id": "bank-1",
        "holder_id": "applicant-1",
        "active": True,
        "verified": True,
    }
    values.update(changes)
    return UPIInput(**values)


def event(index, *, upi_id="upi-1", amount="15000.00", submitted_at=None, cancelled=False):
    return RollingUsageInput(
        id=f"event-{index}",
        bank_id="bank-1",
        upi_id=upi_id,
        amount=Decimal(amount),
        submitted_at=submitted_at or CUTOFF - timedelta(hours=1),
        cancelled=cancelled,
    )


def check(events, *, upi_value=None, amount="15000.00", settings=None):
    return RollingLimitTracker(tuple(events)).check(
        upi=upi_value or upi(),
        amount=Decimal(amount),
        at=CUTOFF,
        config=settings or config(),
    )


def test_rl001_and_rl002_upi_count_boundary():
    five = [event(index) for index in range(5)]
    assert check(five).allowed
    sixth = check([*five, event(5)])
    assert not sixth.allowed
    assert "UPI_LIMIT_EXCEEDED" in sixth.blocking_reasons


def test_rl003_amount_cap_and_upi_override():
    result = check([event(1, amount="490000.00")])
    assert result.allowed is False
    assert result.upi_amount_after == Decimal("505000.00")
    override = check([], upi_value=upi(amount_limit_override=Decimal("10000.00")))
    assert "UPI_LIMIT_EXCEEDED" in override.blocking_reasons


def test_rl004_bank_shared_cap_aggregates_other_upi():
    events = [event(index, upi_id="upi-2") for index in range(6)]
    result = check(events)
    assert result.upi_count_after == 1
    assert result.bank_count_after == 7
    assert result.blocking_reasons == ("BANK_LIMIT_EXCEEDED",)
    assert check(events, settings=config(bank_level_enforcement=False)).allowed


def test_bank_amount_cap_aggregates_other_upi_and_respects_cancellation():
    events = [
        event(1, upi_id="upi-2", amount="490000.00"),
        event(2, upi_id="upi-2", amount="100000.00", cancelled=True),
    ]
    result = check(events)
    assert result.upi_amount_after == Decimal("15000.00")
    assert result.bank_amount_after == Decimal("505000.00")
    assert result.blocking_reasons == ("BANK_LIMIT_EXCEEDED",)
    assert check(events, settings=config(bank_level_enforcement=False)).allowed


def test_rl005_cancelled_does_not_count_and_rl006_released_still_counts():
    events = [event(index) for index in range(5)] + [event(5, cancelled=True)]
    assert check(events).allowed
    # A released mandate remains a submitted application until it ages out.
    assert not check([*events, event(6)]).allowed


def test_rl007_start_boundary_is_excluded_and_cutoff_included():
    old = [event(index, submitted_at=CUTOFF - timedelta(hours=24)) for index in range(6)]
    assert check(old).allowed
    current = [event(index, submitted_at=CUTOFF) for index in range(6)]
    assert not check(current).allowed


def test_reservation_returns_new_tracker_and_respects_zero_override():
    original = RollingLimitTracker()
    updated = original.reserve(
        event_id="planned-1", upi=upi(), amount=Decimal("15000.00"), at=CUTOFF, config=config()
    )
    assert len(original.events) == 0
    assert len(updated.events) == 1
    with pytest.raises(ValueError):
        updated.reserve(
            event_id="planned-1", upi=upi(), amount=Decimal("15000.00"), at=CUTOFF, config=config()
        )
    zero_cap = check([], upi_value=upi(count_limit_override=0))
    assert not zero_cap.allowed
