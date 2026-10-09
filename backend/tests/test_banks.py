from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from funding.models import BalanceChange, BankAccount
from investors.models import Investor


def synthetic_investor(workspace, pan="TESTX0001A"):
    investor = Investor(workspace=workspace, name="Synthetic Person")
    investor.set_pan(pan)
    investor.save()
    return investor


@pytest.mark.django_db
def test_bank_create_has_masked_number_balance_and_opening_history():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    investor = synthetic_investor(workspace)
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("bank-list", args=[workspace.pk])

    response = client.post(
        list_url,
        {
            "owner": str(investor.pk),
            "bank_name": "Demo Bank",
            "account_number": "DEMO-ACCOUNT-0001",
            "initial_balance": "50000.00",
            "cross_funding_policy": "WARN",
        },
    )

    assert response.status_code == 201
    assert response.data["account_masked"] == "••••0001"
    assert response.data["current_balance"] == "50000.00"
    assert "account_number" not in response.data
    bank = BankAccount.objects.get(pk=response.data["id"])
    assert "DEMO-ACCOUNT-0001" not in bank.account_ciphertext
    assert bank.cross_funding_policy == BankAccount.CrossFundingPolicy.WARN
    change = BalanceChange.objects.get(bank=bank)
    assert change.operation == BalanceChange.Operation.SET
    assert change.old_balance == Decimal("0.00")
    assert change.new_balance == Decimal("50000.00")
    assert change.actor == owner

    detail_url = reverse("bank-detail", args=[workspace.pk, bank.pk])
    assert client.patch(detail_url, {"active": False}).status_code == 200
    assert client.patch(detail_url, {"initial_balance": "70000.00"}).status_code == 400
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("50000.00")


@pytest.mark.django_db
def test_bank_owner_must_belong_to_current_workspace():
    owner = User.objects.create_user(email="owner@example.test")
    first = create_workspace(name="First", owner=owner)
    second = create_workspace(name="Second", owner=owner)
    other_investor = synthetic_investor(second)
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        reverse("bank-list", args=[first.pk]),
        {
            "owner": str(other_investor.pk),
            "bank_name": "Demo Bank",
            "account_number": "DEMO-ACCOUNT-0001",
        },
    )

    assert response.status_code == 400
    assert BankAccount.objects.count() == 0


@pytest.mark.django_db
def test_bank_workspace_scope_and_viewer_write_denial():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    investor = synthetic_investor(workspace)
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Demo Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    detail_url = reverse("bank-detail", args=[workspace.pk, bank.pk])
    client = APIClient()

    client.force_authenticate(outsider)
    assert client.get(detail_url).status_code == 403

    client.force_authenticate(viewer)
    assert client.get(detail_url).status_code == 200
    assert client.patch(detail_url, {"active": False}).status_code == 403
