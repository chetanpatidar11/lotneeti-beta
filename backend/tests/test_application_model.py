from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from test_planner_persistence import setup_plan

from accounts.services import create_workspace
from applications.models import Application
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO
from planner.persistence import create_plan_run


def planned_application(workspace, row):
    return Application(
        workspace=workspace,
        plan_row=row,
        ipo=IPO.objects.get(pk=row.ipo_ref),
        applicant=Investor.objects.get(pk=row.applicant_ref),
        demat=DematAccount.objects.get(pk=row.demat_ref),
        bank=BankAccount.objects.get(pk=row.bank_ref),
        upi=UPIHandle.objects.get(pk=row.upi_ref),
        category=row.category,
        lots=row.lots,
        amount=row.amount,
    )


@pytest.mark.django_db
def test_application_statuses_and_timestamps_persist_with_exact_plan_mapping():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    application = planned_application(workspace, run.rows.get())
    application.save()
    assert application.status == Application.Status.PLANNED
    assert application.planned_at is not None
    assert application.submitted_at is None
    assert application.blocked_at is None
    assert application.result_at is None
    application.status = Application.Status.SUBMITTED
    application.submitted_at = datetime(2026, 10, 3, 10, tzinfo=UTC)
    application.save(update_fields=["status", "submitted_at"])
    stored = Application.objects.get(pk=application.pk)
    assert stored.status == Application.Status.SUBMITTED
    assert stored.submitted_at == application.submitted_at
    assert stored.amount == Decimal("15000.00")


@pytest.mark.django_db
def test_application_rejects_changed_amount_and_other_workspace_mapping():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    row = run.rows.get()
    changed = planned_application(workspace, row)
    changed.amount = Decimal("14999.00")
    with pytest.raises(ValidationError, match="must match its reviewed plan row"):
        changed.save()
    other = create_workspace(name="Other synthetic", owner=owner)
    foreign = planned_application(other, row)
    with pytest.raises(ValidationError, match="must match its reviewed plan row"):
        foreign.save()
    assert Application.objects.count() == 0
