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
def test_remove_money_decreases_balance_and_records_negative_change():
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

    response = client.post(
        reverse("bank-remove-money", args=[workspace.pk, bank.pk]),
        {"amount": "5000.00"},
    )

    assert response.status_code == 201
    assert response.data["amount"] == "5000.00"
    assert response.data["balance"] == "45000.00"
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("45000.00")
    change = BalanceChange.objects.get(pk=response.data["id"])
    assert change.operation == BalanceChange.Operation.REMOVE
    assert change.delta == Decimal("-5000.00")
    assert change.new_balance == Decimal("45000.00")
    assert AuditEvent.objects.filter(action="balance.removed", object_id=str(change.pk)).exists()
