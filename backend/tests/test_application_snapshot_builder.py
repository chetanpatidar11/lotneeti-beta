from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from test_planner_preview_api import setup_workspace

from applications.services import mark_allotted, mark_blocked, mark_submitted, start_tracking_plan
from funding.models import BankAccount
from ipos.models import IPO, IPOUserDecision
from planner.cash import cash_at_cutoff
from planner.engine import generate_proposal
from planner.persistence import create_plan_run
from planner.snapshot_builder import build_snapshot


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_live_block_releases_next_day_and_actual_allotment_replaces_expectation():
    owner, workspace, _, ipo, _ = setup_workspace()
    zone = ZoneInfo("Asia/Kolkata")
    as_of = datetime(2030, 10, 2, 10, tzinfo=zone)
    original = build_snapshot(workspace=workspace, as_of=as_of)
    run = create_plan_run(workspace=workspace, snapshot=original, actor=owner)
    application = start_tracking_plan(plan_run=run, actor=owner)[0]
    mark_submitted(application=application, actor=owner)
    mark_blocked(application=application, actor=owner)

    active = build_snapshot(workspace=workspace, as_of=as_of)
    assert len(active.cash_blocks) == 1
    assert len(active.rolling_usage) == 1
    assert len(active.existing_applications) == 1
    assert active.cash_blocks[0].release_at == datetime(2030, 10, 10, 0, tzinfo=zone)
    same_day = datetime(2030, 10, 9, 17, tzinfo=zone)
    next_day = datetime(2030, 10, 10, 0, tzinfo=zone)
    assert cash_at_cutoff(
        bank=active.banks[0], cutoff=same_day, blocks=active.cash_blocks
    ).available == Decimal("35000.00")
    assert cash_at_cutoff(
        bank=active.banks[0], cutoff=next_day, blocks=active.cash_blocks
    ).available == Decimal("50000.00")

    mark_allotted(
        application=application, actor=owner, quantity=150, actual_cost=Decimal("14850.00")
    )
    actual = build_snapshot(workspace=workspace, as_of=as_of)
    assert actual.cash_blocks == ()
    assert actual.banks[0].balance == Decimal("35150.00")
    assert cash_at_cutoff(
        bank=actual.banks[0], cutoff=same_day, blocks=actual.cash_blocks
    ).available == Decimal("35150.00")
    assert len(actual.rolling_usage) == 1
    assert actual.existing_applications[0].ipo_id == str(ipo.pk)


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_ee005_partial_allotment_and_next_day_reuse_in_later_planner_run():
    owner, workspace, _, first_ipo, _ = setup_workspace()
    bank = BankAccount.objects.get(workspace=workspace)
    bank.current_balance = Decimal("20000.00")
    bank.save(update_fields=["current_balance", "updated_at"])
    zone = ZoneInfo("Asia/Kolkata")
    as_of = datetime(2030, 10, 2, 10, tzinfo=zone)
    original = build_snapshot(
        workspace=workspace, as_of=as_of, ipo_ids=frozenset({str(first_ipo.pk)})
    )
    run = create_plan_run(workspace=workspace, snapshot=original, actor=owner)
    application = start_tracking_plan(plan_run=run, actor=owner)[0]
    mark_submitted(application=application, actor=owner)
    mark_blocked(application=application, actor=owner)
    later = IPO.objects.create(
        issuer_name="Synthetic Later Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        open_date=first_ipo.close_date,
        close_date=first_ipo.allotment_date + timedelta(days=1),
        allotment_date=first_ipo.allotment_date + timedelta(days=6),
        status="UPCOMING",
        publication_state="PUBLISHED",
        source_key="manual",
        source_record_id="synthetic-later-ipo",
    )
    IPOUserDecision.objects.create(workspace=workspace, ipo=later, decision="APPLY")
    expected = generate_proposal(build_snapshot(workspace=workspace, as_of=as_of))
    assert expected.audit.valid
    assert [(row.ipo_id, row.amount) for row in expected.coverage.rows] == [
        (str(later.pk), Decimal("15000.00"))
    ]
    mark_allotted(application=application, actor=owner, quantity=50, actual_cost=Decimal("5000.00"))
    actual = build_snapshot(workspace=workspace, as_of=as_of)
    assert actual.cash_blocks == ()
    assert actual.banks[0].balance == Decimal("15000.00")
    result = generate_proposal(actual)
    assert result.audit.valid
    assert [(row.ipo_id, row.amount) for row in result.coverage.rows] == [
        (str(later.pk), Decimal("15000.00"))
    ]
