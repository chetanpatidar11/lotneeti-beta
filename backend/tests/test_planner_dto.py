from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from planner.dto import ApplicantInput, IPOInput, PlannerConfig, PlannerSnapshot, canonical_json


def snapshot(*, reverse=False, as_of=None):
    applicants = (
        ApplicantInput(id="wife", priority=1, active=True),
        ApplicantInput(id="mother", priority=2, active=True),
    )
    ipos = (
        IPOInput(
            id="ipo-b",
            selected=True,
            gmp_percent=Decimal("20.00"),
            upper_price=Decimal("100.00"),
            lot_size=150,
            cutoff_at=datetime(2026, 10, 3, 17, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            allotment_date=date(2026, 10, 8),
            mode="RETAIL_ONLY",
        ),
        IPOInput(
            id="ipo-a",
            selected=False,
            gmp_percent=None,
            upper_price=Decimal("120.00"),
            lot_size=125,
            cutoff_at=datetime(2026, 10, 4, 17, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            allotment_date=date(2026, 10, 9),
            mode="CUSTOM",
        ),
    )
    return PlannerSnapshot(
        as_of=as_of or datetime(2026, 9, 26, 10, tzinfo=UTC),
        config=PlannerConfig(
            version="planner-v2.0",
            platform_cross_funding_policy="ALLOW",
            workspace_cross_funding_policy="DEFAULT",
        ),
        ipos=tuple(reversed(ipos)) if reverse else ipos,
        applicants=tuple(reversed(applicants)) if reverse else applicants,
    )


def test_snapshot_serialization_is_stable_across_input_order_and_timezones():
    first = snapshot()
    same_in_other_zone = snapshot(
        reverse=True,
        as_of=datetime(2026, 9, 26, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )
    assert canonical_json(first) == canonical_json(same_in_other_zone)
    assert '"version":"planner-v2.0"' in canonical_json(first)
    assert '"gmp_percent":"20"' in canonical_json(first)


def test_snapshot_is_immutable_and_rejects_orm_like_or_mutable_inputs():
    with pytest.raises(FrozenInstanceError):
        snapshot().applicants = ()
    with pytest.raises(TypeError):
        PlannerSnapshot(
            as_of=datetime(2026, 9, 26, 10, tzinfo=UTC),
            config=snapshot().config,
            applicants=[ApplicantInput(id="wife", priority=1, active=True)],
        )
    with pytest.raises(TypeError):
        PlannerSnapshot(
            as_of=datetime(2026, 9, 26, 10, tzinfo=UTC),
            config=snapshot().config,
            applicants=(object(),),
        )
    with pytest.raises(ValueError):
        snapshot(as_of=datetime(2026, 9, 26, 10))
