from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import create_workspace
from funding.models import BankAccount
from investors.models import Investor


@pytest.mark.django_db
def test_recent_balance_changes_are_scoped_and_plain_language():
    owner = User.objects.create_user(email="owner@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(
        workspace=workspace,
        owner=investor,
        bank_name="Demo Bank",
        current_balance=Decimal("50000.00"),
    )
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    client = APIClient()
    client.force_authenticate(owner)
    args = [workspace.pk, bank.pk]
    client.post(reverse("bank-add-money", args=args), {"amount": "5000.00"})
    client.post(reverse("bank-remove-money", args=args), {"amount": "2000.00"})
    client.post(reverse("bank-set-balance", args=args), {"amount": "61000.00"})

    response = client.get(reverse("bank-balance-history", args=args))

    assert response.status_code == 200
    assert [item["operation"] for item in response.data] == ["SET", "REMOVE", "ADD"]
    assert response.data[0]["amount"] == "61000.00"
    assert response.data[1]["amount"] == "2000.00"
    assert response.data[2]["amount"] == "5000.00"
    assert response.data[0]["balance"] == "61000.00"

    client.force_authenticate(outsider)
    assert client.get(reverse("bank-balance-history", args=args)).status_code == 403
