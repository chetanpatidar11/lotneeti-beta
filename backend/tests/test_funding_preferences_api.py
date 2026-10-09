import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User, WorkspaceMembership
from accounts.services import create_workspace
from funding.models import BankAccount, FundingPreference
from investors.models import Investor


def make_investor(workspace, name, pan):
    investor = Investor(workspace=workspace, name=name)
    investor.set_pan(pan)
    investor.save()
    return investor


def make_bank(workspace, owner, number):
    bank = BankAccount(workspace=workspace, owner=owner, bank_name="Demo Bank")
    bank.set_account_number(number)
    bank.save()
    return bank


@pytest.mark.django_db
def test_preference_api_creates_ranks_pauses_and_deletes():
    user = User.objects.create_user(email="owner@example.test")
    workspace = create_workspace(name="Family", owner=user)
    beneficiary = make_investor(workspace, "Mother", "TESTX0001A")
    funder = make_investor(workspace, "Wife", "TESTX0002B")
    own = make_bank(workspace, beneficiary, "DEMO-ACCOUNT-0001")
    first = make_bank(workspace, funder, "DEMO-ACCOUNT-0002")
    second = make_bank(workspace, funder, "DEMO-ACCOUNT-0003")
    url = reverse("funding-preference-list", args=[workspace.pk, beneficiary.pk])
    client = APIClient()
    client.force_authenticate(user)

    assert client.post(url, {"bank": own.pk, "priority": 1}).status_code == 400
    created_second = client.post(url, {"bank": second.pk, "priority": 2})
    created_first = client.post(url, {"bank": first.pk, "priority": 1})
    assert created_second.status_code == created_first.status_code == 201
    assert [row["bank"] for row in client.get(url).data] == [first.pk, second.pk]
    assert client.post(url, {"bank": first.pk, "priority": 3}).status_code == 400

    detail = reverse(
        "funding-preference-detail",
        args=[workspace.pk, beneficiary.pk, created_first.data["id"]],
    )
    updated = client.patch(detail, {"priority": 3, "enabled": False})
    assert updated.status_code == 200
    assert updated.data["enabled"] is False
    assert [row["bank"] for row in client.get(url).data] == [second.pk, first.pk]
    assert list(FundingPreference.objects.enabled_for(beneficiary)) == [
        FundingPreference.objects.get(pk=created_second.data["id"])
    ]
    assert client.delete(detail).status_code == 204
    assert len(client.get(url).data) == 1


@pytest.mark.django_db
def test_preference_api_is_workspace_scoped_and_viewer_cannot_write():
    owner = User.objects.create_user(email="owner@example.test")
    viewer = User.objects.create_user(email="viewer@example.test")
    outsider = User.objects.create_user(email="outsider@example.test")
    workspace = create_workspace(name="Family", owner=owner)
    other = create_workspace(name="Other", owner=owner)
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role="VIEWER")
    beneficiary = make_investor(workspace, "Mother", "TESTX0001A")
    funder = make_investor(workspace, "Wife", "TESTX0002B")
    bank = make_bank(workspace, funder, "DEMO-ACCOUNT-0001")
    other_owner = make_investor(other, "Other", "TESTX0003C")
    other_bank = make_bank(other, other_owner, "DEMO-ACCOUNT-0002")
    url = reverse("funding-preference-list", args=[workspace.pk, beneficiary.pk])
    client = APIClient()

    client.force_authenticate(outsider)
    assert client.get(url).status_code == 403
    client.force_authenticate(viewer)
    assert client.get(url).status_code == 200
    assert client.post(url, {"bank": bank.pk, "priority": 1}).status_code == 403
    client.force_authenticate(owner)
    assert client.post(url, {"bank": other_bank.pk, "priority": 1}).status_code == 400
