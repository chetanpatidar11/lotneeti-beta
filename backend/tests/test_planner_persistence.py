from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO
from planner.dto import (
    ApplicantInput,
    BankInput,
    DematInput,
    IPOInput,
    PlannerConfig,
    PlannerSnapshot,
    UPIInput,
)
from planner.export_readiness import assert_exportable_plan
from planner.models import PlanRow, PlanRun
from planner.persistence import create_plan_run


def make_investor(workspace, *, name="Synthetic", pan="TESTX0001A"):
    investor = Investor(workspace=workspace, name=name)
    investor.set_pan(pan)
    investor.save()
    return investor


def setup_plan():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Synthetic workspace", owner=owner)
    investor = make_investor(workspace)
    demat = DematAccount(investor=investor, depository="CDSL", broker="Synthetic Broker")
    demat.set_dp_id("DEMO-DP-001")
    demat.set_client_id("DEMO-CLIENT-001")
    demat.save()
    bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Synthetic Bank",
        current_balance=Decimal("50000.00"),
    )
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    upi = UPIHandle(bank=bank, holder=investor, verified=True)
    upi.set_handle("demo@upi.test")
    upi.save()
    ipo = IPO.objects.create(
        issuer_name="Synthetic Industries",
        issue_type="MAINBOARD",
        lower_price=Decimal("100.00"),
        upper_price=Decimal("100.00"),
        lot_size=150,
        open_date=date(2026, 10, 1),
        close_date=date(2026, 10, 3),
        allotment_date=date(2026, 10, 9),
        status="OPEN",
        publication_state="PUBLISHED",
        source_key="manual",
        source_record_id="synthetic-ipo-1",
    )
    snapshot = PlannerSnapshot(
        as_of=datetime(2026, 9, 27, 10, tzinfo=UTC),
        config=PlannerConfig("planner-v2.0", "ALLOW", "DEFAULT"),
        ipos=(
            IPOInput(
                str(ipo.pk),
                True,
                Decimal("25.00"),
                Decimal("100.00"),
                150,
                datetime(2026, 10, 3, 17, tzinfo=UTC),
                date(2026, 10, 9),
                "RETAIL_ONLY",
            ),
        ),
        applicants=(ApplicantInput(str(investor.pk), 1, True),),
        demats=(DematInput(str(demat.pk), str(investor.pk), True),),
        banks=(BankInput(str(bank.pk), str(investor.pk), Decimal("50000.00"), True, "DEFAULT"),),
        upis=(UPIInput(str(upi.pk), str(bank.pk), str(investor.pk), True, True),),
    )
    return owner, workspace, snapshot


@pytest.mark.django_db
def test_plan_run_saves_snapshot_rows_reasons_hashes_and_audit_event():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    stored = PlanRun.objects.get(pk=run.pk)
    assert stored.status == PlanRun.Status.READY
    assert stored.planned_total == Decimal("15000.00")
    assert len(stored.input_snapshot_hash) == len(stored.output_hash) == 64
    assert "TESTX0001A" not in stored.input_snapshot
    rows = list(stored.rows.all())
    assert len(rows) == 1
    assert rows[0].position == 0
    assert rows[0].applicant_ref == snapshot.applicants[0].id
    assert rows[0].reasons[0]["code"] == "APPLICANT_PRIORITY"
    assert stored.audit_issues == []
    assert (
        AuditEvent.objects.filter(action="planner.run.generated", workspace=workspace).count() == 1
    )


@pytest.mark.django_db
def test_snapshot_from_other_workspace_and_viewer_actor_are_rejected():
    owner, workspace, snapshot = setup_plan()
    other = create_workspace(name="Other", owner=owner)
    outsider = make_investor(other, name="Other Synthetic", pan="TESTX0002B")
    poisoned = replace(snapshot, applicants=(ApplicantInput(str(outsider.pk), 1, True),))
    with pytest.raises(ValidationError, match="out-of-workspace applicants"):
        create_plan_run(workspace=workspace, snapshot=poisoned, actor=owner)
    viewer = User.objects.create_user(email="viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    with pytest.raises(ValidationError, match="cannot generate"):
        create_plan_run(workspace=workspace, snapshot=snapshot, actor=viewer)
    assert PlanRun.objects.count() == 0


@pytest.mark.django_db
def test_row_write_failure_rolls_back_plan_run_and_audit(monkeypatch):
    owner, workspace, snapshot = setup_plan()

    def fail_bulk_create(*_args, **_kwargs):
        raise RuntimeError("Synthetic row insert failure")

    monkeypatch.setattr(PlanRow.objects, "bulk_create", fail_bulk_create)
    with pytest.raises(RuntimeError, match="Synthetic row insert failure"):
        create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    assert PlanRun.objects.count() == 0
    assert AuditEvent.objects.filter(action="planner.run.generated").count() == 0


@pytest.mark.django_db
def test_export_readiness_rejects_blocking_run_or_row_but_allows_warning():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    assert_exportable_plan(run)
    row = run.rows.get()
    row.warnings = ["CROSS_FUNDING"]
    row.save(update_fields=["warnings"])
    assert_exportable_plan(run)
    row.blocking_reasons = ["INSUFFICIENT_BALANCE"]
    row.save(update_fields=["blocking_reasons"])
    with pytest.raises(ValidationError, match="blocking plan issues"):
        assert_exportable_plan(run)
    row.blocking_reasons = []
    row.save(update_fields=["blocking_reasons"])
    run.status = PlanRun.Status.BLOCKED
    run.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="blocking plan issues"):
        assert_exportable_plan(run)
