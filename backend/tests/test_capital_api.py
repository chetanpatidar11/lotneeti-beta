from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User
from funding.models import BankAccount
from planner.capital import capital_totals
from planner.persistence import create_plan_run


def test_bank_level_available_never_goes_negative_and_blocks_reduce_it():
    totals = capital_totals(
        {"a": Decimal("10000.00"), "b": Decimal("30000.00")},
        blocked_by_bank={"a": Decimal("4000.00")},
        planned_by_bank={"a": Decimal("15000.00"), "b": Decimal("5000.00")},
    )
    assert totals.balance == Decimal("40000.00")
    assert totals.blocked == Decimal("4000.00")
    assert totals.planned == Decimal("20000.00")
    assert totals.available == Decimal("25000.00")


@pytest.mark.django_db
def test_workspace_capital_uses_latest_saved_plan_and_is_member_scoped():
    owner, workspace, snapshot = setup_plan()
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("workspace-capital", args=[workspace.pk])
    initial = client.get(url)
    bank_id = str(BankAccount.objects.get(workspace=workspace).pk)
    assert initial.data == {
        "balance": "50000.00",
        "blocked": "0.00",
        "planned": "0.00",
        "available": "50000.00",
        "by_bank": {
            bank_id: {
                "balance": "50000.00",
                "blocked": "0.00",
                "planned": "0.00",
                "available": "50000.00",
            }
        },
    }
    create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    planned = client.get(url)
    assert planned.data["planned"] == "15000.00"
    assert planned.data["available"] == "35000.00"
    bank = BankAccount.objects.get(workspace=workspace)
    bank.current_balance = Decimal("10000.00")
    bank.save(update_fields=["current_balance", "updated_at"])
    assert client.get(url).data["available"] == "0.00"
    client.force_authenticate(User.objects.create_user(email="outsider@example.test"))
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_ba007_add_money_after_plan_updates_live_available_amount():
    owner, workspace, snapshot = setup_plan()
    bank = BankAccount.objects.get(workspace=workspace)
    bank.current_balance = Decimal("20000.00")
    bank.save(update_fields=["current_balance", "updated_at"])
    create_plan_run(workspace=workspace, snapshot=snapshot, actor=owner)
    client = APIClient()
    client.force_authenticate(owner)
    capital_url = reverse("workspace-capital", args=[workspace.pk])
    assert client.get(capital_url).data["available"] == "5000.00"
    added = client.post(
        reverse("bank-add-money", args=[workspace.pk, bank.pk]),
        {"amount": "10000.00"},
        format="json",
    )
    assert added.status_code == 201
    totals = client.get(capital_url).data
    assert totals["balance"] == "30000.00"
    assert totals["planned"] == "15000.00"
    assert totals["available"] == "15000.00"
