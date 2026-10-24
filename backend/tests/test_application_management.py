from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from applications.models import Application
from applications.services import start_tracking_plan
from core.models import AuditEvent
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPOUserDecision
from planner.models import PlanRow
from planner.persistence import create_plan_run
from planner.snapshot_builder import build_snapshot


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
@override_settings(PLANNER_PLATFORM_CROSS_FUNDING_POLICY="ALLOW")
def test_submitted_edit_reallocates_planned_capital_and_cancel_keeps_history():
    owner, workspace, original = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=original, actor=owner)
    item = start_tracking_plan(plan_run=run, actor=owner)[0]
    client = _client(owner)
    original_bank = item.bank
    second_bank = BankAccount(
        workspace=workspace,
        owner=item.applicant,
        bank_name="Second Synthetic Bank",
        current_balance=Decimal("50000.00"),
    )
    second_bank.set_account_number("DEMO-ACCOUNT-0002")
    second_bank.save()
    second_upi = UPIHandle(bank=second_bank, holder=item.applicant, verified=True)
    second_upi.set_handle("second@upi.test")
    second_upi.save()
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, item.pk, "submit"])
        ).status_code
        == 200
    )

    changed = client.post(
        reverse("application-action", args=[workspace.pk, item.pk, "edit"]),
        {
            "category": "RETAIL",
            "lots": 1,
            "bank": str(second_bank.pk),
            "upi": str(second_upi.pk),
        },
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["status"] == "SUBMITTED"
    assert changed.data["edited_at"] is not None
    assert changed.data["bank"] == str(second_bank.pk)
    item.refresh_from_db()
    assert item.plan_row.bank_ref == str(original_bank.pk)
    capital = client.get(reverse("workspace-capital", args=[workspace.pk])).data
    assert capital["by_bank"][str(original_bank.pk)]["planned"] == "0.00"
    assert capital["by_bank"][str(second_bank.pk)]["planned"] == "15000.00"

    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, item.pk, "block"])
        ).status_code
        == 200
    )
    assert (
        client.get(reverse("workspace-capital", args=[workspace.pk])).data["blocked"] == "15000.00"
    )
    cancelled = client.post(reverse("application-action", args=[workspace.pk, item.pk, "cancel"]))
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == "CANCELLED"
    assert cancelled.data["cancelled_at"] is not None
    assert client.get(reverse("workspace-capital", args=[workspace.pk])).data["blocked"] == "0.00"
    assert Application.objects.get(pk=item.pk).submitted_at is not None
    assert AuditEvent.objects.filter(workspace=workspace, action="application.edited").count() == 1
    assert (
        AuditEvent.objects.filter(workspace=workspace, action="application.cancelled").count() == 1
    )

    IPOUserDecision.objects.create(workspace=workspace, ipo=item.ipo, decision="APPLY")
    snapshot = build_snapshot(
        workspace=workspace,
        as_of=datetime(2026, 10, 2, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert snapshot.cash_blocks == ()
    assert snapshot.rolling_usage[0].cancelled is True
    assert snapshot.existing_applications[0].cancelled is True
    assert (
        client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk])).status_code
        == 409
    )
    replacement_run = create_plan_run(workspace=workspace, snapshot=original, actor=owner)
    assert (
        client.post(
            reverse("application-start-tracking", args=[workspace.pk, replacement_run.pk])
        ).status_code
        == 201
    )
    assert Application.objects.filter(workspace=workspace).count() == 2


@pytest.mark.django_db
def test_bulk_update_is_atomic_and_workspace_scoped():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    first = start_tracking_plan(plan_run=run, actor=owner)[0]
    second_investor = Investor(workspace=workspace, name="Second Synthetic")
    second_investor.set_pan("TESTX0002B")
    second_investor.save()
    second_demat = DematAccount(investor=second_investor, depository="CDSL")
    second_demat.set_dp_id("")
    second_demat.set_client_id("DEMO-CLIENT-002")
    second_demat.save()
    row = PlanRow.objects.create(
        plan_run=run,
        position=1,
        ipo_ref=str(first.ipo_id),
        applicant_ref=str(second_investor.pk),
        category="RETAIL",
        lots=1,
        amount=first.amount,
        demat_ref=str(second_demat.pk),
        bank_ref=str(first.bank_id),
        upi_ref=str(first.upi_id),
    )
    second = Application.objects.create(
        workspace=workspace,
        plan_row=row,
        ipo=first.ipo,
        applicant=second_investor,
        demat=second_demat,
        bank=first.bank,
        upi=first.upi,
        category="RETAIL",
        lots=1,
        amount=first.amount,
    )
    ordered = list(Application.objects.filter(pk__in=[first.pk, second.pk]).order_by("pk"))
    client = _client(owner)
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, ordered[1].pk, "submit"])
        ).status_code
        == 200
    )
    bulk_url = reverse("application-bulk", args=[workspace.pk])
    mixed = client.post(
        bulk_url, {"action": "submit", "ids": [str(item.pk) for item in ordered]}, format="json"
    )
    assert mixed.status_code == 409
    ordered[0].refresh_from_db()
    assert ordered[0].status == "PLANNED"
    assert (
        AuditEvent.objects.filter(workspace=workspace, action="application.submitted").count() == 1
    )

    other_workspace = create_workspace(name="Other Synthetic", owner=owner)
    assert (
        client.post(
            reverse("application-bulk", args=[other_workspace.pk]),
            {"action": "cancel", "ids": [str(first.pk)]},
            format="json",
        ).status_code
        == 404
    )
    assert (
        client.post(
            bulk_url, {"action": "cancel", "ids": [str(first.pk), str(first.pk)]}, format="json"
        ).status_code
        == 400
    )
    viewer = User.objects.create_user(email="application-viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert (
        client.post(
            bulk_url, {"action": "cancel", "ids": [str(first.pk)]}, format="json"
        ).status_code
        == 403
    )
    client.force_authenticate(owner)
    cancelled = client.post(
        bulk_url, {"action": "cancel", "ids": [str(first.pk), str(second.pk)]}, format="json"
    )
    assert cancelled.status_code == 200
    assert all(item["status"] == "CANCELLED" for item in cancelled.data)


@pytest.mark.django_db
def test_edit_rejects_other_workspace_payment_mapping_and_invalid_lots():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    item = start_tracking_plan(plan_run=run, actor=owner)[0]
    other = create_workspace(name="Other Synthetic", owner=owner)
    other_investor = Investor(workspace=other, name="Other Synthetic")
    other_investor.set_pan("TESTX0002B")
    other_investor.save()
    bank = BankAccount(workspace=other, owner=other_investor, bank_name="Other Bank")
    bank.set_account_number("DEMO-ACCOUNT-OTHER")
    bank.save()
    upi = UPIHandle(bank=bank, holder=other_investor, verified=True)
    upi.set_handle("other@upi.test")
    upi.save()
    client = _client(owner)
    url = reverse("application-action", args=[workspace.pk, item.pk, "edit"])
    assert (
        client.post(
            url,
            {"category": "RETAIL", "lots": 1, "bank": str(bank.pk), "upi": str(upi.pk)},
            format="json",
        ).status_code
        == 409
    )
    assert (
        client.post(
            url,
            {"category": "RETAIL", "lots": 14, "bank": str(item.bank_id), "upi": str(item.upi_id)},
            format="json",
        ).status_code
        == 409
    )
    assert (
        client.post(
            url,
            {"category": "SHNI", "lots": 14, "bank": str(item.bank_id), "upi": str(item.upi_id)},
            format="json",
        ).status_code
        == 409
    )
    item.refresh_from_db()
    assert item.edited_at is None
