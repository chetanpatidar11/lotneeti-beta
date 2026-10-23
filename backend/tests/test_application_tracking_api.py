from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from applications.models import Application
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount
from planner.export_readiness import assert_exportable_plan
from planner.persistence import create_plan_run


def assert_single_bank_capital(response, *, bank, balance, blocked, planned, available):
    expected = {
        "balance": balance,
        "blocked": blocked,
        "planned": planned,
        "available": available,
    }
    assert response.data == {**expected, "by_bank": {str(bank.pk): expected}}


@pytest.mark.django_db
def test_saved_plan_appears_as_planned_and_materializes_only_when_acted_on():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    row = run.rows.get()
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("application-list", args=[workspace.pk])

    planned = client.get(list_url)
    assert planned.status_code == 200
    assert [(item["id"], item["status"], item["is_plan_row"]) for item in planned.data] == [
        (str(row.pk), "PLANNED", True)
    ]
    assert Application.objects.count() == 0

    track_url = reverse("application-start-tracking", args=[workspace.pk, run.pk])
    tracked = client.post(track_url, {"row_ids": [str(row.pk)]}, format="json")
    assert tracked.status_code == 201
    assert len(tracked.data) == 1
    assert tracked.data[0]["plan_row_id"] == str(row.pk)
    assert tracked.data[0]["is_plan_row"] is False
    assert Application.objects.count() == 1
    assert [(item["id"], item["is_plan_row"]) for item in client.get(list_url).data] == [
        (tracked.data[0]["id"], False)
    ]


@pytest.mark.django_db
def test_saved_plan_projection_clears_and_foreign_rows_cannot_be_materialized():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("application-list", args=[workspace.pk])
    track_url = reverse("application-start-tracking", args=[workspace.pk, run.pk])

    import uuid

    rejected = client.post(track_url, {"row_ids": [str(uuid.uuid4())]}, format="json")
    assert rejected.status_code == 409
    assert Application.objects.count() == 0
    assert client.post(reverse("planner-run-clear", args=[workspace.pk, run.pk])).status_code == 200
    assert client.get(list_url).data == []


@pytest.mark.django_db
def test_submitted_then_blocked_updates_capital_without_changing_balance():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    track_url = reverse("application-start-tracking", args=[workspace.pk, run.pk])
    first = client.post(track_url, {}, format="json")
    assert first.status_code == 201
    assert len(first.data) == 1
    assert first.data[0]["status"] == "PLANNED"
    assert client.post(track_url, {}, format="json").status_code == 201
    assert Application.objects.count() == 1
    application = Application.objects.get()
    assert first.data[0]["upi_label"] == "demo@upi.test"
    assert first.data[0]["close_date"] == application.ipo.close_date
    assert first.data[0]["allotment_date"] == application.ipo.allotment_date
    assert first.data[0]["sold_quantity"] == 0
    capital_url = reverse("workspace-capital", args=[workspace.pk])
    assert client.get(capital_url).data["planned"] == "15000.00"

    submit_url = reverse("application-action", args=[workspace.pk, application.pk, "submit"])
    blocked_url = reverse("application-action", args=[workspace.pk, application.pk, "block"])
    assert client.post(blocked_url, {}, format="json").status_code == 409
    submitted = client.post(submit_url, {}, format="json")
    assert submitted.status_code == 200
    assert submitted.data["submitted_at"] is not None
    assert client.get(capital_url).data["planned"] == "15000.00"
    blocked = client.post(blocked_url, {}, format="json")
    assert blocked.status_code == 200
    assert blocked.data["blocked_at"] is not None
    assert client.post(blocked_url, {}, format="json").status_code == 409
    bank = BankAccount.objects.get(workspace=workspace)
    assert_single_bank_capital(
        client.get(capital_url),
        bank=bank,
        balance="50000.00",
        blocked="15000.00",
        planned="0.00",
        available="35000.00",
    )
    assert BankAccount.objects.get(workspace=workspace).current_balance == Decimal("50000.00")
    assert AuditEvent.objects.filter(action="application.blocked", workspace=workspace).count() == 1


