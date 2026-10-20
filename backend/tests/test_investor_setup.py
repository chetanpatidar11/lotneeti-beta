import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor


@pytest.mark.django_db
def test_investor_setup_creates_optional_accounts_together():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("investor-setup", args=[workspace.pk]),
        {
            "name": "Example Investor",
            "pan": "TESTX0001A",
            "planning_priority": 1,
            "demat": {
                "depository": "CDSL",
                "client_id": "1234567890123456",
                "broker": "Example Broker",
            },
            "bank": {
                "bank_name": "Example Bank",
                "account_number": "1234567890",
                "initial_balance": "25000.00",
                "upi_handle": "example@upi",
            },
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    investor = Investor.objects.get(pk=response.data["investor_id"])
    assert DematAccount.objects.filter(investor=investor).count() == 1
    bank = BankAccount.objects.get(pk=response.data["bank_id"])
    assert bank.owner == investor
    assert str(bank.current_balance) == "25000.00"
    upi = UPIHandle.objects.get(pk=response.data["upi_id"])
    assert upi.bank == bank and upi.holder == investor and upi.verified


@pytest.mark.django_db
def test_investor_setup_rolls_back_when_optional_upi_is_invalid():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.post(
        reverse("investor-setup", args=[workspace.pk]),
        {
            "name": "Example Investor",
            "pan": "TESTX0001A",
            "planning_priority": 1,
            "bank": {
                "bank_name": "Example Bank",
                "account_number": "1234567890",
                "initial_balance": "0.00",
                "upi_handle": "not-a-upi",
            },
        },
        format="json",
    )
    assert response.status_code == 400
    assert not Investor.objects.filter(workspace=workspace).exists()
    assert not BankAccount.objects.filter(workspace=workspace).exists()


@pytest.mark.django_db
def test_viewer_cannot_use_investor_setup():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=viewer, role=WorkspaceMembership.Role.VIEWER
    )
    client = APIClient()
    client.force_authenticate(viewer)
    response = client.post(
        reverse("investor-setup", args=[workspace.pk]),
        {"name": "Example Investor", "pan": "TESTX0001A", "planning_priority": 1},
        format="json",
    )
    assert response.status_code == 403
    assert not Investor.objects.filter(workspace=workspace).exists()
