from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from core.models import AuditEvent
from funding.models import BalanceChange, BankAccount
from investors.models import Investor


@pytest.mark.django_db
def test_add_money_updates_balance_and_records_immutable_history():
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
        reverse("bank-add-money", args=[workspace.pk, bank.pk]),
        {"amount": "5000.00", "note": "Synthetic deposit"},
    )

    assert response.status_code == 201
    assert response.data["balance"] == "55000.00"
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("55000.00")
    change = BalanceChange.objects.get(pk=response.data["id"])
    assert change.old_balance == Decimal("50000.00")
    assert change.delta == Decimal("5000.00")
    assert change.new_balance == Decimal("55000.00")
    assert change.actor == owner
    assert AuditEvent.objects.filter(action="balance.added", object_id=str(change.pk)).exists()
    with pytest.raises(ValueError):
        change.delete()


@pytest.mark.django_db
def test_add_money_rejects_nonpositive_amount_and_viewer_write():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    investor = Investor(workspace=workspace, name="Synthetic")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Demo Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    url = reverse("bank-add-money", args=[workspace.pk, bank.pk])
    client = APIClient()

    client.force_authenticate(owner)
    assert client.post(url, {"amount": "0.00"}).status_code == 400
    client.force_authenticate(viewer)
    assert client.post(url, {"amount": "5000.00"}).status_code == 403
    bank.refresh_from_db()
    assert bank.current_balance == Decimal("0.00")