@pytest.mark.django_db
def test_application_actions_are_scoped_and_viewers_cannot_write():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    viewer = User.objects.create_user(email="viewer@example.test")
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    client.force_authenticate(viewer)
    assert client.get(reverse("application-list", args=[workspace.pk])).status_code == 200
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, application.pk, "submit"]), {}
        ).status_code
        == 403
    )
    outsider = User.objects.create_user(email="outsider@example.test")
    client.force_authenticate(outsider)
    assert client.get(reverse("application-list", args=[workspace.pk])).status_code == 404


@pytest.mark.django_db
def test_not_allotted_releases_full_block_without_a_balance_change():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    for action in ("submit", "block"):
        assert (
            client.post(
                reverse("application-action", args=[workspace.pk, application.pk, action]), {}
            ).status_code
            == 200
        )
    url = reverse("application-action", args=[workspace.pk, application.pk, "not-allotted"])
    result = client.post(url, {})
    assert result.status_code == 200
    assert result.data["status"] == "NOT_ALLOTTED"
    assert result.data["result_at"] is not None
    assert client.post(url, {}).status_code == 409
    assert_single_bank_capital(
        client.get(reverse("workspace-capital", args=[workspace.pk])),
        bank=BankAccount.objects.get(workspace=workspace),
        balance="50000.00",
        blocked="0.00",
        planned="0.00",
        available="50000.00",
    )
    assert BankAccount.objects.get(workspace=workspace).current_balance == Decimal("50000.00")
    assert (
        AuditEvent.objects.filter(action="application.not_allotted", workspace=workspace).count()
        == 1
    )


@pytest.mark.django_db
def test_full_allotment_debits_actual_cost_once_and_releases_entire_block():
    owner, workspace, snapshot = setup_plan()
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    for action in ("submit", "block"):
        assert (
            client.post(
                reverse("application-action", args=[workspace.pk, application.pk, action]), {}
            ).status_code
            == 200
        )
    url = reverse("application-action", args=[workspace.pk, application.pk, "allotted"])
    result = client.post(url, {"quantity": 150, "actual_cost": "14850.00"}, format="json")
    assert result.status_code == 200
    assert result.data["status"] == "ALLOTTED"
    assert result.data["allotted_quantity"] == 150
    assert result.data["actual_cost"] == "14850.00"
    assert result.data["result_at"] is not None
    assert (
        client.post(url, {"quantity": 150, "actual_cost": "14850.00"}, format="json").status_code
        == 409
    )
    assert_single_bank_capital(
        client.get(reverse("workspace-capital", args=[workspace.pk])),
        bank=BankAccount.objects.get(workspace=workspace),
        balance="35150.00",
        blocked="0.00",
        planned="0.00",
        available="35150.00",
    )
    change = BalanceChange.objects.get(operation=BalanceChange.Operation.ALLOTMENT)
    assert change.old_balance == Decimal("50000.00")
    assert change.delta == Decimal("-14850.00")
    assert change.new_balance == Decimal("35150.00")
    assert (
        AuditEvent.objects.filter(action="application.allotted", workspace=workspace).count() == 1
    )


@pytest.mark.django_db
def test_partial_shni_allotment_releases_full_mandate_and_deducts_only_actual_cost():
    owner, workspace, snapshot = setup_plan()
    bank = BankAccount.objects.get(workspace=workspace)
    bank.current_balance = Decimal("230000.00")
    bank.save(update_fields=["current_balance", "updated_at"])
    snapshot = replace(
        snapshot,
        ipos=(replace(snapshot.ipos[0], mode="SHNI_PREFERRED"),),
        banks=(replace(snapshot.banks[0], balance=Decimal("230000.00")),),
    )
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    assert run.rows.get().category == "SHNI"
    assert run.rows.get().amount == Decimal("210000.00")
    client = APIClient()
    client.force_authenticate(owner)
    client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    application = Application.objects.get()
    for action in ("submit", "block"):
        assert (
            client.post(
                reverse("application-action", args=[workspace.pk, application.pk, action]), {}
            ).status_code
            == 200
        )
    result = client.post(
        reverse("application-action", args=[workspace.pk, application.pk, "allotted"]),
        {"quantity": 420, "actual_cost": "42000.00"},
        format="json",
    )
    assert result.status_code == 200
    assert result.data["allotted_quantity"] == 420
    assert result.data["actual_cost"] == "42000.00"
    assert_single_bank_capital(
        client.get(reverse("workspace-capital", args=[workspace.pk])),
        bank=bank,
        balance="188000.00",
        blocked="0.00",
        planned="0.00",
        available="188000.00",
    )
    assert BalanceChange.objects.get(operation="ALLOTMENT").delta == Decimal("-42000.00")


