from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from test_planner_persistence import setup_plan

from accounts.models import User
from accounts.services import create_workspace
from funding.models import BalanceChange, BankAccount


@pytest.mark.django_db
def test_statement_combines_banks_and_filters_with_workspace_scope():
    owner, workspace, _ = setup_plan()
    first = BankAccount.objects.get(workspace=workspace)
    second = BankAccount(
        workspace=workspace,
        owner=first.owner,
        bank_name="Other Synthetic Bank",
        active=False,
    )
    second.set_account_number("DEMO-ACCOUNT-0002")
    second.save()
    for bank in (first, second):
        BalanceChange.objects.create(
            bank=bank,
            operation=BalanceChange.Operation.ADD,
            old_balance=Decimal("0"),
            delta=Decimal("100"),
            new_balance=Decimal("100"),
            actor=owner,
        )
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("workspace-balance-statement", args=[workspace.pk])
    all_rows = client.get(url)
    assert all_rows.status_code == 200
    assert all_rows.data["total"] == 2
    assert {row["bank_id"] for row in all_rows.data["results"]} == {str(first.pk), str(second.pk)}
    filtered = client.get(url, {"bank": str(first.pk)})
    assert filtered.status_code == 200
    assert [row["bank_id"] for row in filtered.data["results"]] == [str(first.pk)]
    assert client.get(url, {"page": "0"}).status_code == 400
    assert client.get(url, {"bank": "not-a-bank"}).status_code == 400
    outsider = User.objects.create_user(email="outsider-statement@example.test")
    other_workspace = create_workspace(name="Other Synthetic Workspace", owner=outsider)
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 403
    client.force_authenticate(owner)
    assert (
        client.get(reverse("workspace-balance-statement", args=[other_workspace.pk])).status_code
        == 403
    )


@pytest.mark.django_db
def test_statement_pages_through_more_than_fifty_changes():
    owner, workspace, _ = setup_plan()
    bank = BankAccount.objects.get(workspace=workspace)
    for index in range(51):
        BalanceChange.objects.create(
            bank=bank,
            operation=BalanceChange.Operation.ADD,
            old_balance=Decimal(index),
            delta=Decimal("1"),
            new_balance=Decimal(index + 1),
            actor=owner,
        )
    client = APIClient()
    client.force_authenticate(owner)
    url = reverse("workspace-balance-statement", args=[workspace.pk])
    first_page = client.get(url)
    second_page = client.get(url, {"page": "2"})
    assert first_page.data["total"] == 51
    assert len(first_page.data["results"]) == 50
    assert first_page.data["next_page"] == 2
    assert len(second_page.data["results"]) == 1
    assert second_page.data["next_page"] is None
