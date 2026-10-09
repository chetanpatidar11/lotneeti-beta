import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from funding.models import BankAccount, RecurringDebit
from investors.models import Investor


@pytest.mark.django_db
def test_scheduled_payment_create_edit_pause_and_delete():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    investor = Investor(workspace=workspace, name="Synthetic")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Demo Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("recurring-debit-list", args=[workspace.pk, bank.pk])

    created = client.post(
        list_url,
        {
            "name": "Home Loan EMI",
            "amount": "8500.00",
            "frequency": "MONTHLY",
            "start_date": "2026-10-05",
        },
    )
    assert created.status_code == 201
    assert created.data["next_due_date"] == "2026-10-05"
    detail_url = reverse("recurring-debit-detail", args=[workspace.pk, bank.pk, created.data["id"]])
    edited = client.patch(detail_url, {"amount": "9000.00", "active": False})
    assert edited.status_code == 200
    assert edited.data["amount"] == "9000.00"
    assert edited.data["active"] is False
    assert client.get(list_url).data[0]["id"] == created.data["id"]
    assert client.delete(detail_url).status_code == 204
    assert client.get(list_url).data == []
    schedule = RecurringDebit.objects.get(pk=created.data["id"])
    assert schedule.active is False
    assert schedule.archived_at is not None


@pytest.mark.django_db
def test_scheduled_payment_scope_and_viewer_write_denial():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    investor = Investor(workspace=workspace, name="Synthetic")
    investor.set_pan("TESTX0001A")
    investor.save()
    bank = BankAccount(workspace=workspace, owner=investor, bank_name="Demo Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    list_url = reverse("recurring-debit-list", args=[workspace.pk, bank.pk])
    client = APIClient()

    client.force_authenticate(outsider)
    assert client.get(list_url).status_code == 403
    client.force_authenticate(viewer)
    assert client.get(list_url).status_code == 200
    assert client.post(list_url, {"name": "Blocked"}).status_code == 403