@pytest.mark.django_db
def test_closing_day_record_plan_can_be_tracked_submitted_and_blocked_but_not_exported():
    owner, workspace, snapshot = setup_plan()
    late_snapshot = replace(snapshot, as_of=datetime(2026, 10, 3, 17, 1, tzinfo=UTC))
    run = create_plan_run(workspace=workspace, snapshot=late_snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    tracked = client.post(reverse("application-start-tracking", args=[workspace.pk, run.pk]), {})
    assert tracked.status_code == 201
    application = Application.objects.get()
    for action in ("submit", "block"):
        assert (
            client.post(
                reverse("application-action", args=[workspace.pk, application.pk, action]), {}
            ).status_code
            == 200
        )
    application.refresh_from_db()
    assert application.status == "BLOCKED"
    with pytest.raises(ValidationError, match="record keeping"):
        assert_exportable_plan(run)


@pytest.mark.django_db
def test_stale_saved_plans_share_six_submission_slots_across_categories_and_upis(monkeypatch):
    from funding.models import UPIHandle
    from ipos.models import IPO
    from planner.models import PlanRow

    owner, workspace, snapshot = setup_plan()
    client = APIClient()
    client.force_authenticate(owner)
    run = create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    row = run.rows.get()
    ipo = IPO.objects.get(pk=row.ipo_ref)
    first_upi = UPIHandle.objects.get(pk=row.upi_ref)
    second_upi = UPIHandle(bank=first_upi.bank, holder=first_upi.holder, verified=True)
    second_upi.set_handle("second@synthetic.test")
    second_upi.save()
    instant = timezone.now()
    monkeypatch.setattr("applications.services.timezone.now", lambda: instant)
    applications = []
    for index in range(7):
        clone = IPO.objects.get(pk=ipo.pk)
        clone.pk = None
        clone.source_record_id = f"synthetic-extra-{index}"
        clone.save()
        category = "SHNI" if index == 0 else "RETAIL"
        lots = 14 if category == "SHNI" else 1
        handle = first_upi if index % 2 == 0 else second_upi
        plan_row = PlanRow.objects.create(
            plan_run=run,
            position=index + 1,
            ipo_ref=str(clone.pk),
            applicant_ref=row.applicant_ref,
            demat_ref=row.demat_ref,
            bank_ref=row.bank_ref,
            upi_ref=str(handle.pk),
            category=category,
            lots=lots,
            amount=Decimal(15000 * lots),
        )
        item = Application.objects.create(
            workspace=workspace,
            plan_row=plan_row,
            ipo=clone,
            applicant_id=row.applicant_ref,
            demat_id=row.demat_ref,
            bank_id=row.bank_ref,
            upi=handle,
            category=category,
            lots=lots,
            amount=plan_row.amount,
        )
        applications.append(item)
    for item in applications[:6]:
        assert (
            client.post(
                reverse("application-action", args=[workspace.pk, item.pk, "submit"]), {}
            ).status_code
            == 200
        )
    seventh = applications[-1]
    response = client.post(
        reverse("application-action", args=[workspace.pk, seventh.pk, "submit"]), {}
    )
    assert response.status_code == 409
    assert "Retail and sHNI" in response.data["detail"]
    seventh.refresh_from_db()
    assert seventh.status == "PLANNED"
    # The half-open 24h window releases exactly expired slots.
    monkeypatch.setattr("applications.services.timezone.now", lambda: instant + timedelta(hours=24))
    assert (
        client.post(
            reverse("application-action", args=[workspace.pk, seventh.pk, "submit"]), {}
        ).status_code
        == 200
    )
