from dataclasses import replace
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User, WorkspaceMembership
from applications.models import Application
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount
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
    assert first.data[0]["upi_label"].startswith("••••@")
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
