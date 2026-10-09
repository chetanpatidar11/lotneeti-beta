from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount
from investors.models import Investor


@pytest.mark.django_db
def test_set_balance_replaces_exact_amount_and_records_difference():
    owner = User.objects.create_user(email="owner@example.test")
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
    url = reverse("bank-set-balance", args=[workspace.pk, bank.pk])

    response = client.post(url, {"amount": "61380.00"})

    assert response.status_code == 201
    assert response.data["balance"] == "61380.00"
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("61380.00")
    change = BalanceChange.objects.get(pk=response.data["id"])
    assert change.operation == BalanceChange.Operation.SET
    assert change.old_balance == Decimal("50000.00")
    assert change.delta == Decimal("11380.00")
    assert change.new_balance == Decimal("61380.00")
    assert AuditEvent.objects.filter(action="balance.set", object_id=str(change.pk)).exists()

    lower = client.post(url, {"amount": "40000.00"})
    assert lower.status_code == 201
    assert BalanceChange.objects.get(pk=lower.data["id"]).delta == Decimal("-21380.00")
