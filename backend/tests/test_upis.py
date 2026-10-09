import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from funding.models import BankAccount, UPIHandle
from investors.models import Investor


def setup_bank(workspace):
    holder = Investor(workspace=workspace, name="Synthetic")
    holder.set_pan("TESTX0001A")
    holder.save()
    bank = BankAccount(workspace=workspace, owner=holder, bank_name="Demo Bank")
    bank.set_account_number("DEMO-ACCOUNT-0001")
    bank.save()
    return holder, bank


@pytest.mark.django_db
def test_upi_create_edit_mask_and_limit_overrides():
    owner = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    holder, bank = setup_bank(workspace)
    client = APIClient()
    client.force_authenticate(owner)
    list_url = reverse("upi-list", args=[workspace.pk, bank.pk])

    response = client.post(
        list_url,
        {
            "holder": str(holder.pk),
            "handle": "DEMO@UPI.TEST",
            "verified": True,
            "count_limit_override": 4,
            "amount_limit_override": "300000.00",
        },
    )

    assert response.status_code == 201
    assert response.data["handle_masked"] == "••••@upi.test"
    assert "handle" not in response.data
    upi = UPIHandle.objects.get(pk=response.data["id"])
    assert "demo@upi.test" not in upi.handle_ciphertext
    assert upi.verified is True
    assert upi.count_limit_override == 4
    detail_url = reverse("upi-detail", args=[workspace.pk, bank.pk, upi.pk])
    updated = client.patch(detail_url, {"active": False, "verified": False})
    assert updated.status_code == 200
    assert updated.data["active"] is False
    assert updated.data["verified"] is False
    assert (
        client.post(list_url, {"holder": str(holder.pk), "handle": "demo@upi.test"}).status_code
        == 400
    )


@pytest.mark.django_db
def test_upi_holder_scope_and_viewer_write_denial():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    first = create_workspace(name="First", owner=owner)
    second = create_workspace(name="Second", owner=owner)
    holder, bank = setup_bank(first)
    other_holder, _ = setup_bank(second)
    WorkspaceMembership.objects.create(workspace=first, user=viewer, role="VIEWER")
    upi = UPIHandle(bank=bank, holder=holder)
    upi.set_handle("demo@upi.test")
    upi.save()
    list_url = reverse("upi-list", args=[first.pk, bank.pk])
    detail_url = reverse("upi-detail", args=[first.pk, bank.pk, upi.pk])
    client = APIClient()

    client.force_authenticate(owner)
    assert (
        client.post(
            list_url, {"holder": str(other_holder.pk), "handle": "other@upi.test"}
        ).status_code
        == 400
    )

    client.force_authenticate(outsider)
    assert client.get(detail_url).status_code == 403

    client.force_authenticate(viewer)
    assert client.get(detail_url).status_code == 200
    assert client.patch(detail_url, {"verified": True}).status_code == 403
